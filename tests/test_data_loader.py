"""Тесты модуля data_loader (локальные, без API)."""

import numpy as np
import pandas as pd
import pytest

from moex_portfolio.data_loader import adjust_prices_for_dividends


def test_adjust_prices_no_dividends():
    """Без дивидендов цены не меняются."""
    prices = pd.DataFrame(
        {"A": [100.0, 110.0, 105.0], "B": [200.0, 210.0, 195.0]},
        index=pd.date_range("2024-01-01", periods=3),
    )
    # Патчим get_dividends чтобы он возвращал None (нет дивидендов)
    import moex_portfolio.data_loader as dl
    original = dl.get_dividends
    dl.get_dividends = lambda t: None
    try:
        result = adjust_prices_for_dividends(prices, tickers=["A", "B"])
        pd.testing.assert_frame_equal(result, prices)
    finally:
        dl.get_dividends = original


def test_adjust_prices_with_dividends():
    """Дивиденды корректируют цены до ex-dividend дат."""
    prices = pd.DataFrame(
        {"A": [100.0, 105.0, 110.0, 103.0, 108.0]},
        index=pd.date_range("2024-01-01", periods=5),
    )
    # Дивиденд 5 руб. с ex-date = 2024-01-04
    divs = pd.DataFrame({
        "registryclosedate": pd.to_datetime(["2024-01-04"]),
        "value": [5.0],
    })

    import moex_portfolio.data_loader as dl
    original = dl.get_dividends
    dl.get_dividends = lambda t: divs
    try:
        result = adjust_prices_for_dividends(
            prices, tickers=["A"], start_date="2024-01-01",
        )
        # Prices before ex-date should be adjusted up
        # Factor = (110 + 5) / 110 ≈ 1.04545
        assert result["A"].iloc[0] > 100.0
        # Prices on/after ex-date should remain the same
        assert result["A"].iloc[-1] == 108.0
    finally:
        dl.get_dividends = original


def test_adjust_prices_zero_dividend():
    """Нулевой дивиденд не влияет."""
    prices = pd.DataFrame(
        {"A": [100.0, 110.0, 105.0]},
        index=pd.date_range("2024-01-01", periods=3),
    )
    divs = pd.DataFrame({
        "registryclosedate": pd.to_datetime(["2024-01-02"]),
        "value": [0.0],
    })

    import moex_portfolio.data_loader as dl
    original = dl.get_dividends
    dl.get_dividends = lambda t: divs
    try:
        result = adjust_prices_for_dividends(
            prices, tickers=["A"], start_date="2024-01-01",
        )
        pd.testing.assert_frame_equal(result, prices)
    finally:
        dl.get_dividends = original
