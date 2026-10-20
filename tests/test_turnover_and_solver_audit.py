"""Проверка оборота, лимитов solver и регрессии против родителя d57de52."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy.optimize import minimize

from moex_portfolio.cli import main
from moex_portfolio.compare import assess_turnover, compare_weights
from moex_portfolio.metrics import portfolio_return, portfolio_volatility, sharpe_ratio
from moex_portfolio.optimizer import (
    InfeasibleWeightConstraints,
    equal_weight_portfolio,
    max_sharpe_portfolio,
    min_variance_portfolio,
    policy_violation,
)
from moex_portfolio.reference_portfolios import reference_returns
from moex_portfolio.risk_models import covariance_matrix
from moex_portfolio.strategies import compare_three_objectives

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "data" / "fixtures" / "synthetic_prices.csv"


def _legacy_max_sharpe(mean, cov, *, max_weight: float, risk_free_rate: float):
    """Solver до d57de52 на выполнимом капе: границы не ослабляются, top-5 нет.

    Ветка 1/n в этом вызове не срабатывает, потому что n * max_weight >= 1.
    """
    n = len(mean)
    assert n * max_weight >= 1.0

    def neg_sharpe(w):
        return -sharpe_ratio(w, mean, cov, risk_free_rate)

    result = minimize(
        neg_sharpe,
        np.full(n, 1.0 / n),
        method="SLSQP",
        bounds=[(0.0, max_weight)] * n,
        constraints=[{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}],
    )
    weights = np.asarray(result.x, dtype=float)
    return {
        "weights": weights,
        "return": portfolio_return(weights, mean),
        "volatility": portfolio_volatility(weights, cov),
        "sharpe": sharpe_ratio(weights, mean, cov, risk_free_rate),
        "success": bool(result.success),
    }


def _panel(n: int, rows: int = 80, seed: int = 4) -> tuple[pd.Series, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    names = [f"T{i}" for i in range(n)]
    noise = rng.normal(0.0002, 0.01, size=(rows, n))
    returns = pd.DataFrame(noise, columns=names)
    cov = pd.DataFrame(np.cov(noise, rowvar=False) + np.eye(n) * 1e-4, index=names, columns=names)
    return returns.mean(), cov


def test_one_way_matches_half_l1_only_when_books_sum_to_one():
    full = assess_turnover({"AAA": 0.6, "BBB": 0.4}, {"AAA": 0.5, "BBB": 0.5})
    assert full["one_way_identified"] is True
    assert full["one_way_turnover"] == pytest.approx(0.1)
    assert full["buys"] == pytest.approx(full["sells"])

    renamed = assess_turnover({"AAA": 0.7, "BBB": 0.3}, {"AAA": 0.7, "CCC": 0.3})
    assert renamed["one_way_turnover"] == pytest.approx(0.3)

    cash = assess_turnover(
        {"AAA": 0.5, "BBB": 0.3, "CASH": 0.2},
        {"AAA": 0.4, "BBB": 0.6, "CASH": 0.0},
    )
    assert cash["one_way_turnover"] == pytest.approx(0.3)
    assert cash["buys"] == pytest.approx(0.3)

    unknown = assess_turnover({"AAA": 0.8}, {"AAA": 1.0})
    assert unknown["status"] == "cash_unknown"
    assert unknown["one_way_turnover"] is None
    assert unknown["gross_abs_weight_change"] is None

    initial = assess_turnover({}, {"AAA": 0.4, "BBB": 0.6})
    assert initial["status"] == "initial_allocation"
    assert initial["one_way_turnover"] is None

    priced = assess_turnover(
        {"AAA": 1.0},
        {"AAA": 0.5, "BBB": 0.5},
        cost_bps=10,
        portfolio_value=1000,
    )
    assert priced["cash_cost"] == pytest.approx(1000 * 0.5 * 10 / 10_000)


def test_compare_does_not_label_incomplete_weights_as_turnover():
    out = compare_weights({"AAA": 0.8}, {"AAA": 1.0}, min_drift=0.05)
    assert out["one_way_turnover"] is None
    assert out["turnover_status"] == "cash_unknown"
    assert "needs_rebalance" in out


@pytest.mark.parametrize("n,cap", [(2, 0.5), (4, 0.25), (5, 0.2), (10, 0.1)])
def test_boundary_n_times_max_weight_equals_one(n, cap):
    mean, cov = _panel(n)
    for fn in (max_sharpe_portfolio, min_variance_portfolio, equal_weight_portfolio):
        result = fn(mean, cov, max_weight=cap, risk_free_rate=0.0)
        assert result["success"] is True
        assert policy_violation(
            result["weights"], min_weight=0.0, max_weight=cap, max_top5=None
        ) is None


def test_infeasible_caps_reject_all_three_objectives():
    mean, cov = _panel(4)
    with pytest.raises(InfeasibleWeightConstraints):
        max_sharpe_portfolio(mean, cov, max_weight=0.2)
    with pytest.raises(InfeasibleWeightConstraints):
        min_variance_portfolio(mean, cov, max_weight=0.2)
    with pytest.raises(InfeasibleWeightConstraints):
        equal_weight_portfolio(mean, cov, min_weight=0.3, max_weight=0.5)
    with pytest.raises(InfeasibleWeightConstraints):
        equal_weight_portfolio(mean, cov, max_weight=0.5, max_top5=0.9)


def test_top5_floor_and_active_cap():
    mean, cov = _panel(10, seed=9)
    with pytest.raises(InfeasibleWeightConstraints):
        max_sharpe_portfolio(mean, cov, max_weight=0.2, max_top5=0.5 - 1e-4)
    bound = max_sharpe_portfolio(mean, cov, max_weight=0.2, max_top5=0.5)
    assert bound["success"] is True
    assert bound["concentration"]["top5_sum"] <= 0.5 + 1e-6
    active = max_sharpe_portfolio(mean, cov, max_weight=0.4, max_top5=0.55)
    assert active["success"] is True
    assert active["concentration"]["top5_sum"] <= 0.55 + 1e-6


def test_failed_optimize_keeps_previous_target(tmp_path, monkeypatch):
    monkeypatch.setattr("moex_portfolio.portfolio_state.HOLDINGS_DIR", tmp_path / "portfolio")
    monkeypatch.setattr("moex_portfolio.run_journal.RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr("moex_portfolio.locks.LOCKS_DIR", tmp_path / "locks")
    monkeypatch.setattr("moex_portfolio.reporting.REPORTS_DIR", tmp_path / "reports")
    target = tmp_path / "outbox" / "last_target.json"
    monkeypatch.setattr("moex_portfolio.cli.LAST_TARGET_PATH", target)
    monkeypatch.setenv("MOEX_DATA_SOURCE", "fixture")
    monkeypatch.setenv("MOEX_ISS_ENABLED", "false")
    monkeypatch.setenv("MOEX_FIXTURE_PATH", str(FIXTURE))
    target.parent.mkdir(parents=True)
    previous = {"weights": {"AAA": 0.5, "BBB": 0.5}, "success": True}
    target.write_text(json.dumps(previous), encoding="utf-8")
    code = main(["optimize", "--allow-optimize", "--max-weight", "0.2"])
    assert code == 2
    assert json.loads(target.read_text(encoding="utf-8")) == previous


def test_new_max_sharpe_matches_parent_when_cap_is_feasible():
    mean, cov = _panel(6, seed=11)
    legacy = _legacy_max_sharpe(mean, cov, max_weight=0.5, risk_free_rate=0.0)
    current = max_sharpe_portfolio(mean, cov, max_weight=0.5, risk_free_rate=0.0)
    assert current["success"] is True
    assert legacy["success"] is True
    assert np.allclose(current["weights"], legacy["weights"], atol=1e-6)
    assert current["sharpe"] == pytest.approx(legacy["sharpe"], abs=1e-6)
    assert current["volatility"] == pytest.approx(legacy["volatility"], abs=1e-6)
    assert current["return"] == pytest.approx(legacy["return"], abs=1e-6)


def test_reported_sharpe_uses_annual_rf():
    mean, cov = _panel(4)
    result = max_sharpe_portfolio(mean, cov, max_weight=0.5, risk_free_rate=0.04)
    expected = sharpe_ratio(np.asarray(result["weights"]), mean, cov, 0.04)
    assert result["sharpe"] == pytest.approx(expected)
    manual = (result["return"] - 0.04) / result["volatility"]
    assert result["sharpe"] == pytest.approx(manual)


def test_holdout_does_not_read_future_prices():
    idx = pd.bdate_range("2024-01-01", periods=40)
    rng = np.random.default_rng(1)
    prices = pd.DataFrame(
        100 * np.exp(np.cumsum(rng.normal(0.0004, 0.01, size=(40, 4)), axis=0)),
        index=idx,
        columns=["A", "B", "C", "D"],
    )
    base = compare_three_objectives(prices, max_weight=0.5)
    changed = prices.copy()
    changed.iloc[20:] = changed.iloc[20:] * 3
    other = compare_three_objectives(changed, max_weight=0.5)
    assert base["in_sample"]["max_sharpe"]["weights"] == pytest.approx(
        other["in_sample"]["max_sharpe"]["weights"]
    )
    assert base["in_sample"]["max_sharpe"]["train_end"] == other["in_sample"]["max_sharpe"]["train_end"]


def test_min_variance_is_not_riskier_than_max_sharpe_and_cash_is_flat():
    mean, cov = _panel(6, seed=3)
    sharpe = max_sharpe_portfolio(mean, cov, max_weight=0.4, risk_free_rate=0.0)
    var = min_variance_portfolio(mean, cov, max_weight=0.4, risk_free_rate=0.0)
    equal = equal_weight_portfolio(mean, cov, max_weight=0.4, risk_free_rate=0.0)
    assert var["volatility"] <= sharpe["volatility"] + 1e-8
    assert np.allclose(equal["weights"], np.full(6, 1 / 6))
    idx = pd.bdate_range("2024-01-01", periods=11)
    prices = pd.DataFrame({"AAA": np.linspace(10, 11, 11), "BBB": np.linspace(20, 22, 11)}, index=idx)
    ref = reference_returns(prices, start_weights={"AAA": 0.5, "BBB": 0.5}, cash_annual=0.252)
    assert ref["cash"]["annual_rate"] == 0.252
    diag: dict = {}
    cov_est = covariance_matrix(pd.DataFrame(np.random.default_rng(0).normal(size=(40, 8))), method="ledoit_wolf", diagnostics=diag)
    assert cov_est.shape == (8, 8)
    assert np.allclose(cov_est.values, cov_est.values.T)
    assert float(np.linalg.eigvalsh(cov_est.values).min()) >= -1e-8
    assert 0.0 <= diag["shrinkage"] <= 1.0
