"""Тесты risk budgeting модуля."""

import numpy as np
import pandas as pd

from moex_portfolio.risk_budget import (
    RiskBudgetResult,
    compute_risk_budget,
    equal_risk_contribution,
    risk_budget_summary,
)


def _make_cov_and_weights():
    np.random.seed(42)
    n = 5
    tickers = [f"S{i}" for i in range(n)]
    raw = np.random.randn(252, n) * 0.01
    cov = pd.DataFrame(np.cov(raw, rowvar=False) * 252, index=tickers, columns=tickers)
    weights = np.array([1.0 / n] * n)
    return weights, cov


def test_risk_budget_basic():
    w, cov = _make_cov_and_weights()
    result = compute_risk_budget(w, cov)
    assert isinstance(result, RiskBudgetResult)
    assert result.portfolio_volatility > 0
    assert len(result.tickers) == 5


def test_risk_budget_sum_pct():
    w, cov = _make_cov_and_weights()
    result = compute_risk_budget(w, cov)
    assert abs(result.pct_risk.sum() - 1.0) < 0.01


def test_risk_budget_summary():
    w, cov = _make_cov_and_weights()
    result = compute_risk_budget(w, cov)
    summary = risk_budget_summary(result)
    assert len(summary) == 5
    assert "Risk Contribution %" in summary.columns
    assert "Weight" in summary.columns


def test_equal_risk_contribution():
    np.random.seed(42)
    n = 5
    raw = np.random.randn(252, n) * 0.01
    cov = pd.DataFrame(np.cov(raw, rowvar=False) * 252)
    weights = equal_risk_contribution(cov)
    assert abs(weights.sum() - 1.0) < 0.01
    assert all(w >= 0 for w in weights)


def test_erc_risk_equalization():
    np.random.seed(42)
    n = 4
    raw = np.random.randn(252, n) * 0.01
    cov = pd.DataFrame(np.cov(raw, rowvar=False) * 252)
    weights = equal_risk_contribution(cov)
    result = compute_risk_budget(weights, cov)
    pct = result.pct_risk
    max_diff = pct.max() - pct.min()
    assert max_diff < 0.15


def test_numpy_input():
    w = np.array([0.3, 0.3, 0.4])
    cov = np.array([[0.04, 0.01, 0.0], [0.01, 0.09, 0.02], [0.0, 0.02, 0.16]])
    result = compute_risk_budget(w, cov)
    assert result.portfolio_volatility > 0
