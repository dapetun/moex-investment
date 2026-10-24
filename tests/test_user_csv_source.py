"""Режим user_csv: локальный импорт без ISS и без подмены fixture."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from moex_portfolio import cli
from moex_portfolio.data_sources import (
    DataSourceError,
    UserCsvDataSource,
    get_data_source,
    validate_user_price_csv,
)

ROOT = Path(__file__).resolve().parents[1]
DIV = ROOT / "data" / "fixtures" / "synthetic_prices_diversified.csv"


def test_validate_and_load_user_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    user = tmp_path / "my_prices.csv"
    shutil.copy2(DIV, user)
    meta = validate_user_price_csv(user)
    assert meta["rows"] >= 20
    assert "AAA" in meta["tickers"]

    monkeypatch.setenv("MOEX_DATA_SOURCE", "user_csv")
    monkeypatch.setenv("MOEX_USER_PRICES_PATH", str(user))
    monkeypatch.setenv("MOEX_ISS_ENABLED", "false")
    src = get_data_source()
    assert src.name == "user_csv"
    df = src.load_prices(tickers=["AAA", "BBB", "CCC"])
    assert list(df.columns)[:3] == ["AAA", "AAA_VALUE", "BBB"] or "AAA" in df.columns


def test_refuse_tracked_fixture(tmp_path: Path) -> None:
    with pytest.raises(DataSourceError, match="USER_CSV_FIXTURE_REFUSED"):
        validate_user_price_csv(DIV)


def test_import_user_prices_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    user = tmp_path / "panel.csv"
    shutil.copy2(DIV, user)
    cache = tmp_path / "runtime_prices.csv"
    monkeypatch.setenv("MOEX_RUNTIME_CACHE", str(cache))
    monkeypatch.setenv("MOEX_ISS_ENABLED", "false")
    monkeypatch.setattr("moex_portfolio.run_journal.RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr("moex_portfolio.locks.LOCKS_DIR", tmp_path / "locks")
    code = cli.main(["import-user-prices", "--csv", str(user), "--skip-staleness"])
    assert code == 0
    assert cache.exists()
    meta = json.loads(
        cache.with_suffix(cache.suffix + ".meta.json").read_text(encoding="utf-8")
    )
    assert meta["source"] == "user_csv"
    assert meta["skip_staleness"] is True


def test_user_csv_path_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOEX_DATA_SOURCE", "user_csv")
    monkeypatch.delenv("MOEX_USER_PRICES_PATH", raising=False)
    src = UserCsvDataSource()
    with pytest.raises(DataSourceError, match="USER_CSV_PATH_REQUIRED"):
        src.load_prices()
