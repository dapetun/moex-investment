"""Корректность лимитов, target_weight, оборот, rf и контрольные стратегии."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from moex_portfolio.compare import compare_weights
from moex_portfolio.measurement_log import (
    append_forecast,
    brier_score,
    register_forecast,
    resolve_forecast,
)
from moex_portfolio.optimizer import (
    InfeasibleWeightConstraints,
    assert_long_only_feasible,
    max_sharpe_portfolio,
)
from moex_portfolio.pipeline import run_optimize
from moex_portfolio.portfolio_adapter import PortfolioAdapterError, csv_row_to_position
from moex_portfolio.reference_portfolios import reference_returns
from moex_portfolio.strategies import compare_three_objectives


def _means_cov(n: int, seed: int = 1):
    rng = np.random.default_rng(seed)
    names = [f"T{i}" for i in range(n)]
    mean = pd.Series(rng.normal(0.0003, 0.0001, n), index=names)
    noise = rng.normal(size=(80, n))
    cov = pd.DataFrame(np.cov(noise, rowvar=False) + np.eye(n) * 0.01, index=names, columns=names)
    return mean, cov


@pytest.mark.parametrize("n", [2, 3, 5, 7, 10])
def test_infeasible_max_weight_is_explicit(n):
    with pytest.raises(InfeasibleWeightConstraints, match="INFEASIBLE_WEIGHT_CONSTRAINTS"):
        assert_long_only_feasible(n, 0.0, 0.15 if n * 0.15 < 1 else 1.0 / (n + 1))


@pytest.mark.parametrize("n", [2, 3, 5, 7, 10])
def test_feasible_cap_is_not_relaxed(n):
    cap = max(0.15, 1.0 / n)
    assert_long_only_feasible(n, 0.0, cap)
    mean, cov = _means_cov(n)
    result = max_sharpe_portfolio(mean, cov, max_weight=cap)
    assert result["success"] is True
    assert max(result["weights"]) <= cap + 1e-5


def test_boundary_n_times_cap_equals_one():
    assert_long_only_feasible(5, 0.0, 0.2)
    with pytest.raises(InfeasibleWeightConstraints):
        assert_long_only_feasible(5, 0.0, 0.2 - 1e-6)


def test_top5_infeasible_for_three_names():
    with pytest.raises(InfeasibleWeightConstraints, match="top-"):
        assert_long_only_feasible(3, 0.0, 0.5, max_top5=0.55)


def test_top5_binds_on_ten_names():
    mean, cov = _means_cov(10, seed=2)
    loose = max_sharpe_portfolio(mean, cov, max_weight=0.5)
    tight = max_sharpe_portfolio(mean, cov, max_weight=0.2, max_top5=0.55)
    assert tight["success"] is True
    assert tight["concentration"]["top5_sum"] <= 0.55 + 1e-4
    assert tight["concentration"]["max_weight_realized"] <= 0.2 + 1e-4
    assert loose["concentration"]["top5_sum"] >= tight["concentration"]["top5_sum"] - 1e-6


def test_target_weight_is_not_current_weight():
    with pytest.raises(PortfolioAdapterError, match="PORTFOLIO_ROW_INCOMPLETE"):
        csv_row_to_position({"ticker": "AAA", "target_weight": "0.2"})
    both = csv_row_to_position(
        {"ticker": "AAA", "weight": "0.4", "target_weight": "0.1", "quantity": "10"}
    )
    assert both["weight"] == 0.4
    assert both["target_weight"] == 0.1
    only_w = csv_row_to_position({"ticker": "BBB", "weight": "0.25"})
    assert "target_weight" not in only_w


def test_compare_turnover_fields_do_not_drop_old_keys():
    out = compare_weights({"AAA": 0.6, "BBB": 0.4}, {"AAA": 0.5, "BBB": 0.5}, min_drift=0.05)
    assert "needs_rebalance" in out
    assert out["gross_abs_weight_change"] == pytest.approx(0.2)
    assert out["one_way_turnover"] == pytest.approx(0.1)
    assert out["cash_cost"] is None
    empty = compare_weights({}, {"AAA": 1.0})
    assert empty["one_way_turnover"] is None
    assert empty["allocation_kind"] == "initial_allocation"


def test_rf_changes_sharpe_not_weights_identity():
    mean, cov = _means_cov(4)
    a = max_sharpe_portfolio(mean, cov, risk_free_rate=0.0, max_weight=0.5)
    b = max_sharpe_portfolio(mean, cov, risk_free_rate=0.1, max_weight=0.5)
    assert a["risk_free_rate_unit"] == "annual"
    assert a["sharpe"] != pytest.approx(b["sharpe"])


def test_three_objectives_and_holdout():
    idx = pd.bdate_range("2024-01-01", periods=80)
    rng = np.random.default_rng(0)
    prices = pd.DataFrame(
        100 * np.exp(np.cumsum(rng.normal(0.0004, 0.01, size=(80, 6)), axis=0)),
        index=idx,
        columns=[f"T{i}" for i in range(6)],
    )
    report = compare_three_objectives(prices, max_weight=0.4, max_top5=0.9)
    assert set(report["in_sample"]) == {"max_sharpe", "min_variance", "equal_weight"}
    assert report["holdout"]["label"] == "out_of_sample_frozen_weights"
    assert "winner_by_in_sample_sharpe_is_not_a_decision" in report["notes"]


def test_reference_portfolios_do_not_invent_index():
    idx = pd.bdate_range("2024-01-01", periods=10)
    prices = pd.DataFrame(
        {"AAA": np.linspace(100, 110, 10), "BBB": np.linspace(50, 55, 10)},
        index=idx,
    )
    out = reference_returns(prices, start_weights={"AAA": 0.5, "BBB": 0.5}, cash_annual=0.0)
    assert "buy_and_hold" in out
    assert "equal_weight" in out
    assert "cash" in out
    assert out["external_index"]["status"] == "not_provided"


def test_forecast_log_rejects_backdating_and_verbal_confidence(tmp_path):
    path = tmp_path / "forecasts.jsonl"
    with pytest.raises(ValueError, match="confidence"):
        append_forecast(
            path,
            {
                "forecast_id": "f-verb",
                "confidence": "high",
                "created_at": "2026-01-01T00:00:00Z",
                "subject": "AAA",
                "horizon": "30d",
            },
        )
    with pytest.raises(ValueError, match="outcome"):
        append_forecast(
            path,
            {
                "forecast_id": "f-both",
                "created_at": "2026-01-01T00:00:00Z",
                "resolved_at": "2026-02-01T00:00:00Z",
                "probability": 0.7,
                "outcome": 1,
                "subject": "AAA",
                "horizon": "30d",
            },
        )
    register_forecast(
        path,
        {
            "forecast_id": "f1",
            "created_at": "2026-01-01T00:00:00Z",
            "probability": 1.0,
            "subject": "AAA",
            "horizon": "30d",
        },
    )
    with pytest.raises(ValueError, match="duplicate"):
        register_forecast(
            path,
            {
                "forecast_id": "f1",
                "created_at": "2026-01-02T00:00:00Z",
                "probability": 0.2,
                "subject": "AAA",
                "horizon": "30d",
            },
        )
    with pytest.raises(ValueError, match="before created_at"):
        resolve_forecast(
            path,
            forecast_id="f1",
            resolved_at="2025-12-01T00:00:00Z",
            outcome=1,
        )
    resolve_forecast(path, forecast_id="f1", resolved_at="2026-02-01T00:00:00Z", outcome=1)
    with pytest.raises(ValueError, match="already resolved"):
        resolve_forecast(path, forecast_id="f1", resolved_at="2026-03-01T00:00:00Z", outcome=0)
    score = brier_score(path)
    assert score["n"] == 1
    assert score["brier"] == 0.0


def test_run_optimize_does_not_relax_cap():
    idx = pd.bdate_range("2024-01-01", periods=40)
    rng = np.random.default_rng(3)
    prices = pd.DataFrame(rng.normal(100, 1, size=(40, 3)), index=idx, columns=["A", "B", "C"])
    for col in prices.columns:
        prices[f"{col}_VALUE"] = 1e8
    result = run_optimize(prices, max_weight=0.2, min_turnover=0.0, cov_method="sample")
    assert result["success"] is False
    assert result["code"] == "INFEASIBLE_WEIGHT_CONSTRAINTS"
    assert result["weights"] == {}
