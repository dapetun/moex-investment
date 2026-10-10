"""Валидация и приём событий бота №1 / адаптер «Корпоративного радара».

Канонический формат CLI требует: event_type, title, url, published_at, source.
Радар (по ревью) использует issuer_name, source_name, source_url, factual_summary
и пакетную обёртку. Полная схема радара в этом репозитории отсутствует —
см. data/inbox/events/RADAR_CONTRACT.md (требует подтверждения).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
from pathlib import Path
from typing import Any

from .config import DATA_DIR

logger = logging.getLogger(__name__)

INBOX_DIR = DATA_DIR / "inbox" / "events"
PROCESSED_DIR = DATA_DIR / "processed" / "events"
REJECTED_DIR = DATA_DIR / "processed" / "rejected"

REQUIRED_FIELDS = ("event_type", "title", "url", "published_at", "source")
ALLOWED_PREFIXES = ("disclosure_", "dividend_")

# Явные алиасы → канонический event_type. Не маппим неизвестное в disclosure_*.
EVENT_TYPE_ALIASES: dict[str, str] = {
    "dividend": "dividend_declared",
    "dividend_declared": "dividend_declared",
    "dividend_forecast": "dividend_forecast",
    "dividend_ex_date": "dividend_ex_date",
    "dividend_recommendation": "dividend_declared",
    "disclosure": "disclosure_filing",
    "disclosure_filing": "disclosure_filing",
    "disclosure_report": "disclosure_report",
    "disclosure_meeting": "disclosure_meeting",
    "disclosure_board_decision": "disclosure_board_decision",
    "e-disclosure": "disclosure_filing",
    "edisclosure": "disclosure_filing",
    "meeting": "disclosure_meeting",
    "board_decision": "disclosure_board_decision",
    "material_fact": "disclosure_material_fact",
}


class EventValidationError(ValueError):
    """Некорректное событие inbox."""


def canonicalize_event_type(value: Any) -> str:
    """Однозначные правила event_type без выдуманного disclosure_*."""
    if value is None or (isinstance(value, str) and not str(value).strip()):
        raise EventValidationError(
            "missing event_type; radar/CLI must provide a mappable type "
            "(code=EVENT_TYPE_REQUIRED)"
        )
    et = str(value).strip()
    if et.startswith("disclosure_") or et.startswith("dividend_"):
        return et
    key = et.lower().replace(" ", "_").replace("-", "_")
    # normalize double underscores from e_disclosure etc.
    key = re.sub(r"_+", "_", key)
    if key in EVENT_TYPE_ALIASES:
        return EVENT_TYPE_ALIASES[key]
    # e_disclosure after replace
    if key.replace("_", "") in {"edisclosure"}:
        return "disclosure_filing"
    raise EventValidationError(
        f"unmapped event_type {value!r}; confirm RADAR_CONTRACT mapping "
        f"(code=EVENT_TYPE_UNMAPPED). Refusing to invent disclosure_*."
    )


def extract_event_list(raw: Any) -> list[dict[str, Any]]:
    """Извлечь список событий из одиночного объекта, массива или обёртки."""
    if isinstance(raw, list):
        if not raw:
            raise EventValidationError("empty events list")
        for i, item in enumerate(raw):
            if not isinstance(item, dict):
                raise EventValidationError(f"events[{i}] must be an object")
        return raw
    if isinstance(raw, dict):
        if "events" in raw:
            events = raw["events"]
            if not isinstance(events, list) or not events:
                raise EventValidationError("'events' must be a non-empty list")
            for i, item in enumerate(events):
                if not isinstance(item, dict):
                    raise EventValidationError(f"events[{i}] must be an object")
            return events
        return [raw]
    raise EventValidationError("payload must be object, array, or {events: [...]}")


def normalize_event(raw: dict[str, Any]) -> dict[str, Any]:
    """Адаптер радар → канон + сохранение исходных полей."""
    if not isinstance(raw, dict):
        raise EventValidationError("event must be a dict")

    out: dict[str, Any] = dict(raw)

    if not out.get("url") and raw.get("source_url"):
        out["url"] = raw["source_url"]
    if not out.get("source") and raw.get("source_name"):
        out["source"] = raw["source_name"]
    if not out.get("summary") and raw.get("factual_summary"):
        out["summary"] = raw["factual_summary"]
    if not out.get("company") and raw.get("issuer_name"):
        out["company"] = raw["issuer_name"]

    type_src = raw.get("event_type") or raw.get("type") or raw.get("category")
    out["event_type"] = canonicalize_event_type(type_src)

    if not out.get("published_at"):
        for key in ("event_date", "disclosure_date", "date", "published_date"):
            if raw.get(key):
                out["published_at"] = raw[key]
                break

    if not out.get("title"):
        summary = out.get("summary") or raw.get("factual_summary")
        if summary:
            out["title"] = str(summary).strip()[:200]
        else:
            company = out.get("company") or raw.get("issuer_name") or "unknown"
            out["title"] = f"{company}: {out['event_type']}"

    # не терять оригинал
    out["radar_original"] = raw
    if "facts" in raw and "facts" not in out:
        out["facts"] = raw["facts"]

    if out.get("event_id") is None and raw.get("id") is not None:
        out["event_id"] = raw["id"]

    # Оценки/скоры радара (акции/облигации) — сохраняем без интерпретации.
    for score_key in (
        "equity_score",
        "bond_score",
        "score_equity",
        "score_bond",
        "scores",
        "impact_score",
        "severity_score",
    ):
        if score_key in raw and score_key not in out:
            out[score_key] = raw[score_key]

    validate_event(out)
    return out


def validate_event(event: dict[str, Any]) -> None:
    """Проверить минимальную каноническую схему события."""
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


def stable_event_filename(event: dict[str, Any]) -> str:
    """Детерминированное имя файла: event_id или хэш канонического содержимого."""
    eid = event.get("event_id")
    if eid is not None and str(eid).strip():
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", str(eid).strip())
        return f"{safe}.json"
    payload = {
        k: event.get(k)
        for k in (
            "event_type",
            "title",
            "url",
            "published_at",
            "source",
            "ticker",
            "company",
            "summary",
        )
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16]
    return f"evt_{digest}.json"


def _events_equivalent(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Сравнение существенных полей (без radar_original для стабильности)."""
    keys = (
        "event_id",
        "event_type",
        "title",
        "url",
        "published_at",
        "source",
        "ticker",
        "company",
        "summary",
        "facts",
        "equity_score",
        "bond_score",
        "scores",
    )
    return all(a.get(k) == b.get(k) for k in keys)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def ingest_events() -> dict[str, Any]:
    """Прочитать inbox: нормализация → processed; дубликаты/конфликты учитываются."""
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    REJECTED_DIR.mkdir(parents=True, exist_ok=True)

    accepted = 0
    rejected = 0
    duplicate_skipped = 0
    conflict = 0
    details: list[dict[str, Any]] = []

    for path in sorted(INBOX_DIR.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            items = extract_event_list(raw)
        except (json.JSONDecodeError, EventValidationError) as e:
            dest = REJECTED_DIR / f"{path.stem}__invalid.json"
            try:
                shutil.move(str(path), str(dest))
            except OSError:
                path.unlink(missing_ok=True)
            rejected += 1
            details.append(
                {"file": path.name, "status": "rejected", "error": str(e)}
            )
            logger.warning("Rejected inbox file %s: %s", path.name, e)
            continue

        for idx, item in enumerate(items):
            try:
                event = normalize_event(item)
                dest_name = stable_event_filename(event)
                dest = PROCESSED_DIR / dest_name
                if dest.exists():
                    existing = json.loads(dest.read_text(encoding="utf-8"))
                    if _events_equivalent(existing, event):
                        duplicate_skipped += 1
                        details.append(
                            {
                                "file": path.name,
                                "index": idx,
                                "event_id": event.get("event_id"),
                                "dest": dest_name,
                                "status": "duplicate_skipped",
                            }
                        )
                        continue
                    conflict += 1
                    rejected += 1
                    rej = REJECTED_DIR / f"{dest.stem}__conflict__{path.stem}_{idx}.json"
                    _write_json(
                        rej,
                        {
                            "error": "processed event exists with different content",
                            "code": "EVENT_CONFLICT",
                            "dest": dest_name,
                            "incoming": event,
                        },
                    )
                    details.append(
                        {
                            "file": path.name,
                            "index": idx,
                            "event_id": event.get("event_id"),
                            "dest": dest_name,
                            "status": "conflict",
                            "error": "EVENT_CONFLICT",
                        }
                    )
                    continue

                _write_json(dest, event)
                accepted += 1
                details.append(
                    {
                        "file": path.name,
                        "index": idx,
                        "event_id": event.get("event_id"),
                        "dest": dest_name,
                        "status": "accepted",
                    }
                )
            except (EventValidationError, OSError, TypeError, ValueError) as e:
                rejected += 1
                rej = REJECTED_DIR / f"{path.stem}_{idx}__rejected.json"
                _write_json(
                    rej,
                    {"error": str(e), "index": idx, "incoming": item},
                )
                details.append(
                    {
                        "file": path.name,
                        "index": idx,
                        "status": "rejected",
                        "error": str(e),
                    }
                )
                logger.warning("Rejected event %s[%s]: %s", path.name, idx, e)

        path.unlink(missing_ok=True)

    return {
        "accepted": accepted,
        "rejected": rejected,
        "duplicate_skipped": duplicate_skipped,
        "conflict": conflict,
        "inbox": str(INBOX_DIR),
        "processed": str(PROCESSED_DIR),
        "details": details,
    }
