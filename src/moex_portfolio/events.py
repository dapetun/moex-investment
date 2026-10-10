"""Валидация и приём структурированных событий от бота №1."""

from __future__ import annotations

import json
import logging
import shutil
from typing import Any

from .config import DATA_DIR

logger = logging.getLogger(__name__)

INBOX_DIR = DATA_DIR / "inbox" / "events"
PROCESSED_DIR = DATA_DIR / "processed" / "events"
REJECTED_DIR = DATA_DIR / "processed" / "rejected"

REQUIRED_FIELDS = ("event_type", "title", "url", "published_at", "source")
ALLOWED_PREFIXES = ("disclosure_", "dividend_")


class EventValidationError(ValueError):
    """Некорректное событие inbox."""


def validate_event(event: dict[str, Any]) -> None:
    """Проверить минимальную схему события."""
    if not isinstance(event, dict):
        raise EventValidationError("event must be a dict")
    for field in REQUIRED_FIELDS:
        val = event.get(field)
        if val is None or (isinstance(val, str) and not val.strip()):
            raise EventValidationError(f"missing required field: {field}")

    et = str(event["event_type"])
    if not any(et.startswith(p) for p in ALLOWED_PREFIXES):
        raise EventValidationError(
            f"event_type must start with {ALLOWED_PREFIXES}, got {et!r}"
        )


def ingest_events() -> dict[str, Any]:
    """Прочитать JSON из inbox, валидные → processed, битые → rejected."""
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    REJECTED_DIR.mkdir(parents=True, exist_ok=True)

    accepted = 0
    rejected = 0
    details: list[dict[str, Any]] = []

    for path in sorted(INBOX_DIR.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            validate_event(raw)
            dest = PROCESSED_DIR / path.name
            shutil.move(str(path), str(dest))
            accepted += 1
            details.append({"file": path.name, "status": "accepted"})
        except (json.JSONDecodeError, EventValidationError, OSError) as e:
            dest = REJECTED_DIR / path.name
            try:
                shutil.move(str(path), str(dest))
            except OSError:
                pass
            rejected += 1
            details.append({"file": path.name, "status": "rejected", "error": str(e)})
            logger.warning("Rejected event %s: %s", path.name, e)

    return {
        "accepted": accepted,
        "rejected": rejected,
        "inbox": str(INBOX_DIR),
        "processed": str(PROCESSED_DIR),
        "details": details,
    }
