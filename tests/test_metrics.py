"""Тесты модуля metrics."""

import numpy as np
import pandas as pd

from moex_portfolio.metrics import (
    max_drawdown,
    portfolio_metrics,
    portfolio_return,
    portfolio_volatility,
    sharpe_ratio,
    sortino_ratio,
)


def test_portfolio_return():
    weights = np.array([0.5, 0.5])
    mean_returns = pd.Series([0.0004, 0.0002])
    ret = portfolio_return(weights, mean_returns)
    expected = (0.5 * 0.0004 + 0.5 * 0.0002) * 252
    assert abs(ret - expected) < 1e-10


def test_portfolio_volatility():
    weights = np.array([1.0, 0.0])
    cov = pd.DataFrame([[0.04, 0.01], [0.01, 0.09]])
    vol = portfolio_volatility(weights, cov)
    expected = np.sqrt(0.04) * np.sqrt(252)
    assert abs(vol - expected) < 1e-10


def test_sharpe_ratio():
    weights = np.array([0.5, 0.5])
    mean_returns = pd.Series([0.0004, 0.0002])
    cov = pd.DataFrame([[0.04, 0.01], [0.01, 0.09]])
    sr = sharpe_ratio(weights, mean_returns, cov, risk_free_rate=0.0)
    assert sr > 0


def test_sortino_ratio():
    weights = np.array([0.5, 0.5])
    mean_returns = pd.Series([0.0004, 0.0002])
    np.random.seed(42)
    returns = pd.DataFrame(
        np.random.randn(252, 2) * 0.02 + [0.0004, 0.0002],
        columns=["A", "B"],
    )
    sr = sortino_ratio(weights, mean_returns, returns, risk_free_rate=0.0)
    assert isinstance(sr, float)


def test_max_drawdown():
    equity = pd.Series([0.01, 0.02, -0.03, 0.01, -0.01])
    dd = max_drawdown(equity)
    assert dd < 0
    assert dd >= -1.0


def test_portfolio_metrics():
    weights = np.array([0.5, 0.5])
    mean_returns = pd.Series([0.0004, 0.0002])
    cov = pd.DataFrame([[0.04, 0.01], [0.01, 0.09]])
    returns = pd.DataFrame(
        np.random.randn(252, 2) * 0.02 + [0.0004, 0.0002],
        columns=["A", "B"],
    )
    result = portfolio_metrics(weights, mean_returns, cov, returns)
    assert "return" in result
    assert "volatility" in result
    assert "sharpe" in result
    assert "sortino" in result
    assert "max_drawdown" in result
    assert result["volatility"] > 0
