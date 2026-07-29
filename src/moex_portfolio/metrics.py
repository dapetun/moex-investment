"""Финансовые метрики портфеля."""

import numpy as np
import pandas as pd

from .config import RISK_FREE_RATE


def portfolio_return(weights: np.ndarray, mean_returns: pd.Series) -> float:
    """Ожидаемая годовая доходность портфеля.

    Args:
        weights: Веса активов.
        mean_returns: Средние дневные доходности.

    Returns:
        Годовая доходность.
    """
    daily_return = np.dot(weights, mean_returns)
    return daily_return * 252


def portfolio_volatility(weights: np.ndarray, cov_matrix: pd.DataFrame) -> float:
    """Годовая волатильность портфеля.

    Args:
        weights: Веса активов.
        cov_matrix: Ковариационная матрица.

    Returns:
        Годовая волатильность.
    """
    daily_vol = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
    return daily_vol * np.sqrt(252)


def sharpe_ratio(
    weights: np.ndarray,
    mean_returns: pd.Series,
    cov_matrix: pd.DataFrame,
    risk_free_rate: float = RISK_FREE_RATE,
) -> float:
    """Коэффициент Шарпа.

    Args:
        weights: Веса активов.
        mean_returns: Средние дневные доходности.
        cov_matrix: Ковариационная матрица.
        risk_free_rate: Безрисковая ставка (годовая).

    Returns:
        Коэффициент Шарпа.
    """
    ret = portfolio_return(weights, mean_returns)
    vol = portfolio_volatility(weights, cov_matrix)
    if vol == 0:
        return 0.0
    return (ret - risk_free_rate) / vol


def sortino_ratio(
    weights: np.ndarray,
    mean_returns: pd.Series,
    returns: pd.DataFrame,
    risk_free_rate: float = RISK_FREE_RATE,
) -> float:
    """Коэффициент Сортино (учитывает только downside risk).

    Args:
        weights: Веса активов.
        mean_returns: Средние дневные доходности.
        returns: DataFrame с доходностями.
        risk_free_rate: Безрисковая ставка (годовая).

    Returns:
        Коэффициент Сортино.
    """
    ret = portfolio_return(weights, mean_returns)
    port_returns = returns.values @ weights
    downside = port_returns[port_returns < 0]
    if len(downside) == 0:
        return float("inf") if ret > risk_free_rate else 0.0
    downside_std = np.std(downside) * np.sqrt(252)
    if downside_std == 0:
        return 0.0
    return (ret - risk_free_rate) / downside_std


def max_drawdown(equity_curve: pd.Series) -> float:
    """Максимальная просадка.

    Args:
        equity_curve: Кривая стоимости портфеля.

    Returns:
        Максимальная просадка (отрицательное число).
    """
    cumulative = (1 + equity_curve).cumprod()
    running_max = cumulative.cummax()
    drawdown = (cumulative - running_max) / running_max
    return drawdown.min()


def information_ratio(
    weights: np.ndarray,
    mean_returns: pd.Series,
    cov_matrix: pd.DataFrame,
    benchmark_return: float = 0.0,
) -> float:
    """Коэффициент информативности (Information Ratio).

    Args:
        weights: Веса активов.
        mean_returns: Средние дневные доходности.
        cov_matrix: Ковариационная матрица.
        benchmark_return: Годовая доходность бенчмарка.

    Returns:
        Information Ratio.
    """
    ret = portfolio_return(weights, mean_returns)
    vol = portfolio_volatility(weights, cov_matrix)
    tracking_error = vol  # Упрощённо: используем волатильность
    if tracking_error == 0:
        return 0.0
    return (ret - benchmark_return) / tracking_error


def calmar_ratio(
    equity_curve_data: pd.Series,
    periods_per_year: int = 252,
) -> float:
    """Коэффициент Калмара.

    Args:
        equity_curve_data: Кривая капитала.
        periods_per_year: Периодов в году.

    Returns:
        Calmar Ratio.
    """
    total_return = equity_curve_data.iloc[-1] / equity_curve_data.iloc[0] - 1
    n_years = len(equity_curve_data) / periods_per_year
    if n_years <= 0:
        return 0.0
    annual_return = (1 + total_return) ** (1 / n_years) - 1

    running_max = equity_curve_data.cummax()
    drawdown = (equity_curve_data - running_max) / running_max
    max_dd = abs(drawdown.min())

    if max_dd == 0:
        return 0.0
    return annual_return / max_dd


