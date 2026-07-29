"""Бенчмарк сравнение:超额收益, tracking error, information ratio.

Бенчмарк — это эталонный портфель, с которым сравнивают доходность
управляемого портфеля. На MOEX доступны:
- IMOEX — индекс Мосбиржи (50 крупнейших акций)
- RGBI — индекс ОФЗ (государственные облигации)

Ключевые метрики:
- Excess return = Portfolio return - Benchmark return (альфа)
- Tracking error = std(Portfolio - Benchmark) — насколько стабильно отклоняемся
- Information ratio = Excess return / Tracking error — качество "активного" управления
- R² = корреляция² — насколько портфель следует бенчмарку
"""

import logging
from datetime import date

import numpy as np
import pandas as pd
import requests

from .config import MOEX_ISS_BASE

logger = logging.getLogger(__name__)

# Кэш индексов
_INDEX_CACHE: dict[str, pd.Series] = {}


def get_index_history(
    index_ticker: str = "IMOEX",
    start_date: date | None = None,
    end_date: date | None = None,
) -> pd.Series:
    """Загрузка истории индекса MOEX.

    Args:
        index_ticker: Тикер индекса ('IMOEX', 'RGBI', 'RTSI').
        start_date: Дата начала.
        end_date: Дата окончания.

    Returns:
        Series с дневными доходностями индекса.
    """
    cache_key = f"{index_ticker}_{start_date}_{end_date}"
    if cache_key in _INDEX_CACHE:
        return _INDEX_CACHE[cache_key]

    if end_date is None:
        end_date = date.today()

    if start_date is None:
        from datetime import timedelta
        start_date = end_date - timedelta(days=800)

    url = f"{MOEX_ISS_BASE}/history/engines/stock/markets/index/boards/SNDX/securities/{index_ticker}.json"
    params = {
        "iss.meta": "off",
        "iss.only": "history",
        "from": start_date.strftime("%Y-%m-%d"),
        "till": end_date.strftime("%Y-%m-%d"),
    }

    try:
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code != 200:
            logger.warning("Failed to fetch index %s: %d", index_ticker, resp.status_code)
            return pd.Series(dtype=float)

        data = resp.json()
        rows = data.get("history", {}).get("data", [])
        cols = data.get("history", {}).get("columns", [])

        if not rows:
            logger.warning("No data for index %s", index_ticker)
            return pd.Series(dtype=float)

        df = pd.DataFrame(rows, columns=cols)
        if "CLOSE" not in df.columns:
            return pd.Series(dtype=float)

        df["date"] = pd.to_datetime(df["LEGALCLOSEDATE"] if "LEGALCLOSEDATE" in df.columns else df["TRADEDATE"])
        df = df.set_index("date").sort_index()
        df["close"] = pd.to_numeric(df["CLOSE"], errors="coerce")
        df = df.dropna(subset=["close"])

        returns = df["close"].pct_change().dropna()
        returns.name = index_ticker

        _INDEX_CACHE[cache_key] = returns
        logger.info("Index %s: %d days loaded", index_ticker, len(returns))
        return returns

    except (requests.RequestException, ValueError, KeyError) as e:
        logger.warning("Index fetch error for %s: %s", index_ticker, e)
        return pd.Series(dtype=float)


