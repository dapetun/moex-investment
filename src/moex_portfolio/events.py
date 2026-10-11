"""Валидация и приём событий «Корпоративного радара» / inbox CLI.

Канон радара (подтверждено Grok Bot, schema_version 1.1):
``/workspace/invest/news/events_latest.json`` — см. data/inbox/events/RADAR_CONTRACT.md.
CLI не подменяет типы радара на выдуманные ``disclosure_*``.

Повторная оценка того же события (тот же event_id + идентичность) принимается
как новая версия: предыдущая копия уходит в history, current обновляется.
EVENT_CONFLICT — только при смене идентичности или если её нельзя подтвердить.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from . import config as _config
from .config import DATA_DIR

logger = logging.getLogger(__name__)

INBOX_DIR = DATA_DIR / "inbox" / "events"
PROCESSED_DIR = DATA_DIR / "processed" / "events"
HISTORY_DIR = DATA_DIR / "processed" / "events_history"
REJECTED_DIR = DATA_DIR / "processed" / "rejected"
INBOX_ARCHIVE_DIR = DATA_DIR / "processed" / "inbox_archive"
BATCH_META_DIR = DATA_DIR / "processed" / "batches"

# Тестовые выпуски (is_test / TEST-EV-) пишутся только в *_test пути.
TEST_EVENT_ID_PREFIX = "TEST-EV-"
_EVENT_DATA_ROOT = DATA_DIR


def apply_event_dirs(
    *,
    test_mode: bool = False,
    data_root: Path | None = None,
) -> dict[str, Path]:
    """Переключить каталоги inbox/processed (prod vs test).

    В тестовом режиме все артефакты уходят в отдельные ``*_test`` пути,
    чтобы не загрязнять обычное ``processed/events/``.
    """
    global INBOX_DIR, PROCESSED_DIR, HISTORY_DIR, REJECTED_DIR
    global INBOX_ARCHIVE_DIR, BATCH_META_DIR, _EVENT_DATA_ROOT

    # ``config.DATA_DIR`` читаем динамически — тесты могут monkeypatch'ить.
    root = Path(data_root) if data_root is not None else Path(_config.DATA_DIR)
    _EVENT_DATA_ROOT = root
    if test_mode:
        INBOX_DIR = root / "inbox" / "events_test"
        PROCESSED_DIR = root / "processed" / "events_test"
        HISTORY_DIR = root / "processed" / "events_history_test"
        REJECTED_DIR = root / "processed" / "rejected_test"
        INBOX_ARCHIVE_DIR = root / "processed" / "inbox_archive_test"
        BATCH_META_DIR = root / "processed" / "batches_test"
    else:
        INBOX_DIR = root / "inbox" / "events"
        PROCESSED_DIR = root / "processed" / "events"
        HISTORY_DIR = root / "processed" / "events_history"
        REJECTED_DIR = root / "processed" / "rejected"
        INBOX_ARCHIVE_DIR = root / "processed" / "inbox_archive"
        BATCH_META_DIR = root / "processed" / "batches"
    return {
        "inbox": INBOX_DIR,
        "processed": PROCESSED_DIR,
        "history": HISTORY_DIR,
        "rejected": REJECTED_DIR,
        "inbox_archive": INBOX_ARCHIVE_DIR,
        "batches": BATCH_META_DIR,
    }


def event_id_is_test(event_id: object) -> bool:
    """True, если event_id в тестовом namespace TEST-EV-."""
    return isinstance(event_id, str) and event_id.startswith(TEST_EVENT_ID_PREFIX)


def classify_release(raw: Any) -> str:
    """Классифицировать выпуск: ``test`` | ``prod`` | ``mixed``.

    Тест: ``is_test: true`` на обёртке и/или все event_id с префиксом TEST-EV-.
    Mixed: часть id тестовые, часть нет, при ``is_test`` не true.
    """
    if not isinstance(raw, dict):
        return "prod"
    batch_test = raw.get("is_test") is True
    try:
        items = extract_event_list(raw)
    except EventValidationError:
        return "test" if batch_test else "prod"

    ids = [
        item.get("event_id")
        for item in items
        if isinstance(item, dict) and item.get("event_id")
    ]
    if not ids:
        return "test" if batch_test else "prod"

    test_flags = [event_id_is_test(i) for i in ids]
    if batch_test:
        return "test"
    if all(test_flags):
        return "test"
    if any(test_flags):
        return "mixed"
    return "prod"


class EventIngestGateError(ValueError):
    """Отказ ingest до записи в хранилище (тестовый/боевой режим)."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code

