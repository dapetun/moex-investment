"""Дивидендные стратегии инвестирования.

Реализация классических стратегий:
- Dogs of the Dow: отбор 10 акций с наибольшей дивидендной доходностью
- Dividend Aristocrats: отбор акций с растущими дивидендами N лет подряд
- High Dividend Yield: портфель из акций с доходностью выше медианной
"""

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def compute_dividend_yield(
    dividends_per_share: pd.Series,
    prices: pd.Series,
) -> pd.Series:
    """Расчёт дивидендной доходности для каждого тикера.

    Dividend Yield = Сумма дивидендов за год / Текущая цена

    Args:
        dividends_per_share: Сумма дивидендов на акцию за период.
        prices: Текущие цены акций.

    Returns:
        Series с дивидендной доходностью.
    """
    common = dividends_per_share.index.intersection(prices.index)
    dy = dividends_per_share.loc[common] / prices.loc[common]
    return dy.replace([np.inf, -np.inf], 0.0).fillna(0.0)


def dogs_of_the_dow(
    returns: pd.DataFrame,
    dividend_yields: pd.Series,
    n_stocks: int = 10,
) -> dict:
    """Стратегия Dogs of the Dow.

    Классическая стратегия: ежегодно покупаем N акций с самой высокой
    дивидендной доходностью, поровну. Переключаемся раз в год.

    Адаптация для MOEX: отбираем top-N по дивидендной доходности.

    Args:
        returns: DataFrame с дневными доходностями.
        dividend_yields: Series с дивидендной доходностью по тикерам.
        n_stocks: Количество акций в портфеле.

    Returns:
        Словарь с:
        - selected_tickers: отобранные тикеры
        - weights: веса (1/N)
        - portfolio_returns: доходность стратегии
        - total_return: суммарная доходность
        - annual_return: годовая доходность
        - annual_volatility: годовая волатильность
        - sharpe: Sharpe Ratio (risk-free=0)
    """
    available = dividend_yields[dividend_yields.index.isin(returns.columns)]
    available = available[available > 0]

    if len(available) == 0:
        logger.warning("No tickers with positive dividend yield found.")
        return _empty_strategy_result()

    selected = available.nlargest(min(n_stocks, len(available))).index.tolist()
    n = len(selected)
    weights = np.array([1.0 / n] * n)

    strat_returns = returns[selected].values @ weights
    strat_series = pd.Series(strat_returns, index=returns.index)

    total_return = (1 + strat_series).prod() - 1
    n_years = len(strat_returns) / 252
    annual_return = (1 + total_return) ** (1 / max(n_years, 0.01)) - 1
    annual_vol = strat_series.std() * np.sqrt(252)
    sharpe = annual_return / annual_vol if annual_vol > 0 else 0.0

    logger.info(
        "Dogs of the Dow: %d stocks, annual_return=%.2f%%, sharpe=%.3f",
        n, annual_return * 100, sharpe,
    )

    return {
        "selected_tickers": selected,
        "weights": weights,
        "portfolio_returns": strat_series,
        "total_return": total_return,
        "annual_return": annual_return,
        "annual_volatility": annual_vol,
        "sharpe": sharpe,
    }


def dividend_aristocrats(
    returns: pd.DataFrame,
    dividend_history: dict[str, list[float]],
    min_years: int = 5,
) -> dict:
    """Стратегия Dividend Aristocrats (Dividend Growth).

    Отбираем акции, которые увеличивали дивиденды не менее min_years лет подряд.
    Портфель — равные веса по отобранным акциям.

    Args:
        returns: DataFrame с дневными доходностями.
        dividend_history: Словарь {ticker: [dividends_year_1, div_year_2, ...]}.
            Значения должны идти в хронологическом порядке.
        min_years: Минимальное число лет подряд с ростом дивидендов.

    Returns:
        Словарь с теми же ключами, что и dogs_of_the_dow.
    """
    aristocrats = []
    for ticker, divs in dividend_history.items():
        if ticker not in returns.columns:
            continue
        if len(divs) < min_years + 1:
            continue
        consecutive_growth = 0
        for i in range(1, len(divs)):
            if divs[i] > divs[i - 1] and divs[i - 1] > 0:
                consecutive_growth += 1
            else:
                consecutive_growth = 0
        if consecutive_growth >= min_years:
            aristocrats.append(ticker)

    if not aristocrats:
        logger.warning(
            "No dividend aristocrats found (min_years=%d).", min_years
        )
        return _empty_strategy_result()

    n = len(aristocrats)
    weights = np.array([1.0 / n] * n)
    strat_returns = returns[aristocrats].values @ weights
    strat_series = pd.Series(strat_returns, index=returns.index)

    total_return = (1 + strat_series).prod() - 1
    n_years = len(strat_returns) / 252
    annual_return = (1 + total_return) ** (1 / max(n_years, 0.01)) - 1
    annual_vol = strat_series.std() * np.sqrt(252)
    sharpe = annual_return / annual_vol if annual_vol > 0 else 0.0

    logger.info(
        "Dividend Aristocrats: %d stocks, annual_return=%.2f%%, sharpe=%.3f",
        n, annual_return * 100, sharpe,
    )

    return {
        "selected_tickers": aristocrats,
        "weights": weights,
        "portfolio_returns": strat_series,
        "total_return": total_return,
        "annual_return": annual_return,
        "annual_volatility": annual_vol,
        "sharpe": sharpe,
    }


