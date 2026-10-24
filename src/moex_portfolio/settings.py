"""Настройки окружения для CLI и источников данных.

MOEX ISS по умолчанию выключен до письменного подтверждения допустимого режима.
"""

from __future__ import annotations

import os
from pathlib import Path

from .config import DATA_DIR

_TRUE = {"1", "true", "yes", "on"}


def iss_enabled() -> bool:
    """Разрешён ли сетевой доступ к MOEX ISS.

    По умолчанию False. HTTP 200 не считается разрешением на использование.
    """
    return os.environ.get("MOEX_ISS_ENABLED", "false").strip().lower() in _TRUE


def get_data_source_name() -> str:
    """Имя активного источника: fixture | market | user_csv | iss.

    ``MOEX_DATA_SOURCE`` имеет приоритет; иначе fixture, пока ISS выключен.
    ``market`` — локальный runtime-кэш с live-политикой свежести (не ISS).
    ``user_csv`` — явно указанный пользователем исторический CSV (не сеть, не ISS).
    """
    explicit = os.environ.get("MOEX_DATA_SOURCE", "").strip().lower()
    if explicit:
        return explicit
    if iss_enabled():
        return "iss"
    return "fixture"


def fixture_path() -> Path:
    """Путь к синтетическому CSV (не seed market cache)."""
    env = os.environ.get("MOEX_FIXTURE_PATH", "").strip()
    if env:
        return Path(env)
    return DATA_DIR / "fixtures" / "synthetic_prices.csv"


def user_prices_path() -> Path | None:
    """Путь к пользовательской панели (``MOEX_USER_PRICES_PATH``)."""
    env = os.environ.get("MOEX_USER_PRICES_PATH", "").strip()
    return Path(env) if env else None


def user_csv_skip_staleness() -> bool:
    """Явное подтверждение исторической панели без проверки свежести."""
    return os.environ.get("MOEX_USER_CSV_SKIP_STALENESS", "false").strip().lower() in _TRUE


def runtime_cache_path() -> Path:
    """Рабочий кэш CLI (не путать с tracked data/price_data.csv)."""
    env = os.environ.get("MOEX_RUNTIME_CACHE", "").strip()
    if env:
        return Path(env)
    return DATA_DIR / "cache" / "runtime_prices.csv"
