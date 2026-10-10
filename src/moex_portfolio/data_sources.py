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

from .settings import fixture_path, get_data_source_name, iss_enabled

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


def get_data_source() -> DataSource:
    """Фабрика активного источника по settings."""
    name = get_data_source_name()
    if name == "fixture":
        return FixtureDataSource()
    if name == "iss":
        return IssDataSource()
    raise DataSourceError(f"unknown data source: {name}")
