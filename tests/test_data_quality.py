"""Тесты проверки полноты и свежести ценовой панели (детерминированные даты)."""

from datetime import date

import pandas as pd

from moex_portfolio.data_quality import (
    ValidationStatus,
    validate_for_optimize,
    validate_price_panel,
)

AS_OF = date(2026, 6, 15)


def test_validate_ok_when_recent_fixed_as_of():
    idx = pd.bdate_range(end=pd.Timestamp(AS_OF), periods=40)
    n = len(idx)
    df = pd.DataFrame(
        {"AAA": [10.0 + i for i in range(n)], "AAA_VALUE": [1e8] * n},
        index=idx,
    )
    report = validate_price_panel(
        df, as_of=AS_OF, max_staleness_days=5, min_rows=20, check_staleness=True
    )
    assert report["status"] == ValidationStatus.OK
    assert report["ok"] is True


def test_validate_stale_fixed_as_of():
    idx = pd.bdate_range("2020-01-02", periods=30)
    n = len(idx)
    df = pd.DataFrame(
        {"AAA": [10.0 + i for i in range(n)], "AAA_VALUE": [1e8] * n},
        index=idx,
    )
    df.index.name = "TRADEDATE"
    report = validate_price_panel(
        df, as_of=AS_OF, max_staleness_days=5, min_rows=20, check_staleness=True
    )
    assert report["status"] == ValidationStatus.STALE
    assert report["ok"] is False


def test_validate_empty():
    df = pd.DataFrame()
    report = validate_price_panel(df, as_of=AS_OF)
    assert report["status"] == ValidationStatus.MISSING


def test_fixture_mode_ignores_staleness():
    idx = pd.bdate_range("2020-01-02", periods=30)
    n = len(idx)
    df = pd.DataFrame(
        {
            "AAA": [10.0 + i for i in range(n)],
            "AAA_VALUE": [1e8] * n,
            "BBB": [20.0 + i for i in range(n)],
            "BBB_VALUE": [1e8] * n,
        },
        index=idx,
    )
    report = validate_for_optimize(df, source_name="fixture", as_of=AS_OF)
    assert report["ok"] is True
    assert report["check_staleness"] is False
    assert report["is_live_market"] is False


def test_market_mode_blocks_stale():
    idx = pd.bdate_range("2020-01-02", periods=30)
    n = len(idx)
    df = pd.DataFrame(
        {
            "AAA": [10.0 + i for i in range(n)],
            "AAA_VALUE": [1e8] * n,
        },
        index=idx,
    )
    report = validate_for_optimize(df, source_name="market", as_of=AS_OF)
    assert report["ok"] is False
    assert report["is_live_market"] is True
    assert report["status"] == ValidationStatus.STALE


def test_critical_nan_gap_invalid():
    idx = pd.bdate_range(end=pd.Timestamp(AS_OF), periods=30)
    values = [float("nan")] * 20 + [10.0 + i for i in range(10)]
    df = pd.DataFrame({"AAA": values, "AAA_VALUE": [1e8] * 30}, index=idx)
    report = validate_price_panel(
        df, as_of=AS_OF, check_staleness=False, min_rows=20, min_price_coverage=0.9
    )
    assert report["ok"] is False
    assert report["status"] == ValidationStatus.INVALID


def test_zero_and_future_prices_invalid():
    idx = pd.bdate_range(end=pd.Timestamp("2030-01-15"), periods=30)
    n = len(idx)
    df = pd.DataFrame(
        {"AAA": [0.0] + [10.0 + i for i in range(n - 1)], "AAA_VALUE": [1e8] * n},
        index=idx,
    )
    report = validate_price_panel(
        df, as_of=AS_OF, check_staleness=False, min_rows=20
    )
    assert report["ok"] is False
    assert any("non-positive" in i for i in report["issues"])
    assert any("ahead of as_of" in i for i in report["issues"])
