"""Тесты HRP (Hierarchical Risk Parity)."""

import numpy as np
import pandas as pd
import pytest

from moex_portfolio.hrp import (
    _correlation_distance,
    _get_cluster_var,
    _quasi_diag,
    hierarchical_risk_parity,
    optimize_hrp,
)


@pytest.fixture
def sample_returns():
    np.random.seed(42)
    n_days = 252
    tickers = ["A", "B", "C", "D", "E", "F", "G", "H"]
    # Create correlated groups
    base = np.random.randn(n_days, 3)
    data = np.column_stack([
        base[:, 0] + np.random.randn(n_days) * 0.01,  # A, B
        base[:, 0] + np.random.randn(n_days) * 0.01,
        base[:, 1] + np.random.randn(n_days) * 0.01,  # C, D
        base[:, 1] + np.random.randn(n_days) * 0.01,
        base[:, 2] + np.random.randn(n_days) * 0.01,  # E, F
        base[:, 2] + np.random.randn(n_days) * 0.01,
        np.random.randn(n_days) * 0.01,                # G
        np.random.randn(n_days) * 0.01,                # H
    ])
    return pd.DataFrame(data * 0.01, columns=tickers)


def test_correlation_distance():
    corr = pd.DataFrame(
        np.array([[1.0, 0.5], [0.5, 1.0]]),
        index=["A", "B"],
        columns=["A", "B"],
    )
    dist = _correlation_distance(corr)
    assert dist.shape == (2, 2)
    assert dist.iloc[0, 0] == 0.0  # distance to self
    assert dist.iloc[0, 1] == pytest.approx(np.sqrt(0.5 * 0.5), abs=1e-10)


def test_quasi_diag():
    # Simple linkage: 4 items, 3 merges
    link = np.array([
        [0, 1, 0.5, 2],
        [2, 3, 0.3, 2],
        [4, 5, 0.2, 4],
    ])
    result = _quasi_diag(link)
    assert len(result) == 4
    assert set(result) == {0, 1, 2, 3}


def test_get_cluster_var():
    np.random.seed(42)
    data = np.random.randn(100, 3)
    cov = pd.DataFrame(np.cov(data.T), index=["A", "B", "C"], columns=["A", "B", "C"])
    var = _get_cluster_var(cov, [0, 1])
    assert var > 0
    assert isinstance(var, float)


def test_hrp_weights_sum_to_one(sample_returns):
    weights = hierarchical_risk_parity(sample_returns)
    assert len(weights) == 8
    np.testing.assert_almost_equal(weights.sum(), 1.0, decimal=5)


def test_hrp_weights_non_negative(sample_returns):
    weights = hierarchical_risk_parity(sample_returns)
    assert (weights >= 0).all()


def test_optimize_hrp(sample_returns):
    result = optimize_hrp(sample_returns)

    assert "weights" in result
    assert "return" in result
    assert "volatility" in result
    assert "sharpe" in result
    assert "weights_dict" in result
    np.testing.assert_almost_equal(sum(result["weights"]), 1.0, decimal=5)


def test_optimize_hrp_bounds(sample_returns):
    result = optimize_hrp(sample_returns, min_weight=0.05, max_weight=0.4)
    assert all(w >= 0.05 - 1e-10 for w in result["weights"])
    assert all(w <= 0.4 + 1e-10 for w in result["weights"])


def test_hrp_different_methods(sample_returns):
    w1 = hierarchical_risk_parity(sample_returns, method="single")
    w2 = hierarchical_risk_parity(sample_returns, method="complete")
    assert len(w1) == len(w2)
    np.testing.assert_almost_equal(w1.sum(), 1.0, decimal=5)
    np.testing.assert_almost_equal(w2.sum(), 1.0, decimal=5)
