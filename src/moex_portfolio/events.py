"""Валидация и приём событий «Корпоративного радара» / inbox CLI.

Канон радара (подтверждено Grok Bot, schema_version 1.1):
``/workspace/invest/news/events_latest.json`` — см. data/inbox/events/RADAR_CONTRACT.md.
CLI не подменяет типы радара на выдуманные ``disclosure_*``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import DATA_DIR

logger = logging.getLogger(__name__)

INBOX_DIR = DATA_DIR / "inbox" / "events"
PROCESSED_DIR = DATA_DIR / "processed" / "events"
REJECTED_DIR = DATA_DIR / "processed" / "rejected"
INBOX_ARCHIVE_DIR = DATA_DIR / "processed" / "inbox_archive"
BATCH_META_DIR = DATA_DIR / "processed" / "batches"

REQUIRED_FIELDS = ("event_type", "title", "url", "published_at", "source")
LEGACY_PREFIXES = ("disclosure_", "dividend_")

# Ключи settings.yaml → equity_rules (+ bond_rules.start), подтверждены RESULT радара.
RADAR_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "default_or_technical_default",
        "sanctions_or_regulatory_ban",
        "bankruptcy_or_license_revocation",
        "delisting_or_listing_change",
        "dividend_recommendation",
        "dividend_policy_change",
        "buyback_or_additional_issue",
        "major_transaction_or_m_and_a",
        "credit_rating_change",
        "financial_statements_ifrs",
        "financial_statements_ras",
        "operating_results",
        "guidance_change",
        "board_decision_other",
        "shareholder_meeting",
        "bond_offer_coupon_or_put",
        "operational_incident",
        "project_launch",
        "management_change_ceo_cfo",
        "management_change_routine",
        "litigation_major",
        "market_technical_notice",
        "press_release_marketing",
        "noise_holiday_award_charity",
        "put_offer_announced",
        "unknown",
    }
)

# Только для legacy CLI-формата (не радар). Не переписываем типы радара.
EVENT_TYPE_ALIASES: dict[str, str] = {
    "dividend": "dividend_declared",
    "dividend_declared": "dividend_declared",
    "dividend_forecast": "dividend_forecast",
    "dividend_ex_date": "dividend_ex_date",
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

BATCH_META_KEYS = (
    "schema_version",
    "generated_at",
    "coverage_from",
    "coverage_to",
    "generated_by",
    "is_test",
    "notes",
    "sources_checked",
)


class EventValidationError(ValueError):
    """Некорректное событие inbox."""


def canonicalize_event_type(value: Any) -> str:
    """Принять тип радара как есть или legacy-алиас; иначе EVENT_TYPE_UNMAPPED."""
    if value is None or (isinstance(value, str) and not str(value).strip()):
        raise EventValidationError(
            "missing event_type; radar/CLI must provide a mappable type "
            "(code=EVENT_TYPE_REQUIRED)"
        )
    et = str(value).strip()
    key = et.lower().replace(" ", "_").replace("-", "_")
    key = re.sub(r"_+", "_", key)

    if key in RADAR_EVENT_TYPES:
        return key
    if et in RADAR_EVENT_TYPES:
        return et
    if et.startswith(LEGACY_PREFIXES):
        return et
    if key in EVENT_TYPE_ALIASES:
        return EVENT_TYPE_ALIASES[key]
    if key.replace("_", "") in {"edisclosure"}:
        return "disclosure_filing"
    raise EventValidationError(
        f"unmapped event_type {value!r}; not in RADAR_EVENT_TYPES and not a "
        f"legacy disclosure_*/dividend_* type (code=EVENT_TYPE_UNMAPPED)"
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


def extract_batch_meta(raw: Any) -> dict[str, Any] | None:
    """Метаданные обёртки выпуска (schema_version, is_test, …)."""
    if not isinstance(raw, dict) or "events" not in raw:
        return None
    return {k: raw[k] for k in BATCH_META_KEYS if k in raw}


def normalize_event(
    raw: dict[str, Any],
    *,
    batch_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Адаптер радар → канон CLI + сохранение исходных полей и оценок."""
    if not isinstance(raw, dict):
        raise EventValidationError("event must be a dict")

    out: dict[str, Any] = dict(raw)

    if not out.get("url"):
        if raw.get("source_url"):
            out["url"] = raw["source_url"]
        elif raw.get("document_url"):
            out["url"] = raw["document_url"]
    if not out.get("source") and raw.get("source_name"):
        out["source"] = raw["source_name"]
    if not out.get("summary") and raw.get("factual_summary"):
        out["summary"] = raw["factual_summary"]
    if not out.get("company") and raw.get("issuer_name"):
        out["company"] = raw["issuer_name"]

    type_src = raw.get("event_type") or raw.get("type") or raw.get("category")
    out["event_type"] = canonicalize_event_type(type_src)

    # published_at и event_date у радара — разные поля; не подменять без нужды.
    if not out.get("published_at"):
        for key in ("disclosure_date", "date", "published_date"):
            if raw.get(key):
                out["published_at"] = raw[key]
                out["published_at_fallback_from"] = key
                break
        if not out.get("published_at") and raw.get("event_date"):
            # только если publication отсутствует — с явной меткой
            out["published_at"] = raw["event_date"]
            out["published_at_fallback_from"] = "event_date"

    if not out.get("title"):
        summary = out.get("summary") or raw.get("factual_summary")
        if summary:
            out["title"] = str(summary).strip()[:200]
        else:
            company = out.get("company") or raw.get("issuer_name") or "unknown"
            out["title"] = f"{company}: {out['event_type']}"

    out["radar_original"] = raw
    if "facts" in raw and "facts" not in out:
        out["facts"] = raw["facts"]

    if out.get("event_id") is None and raw.get("id") is not None:
        out["event_id"] = raw["id"]

    for score_key in (
        "equity_assessment",
        "bond_assessment",
        "equity_score",
        "bond_score",
        "score_equity",
        "score_bond",
        "scores",
        "impact_score",
        "severity_score",
        "materiality",
        "direction",
        "time_horizon",
        "duplicate_of",
        "novelty",
        "validation_status",
        "document_url",
        "event_date",
        "isin",
        "affected_securities",
        "confidence",
        "data_origin",
        "is_test",
    ):
        if score_key in raw:
            out[score_key] = raw[score_key]

    if batch_meta:
        out["radar_batch"] = batch_meta

    validate_event(out)
    return out


