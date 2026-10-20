"""Markowitz Mean-Variance оптимизация портфеля."""

import logging

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from .config import MAX_WEIGHT, MIN_WEIGHT, RISK_FREE_RATE
from .metrics import portfolio_return, portfolio_volatility, sharpe_ratio

logger = logging.getLogger(__name__)

TOP_K_DEFAULT = 5
_FEAS_TOL = 1e-12


class InfeasibleWeightConstraints(ValueError):
    """Ограничения весов несовместны с суммой 1. Лимиты не ослабляются."""

    code = "INFEASIBLE_WEIGHT_CONSTRAINTS"


def assert_long_only_feasible(
    n_assets: int,
    min_weight: float = MIN_WEIGHT,
    max_weight: float = MAX_WEIGHT,
    max_top5: float | None = None,
    *,
    top_k: int = TOP_K_DEFAULT,
) -> None:
    """Проверить, существует ли long-only портфель с суммой 1.

    Равные веса 1/n лежат в [min, max] тогда и только тогда, когда
    n*max >= 1 и n*min <= 1. Минимально возможная сумма k крупнейших
    весов при этом равна k/n (или 1, если k >= n).
    """
    reasons: list[str] = []
    if n_assets < 1:
        reasons.append(f"n_assets={n_assets}")
    if not (0.0 < max_weight <= 1.0):
        reasons.append(f"max_weight={max_weight} not in (0, 1]")
    if min_weight < 0.0 or min_weight > max_weight:
        reasons.append(f"min_weight={min_weight} outside [0, max_weight]")
    if n_assets >= 1 and n_assets * max_weight < 1.0 - _FEAS_TOL:
        reasons.append(
            f"n*max_weight={n_assets * max_weight:.6f} < 1; "
            "cap is not raised to 1/n"
        )
    if n_assets >= 1 and n_assets * min_weight > 1.0 + _FEAS_TOL:
        reasons.append(f"n*min_weight={n_assets * min_weight:.6f} > 1")
    if max_top5 is not None:
        if not (0.0 < max_top5 <= 1.0):
            reasons.append(f"max_top5={max_top5} not in (0, 1]")
        k = min(top_k, n_assets) if n_assets >= 1 else 0
        floor = 1.0 if k == n_assets else (k / n_assets if n_assets else 1.0)
        if max_top5 + _FEAS_TOL < floor:
            reasons.append(
                f"min attainable top-{k} sum is {floor:.6f} > max_top5={max_top5}"
            )
    if reasons:
        raise InfeasibleWeightConstraints(
            "INFEASIBLE_WEIGHT_CONSTRAINTS: " + "; ".join(reasons)
        )


def _normalize_weights(
    n_assets: int,
    min_weight: float = MIN_WEIGHT,
    max_weight: float = MAX_WEIGHT,
    max_top5: float | None = None,
) -> tuple[float, float]:
    """Проверить границы и вернуть их без молчаливого ослабления."""
    assert_long_only_feasible(
        n_assets, min_weight, max_weight, max_top5=max_top5
    )
    return min_weight, max_weight


def _make_constraints(n_assets: int) -> list[dict]:
    """Создание ограничений: сумма весов = 1."""
    return [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]


def _make_bounds(
    n_assets: int,
    min_weight: float = MIN_WEIGHT,
    max_weight: float = MAX_WEIGHT,
    max_top5: float | None = None,
) -> list[tuple[float, float]]:
    """Границы весов. Невыполнимый набор границ — ошибка, не 1/n."""
    min_weight, max_weight = _normalize_weights(
        n_assets, min_weight, max_weight, max_top5=max_top5
    )
    return [(min_weight, max_weight) for _ in range(n_assets)]


def _top_k_constraints(n: int, max_top5: float, top_k: int = TOP_K_DEFAULT) -> tuple[list, int]:
    """Ограничение суммы k крупнейших весов через s, t: k*s + sum t <= L."""
    k = min(top_k, n)
    if k == n or max_top5 >= 1.0 - _FEAS_TOL:
        return [], 0
    extra = 1 + n  # s + t_i

    def top_cap(x, n=n, k=k, limit=max_top5):
        s = x[n]
        t = x[n + 1 : n + 1 + n]
        return limit - (k * s + np.sum(t))

    cons = [{"type": "ineq", "fun": top_cap}]
    for i in range(n):
        cons.append({
            "type": "ineq",
            "fun": lambda x, i=i, n=n: x[n + 1 + i],  # t_i >= 0
        })
        cons.append({
            "type": "ineq",
            "fun": lambda x, i=i, n=n: x[n + 1 + i] - (x[i] - x[n]),  # t >= w - s
        })
    return cons, extra


def concentration_stats(weights: np.ndarray, *, top_k: int = TOP_K_DEFAULT) -> dict:
    """Фактическая концентрация: максимум и сумма k крупнейших весов."""
    w = np.asarray(weights, dtype=float)
    order = np.sort(w)[::-1]
    k = min(top_k, len(order))
    return {
        "max_weight_realized": float(order[0]) if len(order) else 0.0,
        "top5_sum": float(order[:k].sum()) if k else 0.0,
        "top_k": k,
        "n_assets": int(len(order)),
        "n_at_max_bound": None,
    }