REQUIRED_FIELDS = ("event_type", "title", "url", "published_at", "source")
LEGACY_PREFIXES = ("disclosure_", "dividend_")

# Ключи settings.yaml → equity_rules (+ bond_rules.start), подтверждены RESULT радара.
EQUITY_EVENT_TYPES: frozenset[str] = frozenset(
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
        "unknown",
    }
)

# bond_rules.start — только bond-only ключи (RESULT cur-20261010-1936 §2.2).
# Пересечения с equity_rules уже в EQUITY_EVENT_TYPES.
BOND_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "coupon_payment_missed_or_delayed",
        "coupon_payment_regular",
        "principal_redemption_scheduled",
        "put_offer_announced",
        "call_offer_early_redemption",
        "rating_action_downgrade",
        "rating_action_upgrade",
        "rating_action_affirmed",
        "issue_terms_change",
        "covenant_breach_or_waiver",
        "collateral_or_guarantee_change",
        "leverage_change_material",
        "liquidity_stress",
        "refinancing_risk",
        "dividend_large",
    }
)

RADAR_EVENT_TYPES: frozenset[str] = EQUITY_EVENT_TYPES | BOND_EVENT_TYPES

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

# Первичный ключ upsert — event_id (RESULT 1936 §3.3).
# Жёсткая согласованность: смена → EVENT_IDENTITY_MISMATCH.
HARD_IDENTITY_KEYS = (
    "ticker",
    "isin",
    "event_type",
    "event_date",
)
# Мягкие поля: смена при том же event_id → ревизия с флагом, не conflict.
# issuer_name — мягкое: радар может переписать сокращение/кавычки (RESULT 2002).
SOFT_REVISION_KEYS = (
    "document_url",
    "source_url",
    "published_at",
    "url",
    "issuer_name",
)

