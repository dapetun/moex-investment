"""Сравнение текущих и целевых весов портфеля (без брокера)."""

from __future__ import annotations

from typing import Any

from .numeric import (
    NumericValidationError,
    require_finite_number,
    require_nonnegative_finite,
)

WEIGHT_SUM_TOLERANCE = 1e-6


def _validate_weight_map(weights: dict[str, float], name: str) -> dict[str, float]:
    if not isinstance(weights, dict):
        raise NumericValidationError(f"{name} must be a dict")
    clean: dict[str, float] = {}
    for ticker, value in weights.items():
        if not isinstance(ticker, str) or not ticker.strip():
            raise NumericValidationError(f"{name}: empty ticker key")
        w = require_nonnegative_finite(value, f"{name}[{ticker}]")
        clean[ticker.strip().upper()] = w
    return clean


def compare_weights(
    current: dict[str, float],
    target: dict[str, float],
    min_drift: float = 0.05,
) -> dict[str, Any]:
    """Сравнить веса и решить, нужен ли ребаланс по порогу drift.

    Raises:
        NumericValidationError: NaN/Inf/отрицательные веса/некорректный min_drift.
    """
    min_drift_f = require_nonnegative_finite(min_drift, "min_drift")
    current_c = _validate_weight_map(current, "current")
    target_c = _validate_weight_map(target, "target")

    if target_c:
        tw = sum(target_c.values())
        if abs(tw - 1.0) > WEIGHT_SUM_TOLERANCE:
            raise NumericValidationError(
                f"target weights sum to {tw:.6f}, expected 1.0 "
                f"(tol={WEIGHT_SUM_TOLERANCE})"
            )

    tickers = sorted(set(current_c) | set(target_c))
    diffs = []
    max_abs = 0.0
    for t in tickers:
        c = require_finite_number(current_c.get(t, 0.0), f"current[{t}]")
        tg = require_finite_number(target_c.get(t, 0.0), f"target[{t}]")
        if c < 0 or tg < 0:
            raise NumericValidationError(f"negative weight in drift for {t}")
        drift = abs(c - tg)
        if not (drift == drift) or drift == float("inf"):  # pragma: no cover
            raise NumericValidationError(f"non-finite drift for {t}")
        max_abs = max(max_abs, drift)
        diffs.append(
            {
                "ticker": t,
                "current": c,
                "target": tg,
                "drift": drift,
            }
        )

    gross = float(sum(row["drift"] for row in diffs))
    one_way = 0.5 * gross
    max_abs = require_finite_number(max_abs, "max_abs_drift")
    # Пустой текущий портфель + непустой target — первичное размещение, не ребаланс.
    if not current_c and target_c:
        allocation_kind = "initial_allocation"
        needs_action = max_abs >= min_drift_f
    else:
        allocation_kind = "rebalance"
        needs_action = max_abs >= min_drift_f

    return {
        "needs_rebalance": needs_action and allocation_kind == "rebalance",
        "needs_action": needs_action,
        "allocation_kind": allocation_kind,
        "max_abs_drift": max_abs,
        "min_drift": min_drift_f,
        "diffs": diffs,
        "tickers": tickers,
        "gross_abs_weight_change": None if not current_c else gross,
        "one_way_turnover": None if not current_c else one_way,
        "portfolio_share_traded": None if not current_c else one_way,
        "turnover_formula": "one_way = 0.5 * sum(|target-current|)",
        "cash_cost": None,
        "cash_cost_status": "insufficient_data",
    }
