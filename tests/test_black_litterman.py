"""Тесты Black-Litterman модели."""

import numpy as np
import pandas as pd
import pytest

from moex_portfolio.black_litterman import (
    black_litterman_returns,
    create_views_from_correlation,
    implied_returns,
    optimize_black_litterman,
)


@pytest.fixture
def sample_data():
    np.random.seed(42)
    n_days = 252
    tickers = ["A", "B", "C", "D", "E"]
    returns = pd.DataFrame(
        np.random.randn(n_days, 5) * 0.01 + 0.0003,
        columns=tickers,
    )
    cov = returns.cov()
    weights = np.array([0.2] * 5)
    return returns, cov, weights, tickers


def test_implied_returns(sample_data):
    _, cov, weights, _ = sample_data
    pi = implied_returns(cov, weights, risk_aversion=1.0)
    assert len(pi) == 5
    assert isinstance(pi, np.ndarray)


def test_implied_returns_equilibrium(sample_data):
    _, cov, weights, _ = sample_data
    pi = implied_returns(cov, weights, risk_aversion=0.0)
    np.testing.assert_allclose(pi, 0.0, atol=1e-10)


def test_black_litterman_returns(sample_data):
    _, cov, weights, tickers = sample_data
    n = len(tickers)

    # Simple view: A > B
    P = np.zeros((1, n))
    P[0, 0] = 1
    P[0, 1] = -1
    Q = np.array([0.001])

    bl_ret, bl_cov = black_litterman_returns(cov, weights, P, Q)

    assert len(bl_ret) == n
    assert bl_cov.shape == (n, n)
    assert isinstance(bl_cov, pd.DataFrame)


def test_black_litterman_no_views_equals_prior(sample_data):
    """Без views posterior = prior."""
    _, cov, weights, tickers = sample_data
    n = len(tickers)

    # No views
    P = np.zeros((0, n))
    Q = np.array([])

    bl_ret, _ = black_litterman_returns(cov, weights, P, Q, tau=0.01)
    pi = implied_returns(cov, weights)

    np.testing.assert_allclose(bl_ret, pi, atol=1e-6)


def test_optimize_black_litterman(sample_data):
    returns, _, _, tickers = sample_data
    n = len(tickers)

    P = np.zeros((1, n))
    P[0, 0] = 1
    P[0, 1] = -1
    Q = np.array([0.001])

    result = optimize_black_litterman(returns, P, Q)

    assert "weights" in result
    assert "return" in result
    assert "volatility" in result
    assert "sharpe" in result
    assert "bl_returns" in result
    assert "bl_cov" in result
    np.testing.assert_almost_equal(sum(result["weights"]), 1.0, decimal=5)


def test_create_views_from_correlation(sample_data):
    returns, _, _, _ = sample_data
    corr = returns.corr()
    P, Q = create_views_from_correlation(returns, corr, top_n=3)

    assert P.shape == (3, 5)
    assert len(Q) == 3
    # Each row should have exactly one +1 and one -1
    for row in P:
        assert sum(row) == 0
        assert sum(abs(row)) == 2
