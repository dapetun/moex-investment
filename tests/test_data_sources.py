"""Тесты подключаемых источников данных (без сети)."""

from pathlib import Path

import pytest

from moex_portfolio.data_sources import (
    DataSourceError,
    FixtureDataSource,
    IssDataSource,
    get_data_source,
)

FIXTURE = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "synthetic_prices.csv"


def test_fixture_loads_prices():
    src = FixtureDataSource(FIXTURE)
    df = src.load_prices()
    assert "AAA" in df.columns
    assert "AAA_VALUE" in df.columns
    assert len(df) >= 30


def test_fixture_filters_tickers():
    src = FixtureDataSource(FIXTURE)
    df = src.load_prices(tickers=["AAA", "BBB"])
    assert "AAA" in df.columns
    assert "CCC" not in df.columns
    assert "CCC_VALUE" not in df.columns


def test_iss_source_blocked_when_disabled(monkeypatch):
    monkeypatch.setenv("MOEX_ISS_ENABLED", "false")
    src = IssDataSource()
    with pytest.raises(DataSourceError, match="MOEX_ISS_ENABLED"):
        src.load_prices()


def test_get_data_source_fixture_by_default(monkeypatch):
    monkeypatch.delenv("MOEX_ISS_ENABLED", raising=False)
    monkeypatch.delenv("MOEX_DATA_SOURCE", raising=False)
    monkeypatch.setenv("MOEX_FIXTURE_PATH", str(FIXTURE))
    src = get_data_source()
    assert src.name == "fixture"
    df = src.load_prices()
    assert not df.empty
