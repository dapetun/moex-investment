"""Тесты дивидендных стратегий."""

import numpy as np
import pandas as pd

from moex_portfolio.dividend_strategies import (
    compare_dividend_strategies,
    compute_dividend_yield,
    dividend_aristocrats,
    dogs_of_the_dow,
    high_dividend_yield,
)


def _make_returns(n_days=252, n_stocks=10):
    np.random.seed(42)
    cols = [f"S{i}" for i in range(n_stocks)]
    data = np.random.randn(n_days, n_stocks) * 0.02 + 0.0003
    return pd.DataFrame(data, columns=cols)


def test_compute_dividend_yield():
    divs = pd.Series({"A": 10, "B": 5, "C": 0})
    prices = pd.Series({"A": 100, "B": 200, "C": 50})
    dy = compute_dividend_yield(divs, prices)
    assert abs(dy["A"] - 0.10) < 0.001
    assert abs(dy["B"] - 0.025) < 0.001
    assert dy["C"] == 0.0


def test_dogs_of_the_dow():
    returns = _make_returns()
    dy = pd.Series({f"S{i}": 0.05 + i * 0.01 for i in range(10)})
    result = dogs_of_the_dow(returns, dy, n_stocks=5)
    assert len(result["selected_tickers"]) == 5
    assert len(result["weights"]) == 5
    assert abs(sum(result["weights"]) - 1.0) < 1e-10
    assert result["annual_volatility"] > 0


def test_dogs_of_the_dow_no_dividends():
    returns = _make_returns()
    dy = pd.Series({f"S{i}": 0.0 for i in range(10)})
    result = dogs_of_the_dow(returns, dy, n_stocks=5)
    assert len(result["selected_tickers"]) == 0


def test_dividend_aristocrats():
    returns = _make_returns()
    history = {
        "S0": [10, 11, 12, 13, 14, 15],
        "S1": [10, 9, 10, 11, 12, 13],
        "S2": [10, 10, 8, 9, 10, 10],
    }
    result = dividend_aristocrats(returns, history, min_years=3)
    assert "S0" in result["selected_tickers"]
    assert "S1" in result["selected_tickers"]
    assert "S2" not in result["selected_tickers"]


def test_high_dividend_yield():
    returns = _make_returns()
    dy = pd.Series({f"S{i}": 0.02 + i * 0.01 for i in range(10)})
    result = high_dividend_yield(returns, dy, percentile=75)
    assert len(result["selected_tickers"]) > 0
    assert len(result["selected_tickers"]) <= 10


def test_compare_dividend_strategies():
    returns = _make_returns()
    dy = pd.Series({f"S{i}": 0.02 + i * 0.01 for i in range(10)})
    comparison = compare_dividend_strategies(returns, dy)
    assert len(comparison) >= 2
    assert "Strategy" in comparison.columns
    assert "Sharpe" in comparison.columns
