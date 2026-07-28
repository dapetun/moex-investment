"""Расширенная аналитика: Monte Carlo, rolling correlation, equity curve."""

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def equity_curve(
    returns: pd.DataFrame,
    weights: np.ndarray,
) -> pd.Series:
    """Кривая роста капитала портфеля.

    Args:
        returns: DataFrame с доходностями активов.
        weights: Веса активов.

    Returns:
        Series с накопленной доходностью (1.0 = старт).
    """
    port_returns = returns.values @ weights
    cumulative = np.cumprod(1 + port_returns)
    return pd.Series(cumulative, index=returns.index, name="equity_curve")


def monte_carlo_simulation(
    mean_returns: pd.Series,
    cov_matrix: pd.DataFrame,
    weights: np.ndarray,
    n_simulations: int = 10000,
    n_days: int = 252,
    seed: int | None = None,
) -> pd.DataFrame:
    """Monte Carlo симуляция будущих доходностей портфеля.

    Генерирует n_simulations случайных траекторий на n_days дней,
    используя многомерное нормальное распределение.

    Args:
        mean_returns: Средние дневные доходности.
        cov_matrix: Ковариационная матрица.
        weights: Веса портфеля.
        n_simulations: Количество симуляций.
        n_days: Горизонт симуляции (дней).
        seed: Seed для воспроизводимости.

    Returns:
        DataFrame с результатами: final_return, annual_return, annual_vol, max_drawdown.
    """
    rng = np.random.default_rng(seed)

    # Генерируем дневные доходности
    daily_returns = rng.multivariate_normal(
        mean_returns.values, cov_matrix.values, size=(n_simulations, n_days)
    )

    # Считаем портфельные доходности для каждой симуляции
    port_daily = daily_returns @ weights  # (n_simulations, n_days)

    # Кумулятивная доходность
    cumulative = np.cumprod(1 + port_daily, axis=1)

    # Метрики по каждой симуляции
    final_values = cumulative[:, -1]
    annual_returns = final_values - 1.0
    annual_vols = np.std(port_daily, axis=1) * np.sqrt(252)

    # Max drawdown для каждой симуляции
    running_max = np.maximum.accumulate(cumulative, axis=1)
    drawdowns = (cumulative - running_max) / running_max
    max_dds = np.min(drawdowns, axis=1)

    results = pd.DataFrame({
        "annual_return": annual_returns,
        "annual_volatility": annual_vols,
        "max_drawdown": max_dds,
        "sharpe": annual_returns / np.where(annual_vols > 0, annual_vols, 1.0),
    })

    logger.info(
        "Monte Carlo: %d simulations, %d days — "
        "mean return=%.2f%%, mean vol=%.2f%%, mean max_dd=%.2f%%",
        n_simulations,
        n_days,
        results["annual_return"].mean() * 100,
        results["annual_volatility"].mean() * 100,
        results["max_drawdown"].mean() * 100,
    )

    return results


def rolling_correlation(
    returns: pd.DataFrame,
    window: int = 60,
) -> dict[str, pd.Series]:
    """Скользящие корреляции между парами активов.

    Args:
        returns: DataFrame с доходностями.
        window: Размер окна (дней).

    Returns:
        Словарь {ticker_pair: Series корреляций}.
    """
    tickers = returns.columns.tolist()
    rolling_corr = {}

    for i in range(len(tickers)):
        for j in range(i + 1, len(tickers)):
            pair_name = f"{tickers[i]}/{tickers[j]}"
            corr_series = returns[tickers[i]].rolling(window).corr(returns[tickers[j]])
            rolling_corr[pair_name] = corr_series.dropna()

    logger.info(
        "Rolling correlation: %d pairs, window=%d days",
        len(rolling_corr), window,
    )
    return rolling_corr


def rolling_beta(
    returns: pd.DataFrame,
    market_returns: pd.Series,
    window: int = 60,
) -> pd.DataFrame:
    """Скользящая бета для каждого актива.

    Args:
        returns: DataFrame с доходностями активов.
        market_returns: Series с доходностями рынка.
        window: Размер окна (дней).

    Returns:
        DataFrame со скользящими бетами.
    """
    common_idx = returns.index.intersection(market_returns.index)
    r = returns.loc[common_idx]
    m = market_returns.loc[common_idx]

    rolling_betas = pd.DataFrame(index=r.index, columns=r.columns)

    for col in r.columns:
        cov_rm = r[col].rolling(window).cov(m)
        var_m = m.rolling(window).var()
        rolling_betas[col] = cov_rm / var_m.replace(0, np.nan)

    return rolling_betas.astype(float)


def var_historical(
    returns: pd.DataFrame,
    weights: np.ndarray,
    confidence: float = 0.95,
) -> float:
    """Value at Risk (исторический метод).

    Args:
        returns: DataFrame с доходностями.
        weights: Веса портфеля.
        confidence: Уровень доверия (0.95 = 95%).

    Returns:
        VaR (отрицательное число = потери).
    """
    port_returns = returns.values @ weights
    var = np.percentile(port_returns, (1 - confidence) * 100)
    logger.info("Historical VaR (%.0f%%): %.4f", confidence * 100, var)
    return var


def cvar_historical(
    returns: pd.DataFrame,
    weights: np.ndarray,
    confidence: float = 0.95,
) -> float:
    """Conditional VaR (Expected Shortfall).

    Средние потери при условии, что losses превысили VaR.

    Args:
        returns: DataFrame с доходностями.
        weights: Веса портфеля.
        confidence: Уровень доверия.

    Returns:
        CVaR (отрицательное число = средние потери за VaR).
    """
    port_returns = returns.values @ weights
    var = np.percentile(port_returns, (1 - confidence) * 100)
    cvar = port_returns[port_returns <= var].mean()
    logger.info("Historical CVaR (%.0f%%): %.4f", confidence * 100, cvar)
    return cvar