# Поля, изменение которых при той же идентичности = ревизия (update), не conflict.
_CONTENT_COMPARE_KEYS = (
    "event_type",
    "title",
    "url",
    "published_at",
    "source",
    "company",
    "summary",
    "facts",
    "equity_assessment",
    "bond_assessment",
    "equity_score",
    "bond_score",
    "scores",
    "materiality",
    "direction",
    "time_horizon",
    "impact_rationale",
    "duplicate_of",
    "novelty",
    "priority_reason",
    "validation_status",
    "revision",
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


def parse_published_at(value: Any) -> str:
    """Требовать ISO date или datetime; ``unknown``/пусто — reject.

    Не подменяет дату публикации датой события.
    """
    if value is None:
        raise EventValidationError(
            "missing published_at; require ISO date or datetime "
            "(code=PUBLISHED_AT_INVALID)"
        )
    s = str(value).strip()
    if not s or s.lower() in {"unknown", "null", "none", "n/a", "-"}:
        raise EventValidationError(
            f"invalid published_at {value!r}; require ISO date or datetime, "
            f"not unknown/empty (code=PUBLISHED_AT_INVALID)"
        )
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        try:
            date.fromisoformat(s)
        except ValueError as e:
            raise EventValidationError(
                f"invalid published_at date {value!r} (code=PUBLISHED_AT_INVALID)"
            ) from e
        return s
    # datetime: допускаем Z и смещения
    normalized = s.replace("Z", "+00:00") if s.endswith("Z") else s
    try:
        datetime.fromisoformat(normalized)
    except ValueError as e:
        raise EventValidationError(
            f"invalid published_at {value!r}; require ISO date or datetime "
            f"(code=PUBLISHED_AT_INVALID)"
        ) from e
    return s


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

    # published_at и event_date — разные поля. Пустая/unknown строка → reject
    # (не подменять event_date). Fallback только если ключ published_at отсутствует.
    if "published_at" in raw:
        out["published_at"] = parse_published_at(raw.get("published_at"))
    elif not out.get("published_at"):
        for key in ("disclosure_date", "date", "published_date"):
            if raw.get(key):
                out["published_at"] = parse_published_at(raw[key])
                out["published_at_fallback_from"] = key
                break
        if not out.get("published_at"):
            raise EventValidationError(
                "missing published_at; require ISO date or datetime "
                "(code=PUBLISHED_AT_INVALID)"
            )
    else:
        out["published_at"] = parse_published_at(out["published_at"])

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
        "revision",
        "impact_rationale",
        "priority_reason",
        "ticker",
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

    parse_published_at(event["published_at"])

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


def _norm_id_field(key: str, value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in {"null", "none", "unknown", ""}:
        return None
    if key in {"ticker", "isin", "event_type"}:
        return s.upper() if key != "event_type" else s.lower()
    return s


def _field_from_event(event: dict[str, Any], key: str) -> Any:
    if event.get(key) is not None:
        return event.get(key)
    orig = event.get("radar_original")
    if isinstance(orig, dict) and orig.get(key) is not None:
        return orig.get(key)
    aliases = {
        "issuer_name": ("company",),
        "source_url": ("url", "source"),
    }
    for alt in aliases.get(key, ()):
        if event.get(alt) is not None:
            return event.get(alt)
    return None


def hard_identity_mismatch(
    existing: dict[str, Any], incoming: dict[str, Any]
) -> list[str]:
    """Поля жёсткой согласованности, разошедшиеся при том же event_id."""
    mismatched: list[str] = []
    for key in HARD_IDENTITY_KEYS:
        va = _norm_id_field(key, _field_from_event(existing, key))
        vb = _norm_id_field(key, _field_from_event(incoming, key))
        if va is None or vb is None:
            continue
        if va != vb:
            mismatched.append(key)
    return mismatched


def soft_identity_flags(
    existing: dict[str, Any], incoming: dict[str, Any]
) -> list[str]:
    """Мягкие поля, изменившиеся при ревизии (флаг, не conflict)."""
    changed: list[str] = []
    for key in SOFT_REVISION_KEYS:
        va = _norm_id_field(key, _field_from_event(existing, key))
        vb = _norm_id_field(key, _field_from_event(incoming, key))
        if va is None and vb is None:
            continue
        if va != vb:
            changed.append(key)
    return changed


def _events_equivalent(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Полное совпадение существенных полей (точный повтор пакета)."""
    keys = (
        ("event_id",)
        + HARD_IDENTITY_KEYS
        + SOFT_REVISION_KEYS
        + _CONTENT_COMPARE_KEYS
    )
    return all(a.get(k) == b.get(k) for k in keys)


def _content_diff_keys(existing: dict[str, Any], incoming: dict[str, Any]) -> list[str]:
    changed: list[str] = []
    for key in _CONTENT_COMPARE_KEYS:
        if existing.get(key) != incoming.get(key):
            changed.append(key)
    return changed


def _revision_number(event: dict[str, Any]) -> int | None:
    rev = event.get("revision")
    if isinstance(rev, dict) and rev.get("number") is not None:
        try:
            return int(rev["number"])
        except (TypeError, ValueError):
            return None
    return None


def _batch_generated_at(event: dict[str, Any]) -> str | None:
    batch = event.get("radar_batch")
    if isinstance(batch, dict):
        g = batch.get("generated_at")
        if g is not None and str(g).strip():
            return str(g).strip()
    return None


def freshness_decision(
    existing: dict[str, Any], incoming: dict[str, Any]
) -> tuple[str, str, bool]:
    """Решение по свежести: allow | stale | conflict.

    Returns:
        (decision, reason, freshness_guaranteed)
    """
    er = _revision_number(existing)
    ir = _revision_number(incoming)
    if er is not None and ir is not None:
        if ir < er:
            return "stale", f"stale_revision:{ir}<{er}", True
        if ir > er:
            return "allow", f"revision:{ir}>{er}", True
        # одинаковый revision.number — смотрим batch; иначе conflict

    eg = _batch_generated_at(existing)
    ig = _batch_generated_at(incoming)
    if eg and ig:
        if ig < eg:
            return "stale", f"stale_batch:{ig}<{eg}", True
        if ig > eg:
            return "allow", f"batch_generated_at:{ig}>{eg}", True
        # равные метки при разном содержимом → conflict (RESULT 1936 §3.4.2)
        return "conflict", "equal_freshness_different_content", True

    if er is not None and ir is not None and ir == er:
        return "conflict", "equal_revision_different_content", True

    return "allow", "freshness_unknown", False


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def _atomic_write_json(path: Path, data: Any) -> None:
    """Записать JSON атомарно (temp + replace), без потери прежнего файла."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.stem}_", suffix=".tmp", dir=str(path.parent)
    )
    tmp_path = Path(tmp_name)
    try:
        with open(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2, default=str)
            fh.write("\n")
        tmp_path.replace(path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def _archive_history(existing: dict[str, Any], dest_name: str) -> Path:
    """Сохранить предыдущую версию до обновления current."""
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stem = Path(dest_name).stem
    hist = HISTORY_DIR / f"{stem}__{stamp}.json"
    _atomic_write_json(hist, existing)
    return hist


def _archive_inbox_file(path: Path) -> Path:
    """Сохранить исходный inbox-файл до удаления из inbox."""
    INBOX_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = INBOX_ARCHIVE_DIR / f"{path.stem}__{stamp}{path.suffix}"
    # уникальность внутри секунды
    if dest.exists():
        dest = INBOX_ARCHIVE_DIR / f"{path.stem}__{stamp}_{os_getpid()}{path.suffix}"
    shutil.copy2(path, dest)
    return dest


def os_getpid() -> int:
    import os

    return os.getpid()


def _should_skip_radar_semantics(item: dict[str, Any]) -> tuple[str, str] | None:
    """Пропуски по семантике радара (не reject).

    ``novelty=clarification`` с ``duplicate_of`` — не skip (RESULT 1936 §3.3):
    это уточнение, не дубль. Skip только ``novelty=duplicate`` и
    ``materiality=ignore``. Пустой ``duplicate_of`` без novelty=duplicate
    больше не отбрасывает событие.
    """
    novelty = str(item.get("novelty") or "").lower()
    if novelty == "duplicate":
        dup = item.get("duplicate_of")
        return "skipped_novelty_duplicate", f"novelty=duplicate duplicate_of={dup}"
    if str(item.get("materiality") or "").lower() == "ignore":
        return "skipped_materiality_ignore", "materiality=ignore"
    # materiality/novelty unknown — не skip и не downgrade в ignore/low
    return None


def _gate_release_class(
    kind: str,
    *,
    test_mode: bool,
    label: str,
) -> None:
    """Отклонить недопустимую комбинацию test/prod до записи в хранилище."""
    if kind == "mixed":
        raise EventIngestGateError(
            f"{label}: mixed test/prod event_id in one release "
            f"(code=EVENT_TEST_PROD_MIXED)",
            code="EVENT_TEST_PROD_MIXED",
        )
    if kind == "test" and not test_mode:
        raise EventIngestGateError(
            f"{label}: test release requires --test-events "
            f"(is_test and/or {TEST_EVENT_ID_PREFIX}* event_id); "
            f"refusing to write into production processed/events "
            f"(code=EVENT_TEST_MODE_REQUIRED)",
            code="EVENT_TEST_MODE_REQUIRED",
        )
    if kind == "prod" and test_mode:
        raise EventIngestGateError(
            f"{label}: production release cannot be ingested with --test-events "
            f"(code=EVENT_PROD_IN_TEST_MODE)",
            code="EVENT_PROD_IN_TEST_MODE",
        )


def ingest_events(
    *,
    source_path: Path | str | None = None,
    keep_source: bool = True,
    test_mode: bool = False,
    data_root: Path | str | None = None,
) -> dict[str, Any]:
    """Прочитать inbox (и/или ``source_path`` радара) → processed.

    ``source_path`` копируется в inbox без удаления оригинала (по умолчанию
    ``keep_source=True``). Файлы из inbox после обработки уходят в
    ``processed/inbox_archive/``, а не удаляются без следа.

    Тестовые выпуски (``is_test: true`` и/или ``TEST-EV-*``) по умолчанию
    запрещены в обычном ``processed/events/``. Нужен ``test_mode=True``
    (CLI: ``--test-events``) — тогда используются отдельные ``*_test`` пути.

    Повтор event_id с той же идентичностью и изменившимися оценками →
    ``updated`` (история + новая current). Смена идентичности → ``conflict``.
    """
    env_root = os.environ.get("MOEX_EVENT_DATA_ROOT", "").strip()
    root = Path(data_root) if data_root is not None else (
        Path(env_root) if env_root else None
    )

    # Переключаем каталоги при test_mode / data_root / MOEX_EVENT_DATA_ROOT.
    # Иначе сохраняем текущие пути (monkeypatch в тестах).
    if test_mode or root is not None:
        apply_event_dirs(test_mode=test_mode, data_root=root)

    # Классификация ДО создания/записи в prod-хранилище.
    if source_path is not None:
        src = Path(source_path)
        if not src.exists():
            raise FileNotFoundError(f"radar source not found: {src}")
        try:
            raw_src = json.loads(src.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise EventIngestGateError(
                f"source is not valid JSON: {e} (code=EVENT_SOURCE_INVALID_JSON)",
                code="EVENT_SOURCE_INVALID_JSON",
            ) from e
        kind = classify_release(raw_src)
        _gate_release_class(kind, test_mode=test_mode, label=f"source {src.name}")

    # Предпросмотр inbox без записи в processed.
    if INBOX_DIR.exists():
        for path in sorted(INBOX_DIR.glob("*.json")):
            try:
                raw_inbox = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue  # битые файлы отклонит основной цикл в rejected
            kind = classify_release(raw_inbox)
            _gate_release_class(
                kind, test_mode=test_mode, label=f"inbox {path.name}"
            )

    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    REJECTED_DIR.mkdir(parents=True, exist_ok=True)
    INBOX_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    BATCH_META_DIR.mkdir(parents=True, exist_ok=True)

    staged_from_source: list[Path] = []
    if source_path is not None:
        src = Path(source_path)
        dest = INBOX_DIR / src.name
        shutil.copy2(src, dest)
        staged_from_source.append(dest)
        if not keep_source:
            src.unlink(missing_ok=True)

    accepted = 0
    updated = 0
    rejected = 0
    duplicate_skipped = 0
    stale_skipped = 0
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

                    eid_a = _norm_id_field("event_id", existing.get("event_id"))
                    eid_b = _norm_id_field("event_id", event.get("event_id"))
                    same_id = bool(eid_a and eid_b and eid_a == eid_b)

                    if same_id:
                        hard_mis = hard_identity_mismatch(existing, event)
                        if hard_mis:
                            conflict += 1
                            rejected += 1
                            rej = (
                                REJECTED_DIR
                                / f"{dest.stem}__conflict__{path.stem}_{idx}.json"
                            )
                            _write_json(
                                rej,
                                {
                                    "error": "hard identity fields diverged for same "
                                    "event_id",
                                    "code": "EVENT_IDENTITY_MISMATCH",
                                    "mismatched_fields": hard_mis,
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
                                    "error": "EVENT_IDENTITY_MISMATCH",
                                    "mismatched_fields": hard_mis,
                                }
                            )
                            continue

                        decision, fresh_reason, guaranteed = freshness_decision(
                            existing, event
                        )
                        if decision == "stale":
                            stale_skipped += 1
                            details.append(
                                {
                                    "file": path.name,
                                    "index": idx,
                                    "event_id": event.get("event_id"),
                                    "dest": dest_name,
                                    "status": "stale_skipped",
                                    "reason": fresh_reason,
                                }
                            )
                            continue
                        if decision == "conflict":
                            conflict += 1
                            rejected += 1
                            rej = (
                                REJECTED_DIR
                                / f"{dest.stem}__conflict__{path.stem}_{idx}.json"
                            )
                            _write_json(
                                rej,
                                {
                                    "error": "equal freshness with different content",
                                    "code": "EVENT_EQUAL_FRESHNESS_CONFLICT",
                                    "reason": fresh_reason,
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
                                    "error": "EVENT_EQUAL_FRESHNESS_CONFLICT",
                                    "reason": fresh_reason,
                                }
                            )
                            continue

                        changed = _content_diff_keys(existing, event)
                        soft_flags = soft_identity_flags(existing, event)
                        try:
                            hist_path = _archive_history(existing, dest_name)
                            _atomic_write_json(dest, event)
                        except OSError as e:
                            rejected += 1
                            details.append(
                                {
                                    "file": path.name,
                                    "index": idx,
                                    "event_id": event.get("event_id"),
                                    "dest": dest_name,
                                    "status": "rejected",
                                    "error": f"update_write_failed: {e}",
                                    "code": "EVENT_UPDATE_IO",
                                }
                            )
                            logger.warning(
                                "Failed to update event %s: %s", dest_name, e
                            )
                            continue

                        updated += 1
                        details.append(
                            {
                                "file": path.name,
                                "index": idx,
                                "event_id": event.get("event_id"),
                                "dest": dest_name,
                                "status": "updated",
                                "changed_fields": changed,
                                "soft_identity_changed": soft_flags,
                                "history": str(hist_path),
                                "freshness": fresh_reason,
                                "freshness_guaranteed": guaranteed,
                            }
                        )
                        continue

                    # тот же файл без общего event_id (хэш-имя) или коллизия —
                    # не перезаписываем
                    conflict += 1
                    rejected += 1
                    rej = REJECTED_DIR / f"{dest.stem}__conflict__{path.stem}_{idx}.json"
                    _write_json(
                        rej,
                        {
                            "error": "processed slot exists with different event_id "
                            "or unconfirmed id",
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

                _atomic_write_json(dest, event)
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
        "updated": updated,
        "rejected": rejected,
        "duplicate_skipped": duplicate_skipped,
        "stale_skipped": stale_skipped,
        "conflict": conflict,
        "skipped_semantics": skipped_semantics,
        "partial": partial,
        "ok": not partial,
        "test_mode": test_mode,
        "inbox": str(INBOX_DIR),
        "processed": str(PROCESSED_DIR),
        "history": str(HISTORY_DIR),
        "inbox_archive": str(INBOX_ARCHIVE_DIR),
        "archives": archives,
        "source_path": str(source_path) if source_path else None,
        "staged_from_source": [str(p) for p in staged_from_source],
        "details": details,
    }
