"""Локальные append-only журналы прогнозов и испытаний.

Регистрация и разрешение исхода — разные записи. Журнал не подключён к ботам.
Словесный confidence не становится вероятностью. created_at после регистрации
не переписывается.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _parse(ts: str) -> datetime:
    text = ts.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _read(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def register_forecast(path: Path, record: dict[str, Any]) -> dict[str, Any]:
    """Записать прогноз до исхода. Повтор того же forecast_id запрещён."""
    if "outcome" in record or "resolved_at" in record:
        raise ValueError("outcome is recorded only by resolve_forecast")
    if "confidence" in record and "probability" not in record:
        raise ValueError("verbal confidence is not a probability")
    forecast_id = record.get("forecast_id")
    if not isinstance(forecast_id, str) or not forecast_id.strip():
        raise ValueError("forecast_id is required")
    probability = record.get("probability")
    if (
        not isinstance(probability, (int, float))
        or isinstance(probability, bool)
        or not 0.0 <= float(probability) <= 1.0
    ):
        raise ValueError("probability must be a number in [0, 1]")
    for key in ("created_at", "subject", "horizon"):
        if not record.get(key):
            raise ValueError(f"forecast missing {key}")
    _parse(str(record["created_at"]))
    rows = _read(path)
    for row in rows:
        if row.get("record_type") == "forecast" and row.get("forecast_id") == forecast_id:
            raise ValueError("duplicate forecast_id")
        same_claim = (
            row.get("record_type") == "forecast"
            and row.get("subject") == record["subject"]
            and row.get("horizon") == record["horizon"]
            and row.get("created_at") == record["created_at"]
        )
        if same_claim:
            raise ValueError("duplicate forecast claim")
    stored = {
        "record_type": "forecast",
        "forecast_id": forecast_id.strip(),
        "created_at": str(record["created_at"]),
        "subject": record["subject"],
        "horizon": record["horizon"],
        "probability": float(probability),
        "method": record.get("method"),
        "source": record.get("source"),
    }
    append_jsonl(path, stored)
    return stored


def resolve_forecast(
    path: Path,
    *,
    forecast_id: str,
    resolved_at: str,
    outcome: int,
) -> dict[str, Any]:
    """Дописать исход. Вероятность и created_at исходной записи не меняются."""
    if outcome not in (0, 1):
        raise ValueError("outcome must be binary 0 or 1")
    rows = _read(path)
    forecasts = [
        row for row in rows
        if row.get("record_type") == "forecast" and row.get("forecast_id") == forecast_id
    ]
    if len(forecasts) != 1:
        raise ValueError("forecast_id not found")
    if any(
        row.get("record_type") == "resolution" and row.get("forecast_id") == forecast_id
        for row in rows
    ):
        raise ValueError("forecast already resolved")
    if _parse(resolved_at) < _parse(str(forecasts[0]["created_at"])):
        raise ValueError("resolved_at is before created_at")
    stored = {
        "record_type": "resolution",
        "forecast_id": forecast_id,
        "resolved_at": _parse(resolved_at).isoformat(),
        "outcome": outcome,
    }
    append_jsonl(path, stored)
    return stored


def append_forecast(path: Path, record: dict[str, Any]) -> dict[str, Any]:
    """Совместимый вход только для регистрации. Исход в этой записи запрещён."""
    return register_forecast(path, record)


def append_trial(path: Path, record: dict[str, Any]) -> dict[str, Any]:
    """Зафиксировать версию стратегии и параметров."""
    for key in ("trial_id", "strategy", "params", "created_at"):
        if key not in record:
            raise ValueError(f"trial missing {key}")
    rows = _read(path)
    if any(row.get("trial_id") == record["trial_id"] for row in rows):
        raise ValueError("duplicate trial_id")
    stored = dict(record)
    append_jsonl(path, stored)
    return stored


def brier_score(path: Path) -> dict[str, Any]:
    """Brier только по прогнозам с одной резолюцией и бинарным исходом."""
    rows = _read(path)
    if not rows:
        return {"n": 0, "brier": None, "status": "empty"}
    forecasts = {
        row["forecast_id"]: row
        for row in rows
        if row.get("record_type") == "forecast"
    }
    total = 0.0
    n = 0
    for row in rows:
        if row.get("record_type") != "resolution":
            continue
        forecast = forecasts.get(row.get("forecast_id"))
        outcome = row.get("outcome")
        if forecast is None or outcome not in (0, 1):
            continue
        total += (float(forecast["probability"]) - float(outcome)) ** 2
        n += 1
    if n == 0:
        return {"n": 0, "brier": None, "status": "no_resolved_binary_outcomes"}
    return {"n": n, "brier": total / n, "status": "ok"}
