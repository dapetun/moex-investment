"""Тесты модуля filters."""

import numpy as np
import pandas as pd

from moex_portfolio.filters import (
    compute_returns,
    filter_by_turnover,
    prepare_returns,
    remove_anomalies,
    remove_zero_volatility,
    separate_prices_and_volumes,
)


def test_separate_prices_and_volumes():
    data = pd.DataFrame(
        {"A": [100, 110], "A_VALUE": [1000, 2000], "B": [200, 190], "B_VALUE": [3000, 4000]},
        index=pd.date_range("2024-01-01", periods=2),
    )
    prices, volumes = separate_prices_and_volumes(data)
    assert list(prices.columns) == ["A", "B"]
    assert list(volumes.columns) == ["A_VALUE", "B_VALUE"]


def test_compute_returns():
    prices = pd.DataFrame(
        {"A": [100.0, 110.0, 105.0], "B": [200.0, 190.0, 210.0]},
        index=pd.date_range("2024-01-01", periods=3),
    )
    returns = compute_returns(prices)
    assert returns.shape == (2, 2)
    assert abs(returns["A"].iloc[0] - 0.1) < 1e-10
    assert abs(returns["B"].iloc[0] - (-0.05)) < 1e-10


def test_remove_anomalies():
    returns = pd.DataFrame(
        {"A": [0.01, 0.9, 0.02, -0.01], "B": [0.02, 0.03, 0.01, 0.02]},
        index=pd.date_range("2024-01-01", periods=4),
    )
    cleaned = remove_anomalies(returns, max_change=0.8)
    assert len(cleaned) == 3
    assert 0.9 not in cleaned["A"].values


def test_remove_zero_volatility():
    returns = pd.DataFrame(
        {"A": [0.01, 0.02, 0.03], "B": [0.0, 0.0, 0.0]},
        index=pd.date_range("2024-01-01", periods=3),
    )
    cleaned = remove_zero_volatility(returns)
    assert list(cleaned.columns) == ["A"]


def test_filter_by_turnover():
    prices = pd.DataFrame(
        {"A": [100, 110], "B": [200, 210]},
        index=pd.date_range("2024-01-01", periods=2),
    )
    volumes = pd.DataFrame(
        {"A_VALUE": [60_000_000, 70_000_000], "B_VALUE": [10_000_000, 20_000_000]},
        index=pd.date_range("2024-01-01", periods=2),
    )
    result = filter_by_turnover(prices, volumes, min_turnover=50_000_000)
    assert result == ["A"]


def test_prepare_returns():
    data = pd.DataFrame(
        {
            "A": np.random.uniform(90, 110, 600),
            "A_VALUE": np.random.uniform(60_000_000, 80_000_000, 600),
            "B": np.random.uniform(90, 110, 600),
            "B_VALUE": np.random.uniform(60_000_000, 80_000_000, 600),
        },
        index=pd.date_range("2022-01-01", periods=600),
    )
    returns, tickers = prepare_returns(data, min_turnover=50_000_000)
    assert len(tickers) > 0
    assert returns.shape[0] > 0