def validate_event(event: dict[str, Any]) -> None:
    """Проверить минимальную каноническую схему события."""
    if not isinstance(event, dict):
        raise EventValidationError("event must be a dict")
    for field in REQUIRED_FIELDS:
        val = event.get(field)
        if val is None or (isinstance(val, str) and not str(val).strip()):
            raise EventValidationError(f"missing required field: {field}")

    et = str(event["event_type"])
    if et in RADAR_EVENT_TYPES:
        return
    if any(et.startswith(p) for p in LEGACY_PREFIXES):
        return
    raise EventValidationError(
        f"event_type not allowed: {et!r} (code=EVENT_TYPE_UNMAPPED)"
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
        "equity_assessment",
        "bond_assessment",
        "equity_score",
        "bond_score",
        "scores",
        "materiality",
        "duplicate_of",
    )
    return all(a.get(k) == b.get(k) for k in keys)


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def _archive_inbox_file(path: Path) -> Path:
    """Сохранить исходный inbox-файл до удаления из inbox."""
    INBOX_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = INBOX_ARCHIVE_DIR / f"{path.stem}__{stamp}{path.suffix}"
    shutil.copy2(path, dest)
    return dest


def _should_skip_radar_semantics(item: dict[str, Any]) -> tuple[str, str] | None:
    """Пропуски по семантике радара (не reject): duplicate_of / ignore / novelty."""
    dup = item.get("duplicate_of")
    if dup is not None and str(dup).strip() and str(dup).lower() not in {"null", "none"}:
        return "skipped_duplicate_of", f"duplicate_of={dup}"
    if str(item.get("novelty") or "").lower() == "duplicate":
        return "skipped_novelty_duplicate", "novelty=duplicate"
    if str(item.get("materiality") or "").lower() == "ignore":
        return "skipped_materiality_ignore", "materiality=ignore"
    return None


