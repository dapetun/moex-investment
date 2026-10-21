"""Стадии proposed, funded и actual не смешиваются."""

from __future__ import annotations

import json

import pytest

from moex_portfolio.cli import main
from moex_portfolio.portfolio_lifecycle import (
    LifecycleError,
    estimate_after_prices,
    fund_plan,
    parse_snapshot_csv,
    propose_allocation,
)
from moex_portfolio.walk_forward import synthetic_price_panel


def _prices():
    frame = synthetic_price_panel("stable", n_assets=4, n_days=40, seed=3)
    frame.columns = ["AAA", "BBB", "CCC", "DDD"]
    frame.index.name = "TRADEDATE"
    return frame


def _write(path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def test_proposal_has_no_holdings_and_compares_three_strategies():
    result = propose_allocation(_prices(), ["AAA", "BBB", "CCC", "DDD"], max_weight=0.5)
    assert result["stage"] == "proposed"
    assert result["status"] == "project_not_holdings"
    assert result["execution_recommendation"] is False
    assert result["preferred_strategy"] is None
    assert set(result["proposals"]) == {"max_sharpe", "min_variance", "equal_weight"}
    for proposal in result["proposals"].values():
        assert abs(sum(proposal["weights"].values()) - 1.0) < 1e-6
        assert "quantity" not in proposal


def test_infeasible_cap_is_not_relaxed():
    with pytest.raises(LifecycleError, match="INFEASIBLE_WEIGHT_CONSTRAINTS"):
        propose_allocation(_prices(), ["AAA", "BBB", "CCC", "DDD"], max_weight=0.2)


def test_cash_sleeves():
    full = propose_allocation(_prices(), ["AAA", "BBB"], cash_weight=1.0, max_weight=1.0)
    assert full["proposals"]["equal_weight"]["weights"] == {"CASH": 1.0}
    five = propose_allocation(_prices(), ["AAA", "BBB", "CCC", "DDD"], cash_weight=0.05, max_weight=0.5)
    weights = five["proposals"]["equal_weight"]["weights"]
    assert weights["CASH"] == pytest.approx(0.05)
    assert abs(sum(weights.values()) - 1.0) < 1e-6
    zero = propose_allocation(_prices(), ["AAA", "BBB", "CCC", "DDD"], cash_weight=0.0, max_weight=0.5)
    assert "CASH" not in zero["proposals"]["equal_weight"]["weights"]


def test_funded_amounts_lots_and_missing_prices():
    weights = {"AAA": 0.4, "BBB": 0.35, "CCC": 0.25}
    plan = fund_plan(weights, budget=500_000, currency="RUB")
    assert plan["stage"] == "funded"
    amounts = {line["secid"]: line["planned_value"] for line in plan["lines"]}
    assert amounts == {"AAA": 200_000, "BBB": 175_000, "CCC": 125_000}
    assert all(line["planned_quantity"] is None for line in plan["lines"])
    lots = fund_plan(
        weights,
        budget=500_000,
        currency="RUB",
        prices={"AAA": 100, "BBB": 50, "CCC": 80},
        lot_sizes={"AAA": 10, "BBB": 10, "CCC": 10},
        cost_bps=0,
    )
    aaa = next(line for line in lots["lines"] if line["secid"] == "AAA")
    assert aaa["planned_quantity"] == 2000
    assert lots["planned_purchases"] + lots["cash_residual"] == pytest.approx(500_000)
    assert lots["orders_created"] is False
    with pytest.raises(LifecycleError, match="FUND_BUDGET_REQUIRED"):
        fund_plan(weights, budget=0, currency="RUB")


def test_snapshot_formats_and_conflicts(tmp_path):
    weight = tmp_path / "w.csv"
    _write(
        weight,
        "as_of,secid,weight,currency,data_source\n"
        "2026-01-01,AAA,0.4,RUB,broker_export\n"
        "2026-01-01,BBB,0.6,RUB,broker_export\n",
    )
    parsed = parse_snapshot_csv(weight)
    assert parsed["stage"] == "actual"
    assert parsed["weight_basis"] == "weight"
    assert "market_value" not in parsed["positions"][0]
    assert str(weight) not in json.dumps(parsed)

    values = tmp_path / "v.csv"
    _write(
        values,
        "as_of,secid,market_value,currency,data_source\n"
        "2026-01-01,AAA,200,RUB,broker_export\n"
        "2026-01-01,BBB,300,RUB,broker_export\n",
    )
    valued = parse_snapshot_csv(values)
    assert valued["positions"][0]["weight"] == pytest.approx(0.4)

    qty = tmp_path / "q.csv"
    _write(
        qty,
        "as_of,secid,quantity,price,currency,data_source\n"
        "2026-01-01,AAA,10,20,RUB,broker_export\n"
        "2026-01-01,BBB,5,60,RUB,broker_export\n",
    )
    counted = parse_snapshot_csv(qty)
    assert counted["positions"][0]["market_value"] == 200

    bad = tmp_path / "bad.csv"
    _write(
        bad,
        "as_of,secid,weight,market_value,currency,data_source\n"
        "2026-01-01,AAA,0.9,100,RUB,broker_export\n"
        "2026-01-01,BBB,0.1,100,RUB,broker_export\n",
    )
    with pytest.raises(LifecycleError, match="SNAPSHOT_WEIGHT_VALUE_MISMATCH"):
        parse_snapshot_csv(bad)

    mixed = tmp_path / "fx.csv"
    _write(
        mixed,
        "as_of,secid,weight,currency,data_source\n"
        "2026-01-01,AAA,0.5,RUB,broker_export\n"
        "2026-01-01,BBB,0.5,USD,broker_export\n",
    )
    with pytest.raises(LifecycleError, match="SNAPSHOT_MIXED_CURRENCY"):
        parse_snapshot_csv(mixed)

    accounts = tmp_path / "acc.csv"
    _write(
        accounts,
        "as_of,secid,market_value,currency,data_source,account\n"
        "2026-01-01,AAA,100,RUB,broker_export,a\n"
        "2026-01-01,AAA,100,RUB,broker_export,b\n"
        "2026-01-01,BBB,200,RUB,broker_export,a\n",
    )
    combined = parse_snapshot_csv(accounts)
    aaa = next(pos for pos in combined["positions"] if pos["secid"] == "AAA")
    assert aaa["market_value"] == 200
    assert aaa["weight"] == pytest.approx(0.5)


def test_estimate_marks_missing_corporate_actions():
    actual = {
        "stage": "actual",
        "weight_basis": "market_value",
        "currency": "RUB",
        "positions": [
            {"secid": "AAA", "quantity": 10, "market_value": 1000, "weight": 0.5},
            {"secid": "CASH", "market_value": 1000, "weight": 0.5},
        ],
    }
    estimated = estimate_after_prices(actual, {"AAA": 150})
    assert estimated["weight_status"] == "estimated"
    assert "dividends" in estimated["not_accounted"]
    aaa = next(pos for pos in estimated["positions"] if pos["secid"] == "AAA")
    assert aaa["estimated_weight"] == pytest.approx(0.6)


def test_propose_command_does_not_write_target(tmp_path, monkeypatch):
    prices = tmp_path / "prices.csv"
    frame = _prices()
    frame.to_csv(prices, sep=";")
    target = tmp_path / "last_target.json"
    target.write_text('{"untouched": true}', encoding="utf-8")
    monkeypatch.setattr("moex_portfolio.cli.LAST_TARGET_PATH", target)
    code = main([
        "propose-portfolio",
        "--prices",
        str(prices),
        "--tickers",
        "AAA,BBB,CCC,DDD",
        "--max-weight",
        "0.5",
    ])
    assert code == 0
    assert json.loads(target.read_text(encoding="utf-8")) == {"untouched": True}
