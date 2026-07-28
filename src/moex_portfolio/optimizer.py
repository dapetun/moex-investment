"""Markowitz Mean-Variance оптимизация портфеля."""

import logging

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from .config import MAX_WEIGHT, MIN_WEIGHT, RISK_FREE_RATE
from .metrics import portfolio_return, portfolio_volatility, sharpe_ratio

logger = logging.getLogger(__name__)


def _normalize_weights(
    n_assets: int,
    min_weight: float = MIN_WEIGHT,
    max_weight: float = MAX_WEIGHT,
) -> tuple[float, float]:
    """Корректировка весов: если max_weight * n_assets < 1, увеличиваем max."""
    if max_weight * n_assets < 1.0:
        max_weight = 1.0 / n_assets
    if min_weight * n_assets > 1.0:
        min_weight = 1.0 / n_assets
    return min_weight, max_weight


def _make_constraints(n_assets: int) -> list[dict]:
    """Создание ограничений: сумма весов = 1."""
    return [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]


def _make_bounds(
    n_assets: int,
    min_weight: float = MIN_WEIGHT,
    max_weight: float = MAX_WEIGHT,
) -> list[tuple[float, float]]:
    """Создание границ для весов каждого актива."""
    min_weight, max_weight = _normalize_weights(n_assets, min_weight, max_weight)
    return [(min_weight, max_weight) for _ in range(n_assets)]


def max_sharpe_portfolio(
    mean_returns: pd.Series,
    cov_matrix: pd.DataFrame,
    risk_free_rate: float = RISK_FREE_RATE,
    min_weight: float = MIN_WEIGHT,
    max_weight: float = MAX_WEIGHT,
) -> dict:
    """Оптимизация портфеля: максимальный Sharpe ratio.

    Args:
        mean_returns: Средние дневные доходности.
        cov_matrix: Ковариационная матрица.
        risk_free_rate: Безрисковая ставка.
        min_weight: Минимальный вес актива.
        max_weight: Максимальный вес актива.

    Returns:
        Словарь с: weights, return, volatility, sharpe.
    """
    n = len(mean_returns)
    init_weights = np.array([1.0 / n] * n)

    bounds = _make_bounds(n, min_weight, max_weight)
    constraints = _make_constraints(n)

    def neg_sharpe(w):
        return -sharpe_ratio(w, mean_returns, cov_matrix, risk_free_rate)

    result = minimize(
        neg_sharpe,
        init_weights,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
    )

    if not result.success:
        logger.warning("Optimization failed: %s", result.message)

    weights = result.x
    return {
        "weights": weights,
        "return": portfolio_return(weights, mean_returns),
        "volatility": portfolio_volatility(weights, cov_matrix),
        "sharpe": sharpe_ratio(weights, mean_returns, cov_matrix, risk_free_rate),
    }


def min_variance_portfolio(
    mean_returns: pd.Series,
    cov_matrix: pd.DataFrame,
    min_weight: float = MIN_WEIGHT,
    max_weight: float = MAX_WEIGHT,
) -> dict:
    """Портфель с минимальной волатильностью.

    Args:
        mean_returns: Средние дневные доходности.
        cov_matrix: Ковариационная матрица.
        min_weight: Минимальный вес актива.
        max_weight: Максимальный вес актива.

    Returns:
        Словарь с: weights, return, volatility, sharpe.
    """
    n = len(mean_returns)
    init_weights = np.array([1.0 / n] * n)

    bounds = _make_bounds(n, min_weight, max_weight)
    constraints = _make_constraints(n)

    def volatility(w):
        return portfolio_volatility(w, cov_matrix)

    result = minimize(
        volatility,
        init_weights,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
    )

    if not result.success:
        logger.warning("Optimization failed: %s", result.message)

    weights = result.x
    return {
        "weights": weights,
        "return": portfolio_return(weights, mean_returns),
        "volatility": portfolio_volatility(weights, cov_matrix),
        "sharpe": sharpe_ratio(weights, mean_returns, cov_matrix),
    }