def ingest_events(
    *,
    source_path: Path | str | None = None,
    keep_source: bool = True,
) -> dict[str, Any]:
    """Прочитать inbox (и/или ``source_path`` радара) → processed.

    ``source_path`` копируется в inbox без удаления оригинала (по умолчанию
    ``keep_source=True``). Файлы из inbox после обработки уходят в
    ``processed/inbox_archive/``, а не удаляются без следа.
    """
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    REJECTED_DIR.mkdir(parents=True, exist_ok=True)
    INBOX_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    BATCH_META_DIR.mkdir(parents=True, exist_ok=True)

    staged_from_source: list[Path] = []
    if source_path is not None:
        src = Path(source_path)
        if not src.exists():
            raise FileNotFoundError(f"radar source not found: {src}")
        dest = INBOX_DIR / src.name
        shutil.copy2(src, dest)
        staged_from_source.append(dest)
        if not keep_source:
            src.unlink(missing_ok=True)

    accepted = 0
    rejected = 0
    duplicate_skipped = 0
    conflict = 0
    skipped_semantics = 0
    details: list[dict[str, Any]] = []
    archives: list[str] = []

    for path in sorted(INBOX_DIR.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            items = extract_event_list(raw)
            batch_meta = extract_batch_meta(raw)
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

        if batch_meta:
            _write_json(BATCH_META_DIR / f"{path.stem}.json", batch_meta)

        for idx, item in enumerate(items):
            eid_hint = item.get("event_id") if isinstance(item, dict) else None
            skip = (
                _should_skip_radar_semantics(item)
                if isinstance(item, dict)
                else None
            )
            if skip:
                status, reason = skip
                skipped_semantics += 1
                details.append(
                    {
                        "file": path.name,
                        "index": idx,
                        "event_id": eid_hint,
                        "status": status,
                        "reason": reason,
                    }
                )
                continue

            try:
                event = normalize_event(item, batch_meta=batch_meta)
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
                        "event_type": event.get("event_type"),
                    }
                )
            except (EventValidationError, OSError, TypeError, ValueError) as e:
                rejected += 1
                rej = REJECTED_DIR / f"{path.stem}_{idx}__rejected.json"
                _write_json(
                    rej,
                    {
                        "error": str(e),
                        "index": idx,
                        "event_id": eid_hint,
                        "incoming": item,
                    },
                )
                details.append(
                    {
                        "file": path.name,
                        "index": idx,
                        "event_id": eid_hint,
                        "status": "rejected",
                        "error": str(e),
                    }
                )
                logger.warning("Rejected event %s[%s]: %s", path.name, idx, e)

        archived = _archive_inbox_file(path)
        archives.append(str(archived))
        path.unlink(missing_ok=True)

    partial = rejected > 0
    return {
        "accepted": accepted,
        "rejected": rejected,
        "duplicate_skipped": duplicate_skipped,
        "conflict": conflict,
        "skipped_semantics": skipped_semantics,
        "partial": partial,
        "ok": not partial,
        "inbox": str(INBOX_DIR),
        "processed": str(PROCESSED_DIR),
        "inbox_archive": str(INBOX_ARCHIVE_DIR),
        "archives": archives,
        "source_path": str(source_path) if source_path else None,
        "staged_from_source": [str(p) for p in staged_from_source],
        "details": details,
    }
