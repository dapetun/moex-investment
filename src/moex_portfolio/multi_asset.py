"""Мульти-активная оптимизация: акции + облигации в одном портфеле.

Ключевая идея: объединяем доходности акций и облигаций в единую
ковариационную матрицу и оптимизируем портфель через Markowitz.

Акции и облигации обычно имеют слабую или отрицательную корреляцию,
что делает их идеальными кандидатами для диверсификации:
- Акции растут в периоды экономического роста
- Облигации растут, когда ЦБ снижает ставки (рецессия)
- В кризисах облигации смягчают просадки портфеля
"""

import logging

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from .config import MAX_WEIGHT, MIN_WEIGHT, RISK_FREE_RATE
from .metrics import (
    portfolio_return,
    portfolio_volatility,
    sharpe_ratio,
)

logger = logging.getLogger(__name__)


def combine_asset_returns(
    stock_returns: pd.DataFrame,
    bond_returns: pd.DataFrame | None = None,
    bond_yields: pd.Series | None = None,
    bond_annualization: int = 252,
) -> pd.DataFrame:
    """Объединение доходностей акций и облигаций.

    Облигации можно представить двумя способами:
    1. bond_returns — исторические дневные доходности (если есть данные)
    2. bond_yields — годовые доходности (YTM), конвертируемые в дневные

    Для облигаций с фиксированным купоном дневная доходность ≈ YTM / 252.

    Args:
        stock_returns: DataFrame с дневными доходностями акций.
        bond_returns: DataFrame с дневными доходностями облигаций (опционально).
        bond_yields: Series с годовыми YTM по облигациям (опционально).
        bond_annualization: Торговых дней в году (252 для MOEX).

    Returns:
        Объединённый DataFrame с доходностями всех активов.
    """
    combined = stock_returns.copy()

    if bond_returns is not None and not bond_returns.empty:
        # Приводим индексы к общему множеству
        common_idx = combined.index.intersection(bond_returns.index)
        combined = combined.loc[common_idx]
        bond_rets = bond_returns.loc[common_idx].copy()

        # Всегда добавляем BOND_ префикс для консистентности
        bond_rets.columns = [f"BOND_{c}" for c in bond_rets.columns]

        combined = pd.concat([combined, bond_rets], axis=1)

    elif bond_yields is not None and not bond_yields.empty:
        # Конвертируем годовые YTM в дневные доходности
        daily_yields = bond_yields / bond_annualization
        for ticker in bond_yields.index:
            col_name = f"BOND_{ticker}"
            combined[col_name] = daily_yields[ticker]

    logger.info(
        "Combined assets: %d stocks + %d bonds = %d total",
        stock_returns.shape[1],
        combined.shape[1] - stock_returns.shape[1],
        combined.shape[1],
    )
    return combined