def max_sharpe_portfolio(
    mean_returns: pd.Series,
    cov_matrix: pd.DataFrame,
    risk_free_rate: float = RISK_FREE_RATE,
    min_weight: float = MIN_WEIGHT,
    max_weight: float = MAX_WEIGHT,
    max_top5: float | None = None,
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

    def neg_sharpe(w):
        return -sharpe_ratio(w, mean_returns, cov_matrix, risk_free_rate)

    solved = _solve_long_only(
        n,
        neg_sharpe,
        min_weight=min_weight,
        max_weight=max_weight,
        max_top5=max_top5,
    )
    weights = solved["weights"]
    stats = concentration_stats(weights)
    stats["n_at_max_bound"] = int(np.sum(weights >= max_weight - 1e-6))
    return {
        "weights": weights,
        "return": portfolio_return(weights, mean_returns),
        "volatility": portfolio_volatility(weights, cov_matrix),
        "sharpe": sharpe_ratio(weights, mean_returns, cov_matrix, risk_free_rate),
        "success": solved["success"],
        "message": solved["message"],
        "risk_free_rate": risk_free_rate,
        "risk_free_rate_unit": "annual",
        "max_weight": max_weight,
        "max_top5": max_top5,
        "concentration": stats,
    }


def _solve_long_only(
    n: int,
    objective_on_weights,
    *,
    min_weight: float,
    max_weight: float,
    max_top5: float | None,
) -> dict:
    """SLSQP по весам. При max_top5 добавляются s и t без ослабления лимита."""
    bounds_w = _make_bounds(n, min_weight, max_weight, max_top5=max_top5)
    extra_cons, n_extra = _top_k_constraints(n, max_top5 if max_top5 is not None else 1.0)
    init_w = np.full(n, 1.0 / n)
    constraints = _make_constraints(n) if n_extra == 0 else [
        {"type": "eq", "fun": lambda x, n=n: np.sum(x[:n]) - 1.0},
        *extra_cons,
    ]
    if n_extra == 0:
        result = minimize(
            objective_on_weights,
            init_w,
            method="SLSQP",
            bounds=bounds_w,
            constraints=constraints,
        )
        weights = np.asarray(result.x, dtype=float)
    else:
        # s свободен в [0, max_weight], t >= 0
        bounds = list(bounds_w) + [(0.0, max_weight)] + [(0.0, None)] * n
        x0 = np.concatenate([init_w, np.array([0.0]), np.zeros(n)])

        def wrapped(x, n=n):
            return objective_on_weights(x[:n])

        result = minimize(
            wrapped,
            x0,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
        )
        weights = np.asarray(result.x[:n], dtype=float)
    if not result.success:
        logger.warning("Optimization failed: %s", result.message)
    return {
        "weights": weights,
        "success": bool(result.success),
        "message": str(result.message),
    }


def equal_weight_portfolio(
    mean_returns: pd.Series,
    cov_matrix: pd.DataFrame,
    risk_free_rate: float = RISK_FREE_RATE,
    min_weight: float = MIN_WEIGHT,
    max_weight: float = MAX_WEIGHT,
    max_top5: float | None = None,
) -> dict:
    """Портфель 1/N. Невыполнимые лимиты — ошибка, веса не подгоняются."""
    n = len(mean_returns)
    assert_long_only_feasible(n, min_weight, max_weight, max_top5=max_top5)
    weights = np.full(n, 1.0 / n)
    if np.any(weights < min_weight - 1e-12) or np.any(weights > max_weight + 1e-12):
        raise InfeasibleWeightConstraints(
            "INFEASIBLE_WEIGHT_CONSTRAINTS: equal weight outside bounds"
        )
    stats = concentration_stats(weights)
    return {
        "weights": weights,
        "return": portfolio_return(weights, mean_returns),
        "volatility": portfolio_volatility(weights, cov_matrix),
        "sharpe": sharpe_ratio(weights, mean_returns, cov_matrix, risk_free_rate),
        "success": True,
        "message": "equal_weight",
        "risk_free_rate": risk_free_rate,
        "risk_free_rate_unit": "annual",
        "max_weight": max_weight,
        "max_top5": max_top5,
        "concentration": stats,
    }


def min_variance_portfolio(
    mean_returns: pd.Series,
    cov_matrix: pd.DataFrame,
    min_weight: float = MIN_WEIGHT,
    max_weight: float = MAX_WEIGHT,
    max_top5: float | None = None,
    risk_free_rate: float = RISK_FREE_RATE,
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

    def volatility(w):
        return portfolio_volatility(w, cov_matrix)

    solved = _solve_long_only(
        n,
        volatility,
        min_weight=min_weight,
        max_weight=max_weight,
        max_top5=max_top5,
    )
    weights = solved["weights"]
    return {
        "weights": weights,
        "return": portfolio_return(weights, mean_returns),
        "volatility": portfolio_volatility(weights, cov_matrix),
        "sharpe": sharpe_ratio(weights, mean_returns, cov_matrix, risk_free_rate),
        "success": solved["success"],
        "message": solved["message"],
        "risk_free_rate": risk_free_rate,
        "risk_free_rate_unit": "annual",
        "max_weight": max_weight,
        "max_top5": max_top5,
        "concentration": concentration_stats(weights),
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
    sectors = sorted({sector_map.get(t, "Unknown") for t in tickers})
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
