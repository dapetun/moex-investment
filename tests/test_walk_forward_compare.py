"""Детерминированные проверки walk-forward без look-ahead и без ослабления лимитов."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from moex_portfolio.optimizer import InfeasibleWeightConstraints
from moex_portfolio.walk_forward import (
    monte_carlo_compare,
    synthetic_price_panel,
    walk_forward_compare,
)


def _report(**kwargs):
    prices = synthetic_price_panel("stable", n_assets=4, n_days=80, seed=1)
    params = dict(train_days=20, rebalance_every=5, max_weight=0.5, cost_bps=0.0)
    params.update(kwargs)
    return walk_forward_compare(prices, **params)


def test_insufficient_history_is_explicit():
    prices = synthetic_price_panel("stable", n_days=10, seed=1)
    report = walk_forward_compare(prices, train_days=40, rebalance_every=5)
    assert report["status"] == "insufficient_observations"
    assert report["strategies"] == {}


def test_no_lookahead_and_no_train_test_overlap():
    base = synthetic_price_panel("stable", n_days=80, seed=2)
    changed = base.copy()
    changed.iloc[25:] = changed.iloc[25:] * 1.5
    left = walk_forward_compare(base, train_days=20, rebalance_every=10, max_weight=0.5)
    right = walk_forward_compare(changed, train_days=20, rebalance_every=10, max_weight=0.5)
    left_step = left["strategies"]["max_sharpe"]["steps"][0]
    right_step = right["strategies"]["max_sharpe"]["steps"][0]
    assert left_step["train_end"] < left_step["oos_start"]
    assert left_step["estimation"] == "in_sample"
    assert left_step["performance"] == "out_of_sample"
    assert left["performance_sample"] == "out_of_sample"
    assert left_step["status"] == right_step["status"]
    assert left["strategies"]["max_sharpe"]["steps"][0]["oos_start"] == right["strategies"]["max_sharpe"]["steps"][0]["oos_start"]


def test_first_decision_ignores_future_prices():
    prices = synthetic_price_panel("regime", n_days=90, seed=3)
    train_days = 30
    original = walk_forward_compare(prices, train_days=train_days, rebalance_every=15, max_weight=0.5, cov_method="ledoit_wolf")
    mutated = prices.copy()
    mutated.iloc[train_days:] *= 2
    other = walk_forward_compare(mutated, train_days=train_days, rebalance_every=15, max_weight=0.5, cov_method="ledoit_wolf")
    assert original["strategies"]["max_sharpe"]["steps"][0]["covariance_observations"] == train_days - 1
    assert original["strategies"]["max_sharpe"]["steps"][0]["weights"] == other["strategies"]["max_sharpe"]["steps"][0]["weights"]


def test_equal_weight_rebalances_and_buy_hold_does_not():
    report = _report()
    ew = report["strategies"]["equal_weight"]
    bh = report["strategies"]["buy_and_hold"]
    assert ew["formations"] == 1
    assert ew["rebalances"] > 0
    assert bh["formations"] == 1
    assert bh["rebalances"] == 0
    assert ew["cumulative_net_return"] != bh["cumulative_net_return"]


def test_costs_zero_when_bps_zero_and_positive_when_charged_once():
    free = _report(cost_bps=0.0)
    paid = _report(cost_bps=10.0)
    assert free["strategies"]["max_sharpe"]["total_cash_cost"] == 0.0
    assert free["strategies"]["max_sharpe"]["one_way_turnover_sum"] > 0
    formation = paid["strategies"]["buy_and_hold"]["steps"][0]
    assert formation["one_way_turnover"] == 1.0
    assert formation["cash_cost"] == 1.0 * 10 / 10_000
    assert paid["strategies"]["buy_and_hold"]["total_cash_cost"] == formation["cash_cost"]
    assert paid["strategies"]["max_sharpe"]["final_value"] < free["strategies"]["max_sharpe"]["final_value"]
    assert abs(paid["strategies"]["max_sharpe"]["return_identity_gap"]) < 1e-8
    assert abs(free["strategies"]["buy_and_hold"]["return_identity_gap"]) < 1e-8


def test_infeasible_limits_are_not_relaxed_and_target_file_is_untouched(tmp_path, monkeypatch):
    target = tmp_path / "last_target.json"
    target.write_text(json.dumps({"weights": {"AAA": 1.0}, "success": True}), encoding="utf-8")
    monkeypatch.setattr("moex_portfolio.cli.LAST_TARGET_PATH", target)
    prices = synthetic_price_panel("stable", n_assets=4, n_days=60, seed=4)
    report = walk_forward_compare(prices, train_days=20, rebalance_every=5, max_weight=0.2)
    for name, row in report["strategies"].items():
        assert row["failed_attempt_share"] == 1.0
        assert row["formations"] == 0
        assert row["final_value"] == 1.0
        assert name in {"max_sharpe", "min_variance", "equal_weight", "buy_and_hold"}
    assert json.loads(target.read_text(encoding="utf-8"))["weights"]["AAA"] == 1.0


def test_close_fill_identity_and_single_initial_fee():
    idx = pd.bdate_range("2021-01-04", periods=8)
    prices = pd.DataFrame(
        {name: np.linspace(100, 107, 8) for name in ("A0", "A1", "A2", "A3")},
        index=idx,
    )
    report = walk_forward_compare(
        prices,
        train_days=4,
        rebalance_every=10,
        strategies=["buy_and_hold"],
        max_weight=0.5,
        cost_bps=100,
    )
    row = report["strategies"]["buy_and_hold"]
    assert report["execution_model"]["fill"] == "same close"
    assert report["execution_model"]["realistic_execution"] is False
    assert row["steps"][0]["train_end"] == row["steps"][0]["decision_date"]
    assert row["steps"][0]["oos_start"] > row["steps"][0]["train_end"]
    assert row["one_way_turnover_sum"] == 1.0
    assert row["total_cash_cost"] == 0.01
    assert abs(row["return_identity_gap"]) < 1e-9
    assert row["market_days"] == 4
    gross = prices.iloc[-1, 0] / prices.iloc[3, 0] - 1
    assert row["final_value"] == pytest.approx(0.99 * (1 + gross), rel=1e-9)


def test_mid_period_solver_failure_keeps_previous_weights(monkeypatch):
    import moex_portfolio.walk_forward as walk_forward

    calls = {"n": 0}
    original = walk_forward.max_sharpe_portfolio

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] > 1:
            raise InfeasibleWeightConstraints("INFEASIBLE_WEIGHT_CONSTRAINTS: forced")
        return original(*args, **kwargs)

    monkeypatch.setitem(walk_forward._SOLVERS, "max_sharpe", flaky)
    prices = synthetic_price_panel("stable", n_days=40, seed=7)
    report = walk_forward_compare(
        prices,
        train_days=15,
        rebalance_every=5,
        strategies=["max_sharpe"],
        max_weight=0.5,
    )
    row = report["strategies"]["max_sharpe"]
    assert row["formations"] == 1
    assert row["failure_counts"]["infeasible_constraints"] >= 1
    assert row["cash_day_share"] == 0.0
    assert row["steps"][1]["failure_class"] == "infeasible_constraints"
    assert row["steps"][1]["weights"] is None
    assert report["comparison_warning"] is None


def test_monte_carlo_uses_every_seed_on_one_path():
    summary = monte_carlo_compare(scenario="stable", n_runs=3, seed0=20, n_days=40, train_days=15, rebalance_every=5)
    assert summary["seeds"] == [20, 21, 22]
    assert summary["n_runs"] == 3
    assert "not independent years" in summary["warning"]
    eq = summary["strategies"]["equal_weight"]["share_of_runs_ahead_of_equal_weight"]
    assert eq is None


def test_missing_prices_are_not_bridged():
    prices = synthetic_price_panel("crash", n_days=70, seed=5)
    prices.iloc[10, 0] = np.nan
    report = walk_forward_compare(prices, train_days=20, rebalance_every=5, max_weight=0.5)
    assert report["rows_with_missing_prices"] == 1
    assert report["status"] == "ok"
    missing = report["strategies"]["equal_weight"]["failure_counts"]["missing_data"]
    assert missing >= 1
    assert abs(report["strategies"]["equal_weight"]["return_identity_gap"]) < 1e-9
