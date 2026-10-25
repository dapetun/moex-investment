"""Негативы и покрытие validate_user_price_csv."""

from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd
import pytest

from moex_portfolio.data_sources import DataSourceError, validate_user_price_csv

ROOT = Path(__file__).resolve().parents[1]
DIV = ROOT / "data" / "fixtures" / "synthetic_prices_diversified.csv"


def _copy_ok(tmp_path: Path) -> Path:
    p = tmp_path / "ok_prices.csv"
    shutil.copy2(DIV, p)
    return p


def test_ok_and_redacted_path(tmp_path: Path) -> None:
    p = _copy_ok(tmp_path)
    meta = validate_user_price_csv(p, require_tickers=["AAA", "BBB", "CCC"])
    assert meta["rows"] >= 20
    assert "Users" not in str(meta["path"])
    assert meta["path_basename"] == "ok_prices.csv"


def test_missing_required_ticker(tmp_path: Path) -> None:
    p = _copy_ok(tmp_path)
    with pytest.raises(DataSourceError, match="USER_CSV_TICKERS_MISSING"):
        validate_user_price_csv(p, require_tickers=["AAA", "ZZZ"])


def test_duplicate_dates(tmp_path: Path) -> None:
    p = _copy_ok(tmp_path)
    df = pd.read_csv(p, sep=";", index_col="TRADEDATE", parse_dates=True)
    df = pd.concat([df, df.iloc[[-1]]])
    bad = tmp_path / "dup.csv"
    df.to_csv(bad, sep=";")
    with pytest.raises(DataSourceError, match="USER_CSV_DUP_DATES"):
        validate_user_price_csv(bad)


def test_non_positive_price(tmp_path: Path) -> None:
    p = _copy_ok(tmp_path)
    df = pd.read_csv(p, sep=";", index_col="TRADEDATE", parse_dates=True)
    df.iloc[5, df.columns.get_loc("AAA")] = -1.0
    bad = tmp_path / "neg.csv"
    df.to_csv(bad, sep=";")
    with pytest.raises(DataSourceError, match="USER_CSV_NON_POSITIVE"):
        validate_user_price_csv(bad)


def test_price_anomaly(tmp_path: Path) -> None:
    p = _copy_ok(tmp_path)
    df = pd.read_csv(p, sep=";", index_col="TRADEDATE", parse_dates=True)
    df.iloc[10, df.columns.get_loc("AAA")] = float(df.iloc[9]["AAA"]) * 3.0
    bad = tmp_path / "anom.csv"
    df.to_csv(bad, sep=";")
    with pytest.raises(DataSourceError, match="USER_CSV_PRICE_ANOMALY"):
        validate_user_price_csv(bad, max_daily_change=0.5)


def test_refuse_fixture_dir() -> None:
    with pytest.raises(DataSourceError, match="USER_CSV_FIXTURE_REFUSED"):
        validate_user_price_csv(DIV)
