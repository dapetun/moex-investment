"""Risk Budgeting — анализ вклада каждой акции в общий риск портфеля.

Показывает marginal risk contribution, component risk contribution
и процентный risk contribution для каждого актива.
"""

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class RiskBudgetResult:
    """Результаты risk budgeting анализа."""

    tickers: list[str]
    weights: np.ndarray
    marginal_risk: np.ndarray
    component_risk: np.ndarray
    pct_risk: np.ndarray
    portfolio_volatility: float


def compute_risk_budget(
    weights: np.ndarray | list[float],
    cov_matrix: pd.DataFrame | np.ndarray,
) -> RiskBudgetResult:
    """Расчёт вклада каждой акции в риск портфеля.

    Формулы:
    - Portfolio variance: σ²_p = w^T · Σ · w
    - Portfolio volatility: σ_p = sqrt(σ²_p)
    - Marginal risk: ∂σ_p / ∂w_i = (Σ · w)_i / σ_p
    - Component risk: CR_i = w_i × MCR_i
    - Percent contribution: PCR_i = CR_i / σ_p

    Args:
        weights: Веса акций в портфеле.
        cov_matrix: Ковариационная матрица.

    Returns:
        RiskBudgetResult с результатами.
    """
    w = np.asarray(weights, dtype=float)
    if isinstance(cov_matrix, pd.DataFrame):
        tickers = cov_matrix.columns.tolist()
        cov = cov_matrix.values
    else:
        tickers = [f"Asset_{i}" for i in range(len(w))]
        cov = cov_matrix

    port_var = float(w @ cov @ w)
    port_vol = np.sqrt(port_var) if port_var > 0 else 1e-10

    sigma_w = cov @ w
    marginal = sigma_w / port_vol
    component = w * marginal
    pct = component / port_vol

    logger.info(
        "Risk budget: vol=%.2f%%, top contributor=%s (%.1f%%)",
        port_vol * 100,
        tickers[int(np.argmax(np.abs(pct)))] if len(tickers) > 0 else "N/A",
        float(np.max(np.abs(pct))) * 100,
    )

    return RiskBudgetResult(
        tickers=tickers,
        weights=w,
        marginal_risk=marginal,
        component_risk=component,
        pct_risk=pct,
        portfolio_volatility=port_vol,
    )


def risk_budget_summary(result: RiskBudgetResult) -> pd.DataFrame:
    """Сводная таблица risk budgeting.

    Args:
        result: RiskBudgetResult.

    Returns:
        DataFrame с вкладом каждой акции.
    """
    df = pd.DataFrame({
        "Ticker": result.tickers,
        "Weight": result.weights,
        "Marginal Risk": result.marginal_risk,
        "Component Risk": result.component_risk,
        "Risk Contribution %": result.pct_risk,
    })

    df["Risk/Return Ratio"] = np.where(
        df["Weight"] > 0,
        df["Component Risk"] / df["Weight"],
        0.0,
    )

    return df.sort_values("Risk Contribution %", ascending=False).reset_index(drop=True)


def equal_risk_contribution(
    cov_matrix: pd.DataFrame | np.ndarray,
    n_assets: int | None = None,
    max_iter: int = 1000,
    tol: float = 1e-8,
) -> np.ndarray:
    """Расчёт весов для Equal Risk Contribution (ERC) портфеля.

    ERC: каждая акция вносит одинаковый % в общий риск.

    Алгоритм: итеративная аппроксимация (Spinu 2013).

    Args:
        cov_matrix: Ковариационная матрица.
        n_assets: Число активов (определяется автоматически).
        max_iter: Максимальное число итераций.
        tol: Точность сходимости.

    Returns:
        Веса ERC портфеля.
    """
    if isinstance(cov_matrix, pd.DataFrame):
        cov = cov_matrix.values
    else:
        cov = np.asarray(cov_matrix)

    if n_assets is None:
        n_assets = cov.shape[0]

    from scipy.optimize import minimize

    def _erc_objective(w):
        port_vol = np.sqrt(w @ cov @ w)
        if port_vol < 1e-12:
            return 1e10
        marginal = cov @ w / port_vol
        risk_contrib = w * marginal
        total_rc = risk_contrib.sum()
        if total_rc < 1e-12:
            return 1e10
        current_pct = risk_contrib / total_rc
        target = np.ones(n_assets) / n_assets
        return float(np.sum((current_pct - target) ** 2))

    x0 = np.ones(n_assets) / n_assets
    bounds = [(1e-6, 1.0)] * n_assets
    constraints = {"type": "eq", "fun": lambda w: w.sum() - 1.0}

    result = minimize(_erc_objective, x0, method="SLSQP", bounds=bounds, constraints=constraints)
    w = result.x / result.x.sum()

    logger.info("ERC: optimized, success=%s, error=%.2e", result.success, result.fun)
    return w
