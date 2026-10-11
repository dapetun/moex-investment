"""Подключаемые источники рыночных данных.

По умолчанию — синтетические фикстуры. MOEX ISS не вызывается, пока
``MOEX_ISS_ENABLED=true`` и выбран источник ``iss``. Seed CSV из репозитория
не используется как «разрешённый» обход.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

import pandas as pd

from .settings import (
    fixture_path,
    get_data_source_name,
    iss_enabled,
    runtime_cache_path,
    user_prices_path,
)

logger = logging.getLogger(__name__)


class DataSourceError(RuntimeError):
    """Ошибка источника данных или нарушение политики доступа."""


class DataSource(Protocol):
    """Контракт источника цен."""

    @property
    def name(self) -> str: ...

    def load_prices(self, tickers: list[str] | None = None) -> pd.DataFrame: ...


class FixtureDataSource:
    """Чтение синтетического CSV (sep=';', TRADEDATE + TICKER / TICKER_VALUE)."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or fixture_path()

    @property
    def name(self) -> str:
        return "fixture"

    def load_prices(self, tickers: list[str] | None = None) -> pd.DataFrame:
        if not self.path.exists():
            raise DataSourceError(f"fixture not found: {self.path}")

        df = pd.read_csv(self.path, sep=";", index_col="TRADEDATE", parse_dates=True)
        df = df.sort_index()
        if tickers:
            cols: list[str] = []
            for t in tickers:
                if t in df.columns:
                    cols.append(t)
                value_col = f"{t}_VALUE"
                if value_col in df.columns:
                    cols.append(value_col)
            missing = [t for t in tickers if t not in df.columns]
            if missing:
                raise DataSourceError(f"tickers missing in fixture: {missing}")
            df = df[cols]
        logger.info("Loaded fixture prices: %s rows=%d cols=%d", self.path, len(df), len(df.columns))
        return df


class IssDataSource:
    """Заглушка/гейт для MOEX ISS.

    Реальная загрузка через data_loader не вызывается, пока нет явного
    включения и отдельного решения по условиям использования.
    """

    @property
    def name(self) -> str:
        return "iss"

    def load_prices(self, tickers: list[str] | None = None) -> pd.DataFrame:
        if not iss_enabled():
            raise DataSourceError(
                "MOEX ISS disabled (MOEX_ISS_ENABLED=false). "
                "Automated portfolio use awaits written confirmation from the exchange. "
                "Use fixture source for offline development."
            )
        # Даже при флаге true не подключаем live ISS в этом MVP без явного решения.
        raise DataSourceError(
            "MOEX ISS source is gated: even with MOEX_ISS_ENABLED=true, "
            "live fetch is not wired until legal clearance is recorded. "
            "Keep using fixtures."
        )


class RuntimeCacheDataSource:
    """Локальный runtime-кэш как будущий «рыночный» режим без сети.

    Не ISS и не seed ``price_data.csv``. Требует предварительного
    ``update-data`` из разрешённого источника. К свежести применяется
    live-политика QC.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or runtime_cache_path()

    @property
    def name(self) -> str:
        return "market"

    def load_prices(self, tickers: list[str] | None = None) -> pd.DataFrame:
        if not self.path.exists():
            raise DataSourceError(
                f"market runtime cache not found: {self.path}. "
                "Populate via an approved offline path first; ISS remains gated."
            )
        # тот же формат CSV, что у fixture
        return FixtureDataSource(self.path).load_prices(tickers=tickers)


class UserCsvDataSource:
    """Явно выбранная пользователем локальная ценовая панель.

    Не сеть, не ISS, не подмена fixture. Требует ``MOEX_USER_PRICES_PATH``
    или путь в конструкторе. Формат как у fixture (``;``, TRADEDATE).
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or user_prices_path()

    @property
    def name(self) -> str:
        return "user_csv"

    def load_prices(self, tickers: list[str] | None = None) -> pd.DataFrame:
        if self.path is None:
            raise DataSourceError(
                "user_csv requires MOEX_USER_PRICES_PATH "
                "(code=USER_CSV_PATH_REQUIRED)"
            )
        if not self.path.exists():
            raise DataSourceError(
                f"user price CSV not found: {self.path} (code=USER_CSV_MISSING)"
            )
        # Запрет читать tracked fixture как «пользовательский рынок»
        fixture = fixture_path().resolve()
        try:
            if self.path.resolve() == fixture:
                raise DataSourceError(
                    "refusing to treat synthetic fixture as user_csv; "
                    "copy/export a separate file (code=USER_CSV_FIXTURE_REFUSED)"
                )
        except DataSourceError:
            raise
        except OSError:
            pass
        logger.info("Loading user_csv prices from %s", self.path)
        return FixtureDataSource(self.path).load_prices(tickers=tickers)


def validate_user_price_csv(path: Path) -> dict[str, object]:
    """Структурная проверка пользовательского CSV до импорта в кэш."""
    if not path.exists():
        raise DataSourceError(f"user price CSV not found: {path}")
    try:
        resolved = path.resolve()
        fixtures_dir = fixture_path().resolve().parent
        if resolved == fixture_path().resolve() or resolved.parent == fixtures_dir:
            raise DataSourceError(
                "refusing to import tracked synthetic fixtures as user market data "
                "(code=USER_CSV_FIXTURE_REFUSED)"
            )
    except DataSourceError:
        raise
    except OSError:
        pass
    df = FixtureDataSource(path).load_prices()
    price_cols = [c for c in df.columns if not str(c).endswith("_VALUE")]
    if len(price_cols) < 2:
        raise DataSourceError(
            "user CSV needs >=2 price columns (code=USER_CSV_TOO_FEW_TICKERS)"
        )
    if len(df) < 20:
        raise DataSourceError(
            f"user CSV has {len(df)} rows, need >=20 (code=USER_CSV_TOO_SHORT)"
        )
    if df[price_cols].isna().all().any():
        raise DataSourceError(
            "user CSV has all-NA price column (code=USER_CSV_EMPTY_COLUMN)"
        )
    last = df.index.max()
    return {
        "path": str(path.resolve()),
        "rows": int(len(df)),
        "tickers": price_cols,
        "last_data_date": str(pd.Timestamp(last).date()),
        "format": "moex_panel_semicolon_v1",
    }


def get_data_source() -> DataSource:
    """Фабрика активного источника по settings."""
    name = get_data_source_name()
    if name == "fixture":
        return FixtureDataSource()
    if name == "market":
        return RuntimeCacheDataSource()
    if name == "user_csv":
        return UserCsvDataSource()
    if name == "iss":
        return IssDataSource()
    raise DataSourceError(f"unknown data source: {name}")
