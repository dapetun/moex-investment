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

_LIVE_SOURCES = frozenset({"market", "iss"})


def validate_price_panel(
    df: pd.DataFrame,
    as_of: date | None = None,
    max_staleness_days: int = 5,
    min_rows: int = 20,
    *,
    check_staleness: bool = True,
    min_price_coverage: float = 0.8,
) -> dict[str, Any]:
    """Проверить панель цен.

    Args:
        check_staleness: Если False (синтетика), возраст last bar не блокирует.
        min_price_coverage: Мин. доля non-NA в столбцах цен.

    Returns:
        Словарь: ok, status, last_data_date, age_days, rows, columns, issues, ...
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

    base_meta = {
        "as_of": as_of.isoformat(),
        "max_staleness_days": max_staleness_days,
        "check_staleness": check_staleness,
        "min_price_coverage": min_price_coverage,
    }

    if df is None or df.empty:
        return {
            "ok": False,
            "status": ValidationStatus.MISSING.value,
            "last_data_date": None,
            "age_days": None,
            "rows": 0,
            "columns": 0,
            "issues": ["empty price panel"],
            **base_meta,
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
                **base_meta,
            }

    if rows < min_rows:
        _bump(ValidationStatus.INVALID)
        issues.append(f"rows {rows} < min_rows {min_rows}")

    price_cols = [c for c in work.columns if not str(c).endswith("_VALUE")]
    if not price_cols:
        _bump(ValidationStatus.INVALID)
        issues.append("no price columns found")
    else:
        coverage = work[price_cols].notna().mean().min()
        if float(coverage) < min_price_coverage:
            _bump(ValidationStatus.INVALID)
            issues.append(
                f"price coverage {float(coverage):.3f} < min_price_coverage "
                f"{min_price_coverage}"
            )

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
            **base_meta,
        }

    last_data_date = last_date.isoformat()
    age_days = (as_of - last_date).days
    if check_staleness and age_days > max_staleness_days:
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
        **base_meta,
    }


def validate_for_optimize(
    df: pd.DataFrame,
    source_name: str,
    as_of: date | None = None,
    max_staleness_days: int = 5,
) -> dict[str, Any]:
    """QC перед optimize: фикстура ≠ живой рынок.

    Для ``fixture`` / синтетики не требуем календарной свежести.
    Для ``market`` / ``iss`` блокируем stale/missing/invalid.
    """
    is_live = source_name in _LIVE_SOURCES
    report = validate_price_panel(
        df,
        as_of=as_of,
        max_staleness_days=max_staleness_days,
        check_staleness=is_live,
    )
    report["source"] = source_name
    report["is_live_market"] = is_live
    if not is_live:
        report["note"] = (
            "synthetic/fixture source: not treated as live market quotes; "
            "staleness check skipped"
        )
    return report
