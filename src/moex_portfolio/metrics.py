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


def portfolio_metrics(
    weights: np.ndarray,
    mean_returns: pd.Series,
    cov_matrix: pd.DataFrame,
    returns: pd.DataFrame | None = None,
    risk_free_rate: float = RISK_FREE_RATE,
) -> dict:
    """Все метрики портфеля одним вызовом.

    Args:
        weights: Веса активов.
        mean_returns: Средние дневные доходности.
        cov_matrix: Ковариационная матрица.
        returns: DataFrame с доходностями (для Sortino и max drawdown).
        risk_free_rate: Безрисковая ставка.

    Returns:
        Словарь с метриками: return, volatility, sharpe, sortino, max_drawdown.
    """
    result = {
        "return": portfolio_return(weights, mean_returns),
        "volatility": portfolio_volatility(weights, cov_matrix),
        "sharpe": sharpe_ratio(weights, mean_returns, cov_matrix, risk_free_rate),
    }

    if returns is not None:
        result["sortino"] = sortino_ratio(
            weights, mean_returns, returns, risk_free_rate
        )
        port_daily = returns.values @ weights
        result["max_drawdown"] = max_drawdown(pd.Series(port_daily))
    else:
        result["sortino"] = None
        result["max_drawdown"] = None

    return result
