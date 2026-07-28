"""Тесты для модуля charts."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest

from moex_portfolio.charts import (
    plot_efficient_frontier_plotly,
    plot_equity_curve_plotly,
    plot_mc_percentiles_table,
    plot_monte_carlo_plotly,
    plot_weights_bar_plotly,
)


@pytest.fixture
def sample_ef():
    np.random.seed(42)
    n = 20
    return pd.DataFrame({
        "return": np.linspace(0.05, 0.40, n),
        "volatility": np.linspace(0.10, 0.30, n),
        "sharpe": np.linspace(0.5, 2.0, n),
    })


@pytest.fixture
def sample_opt_result():
    return {"return": 0.30, "volatility": 0.20, "sharpe": 1.5}


@pytest.fixture
def sample_min_var():
    return {"return": 0.15, "volatility": 0.12, "sharpe": 1.25}


@pytest.fixture
def sample_mc():
    np.random.seed(42)
    n = 1000
    return pd.DataFrame({
        "annual_return": np.random.normal(0.20, 0.10, n),
        "annual_volatility": np.random.normal(0.18, 0.05, n),
        "max_drawdown": np.random.normal(-0.15, 0.05, n),
        "sharpe": np.random.normal(1.2, 0.3, n),
    })


@pytest.fixture
def sample_equity():
    np.random.seed(42)
    n = 200
    dates = pd.bdate_range("2024-01-01", periods=n)
    cumulative = np.cumprod(1 + np.random.normal(0.001, 0.02, n))
    return pd.Series(cumulative, index=dates)


def test_efficient_frontier_plotly(sample_ef, sample_opt_result, sample_min_var):
    fig = plot_efficient_frontier_plotly(sample_ef, sample_opt_result, sample_min_var)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 3  # frontier + max_sharpe + min_var


def test_monte_carlo_plotly(sample_mc):
    fig = plot_monte_carlo_plotly(sample_mc)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 3  # 3 histograms


def test_equity_curve_plotly(sample_equity):
    fig = plot_equity_curve_plotly(sample_equity)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) >= 2  # line + max_dd marker


def test_weights_bar_plotly():
    clique = ["A", "B", "C"]
    weights = np.array([0.5, 0.3, 0.2])
    fig = plot_weights_bar_plotly(clique, weights)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 1  # one bar trace


def test_mc_percentiles_table(sample_mc):
    df = plot_mc_percentiles_table(sample_mc)
    assert len(df) == 7  # 7 percentiles
    assert "Annual Return" in df.columns
    assert "Max Drawdown" in df.columns