def optimize_multi_asset(
    combined_returns: pd.DataFrame,
    risk_free_rate: float = RISK_FREE_RATE,
    min_weight: float = MIN_WEIGHT,
    max_weight: float = MAX_WEIGHT,
    asset_constraints: dict[str, dict] | None = None,
) -> dict:
    """Оптимизация мульти-активного портфеля (max Sharpe).

    Поддерживает ограничения на уровне классов активов:
    - max_stock_weight: максимальная доля всех акций
    - max_bond_weight: максимальная доля всех облигаций
    - min_stock_weight: минимальная доля всех акций
    - min_bond_weight: минимальная доля всех облигаций

    Args:
        combined_returns: Объединённый DataFrame доходностей.
        risk_free_rate: Безрисковая ставка.
        min_weight: Минимальный вес одного актива.
        max_weight: Максимальный вес одного актива.
        asset_constraints: Ограничения по классам активов.
            Например: {"stock": {"max": 0.8}, "bond": {"min": 0.2}}

    Returns:
        Словарь с weights, return, volatility, sharpe, asset_weights.
    """
    mean_returns = combined_returns.mean() * 252  # Годовые
    cov_matrix = combined_returns.cov() * 252  # Годовая ковариация
    n = len(mean_returns)

    # Нормализуем веса
    min_w, max_w = min_weight, max_weight
    if max_w * n < 1.0:
        max_w = 1.0 / n

    bounds = [(min_w, max_w)] * n
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]

    # Ограничения по классам активов
    if asset_constraints:
        tickers = list(combined_returns.columns)
        stock_idx = [i for i, t in enumerate(tickers) if not t.startswith("BOND_")]
        bond_idx = [i for i, t in enumerate(tickers) if t.startswith("BOND_")]

        if asset_constraints.get("stock", {}).get("max") is not None:
            smax = asset_constraints["stock"]["max"]
            constraints.append({
                "type": "ineq",
                "fun": lambda w, idx=stock_idx: smax - sum(w[i] for i in idx),
            })

        if asset_constraints.get("stock", {}).get("min") is not None:
            smin = asset_constraints["stock"]["min"]
            constraints.append({
                "type": "ineq",
                "fun": lambda w, idx=stock_idx: sum(w[i] for i in idx) - smin,
            })

        if asset_constraints.get("bond", {}).get("max") is not None:
            bmax = asset_constraints["bond"]["max"]
            constraints.append({
                "type": "ineq",
                "fun": lambda w, idx=bond_idx: bmax - sum(w[i] for i in idx),
            })

        if asset_constraints.get("bond", {}).get("min") is not None:
            bmin = asset_constraints["bond"]["min"]
            constraints.append({
                "type": "ineq",
                "fun": lambda w, idx=bond_idx: sum(w[i] for i in idx) - bmin,
            })

    def neg_sharpe(w):
        return -sharpe_ratio(w, mean_returns, cov_matrix, risk_free_rate)

    init_weights = np.array([1.0 / n] * n)

    # Пробуем SLSQP, при неудаче — COBYLA (без gradient, но более robust)
    result = minimize(
        neg_sharpe,
        init_weights,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
    )

    if not result.success:
        logger.debug("SLSQP failed, trying COBYLA: %s", result.message)
        result = minimize(
            neg_sharpe,
            init_weights,
            method="COBYLA",
            constraints=[
                {"type": "eq", "fun": lambda w: np.sum(w) - 1.0},
            ] + list(constraints[1:]),
        )

    if not result.success:
        logger.warning("Multi-asset optimization failed: %s", result.message)

    weights = result.x

    # Считаем доли по классам
    tickers = list(combined_returns.columns)
    stock_weight = sum(weights[i] for i, t in enumerate(tickers) if not t.startswith("BOND_"))
    bond_weight = sum(weights[i] for i, t in enumerate(tickers) if t.startswith("BOND_"))

    return {
        "weights": weights,
        "return": portfolio_return(weights, mean_returns),
        "volatility": portfolio_volatility(weights, cov_matrix),
        "sharpe": sharpe_ratio(weights, mean_returns, cov_matrix, risk_free_rate),
        "stock_weight": stock_weight,
        "bond_weight": bond_weight,
        "tickers": tickers,
    }


def min_variance_multi_asset(
    combined_returns: pd.DataFrame,
    min_weight: float = MIN_WEIGHT,
    max_weight: float = MAX_WEIGHT,
    asset_constraints: dict[str, dict] | None = None,
) -> dict:
    """Мульти-активный портфель минимальной волатильности.

    Args:
        combined_returns: Объединённый DataFrame доходностей.
        min_weight: Минимальный вес одного актива.
        max_weight: Максимальный вес одного актива.
        asset_constraints: Ограничения по классам активов.

    Returns:
        Словарь с weights, return, volatility, sharpe, stock/bond weights.
    """
    mean_returns = combined_returns.mean() * 252
    cov_matrix = combined_returns.cov() * 252
    n = len(mean_returns)

    min_w, max_w = min_weight, max_weight
    if max_w * n < 1.0:
        max_w = 1.0 / n

    bounds = [(min_w, max_w)] * n
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]

    if asset_constraints:
        tickers = list(combined_returns.columns)
        stock_idx = [i for i, t in enumerate(tickers) if not t.startswith("BOND_")]
        bond_idx = [i for i, t in enumerate(tickers) if t.startswith("BOND_")]

        if asset_constraints.get("stock", {}).get("max") is not None:
            smax = asset_constraints["stock"]["max"]
            constraints.append({
                "type": "ineq",
                "fun": lambda w, idx=stock_idx: smax - sum(w[i] for i in idx),
            })

        if asset_constraints.get("bond", {}).get("min") is not None:
            bmin = asset_constraints["bond"]["min"]
            constraints.append({
                "type": "ineq",
                "fun": lambda w, idx=bond_idx: sum(w[i] for i in idx) - bmin,
            })

    def volatility(w):
        return portfolio_volatility(w, cov_matrix)

    init_weights = np.array([1.0 / n] * n)
    result = minimize(
        volatility,
        init_weights,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
    )

    if not result.success:
        logger.warning("Multi-asset min-var optimization failed: %s", result.message)

    weights = result.x
    tickers = list(combined_returns.columns)
    stock_weight = sum(weights[i] for i, t in enumerate(tickers) if not t.startswith("BOND_"))
    bond_weight = sum(weights[i] for i, t in enumerate(tickers) if t.startswith("BOND_"))

    return {
        "weights": weights,
        "return": portfolio_return(weights, mean_returns),
        "volatility": portfolio_volatility(weights, cov_matrix),
        "sharpe": sharpe_ratio(weights, mean_returns, cov_matrix),
        "stock_weight": stock_weight,
        "bond_weight": bond_weight,
        "tickers": tickers,
    }