def compute_benchmark_metrics(
    portfolio_returns: pd.Series,
    benchmark_returns: pd.Series,
    risk_free_rate: float = 0.0,
    annualization: int = 252,
) -> dict:
    """Метрики сравнения портфеля с бенчмарком.

    Args:
        portfolio_returns: Дневные доходности портфеля.
        benchmark_returns: Дневные доходности бенчмарка.
        risk_free_rate: Безрисковая ставка (годовая).
        annualization: Торговых дней в году.

    Returns:
        Словарь с метриками.
    """
    # Приводим к общему индексу
    common_idx = portfolio_returns.index.intersection(benchmark_returns.index)
    p = portfolio_returns.loc[common_idx].values
    b = benchmark_returns.loc[common_idx].values

    if len(common_idx) < 10:
        return {"error": "Insufficient overlapping data"}

    # Доходности
    port_annual = float(np.mean(p) * annualization)
    bench_annual = float(np.mean(b) * annualization)
    excess_return = port_annual - bench_annual

    # Tracking error
    active_returns = p - b
    tracking_error = float(np.std(active_returns) * np.sqrt(annualization))

    # Information ratio
    information_ratio = excess_return / tracking_error if tracking_error > 0 else 0.0

    # R-squared
    correlation = np.corrcoef(p, b)[0, 1]
    r_squared = float(correlation ** 2)

    # Beta и Alpha
    cov_pb = np.cov(p, b)[0, 1]
    var_b = np.var(b)
    beta = cov_pb / var_b if var_b > 0 else 0.0
    alpha = float((port_annual - risk_free_rate) - beta * (bench_annual - risk_free_rate))

    # Drawdown портфеля и бенчмарка
    cum_port = np.cumprod(1 + p)
    cum_bench = np.cumprod(1 + b)
    port_maxdd = float(np.min((cum_port - np.maximum.accumulate(cum_port)) / np.maximum.accumulate(cum_port)))
    bench_maxdd = float(np.min((cum_bench - np.maximum.accumulate(cum_bench)) / np.maximum.accumulate(cum_bench)))

    # Information Ratio (rolling 60 days)
    rolling_ir = pd.Series(active_returns).rolling(60).mean() / pd.Series(active_returns).rolling(60).std()
    rolling_ir = rolling_ir.replace([np.inf, -np.inf], np.nan).dropna()

    return {
        "portfolio_return": port_annual,
        "benchmark_return": bench_annual,
        "excess_return": excess_return,
        "tracking_error": tracking_error,
        "information_ratio": information_ratio,
        "r_squared": r_squared,
        "correlation": float(correlation),
        "beta": float(beta),
        "alpha": alpha,
        "portfolio_max_drawdown": port_maxdd,
        "benchmark_max_drawdown": bench_maxdd,
        "n_days": len(common_idx),
        "rolling_ir": rolling_ir,
        "active_returns": pd.Series(active_returns, index=common_idx),
    }


def rolling_tracking_error(
    portfolio_returns: pd.Series,
    benchmark_returns: pd.Series,
    window: int = 60,
) -> pd.Series:
    """Скользящий tracking error.

    Args:
        portfolio_returns: Доходности портфеля.
        benchmark_returns: Доходности бенчмарка.
        window: Размер окна.

    Returns:
        Series со скользящим TE.
    """
    common_idx = portfolio_returns.index.intersection(benchmark_returns.index)
    active = portfolio_returns.loc[common_idx] - benchmark_returns.loc[common_idx]
    return active.rolling(window).std() * np.sqrt(252)


def summary_table(
    portfolio_returns: pd.Series,
    benchmark_returns: pd.Series,
    risk_free_rate: float = 0.0,
) -> pd.DataFrame:
    """Сводная таблица сравнения.

    Args:
        portfolio_returns: Доходности портфеля.
        benchmark_returns: Доходности бенчмарка.
        risk_free_rate: Безрисковая ставка.

    Returns:
        DataFrame с одной строкой: все метрики.
    """
    metrics = compute_benchmark_metrics(
        portfolio_returns, benchmark_returns, risk_free_rate
    )

    if "error" in metrics:
        return pd.DataFrame([metrics])

    summary = {
        "Portfolio Return": f"{metrics['portfolio_return']:.2%}",
        "Benchmark Return": f"{metrics['benchmark_return']:.2%}",
        "Excess Return (Alpha)": f"{metrics['excess_return']:.2%}",
        "Tracking Error": f"{metrics['tracking_error']:.2%}",
        "Information Ratio": f"{metrics['information_ratio']:.3f}",
        "R²": f"{metrics['r_squared']:.4f}",
        "Correlation": f"{metrics['correlation']:.4f}",
        "Beta": f"{metrics['beta']:.3f}",
        "Jensen's Alpha": f"{metrics['alpha']:.2%}",
        "Portfolio Max DD": f"{metrics['portfolio_max_drawdown']:.2%}",
        "Benchmark Max DD": f"{metrics['benchmark_max_drawdown']:.2%}",
        "Observations": str(metrics["n_days"]),
    }

    return pd.DataFrame(summary, index=["Value"]).T