def max_sharpe_with_sectors(
    mean_returns: pd.Series,
    cov_matrix: pd.DataFrame,
    sector_map: dict[str, str],
    max_sector_weight: float = 0.40,
    risk_free_rate: float = RISK_FREE_RATE,
    min_weight: float = MIN_WEIGHT,
    max_weight: float = MAX_WEIGHT,
) -> dict:
    """Оптимизация портфеля с секторальными ограничениями.

    Args:
        mean_returns: Средние дневные доходности.
        cov_matrix: Ковариационная матрица.
        sector_map: Маппинг тикер -> сектор (например {"SBER": "Finance", ...}).
        max_sector_weight: Максимальная доля одного сектора (0.4 = 40%).
        risk_free_rate: Безрисковая ставка.
        min_weight: Минимальный вес актива.
        max_weight: Максимальный вес актива.

    Returns:
        Словарь с: weights, return, volatility, sharpe, sector_weights.
    """
    tickers = list(mean_returns.index)
    n = len(tickers)
    init_weights = np.array([1.0 / n] * n)

    bounds = _make_bounds(n, min_weight, max_weight)
    constraints = _make_constraints(n)

    # Секторальные ограничения
    sectors = sorted(set(sector_map.get(t, "Unknown") for t in tickers))
    for sector in sectors:
        sector_indices = [i for i, t in enumerate(tickers) if sector_map.get(t, "Unknown") == sector]
        if len(sector_indices) > 0:
            constraints.append({
                "type": "ineq",
                "fun": lambda w, idx=sector_indices: max_sector_weight - sum(w[i] for i in idx),
            })

    def neg_sharpe(w):
        return -sharpe_ratio(w, mean_returns, cov_matrix, risk_free_rate)

    result = minimize(
        neg_sharpe,
        init_weights,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
    )

    if not result.success:
        logger.warning("Optimization failed: %s", result.message)

    weights = result.x

    # Вычисляем доли секторов
    sector_weights = {}
    for sector in sectors:
        sector_idx = [i for i, t in enumerate(tickers) if sector_map.get(t, "Unknown") == sector]
        sector_weights[sector] = sum(weights[i] for i in sector_idx)

    return {
        "weights": weights,
        "return": portfolio_return(weights, mean_returns),
        "volatility": portfolio_volatility(weights, cov_matrix),
        "sharpe": sharpe_ratio(weights, mean_returns, cov_matrix, risk_free_rate),
        "sector_weights": sector_weights,
    }


def efficient_frontier(
    mean_returns: pd.Series,
    cov_matrix: pd.DataFrame,
    n_points: int = 100,
    min_weight: float = MIN_WEIGHT,
    max_weight: float = MAX_WEIGHT,
) -> pd.DataFrame:
    """Расчёт эффективного фронтиера.

    Args:
        mean_returns: Средние дневные доходности.
        cov_matrix: Ковариационная матрица.
        n_points: Количество точек на фронтиере.
        min_weight: Минимальный вес актива.
        max_weight: Максимальный вес актива.

    Returns:
        DataFrame с колонками [return, volatility, sharpe, weights].
    """
    n = len(mean_returns)
    min_weight, max_weight = _normalize_weights(n, min_weight, max_weight)
    bounds = _make_bounds(n, min_weight, max_weight)
    constraints = _make_constraints(n)

    # Определяем диапазон доходностей на основе границ весов
    min_ret = sum(min_weight * mean_returns) * 252
    max_ret = sum(max_weight * mean_returns) * 252
    if min_ret > max_ret:
        min_ret, max_ret = max_ret, min_ret
    target_returns = np.linspace(min_ret, max_ret, n_points)

    results = []

    for target in target_returns:
        init_weights = np.array([1.0 / n] * n)

        def ret_constraint(w, target=target):
            return portfolio_return(w, mean_returns) - target

        cons = constraints + [{"type": "eq", "fun": ret_constraint}]

        def vol(w):
            return portfolio_volatility(w, cov_matrix)

        res = minimize(
            vol,
            init_weights,
            method="SLSQP",
            bounds=bounds,
            constraints=cons,
        )

        if res.success:
            w = res.x
            results.append(
                {
                    "return": portfolio_return(w, mean_returns),
                    "volatility": portfolio_volatility(w, cov_matrix),
                    "sharpe": sharpe_ratio(w, mean_returns, cov_matrix),
                    "weights": w,
                }
            )

    return pd.DataFrame(results)
