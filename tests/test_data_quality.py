"""Тесты проверки полноты и свежести ценовой панели."""

from datetime import date
from pathlib import Path

import pandas as pd

from moex_portfolio.data_quality import ValidationStatus, validate_price_panel
from moex_portfolio.data_sources import FixtureDataSource

FIXTURE = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "synthetic_prices.csv"


def test_validate_ok_when_recent():
    src = FixtureDataSource(FIXTURE)
    df = src.load_prices()
    # сдвигаем индекс так, будто последняя дата = сегодня
    last = pd.Timestamp(date.today())
    df = df.copy()
    df.index = pd.bdate_range(end=last, periods=len(df))
    report = validate_price_panel(df, as_of=date.today(), max_staleness_days=5)
    assert report["status"] == ValidationStatus.OK
    assert report["ok"] is True


def test_validate_stale():
    idx = pd.bdate_range("2020-01-02", periods=30)
    df = pd.DataFrame(
        {"AAA": range(len(idx)), "AAA_VALUE": [1e8] * len(idx)},
        index=idx,
    )
    df.index.name = "TRADEDATE"
    report = validate_price_panel(df, as_of=date.today(), max_staleness_days=5, min_rows=20)
    assert report["status"] == ValidationStatus.STALE
    assert report["ok"] is False


def test_validate_empty():
    df = pd.DataFrame()
    report = validate_price_panel(df, as_of=date.today())
    assert report["status"] == ValidationStatus.MISSING
