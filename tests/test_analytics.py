"""Тесты для модуля analytics."""

import numpy as np
import pandas as pd
import pytest

from moex_portfolio.analytics import (
    cvar_historical,
    equity_curve,
    monte_carlo_simulation,
    rolling_correlation,
    var_historical,
)


@pytest.fixture
def sample_returns():
    np.random.seed(42)
    n = 200
    dates = pd.bdate_range("2024-01-01", periods=n)
    return pd.DataFrame(
        {
            "A": np.random.normal(0.001, 0.02, n),
            "B": np.random.normal(0.0005, 0.015, n),
            "C": np.random.normal(-0.001, 0.025, n),
        },
        index=dates,
    )


@pytest.fixture
def weights():
    return np.array([0.4, 0.35, 0.25])


def test_equity_curve(sample_returns, weights):
    eq = equity_curve(sample_returns, weights)
    assert len(eq) == len(sample_returns)
    # First value = 1 + first_day_portfolio_return
    first_day_ret = np.dot(sample_returns.iloc[0].values, weights)
    assert eq.iloc[0] == pytest.approx(1.0 + first_day_ret)
    assert eq.name == "equity_curve"


def test_equity_curve_grows(sample_returns, weights):
    eq = equity_curve(sample_returns, weights)
    # Все значения положительные
    assert (eq > 0).all()


def test_monte_carlo_simulation(sample_returns, weights):
    mean_ret = sample_returns.mean()
    cov = sample_returns.cov()
    mc = monte_carlo_simulation(
        mean_ret, cov, weights, n_simulations=1000, n_days=252, seed=42
    )
    assert len(mc) == 1000
    assert "annual_return" in mc.columns
    assert "annual_volatility" in mc.columns
    assert "max_drawdown" in mc.columns
    assert "sharpe" in mc.columns


def test_monte_carlo_seed_reproducible(sample_returns, weights):
    mean_ret = sample_returns.mean()
    cov = sample_returns.cov()
    mc1 = monte_carlo_simulation(
        mean_ret, cov, weights, n_simulations=100, seed=123
    )
    mc2 = monte_carlo_simulation(
        mean_ret, cov, weights, n_simulations=100, seed=123
    )
    pd.testing.assert_frame_equal(mc1, mc2)


def test_rolling_correlation(sample_returns):
    rc = rolling_correlation(sample_returns, window=30)
    assert len(rc) == 3  # C(3,2) = 3 пары
    for pair_name, series in rc.items():
        assert "/" in pair_name
        assert len(series) > 0


def test_var_historical(sample_returns, weights):
    var = var_historical(sample_returns, weights, confidence=0.95)
    assert var < 0  # VaR — потери (отрицательное число)


def test_cvar_historical(sample_returns, weights):
    cvar = cvar_historical(sample_returns, weights, confidence=0.95)
    var = var_historical(sample_returns, weights, confidence=0.95)
    assert cvar <= var  # CVaR <= VaR (средние потери за порогом)


def test_var_different_confidence(sample_returns, weights):
    var_95 = var_historical(sample_returns, weights, confidence=0.95)
    var_99 = var_historical(sample_returns, weights, confidence=0.99)
    # 99% VaR — более экстремальные потери
    assert var_99 <= var_95