def efficient_frontier_multi_asset(
    combined_returns: pd.DataFrame,
    n_points: int = 50,
    min_weight: float = MIN_WEIGHT,
    max_weight: float = MAX_WEIGHT,
    asset_constraints: dict[str, dict] | None = None,
) -> pd.DataFrame:
    """Эффективный фронтёр для мульти-активного портфеля.

    Args:
        combined_returns: Объединённый DataFrame доходностей.
        n_points: Количество точек.
        min_weight: Минимальный вес.
        max_weight: Максимальный вес.
        asset_constraints: Ограничения по классам активов.

    Returns:
        DataFrame с [return, volatility, sharpe, weights].
    """
    mean_returns = combined_returns.mean() * 252
    cov_matrix = combined_returns.cov() * 252
    n = len(mean_returns)

    min_w, max_w = min_weight, max_weight
    if max_w * n < 1.0:
        max_w = 1.0 / n

    bounds = [(min_w, max_w)] * n
    base_constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]

    if asset_constraints:
        tickers = list(combined_returns.columns)
        stock_idx = [i for i, t in enumerate(tickers) if not t.startswith("BOND_")]
        bond_idx = [i for i, t in enumerate(tickers) if t.startswith("BOND_")]

        if asset_constraints.get("stock", {}).get("max") is not None:
            smax = asset_constraints["stock"]["max"]
            base_constraints.append({
                "type": "ineq",
                "fun": lambda w, idx=stock_idx: smax - sum(w[i] for i in idx),
            })
        if asset_constraints.get("bond", {}).get("min") is not None:
            bmin = asset_constraints["bond"]["min"]
            base_constraints.append({
                "type": "ineq",
                "fun": lambda w, idx=bond_idx: sum(w[i] for i in idx) - bmin,
            })

    min_ret = sum(min_w * mean_returns) * 1
    max_ret = sum(max_w * mean_returns) * 1
    # Recompute with actual bounds
    per_asset_min = np.array([b[0] for b in bounds])
    per_asset_max = np.array([b[1] for b in bounds])
    min_ret = float(per_asset_min @ mean_returns.values)
    max_ret = float(per_asset_max @ mean_returns.values)
    if min_ret > max_ret:
        min_ret, max_ret = max_ret, min_ret

    target_returns = np.linspace(min_ret, max_ret, n_points)
    results = []

    for target in target_returns:
        init_weights = np.array([1.0 / n] * n)

        def ret_constraint(w, t=target):
            return portfolio_return(w, mean_returns) - t

        cons = base_constraints + [{"type": "eq", "fun": ret_constraint}]

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
            tickers = list(combined_returns.columns)
            stock_w = sum(w[i] for i, t in enumerate(tickers) if not t.startswith("BOND_"))
            bond_w = sum(w[i] for i, t in enumerate(tickers) if t.startswith("BOND_"))
            results.append({
                "return": portfolio_return(w, mean_returns),
                "volatility": portfolio_volatility(w, cov_matrix),
                "sharpe": sharpe_ratio(w, mean_returns, cov_matrix),
                "weights": w,
                "stock_weight": stock_w,
                "bond_weight": bond_w,
            })

    return pd.DataFrame(results)
