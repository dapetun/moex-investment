"""Локальные append-only журналы прогнозов и испытаний.

Не подключены к ботам. Словесный confidence не превращается в вероятность.
Запись с датой раньше исхода, но с created_at после resolved_at, отклоняется.
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


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def append_forecast(path: Path, record: dict[str, Any]) -> dict[str, Any]:
    """Записать прогноз. p — число в [0, 1], не метка confidence."""
    if "confidence" in record and "probability" not in record:
        raise ValueError("verbal confidence is not a probability")
    p = record.get("probability")
    if not isinstance(p, (int, float)) or isinstance(p, bool) or not 0.0 <= float(p) <= 1.0:
        raise ValueError("probability must be a number in [0, 1]")
    created = _parse(str(record["created_at"]))
    resolved = record.get("resolved_at")
    if resolved and _parse(str(resolved)) < created:
        raise ValueError("forecast created_at is after resolved_at")
    stored = dict(record)
    stored["probability"] = float(p)
    append_jsonl(path, stored)
    return stored


def append_trial(path: Path, record: dict[str, Any]) -> dict[str, Any]:
    """Зафиксировать версию стратегии и параметров."""
    for key in ("trial_id", "strategy", "params", "created_at"):
        if key not in record:
            raise ValueError(f"trial missing {key}")
    append_jsonl(path, dict(record))
    return dict(record)


def brier_score(path: Path) -> dict[str, Any]:
    """Brier только по записям с однозначным бинарным исходом 0 или 1."""
    if not path.exists():
        return {"n": 0, "brier": None, "status": "empty"}
    total = 0.0
    n = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        outcome = row.get("outcome")
        if outcome not in (0, 1):
            continue
        total += (float(row["probability"]) - float(outcome)) ** 2
        n += 1
    if n == 0:
        return {"n": 0, "brier": None, "status": "no_resolved_binary_outcomes"}
    return {"n": n, "brier": total / n, "status": "ok"}