def treynor_ratio(
    weights: np.ndarray,
    returns: pd.DataFrame,
    market_returns: pd.Series,
    risk_free_rate: float = RISK_FREE_RATE,
) -> float:
    """Коэффициент Трейнора.

    Трейнор = (Rp - Rf) / beta_p
    Показывает доходность на единицу систематического риска.

    Args:
        weights: Веса активов.
        returns: DataFrame с доходностями активов.
        market_returns: Series с доходностями рынка (бенчмарка).
        risk_free_rate: Безрисковая ставка (годовая).

    Returns:
        Коэффициент Трейнора.
    """
    common_idx = returns.index.intersection(market_returns.index)
    r = returns.loc[common_idx]
    m = market_returns.loc[common_idx]

    port_daily = r.values @ weights
    port_series = pd.Series(port_daily, index=common_idx)

    cov_pm = port_series.cov(m)
    var_m = m.var()

    if var_m == 0:
        return 0.0
    beta_p = cov_pm / var_m

    port_annual = port_daily.mean() * 252
    if beta_p == 0:
        return 0.0
    return (port_annual - risk_free_rate) / beta_p


def modigliani_ratio(
    weights: np.ndarray,
    mean_returns: pd.Series,
    cov_matrix: pd.DataFrame,
    market_returns: pd.Series,
    risk_free_rate: float = RISK_FREE_RATE,
) -> float:
    """Коэффициент Модильяни (M² / Modigliani-Modigliani Measure).

    M² = Rf + Sharpe_p * sigma_m
    Скорректированная доходность портфеля, приведённая к волатильности рынка.

    Args:
        weights: Веса активов.
        mean_returns: Средние дневные доходности.
        cov_matrix: Ковариационная матрица.
        market_returns: Series с доходностями рынка.
        risk_free_rate: Безрисковая ставка (годовая).

    Returns:
        M² (годовая доходность, скорректированная на риск).
    """
    market_vol = market_returns.std() * np.sqrt(252)
    sr = sharpe_ratio(weights, mean_returns, cov_matrix, risk_free_rate)

    return sr * market_vol + risk_free_rate


def portfolio_metrics(
    weights: np.ndarray,
    mean_returns: pd.Series,
    cov_matrix: pd.DataFrame,
    returns: pd.DataFrame | None = None,
    risk_free_rate: float = RISK_FREE_RATE,
    market_returns: pd.Series | None = None,
) -> dict:
    """Все метрики портфеля одним вызовом.

    Args:
        weights: Веса активов.
        mean_returns: Средние дневные доходности.
        cov_matrix: Ковариационная матрица.
        returns: DataFrame с доходностями (для Sortino, max drawdown, Calmar).
        risk_free_rate: Безрисковая ставка.
        market_returns: Доходности рынка (для Treynor, M²).

    Returns:
        Словарь с метриками.
    """
    result = {
        "return": portfolio_return(weights, mean_returns),
        "volatility": portfolio_volatility(weights, cov_matrix),
        "sharpe": sharpe_ratio(weights, mean_returns, cov_matrix, risk_free_rate),
        "information_ratio": information_ratio(weights, mean_returns, cov_matrix),
    }

    if returns is not None:
        result["sortino"] = sortino_ratio(
            weights, mean_returns, returns, risk_free_rate
        )
        port_daily = returns.values @ weights
        result["max_drawdown"] = max_drawdown(pd.Series(port_daily))

        eq = (1 + pd.Series(port_daily)).cumprod()
        result["calmar"] = calmar_ratio(eq)
    else:
        result["sortino"] = None
        result["max_drawdown"] = None
        result["calmar"] = None

    if market_returns is not None:
        result["treynor"] = treynor_ratio(weights, returns if returns is not None else pd.DataFrame(), market_returns, risk_free_rate)
        result["modigliani_m2"] = modigliani_ratio(weights, mean_returns, cov_matrix, market_returns, risk_free_rate)
    else:
        result["treynor"] = None
        result["modigliani_m2"] = None

    return result