def high_dividend_yield(
    returns: pd.DataFrame,
    dividend_yields: pd.Series,
    percentile: float = 75,
) -> dict:
    """Стратегия High Dividend Yield.

    Отбираем акции с дивидендной доходностью выше percentile-го порога.

    Args:
        returns: DataFrame с дневными доходностями.
        dividend_yields: Series с дивидендной доходностью.
        percentile: Процентиль для отбора (75 = top 25%).

    Returns:
        Словарь с теми же ключами.
    """
    available = dividend_yields[dividend_yields.index.isin(returns.columns)]
    available = available[available > 0]

    if len(available) == 0:
        return _empty_strategy_result()

    threshold = np.percentile(available.values, percentile)
    selected = available[available >= threshold].index.tolist()

    if not selected:
        return _empty_strategy_result()

    n = len(selected)
    weights = np.array([1.0 / n] * n)
    strat_returns = returns[selected].values @ weights
    strat_series = pd.Series(strat_returns, index=returns.index)

    total_return = (1 + strat_series).prod() - 1
    n_years = len(strat_returns) / 252
    annual_return = (1 + total_return) ** (1 / max(n_years, 0.01)) - 1
    annual_vol = strat_series.std() * np.sqrt(252)
    sharpe = annual_return / annual_vol if annual_vol > 0 else 0.0

    return {
        "selected_tickers": selected,
        "weights": weights,
        "portfolio_returns": strat_series,
        "total_return": total_return,
        "annual_return": annual_return,
        "annual_volatility": annual_vol,
        "sharpe": sharpe,
    }


def compare_dividend_strategies(
    returns: pd.DataFrame,
    dividend_yields: pd.Series,
    dividend_history: dict[str, list[float]] | None = None,
) -> pd.DataFrame:
    """Сравнение всех дивидендных стратегий.

    Args:
        returns: DataFrame с дневными доходностями.
        dividend_yields: Series с дивидендной доходностью.
        dividend_history: История дивидендов для Aristocrats (опционально).

    Returns:
        DataFrame со сравнением стратегий.
    """
    results = []

    dogs = dogs_of_the_dow(returns, dividend_yields)
    results.append({
        "Strategy": "Dogs of the Dow (Top-10 Yield)",
        "Stocks": len(dogs["selected_tickers"]),
        "Annual Return": dogs["annual_return"],
        "Annual Volatility": dogs["annual_volatility"],
        "Sharpe": dogs["sharpe"],
    })

    hd = high_dividend_yield(returns, dividend_yields, percentile=75)
    results.append({
        "Strategy": "High Dividend (Top 25%)",
        "Stocks": len(hd["selected_tickers"]),
        "Annual Return": hd["annual_return"],
        "Annual Volatility": hd["annual_volatility"],
        "Sharpe": hd["sharpe"],
    })

    if dividend_history:
        aristocrats = dividend_aristocrats(returns, dividend_history)
        results.append({
            "Strategy": f"Dividend Aristocrats (>= {5}yr growth)",
            "Stocks": len(aristocrats["selected_tickers"]),
            "Annual Return": aristocrats["annual_return"],
            "Annual Volatility": aristocrats["annual_volatility"],
            "Sharpe": aristocrats["sharpe"],
        })

    equal_weight_returns = returns.mean(axis=1)
    ew_annual = equal_weight_returns.mean() * 252
    ew_vol = equal_weight_returns.std() * np.sqrt(252)
    results.append({
        "Strategy": "Equal Weight (Benchmark)",
        "Stocks": len(returns.columns),
        "Annual Return": ew_annual,
        "Annual Volatility": ew_vol,
        "Sharpe": ew_annual / ew_vol if ew_vol > 0 else 0,
    })

    return pd.DataFrame(results)


def _empty_strategy_result() -> dict:
    """Пустой результат, если стратегия не нашла акций."""
    return {
        "selected_tickers": [],
        "weights": np.array([]),
        "portfolio_returns": pd.Series(dtype=float),
        "total_return": 0.0,
        "annual_return": 0.0,
        "annual_volatility": 0.0,
        "sharpe": 0.0,
    }
