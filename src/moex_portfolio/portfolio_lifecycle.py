"""Стадии портфеля: проект, денежный план, фактические holdings.

Проект не записывается в last_target и не считается текущим портфелем.
Фактические суммы в логах не печатаются: наружу уходят только запрошенные поля.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .data_sources import FixtureDataSource
from .numeric import require_nonnegative_finite
from .optimizer import (
    InfeasibleWeightConstraints,
    equal_weight_portfolio,
    max_sharpe_portfolio,
    min_variance_portfolio,
)

TOL = 1e-6
CASH = "CASH"
STAGES = ("proposed", "funded", "actual")
NOT_ACCOUNTED = (
    "dividends",
    "bond_coupons",
    "bond_amortization",
    "corporate_actions",
    "fx_moves",
    "contributions_and_withdrawals",
    "trades_since_snapshot",
)


class LifecycleError(ValueError):
    """Нехватка или противоречие данных. Лимиты и суммы не подгоняются."""


def _num(value: str, name: str) -> float:
    return float(require_nonnegative_finite(float(str(value).replace(",", ".")), name))


def _cell(row: dict[str, str], *names: str) -> str | None:
    lower = {str(k).strip().lower(): v for k, v in row.items() if k is not None}
    for name in names:
        raw = lower.get(name.lower())
        if raw is not None and str(raw).strip():
            return str(raw).strip()
    return None


def parse_snapshot_csv(
    path: Path,
    *,
    data_source: str | None = None,
) -> dict[str, Any]:
    """Прочитать снимок. Weight-only не получает выдуманные quantity и cost."""
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise LifecycleError("snapshot is empty (code=SNAPSHOT_EMPTY)")
    parsed: list[dict[str, Any]] = []
    as_of = None
    source = data_source
    for row in rows:
        secid = (_cell(row, "secid", "ticker") or "").upper()
        if not secid:
            raise LifecycleError("secid is required (code=SNAPSHOT_ID_MISSING)")
        row_as_of = _cell(row, "as_of", "as_of_date")
        if row_as_of is None:
            raise LifecycleError("as_of is required (code=SNAPSHOT_DATE_MISSING)")
        if as_of is None:
            as_of = row_as_of
        elif as_of != row_as_of:
            raise LifecycleError("mixed as_of dates (code=SNAPSHOT_MIXED_DATES)")
        currency = (_cell(row, "currency") or "").upper()
        if not currency:
            raise LifecycleError("currency is required (code=SNAPSHOT_CURRENCY_MISSING)")
        row_source = _cell(row, "data_source", "source")
        if row_source:
            if source is None:
                source = row_source
            elif source != row_source:
                raise LifecycleError("mixed data_source (code=SNAPSHOT_MIXED_SOURCE)")
        item: dict[str, Any] = {
            "secid": secid,
            "currency": currency,
            "account": _cell(row, "account", "account_label"),
        }
        for key, names in (
            ("weight", ("weight",)),
            ("target_weight", ("target_weight",)),
            ("market_value", ("market_value",)),
            ("planned_value", ("planned_value",)),
            ("quantity", ("quantity",)),
            ("planned_quantity", ("planned_quantity",)),
            ("price", ("price",)),
        ):
            raw = _cell(row, *names)
            if raw is not None:
                item[key] = _num(raw, key)
        parsed.append(item)
    if source is None:
        raise LifecycleError("data_source is required (code=SNAPSHOT_SOURCE_MISSING)")
    currencies = {item["currency"] for item in parsed}
    if len(currencies) != 1:
        raise LifecycleError("mixed currencies (code=SNAPSHOT_MIXED_CURRENCY)")
    return _aggregate_actual(parsed, as_of=as_of, data_source=source)


def _aggregate_actual(
    rows: list[dict[str, Any]],
    *,
    as_of: str,
    data_source: str,
) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(row["secid"], []).append(row)
    positions: list[dict[str, Any]] = []
    for secid, items in groups.items():
        if len(items) > 1 and not all("market_value" in item or ("quantity" in item and "price" in item) for item in items):
            raise LifecycleError(
                f"{secid}: multiple accounts without a value denominator "
                "(code=SNAPSHOT_ACCOUNTS_NOT_ADDITIVE)"
            )
        position: dict[str, Any] = {
            "secid": secid,
            "currency": items[0]["currency"],
            "accounts": [item.get("account") for item in items if item.get("account")],
        }
        if any("quantity" in item and "price" in item for item in items):
            qty = 0.0
            price = items[0].get("price")
            for item in items:
                if "quantity" not in item or "price" not in item:
                    raise LifecycleError(f"{secid}: incomplete quantity row (code=SNAPSHOT_BAD_QUANTITY)")
                if item["price"] != price:
                    raise LifecycleError(f"{secid}: conflicting prices (code=SNAPSHOT_PRICE_CONFLICT)")
                qty += item["quantity"]
            position["quantity"] = qty
            position["price"] = price
            position["market_value"] = qty * price
        elif any("market_value" in item for item in items):
            position["market_value"] = sum(item.get("market_value", 0.0) for item in items)
        if any("weight" in item for item in items):
            if len(items) > 1:
                raise LifecycleError(
                    f"{secid}: cannot add weights across accounts (code=SNAPSHOT_WEIGHTS_NOT_ADDITIVE)"
                )
            position["weight"] = items[0]["weight"]
        if any("target_weight" in item for item in items):
            position["target_weight"] = items[0]["target_weight"]
        if any("planned_value" in item for item in items):
            position["planned_value"] = items[0]["planned_value"]
        if "weight" not in position and "market_value" not in position:
            raise LifecycleError(f"{secid}: no actual weight or value (code=SNAPSHOT_INCOMPLETE)")
        positions.append(position)
    values = [pos["market_value"] for pos in positions if "market_value" in pos]
    if values and len(values) == len(positions):
        total = sum(values)
        if total <= 0:
            raise LifecycleError("market value total is zero (code=SNAPSHOT_ZERO_VALUE)")
        for pos in positions:
            implied = pos["market_value"] / total
            if "weight" in pos and abs(pos["weight"] - implied) > TOL:
                raise LifecycleError(
                    f"{pos['secid']}: weight disagrees with market value "
                    "(code=SNAPSHOT_WEIGHT_VALUE_MISMATCH)"
                )
            pos["weight"] = implied
        weight_basis = "market_value"
    else:
        weight_sum = sum(pos.get("weight", 0.0) for pos in positions)
        if abs(weight_sum - 1.0) > TOL:
            raise LifecycleError(
                f"weights sum to {weight_sum}, expected 1 within {TOL} "
                "(code=SNAPSHOT_WEIGHT_SUM)"
            )
        weight_basis = "weight"
        for pos in positions:
            pos.pop("market_value", None)
            pos.pop("quantity", None)
    return {
        "stage": "actual",
        "status": "actual_snapshot",
        "as_of": as_of,
        "currency": positions[0]["currency"],
        "data_source": data_source,
        "weight_basis": weight_basis,
        "weight_status": "actual",
        "positions": positions,
        "private_values_redacted": weight_basis == "weight",
    }


def _sleeve_weights(
    prices: pd.DataFrame,
    tickers: list[str],
    *,
    solver,
    max_weight: float,
    max_top5: float | None,
    risk_free_rate: float,
    investable: float,
) -> dict[str, float]:
    if investable <= TOL:
        return {}
    cap = max_weight / investable
    if cap > 1.0 + TOL:
        cap = 1.0
    panel = prices[tickers]
    returns = panel.pct_change().dropna(how="any")
    if len(returns) < 2:
        raise LifecycleError("not enough prices (code=PROPOSAL_SHORT_HISTORY)")
    try:
        solved = solver(
            returns.mean(),
            returns.cov(),
            risk_free_rate=risk_free_rate,
            max_weight=cap,
            max_top5=None if max_top5 is None else min(1.0, max_top5 / investable),
        )
    except InfeasibleWeightConstraints as exc:
        raise LifecycleError(str(exc)) from exc
    if solved.get("success") is not True:
        raise LifecycleError(str(solved.get("message") or "solver failed"))
    raw = np.asarray(solved["weights"], dtype=float) * investable
    return {ticker: float(weight) for ticker, weight in zip(tickers, raw)}


def propose_allocation(
    prices: pd.DataFrame,
    tickers: list[str],
    *,
    max_weight: float = 0.5,
    max_top5: float | None = None,
    cash_weight: float = 0.0,
    risk_free_rate: float = 0.0,
    as_of: str | None = None,
    horizon: str | None = None,
    data_source: str = "synthetic",
) -> dict[str, Any]:
    """Проект распределения. Пустой фактический портфель здесь не ошибка."""
    if not 0.0 <= cash_weight <= 1.0:
        raise LifecycleError("cash_weight must be in [0, 1] (code=PROPOSAL_BAD_CASH)")
    missing = [ticker for ticker in tickers if ticker not in prices.columns]
    if missing:
        raise LifecycleError(f"tickers missing in prices: {missing} (code=PROPOSAL_MISSING_PRICES)")
    investable = 1.0 - cash_weight
    if investable > TOL and len(tickers) * max_weight + TOL < investable:
        raise LifecycleError(
            "INFEASIBLE_WEIGHT_CONSTRAINTS: caps cannot fund the investable share"
        )
    solvers = {
        "max_sharpe": max_sharpe_portfolio,
        "min_variance": min_variance_portfolio,
        "equal_weight": equal_weight_portfolio,
    }
    proposals = {}
    for name, solver in solvers.items():
        weights = _sleeve_weights(
            prices,
            tickers,
            solver=solver,
            max_weight=max_weight,
            max_top5=max_top5,
            risk_free_rate=risk_free_rate,
            investable=investable,
        )
        if cash_weight > 0:
            weights[CASH] = cash_weight
        proposals[name] = {
            "weights": weights,
            "max_weight_realized": max(weights.values()) if weights else 0.0,
            "model_estimate": True,
        }
    return {
        "stage": "proposed",
        "status": "project_not_holdings",
        "execution_recommendation": False,
        "as_of": as_of,
        "horizon": horizon,
        "data_source": data_source,
        "risk_free_rate": risk_free_rate,
        "risk_free_rate_unit": "annual",
        "max_weight": max_weight,
        "max_top5": max_top5,
        "cash_weight": cash_weight,
        "preferred_strategy": None,
        "proposals": proposals,
        "note": "Model estimates from the supplied price panel. Not actual holdings.",
    }


def fund_plan(
    weights: dict[str, float],
    *,
    budget: float,
    currency: str,
    cost_bps: float = 0.0,
    slippage_bps: float = 0.0,
    prices: dict[str, float] | None = None,
    lot_sizes: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Перевести проектные веса в суммы. Без бюджета этот шаг не вызывается."""
    if budget <= 0:
        raise LifecycleError("budget must be positive (code=FUND_BUDGET_REQUIRED)")
    if not currency:
        raise LifecycleError("currency is required (code=FUND_CURRENCY_REQUIRED)")
    total_weight = sum(weights.values())
    if abs(total_weight - 1.0) > TOL:
        raise LifecycleError(f"weights sum to {total_weight} (code=FUND_WEIGHT_SUM)")
    lines = []
    spent = 0.0
    cash = 0.0
    for secid, weight in weights.items():
        raw_amount = budget * weight
        line: dict[str, Any] = {
            "secid": secid,
            "target_weight": weight,
            "planned_value": raw_amount,
            "planned_quantity": None,
            "price_status": "not_used",
        }
        if secid == CASH:
            cash += raw_amount
        elif prices and secid in prices and lot_sizes and secid in lot_sizes:
            price = prices[secid]
            lot = lot_sizes[secid]
            if price <= 0 or lot <= 0:
                raise LifecycleError(f"{secid}: bad price or lot (code=FUND_BAD_LOT)")
            lots = int(raw_amount // (price * lot))
            quantity = lots * lot
            value = quantity * price
            line["planned_quantity"] = quantity
            line["planned_value"] = value
            line["price_status"] = "supplied"
            line["lot_size"] = lot
            cash += raw_amount - value
            spent += value
        else:
            line["price_status"] = "missing_no_quantity"
            spent += raw_amount
        lines.append(line)
    assumed_cost = spent * (cost_bps + slippage_bps) / 10_000.0
    status = "funded_plan"
    if cash + TOL < assumed_cost:
        status = "budget_insufficient_for_assumed_costs"
    else:
        cash -= assumed_cost
    if spent + assumed_cost + cash > budget + TOL:
        status = "budget_identity_failed"
    return {
        "stage": "funded",
        "status": status,
        "currency": currency.upper(),
        "budget": budget,
        "planned_purchases": spent,
        "assumed_cost": assumed_cost,
        "cash_residual": cash,
        "cost_bps": cost_bps,
        "slippage_bps": slippage_bps,
        "cost_assumption": "cost and slippage are assumptions, not a broker quote",
        "lines": lines,
        "orders_created": False,
    }


def estimate_after_prices(
    snapshot: dict[str, Any],
    new_prices: dict[str, float],
) -> dict[str, Any]:
    """Оценить веса после цен. Не выдавать оценку за новый фактический снимок."""
    if snapshot.get("stage") != "actual":
        raise LifecycleError("estimate requires an actual snapshot (code=ESTIMATE_NOT_ACTUAL)")
    if snapshot.get("weight_basis") != "market_value":
        raise LifecycleError(
            "weight-only snapshot cannot be revalued (code=ESTIMATE_INSUFFICIENT)"
        )
    positions = []
    total = 0.0
    for pos in snapshot["positions"]:
        secid = pos["secid"]
        if secid == CASH:
            value = float(pos["market_value"])
            positions.append({**pos, "estimated_market_value": value, "price_status": "cash_unchanged"})
            total += value
            continue
        if "quantity" not in pos or secid not in new_prices:
            raise LifecycleError(
                f"{secid}: need quantity and a new price (code=ESTIMATE_INSUFFICIENT)"
            )
        value = float(pos["quantity"]) * float(new_prices[secid])
        positions.append({
            "secid": secid,
            "estimated_market_value": value,
            "price_status": "marked",
        })
        total += value
    for pos in positions:
        pos["estimated_weight"] = pos["estimated_market_value"] / total
    return {
        "stage": "actual",
        "weight_status": "estimated",
        "status": "estimated_from_prices",
        "currency": snapshot["currency"],
        "positions": positions,
        "accounted_exactly": ("prior quantity", "new price in the same currency", "unchanged cash"),
        "accounted_approximately": (),
        "not_accounted": NOT_ACCOUNTED,
    }


def load_price_panel(path: Path) -> pd.DataFrame:
    return FixtureDataSource(path).load_prices()
