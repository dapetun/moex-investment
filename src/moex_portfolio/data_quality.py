"""Проверка полноты и свежести ценовой панели (без сетевых вызовов)."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

import pandas as pd


class ValidationStatus(str, Enum):
    OK = "ok"
    STALE = "stale"
    MISSING = "missing"
    INVALID = "invalid"


_SEVERITY = {
    ValidationStatus.OK: 0,
    ValidationStatus.STALE: 1,
    ValidationStatus.INVALID: 2,
    ValidationStatus.MISSING: 3,
}


def validate_price_panel(
    df: pd.DataFrame,
    as_of: date | None = None,
    max_staleness_days: int = 5,
    min_rows: int = 20,
) -> dict[str, Any]:
    """Проверить панель цен.

    Returns:
        Словарь: ok, status, last_data_date, age_days, rows, columns, issues.
    """
    as_of = as_of or date.today()
    issues: list[str] = []
    status = ValidationStatus.OK
    last_data_date = None
    age_days = None
    rows = 0
    columns = 0

    def _bump(new: ValidationStatus) -> None:
        nonlocal status
        if _SEVERITY[new] > _SEVERITY[status]:
            status = new

    if df is None or df.empty:
        return {
            "ok": False,
            "status": ValidationStatus.MISSING.value,
            "last_data_date": None,
            "age_days": None,
            "rows": 0,
            "columns": 0,
            "issues": ["empty price panel"],
            "as_of": as_of.isoformat(),
            "max_staleness_days": max_staleness_days,
        }

    rows = int(len(df))
    columns = int(len(df.columns))
    work = df

    if not isinstance(work.index, pd.DatetimeIndex):
        try:
            work = work.copy()
            work.index = pd.to_datetime(work.index)
        except (TypeError, ValueError):
            _bump(ValidationStatus.INVALID)
            issues.append("index is not datetime")
            return {
                "ok": False,
                "status": status.value,
                "last_data_date": None,
                "age_days": None,
                "rows": rows,
                "columns": columns,
                "issues": issues,
                "as_of": as_of.isoformat(),
                "max_staleness_days": max_staleness_days,
            }

    if rows < min_rows:
        _bump(ValidationStatus.INVALID)
        issues.append(f"rows {rows} < min_rows {min_rows}")

    last = work.index.max()
    if isinstance(last, pd.Timestamp):
        last_date = last.date()
    elif isinstance(last, datetime):
        last_date = last.date()
    else:
        _bump(ValidationStatus.INVALID)
        issues.append("cannot parse last_data_date")
        return {
            "ok": False,
            "status": status.value,
            "last_data_date": None,
            "age_days": None,
            "rows": rows,
            "columns": columns,
            "issues": issues,
            "as_of": as_of.isoformat(),
            "max_staleness_days": max_staleness_days,
        }

    last_data_date = last_date.isoformat()
    age_days = (as_of - last_date).days
    if age_days > max_staleness_days:
        _bump(ValidationStatus.STALE)
        issues.append(
            f"last_data_date {last_date} is {age_days}d behind as_of {as_of}"
        )

    if work.index.duplicated().any():
        _bump(ValidationStatus.INVALID)
        issues.append("duplicate dates in index")

    return {
        "ok": status == ValidationStatus.OK,
        "status": status.value,
        "last_data_date": last_data_date,
        "age_days": age_days,
        "rows": rows,
        "columns": columns,
        "issues": issues,
        "as_of": as_of.isoformat(),
        "max_staleness_days": max_staleness_days,
    }
