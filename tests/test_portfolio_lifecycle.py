"""Стадии proposed, funded и actual не смешиваются."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from moex_portfolio.cli import main
from moex_portfolio.portfolio_lifecycle import (
    LifecycleError,
    estimate_after_prices,
    estimate_from_relative_returns,
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


def _weight_snapshot() -> dict:
    return {
        "stage": "actual",
        "as_of": "2026-01-01",
        "currency": "RUB",
        "weight_basis": "weight",
        "positions": [
            {"secid": "AAA", "weight": 0.5},
            {"secid": "BBB", "weight": 0.3},
            {"secid": "CASH", "weight": 0.2},
        ],
    }


def test_relative_revaluation_keeps_sum_and_cash_identity():
    snapshot = _weight_snapshot()
    same = estimate_from_relative_returns(
        snapshot,
        valuation_date="2026-02-01",
        total_returns={"AAA": 0.1, "BBB": 0.1, "CASH": 0.1},
    )
    assert same["estimated"] is True
    assert same["estimation_method"] == "relative_returns"
    assert abs(sum(pos["estimated_weight"] for pos in same["positions"]) - 1) < 1e-12
    for pos in same["positions"]:
        assert pos["estimated_weight"] == pytest.approx(pos["previous_weight"])
        assert "quantity" not in pos
        assert "market_value" not in pos
    grown = estimate_from_relative_returns(
        snapshot,
        valuation_date="2026-02-01",
        total_returns={"AAA": 1.0, "BBB": 0.0, "CASH": 0.0},
    )
    weights = {pos["secid"]: pos["estimated_weight"] for pos in grown["positions"]}
    assert weights["AAA"] > 0.5
    assert weights["CASH"] < 0.2
    assert weights["CASH"] == pytest.approx(0.2 / 1.5)
    cash_up = estimate_from_relative_returns(
        snapshot,
        valuation_date="2026-02-01",
        total_returns={"AAA": 0.0, "BBB": 0.0, "CASH": 1.0},
    )
    cash_weight = next(pos["estimated_weight"] for pos in cash_up["positions"] if pos["secid"] == "CASH")
    assert cash_weight == pytest.approx(0.4 / 1.2)
    assert cash_weight > 0.2
    with pytest.raises(LifecycleError, match="ESTIMATE_BAD_DATES"):
        estimate_from_relative_returns(
            snapshot,
            valuation_date="2025-12-01",
            total_returns={"AAA": 0.0, "BBB": 0.0, "CASH": 0.0},
        )
    with pytest.raises(LifecycleError, match="ESTIMATE_RETURN_MISSING"):
        estimate_from_relative_returns(
            snapshot,
            valuation_date="2026-02-01",
            total_returns={"AAA": 0.0, "BBB": 0.0},
        )
    broken = _weight_snapshot()
    broken["positions"][0]["weight"] = 0.6
    with pytest.raises(LifecycleError, match="ESTIMATE_WEIGHT_SUM"):
        estimate_from_relative_returns(
            broken,
            valuation_date="2026-02-01",
            total_returns={"AAA": 0.0, "BBB": 0.0, "CASH": 0.0},
        )
    mixed = _weight_snapshot()
    mixed["positions"][0]["currency"] = "USD"
    with pytest.raises(LifecycleError, match="ESTIMATE_FX"):
        estimate_from_relative_returns(
            mixed,
            valuation_date="2026-02-01",
            total_returns={"AAA": 0.0, "BBB": 0.0, "CASH": 0.0},
        )


def test_price_return_requires_explicit_warning():
    idx = pd.bdate_range("2026-01-01", periods=2)
    prices = pd.DataFrame({"AAA": [100.0, 110.0], "BBB": [50.0, 50.0]}, index=idx)
    snapshot = {
        "stage": "actual",
        "as_of": "2026-01-01",
        "currency": "RUB",
        "positions": [{"secid": "AAA", "weight": 0.5}, {"secid": "BBB", "weight": 0.5}],
    }
    with pytest.raises(LifecycleError, match="ESTIMATE_PRICE_RETURN_UNACKNOWLEDGED"):
        estimate_from_relative_returns(
            snapshot,
            valuation_date="2026-01-02",
            prices=prices,
            corporate_actions="none",
        )
    with pytest.raises(LifecycleError, match="ESTIMATE_CORPORATE_ACTIONS"):
        estimate_from_relative_returns(
            snapshot,
            valuation_date="2026-01-02",
            prices=prices,
            price_return_only=True,
        )
    estimated = estimate_from_relative_returns(
        snapshot,
        valuation_date="2026-01-02",
        prices=prices,
        price_return_only=True,
        corporate_actions="none",
    )
    aaa = next(pos for pos in estimated["positions"] if pos["secid"] == "AAA")
    assert aaa["estimated_weight"] == pytest.approx(0.55 / 1.05)
    assert "quantity" not in aaa and "market_value" not in aaa
    assert "dividends" in estimated["not_accounted"]
    assert any("price return only" in item for item in estimated["assumptions"])
    assert "share_count_changes" not in estimated["not_accounted"]


def test_gap_is_refused_cash_is_explicit_and_zero_gross_is_kept():
    snapshot = _weight_snapshot()
    wiped = estimate_from_relative_returns(
        snapshot,
        valuation_date="2026-02-01",
        total_returns={"AAA": -1.0, "BBB": 0.0, "CASH": 0.0},
    )
    weights = {pos["secid"]: pos["estimated_weight"] for pos in wiped["positions"]}
    assert weights["AAA"] == 0.0
    assert weights["BBB"] == pytest.approx(0.6)
    assert weights["CASH"] == pytest.approx(0.4)
    assert abs(sum(weights.values()) - 1) < 1e-12
    with pytest.raises(LifecycleError, match="ESTIMATE_BAD_RETURN"):
        estimate_from_relative_returns(
            snapshot,
            valuation_date="2026-02-01",
            total_returns={"AAA": -1.01, "BBB": 0.0, "CASH": 0.0},
        )
    gappy = pd.DataFrame(
        {"AAA": [100.0, float("nan"), 130.0], "BBB": [50.0, 50.0, 50.0]},
        index=pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-05"]),
    )
    book = {
        "stage": "actual",
        "as_of": "2026-01-01",
        "currency": "RUB",
        "positions": [{"secid": "AAA", "weight": 0.5}, {"secid": "BBB", "weight": 0.5}],
    }
    with pytest.raises(LifecycleError, match="ESTIMATE_BAD_DATES"):
        estimate_from_relative_returns(
            book,
            valuation_date="2026-01-05",
            prices=gappy,
            price_return_only=True,
            corporate_actions="none",
        )
    spanned = pd.DataFrame(
        {"AAA": [100.0, 110.0], "BBB": [40.0, 40.0]},
        index=pd.to_datetime(["2026-01-01", "2026-01-05"]),
    )
    estimated = estimate_from_relative_returns(
        book,
        valuation_date="2026-01-05",
        prices=spanned,
        price_return_only=True,
        corporate_actions="none",
    )
    aaa = next(pos for pos in estimated["positions"] if pos["secid"] == "AAA")
    assert aaa["gross_return"] == pytest.approx(1.1)
    priced = pd.DataFrame(
        {"AAA": [100.0, 110.0], "BBB": [40.0, 40.0]},
        index=pd.to_datetime(["2026-01-01", "2026-01-02"]),
    )
    with pytest.raises(LifecycleError, match="ESTIMATE_CASH_RETURN"):
        estimate_from_relative_returns(
            snapshot,
            valuation_date="2026-01-02",
            prices=priced,
            price_return_only=True,
            corporate_actions="none",
        )


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


def test_estimate_weights_command_does_not_write_target(tmp_path, monkeypatch, capsys):
    snapshot = tmp_path / "snapshot.json"
    returns = tmp_path / "returns.json"
    snapshot.write_text(json.dumps(_weight_snapshot()), encoding="utf-8")
    returns.write_text(json.dumps({"AAA": 0.0, "BBB": 0.0, "CASH": 0.0}), encoding="utf-8")
    target = tmp_path / "last_target.json"
    target.write_text('{"untouched": true}', encoding="utf-8")
    monkeypatch.setattr("moex_portfolio.cli.LAST_TARGET_PATH", target)
    code = main([
        "estimate-weights",
        "--snapshot-json",
        str(snapshot),
        "--valuation-date",
        "2026-02-01",
        "--returns-json",
        str(returns),
    ])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["estimated"] is True
    assert payload["estimation_method"] == "relative_returns"
    assert payload["as_of"] == "2026-02-01"
    assert abs(sum(pos["estimated_weight"] for pos in payload["positions"]) - 1) < 1e-12
    assert all("quantity" not in pos and "market_value" not in pos for pos in payload["positions"])
    assert json.loads(target.read_text(encoding="utf-8")) == {"untouched": True}
    code = main([
        "estimate-weights",
        "--snapshot-json",
        str(snapshot),
        "--valuation-date",
        "2025-12-01",
        "--returns-json",
        str(returns),
    ])
    assert code == 2
    err = json.loads(capsys.readouterr().err)
    assert err["estimated"] is False
    assert "ESTIMATE_BAD_DATES" in err["error"]
    assert json.loads(target.read_text(encoding="utf-8")) == {"untouched": True}
