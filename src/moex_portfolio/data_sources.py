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
        _refuse_fixture_path(self.path)
        logger.info("Loading user_csv prices from %s", self.path)
        return FixtureDataSource(self.path).load_prices(tickers=tickers)


def _refuse_fixture_path(path: Path) -> None:
    """Запрет использовать tracked fixtures как пользовательский рынок."""
    try:
        resolved = path.resolve()
        fixtures_dir = fixture_path().resolve().parent
        if resolved == fixture_path().resolve() or resolved.parent == fixtures_dir:
            raise DataSourceError(
                "refusing to use tracked synthetic fixtures as user market data "
                "(code=USER_CSV_FIXTURE_REFUSED)"
            )
    except DataSourceError:
        raise
    except OSError:
        pass


def redact_local_path(path: Path | str) -> str:
    """Скрыть абсолютный домашний путь в публичных метаданных."""
    s = str(path).replace("\\", "/")
    name = Path(s).name
    if "/" in s:
        return f"<local>/{name}"
    return name


def validate_user_price_csv(
    path: Path,
    *,
    require_tickers: list[str] | None = None,
    max_daily_change: float = 0.8,
    redact_paths: bool = True,
) -> dict[str, object]:
    """Структурная проверка пользовательского CSV до импорта в кэш.

    Ловит: слишком короткую историю, пустые столбцы, дубликаты дат,
    нечисловые/неположительные цены, аномальные дневные скачки,
    отсутствие требуемых тикеров. Не обращается к сети/ISS.
    """
    if not path.exists():
        raise DataSourceError(f"user price CSV not found: {path}")
    _refuse_fixture_path(path)
    df = FixtureDataSource(path).load_prices()
    if not isinstance(df.index, pd.DatetimeIndex):
        raise DataSourceError(
            "user CSV TRADEDATE index invalid (code=USER_CSV_BAD_DATES)"
        )
    if df.index.has_duplicates:
        raise DataSourceError(
            "user CSV has duplicate TRADEDATE rows (code=USER_CSV_DUP_DATES)"
        )
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
    # нечисловые / неположительные / аномальные скачки
    for col in price_cols:
        raw = df[col]
        series = pd.to_numeric(raw, errors="coerce")
        if int(series.isna().sum()) > int(raw.isna().sum()):
            raise DataSourceError(
                f"user CSV column {col} has non-numeric prices "
                f"(code=USER_CSV_NON_NUMERIC)"
            )
        if (series.dropna() <= 0).any():
            raise DataSourceError(
                f"user CSV column {col} has non-positive prices "
                f"(code=USER_CSV_NON_POSITIVE)"
            )
        rets = series.pct_change().dropna()
        if not rets.empty and bool((rets.abs() > max_daily_change).any()):
            raise DataSourceError(
                f"user CSV column {col} has daily change > {max_daily_change} "
                f"(code=USER_CSV_PRICE_ANOMALY)"
            )
    missing_req: list[str] = []
    if require_tickers:
        have = {str(c).upper() for c in price_cols}
        missing_req = [t for t in require_tickers if t.upper() not in have]
        if missing_req:
            raise DataSourceError(
                f"user CSV missing required tickers {missing_req} "
                f"(code=USER_CSV_TICKERS_MISSING)"
            )
    # крупные дыры в календаре (предупреждение, не блок)
    gaps_days = 0
    if len(df.index) >= 2:
        deltas = df.index.to_series().diff().dt.days.dropna()
        gaps_days = int(deltas.max()) if len(deltas) else 0
    warnings: list[str] = []
    if gaps_days > 10:
        warnings.append(
            f"largest calendar gap between bars is {gaps_days} days "
            "(code=USER_CSV_GAP_WARN)"
        )
    last = df.index.max()
    path_out = redact_local_path(path) if redact_paths else str(path.resolve())
    return {
        "path": path_out,
        "path_basename": Path(path).name,
        "rows": int(len(df)),
        "tickers": price_cols,
        "last_data_date": str(pd.Timestamp(last).date()),
        "format": "moex_panel_semicolon_v1",
        "require_tickers_ok": not missing_req,
        "max_calendar_gap_days": gaps_days,
        "warnings": warnings,
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
