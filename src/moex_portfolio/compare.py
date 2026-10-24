"""Сравнение текущих и целевых весов портфеля (без брокера)."""

from __future__ import annotations

from typing import Any

from .numeric import (
    NumericValidationError,
    require_finite_number,
    require_nonnegative_finite,
)

WEIGHT_SUM_TOLERANCE = 1e-6
CASH_ASSET = "CASH"


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


def assess_turnover(
    current: dict[str, float],
    target: dict[str, float],
    *,
    cash_current: float | None = None,
    cash_target: float | None = None,
    cost_bps: float | None = None,
    portfolio_value: float | None = None,
    max_turnover: float | None = None,
) -> dict[str, Any]:
    """Оборот только когда обе книги полностью инвестированы.

    Односторонний оборот равен 0.5 * Σ|Δw| тогда и только тогда, когда
    суммы весов совпадают: покупки равны продажам. Для полностью
    инвестированного портфеля обе суммы равны 1. Кэш должен входить в
    вектор весов, иначе смена доли кэша ломает равенство.

    Если текущего портфеля нет, кэш неизвестен или суммы не сходятся,
    one_way_turnover остаётся null. L1 по неполным весам оборотом не называется.
    """
    empty = {
        "status": "initial_allocation",
        "one_way_identified": False,
        "gross_abs_weight_change": None,
        "one_way_turnover": None,
        "portfolio_share_traded": None,
        "buys": None,
        "sells": None,
        "cash_cost": None,
        "cash_cost_status": "insufficient_data",
        "turnover_limit_breached": False,
        "formula": "not identified",
    }
    if not current and cash_current is None:
        return empty

    cur = {str(k).strip().upper(): float(v) for k, v in current.items()}
    tgt = {str(k).strip().upper(): float(v) for k, v in target.items()}

    def _add_cash(book: dict[str, float], cash: float | None) -> dict[str, float]:
        if cash is None:
            return book
        if CASH_ASSET in book:
            raise ValueError("CASH is both a weight and a separate cash argument")
        out = dict(book)
        out[CASH_ASSET] = float(cash)
        return out

    cur = _add_cash(cur, cash_current)
    tgt = _add_cash(tgt, cash_target)
    names = set(cur) | set(tgt)
    buys = 0.0
    sells = 0.0
    for name in names:
        delta = float(tgt.get(name, 0.0)) - float(cur.get(name, 0.0))
        if delta > 0:
            buys += delta
        elif delta < 0:
            sells -= delta
    sum_c = float(sum(cur.values()))
    sum_t = float(sum(tgt.values()))
    sums_equal = abs(sum_c - sum_t) <= WEIGHT_SUM_TOLERANCE
    both_full = (
        abs(sum_c - 1.0) <= WEIGHT_SUM_TOLERANCE
        and abs(sum_t - 1.0) <= WEIGHT_SUM_TOLERANCE
    )
    identified = both_full and sums_equal and abs(buys - sells) <= WEIGHT_SUM_TOLERANCE
    one_way = 0.5 * (buys + sells) if identified else None
    cash_cost = None
    cash_status = "insufficient_data"
    if identified and cost_bps is not None and portfolio_value is not None:
        cash_cost = one_way * float(portfolio_value) * float(cost_bps) / 10_000.0
        cash_status = "estimated"
    if identified:
        status = "ok"
        formula = "one_way = 0.5 * sum(|dw|) because buys == sells and both books sum to 1"
    elif cash_current is None and cash_target is None and CASH_ASSET not in names:
        status = "cash_unknown"
        formula = "one_way withheld: weight sums are not both 1 and cash was not supplied"
    else:
        status = "weight_sums_differ"
        formula = "one_way withheld: buys != sells"
    breached = bool(
        identified
        and max_turnover is not None
        and one_way is not None
        and one_way > float(max_turnover) + WEIGHT_SUM_TOLERANCE
    )
    return {
        "status": status,
        "one_way_identified": identified,
        "gross_abs_weight_change": (buys + sells) if identified else None,
        "one_way_turnover": one_way,
        "portfolio_share_traded": one_way,
        "buys": buys if identified else None,
        "sells": sells if identified else None,
        "current_weight_sum": sum_c,
        "target_weight_sum": sum_t,
        "cost_bps": cost_bps,
        "portfolio_value": portfolio_value,
        "cash_cost": cash_cost,
        "cash_cost_status": cash_status,
        "max_turnover": max_turnover,
        "turnover_limit_breached": breached,
        "formula": formula,
    }


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

    max_abs = require_finite_number(max_abs, "max_abs_drift")
    turnover = assess_turnover(current_c, target_c)
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
        "gross_abs_weight_change": turnover["gross_abs_weight_change"],
        "one_way_turnover": turnover["one_way_turnover"],
        "portfolio_share_traded": turnover["portfolio_share_traded"],
        "turnover_status": turnover["status"],
        "turnover_formula": turnover["formula"],
        "cash_cost": None,
        "cash_cost_status": "insufficient_data",
    }
