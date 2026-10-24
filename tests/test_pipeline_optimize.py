"""Тесты headless-оптимизации на синтетических данных (без ISS)."""

from pathlib import Path

import pytest

from moex_portfolio.data_sources import FixtureDataSource
from moex_portfolio.pipeline import run_optimize
from moex_portfolio.portfolio_state import HoldingsValidationError

FIXTURE = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "synthetic_prices.csv"


def test_optimize_on_fixture_returns_weights():
    src = FixtureDataSource(FIXTURE)
    prices = src.load_prices()
    result = run_optimize(prices, max_weight=0.5, mode="universe")
    assert "weights" in result
    assert result["success"] is True
    assert abs(sum(result["weights"].values()) - 1.0) < 1e-6
    assert set(result["tickers"]) <= {"AAA", "BBB", "CCC"}


def test_optimize_holdings_mode_empty_raises():
    src = FixtureDataSource(FIXTURE)
    prices = src.load_prices()
    with pytest.raises(HoldingsValidationError):
        run_optimize(
            prices,
            max_weight=0.5,
            mode="holdings",
            holdings={"as_of": None, "cash": 0.0, "positions": []},
        )
