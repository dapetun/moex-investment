"""Сборка пакета артефактов CLI для одноразового задания Аналитику.

Не пересчитывает веса и не подменяет solver — только собирает уже
полученные результаты optimize/compare/ingest/QC.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import events as events_mod
from .config import DATA_DIR
from .portfolio_state import holdings_path, load_holdings
from .run_journal import RUNS_DIR

logger = logging.getLogger(__name__)

BUNDLE_SCHEMA = "moex_analyst_bundle.v1"
DEFAULT_BUNDLE_DIR = DATA_DIR / "outbox" / "analyst_bundles"


def _read_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _list_event_summaries(processed_dir: Path, *, limit: int = 50) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not processed_dir.exists():
        return out
    for path in sorted(processed_dir.glob("*.json"))[:limit]:
        try:
            ev = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(ev, dict):
            continue
        eq = ev.get("equity_assessment") if isinstance(ev.get("equity_assessment"), dict) else {}
        bond = ev.get("bond_assessment") if isinstance(ev.get("bond_assessment"), dict) else {}
        materiality = eq.get("materiality") if eq else ev.get("materiality")
        out.append(
            {
                "event_id": ev.get("event_id"),
                "ticker": ev.get("ticker"),
                "event_type": ev.get("event_type"),
                "event_date": ev.get("event_date"),
                "published_at": ev.get("published_at"),
                "source": ev.get("source") or ev.get("source_name"),
                "url": ev.get("url") or ev.get("source_url"),
                "title": ev.get("title") or ev.get("summary"),
                "factual_summary": ev.get("factual_summary"),
                "company": ev.get("company") or ev.get("issuer_name"),
                "materiality": materiality,
                "equity_assessment": {
                    "materiality": eq.get("materiality"),
                    "direction": eq.get("direction"),
                    "confidence": eq.get("confidence"),
                    "rationale": eq.get("rationale"),
                }
                if eq
                else None,
                "bond_assessment": {
                    "materiality": bond.get("materiality"),
                    "direction": bond.get("direction"),
                    "confidence": bond.get("confidence"),
                    "rationale": bond.get("rationale"),
                }
                if bond
                else None,
                "path": str(path),
            }
        )
    return out


def build_analyst_bundle(
    *,
    target_path: Path | None = None,
    compare_payload: dict[str, Any] | None = None,
    validation_payload: dict[str, Any] | None = None,
    ingest_payload: dict[str, Any] | None = None,
    run_ids: list[str] | None = None,
    processed_dir: Path | None = None,
    history_dir: Path | None = None,
    synthetic: bool = True,
    notes: str | None = None,
) -> dict[str, Any]:
    """Собрать структурированный JSON для Аналитика портфеля."""
    holdings = load_holdings()
    target_file = target_path or (DATA_DIR / "outbox" / "last_target.json")
    target = _read_json(Path(target_file))

    # Пути events.* читать в runtime — apply_event_dirs может переключить каталоги.
    proc = Path(processed_dir) if processed_dir else events_mod.PROCESSED_DIR
    hist = Path(history_dir) if history_dir else events_mod.HISTORY_DIR

    runs: list[dict[str, Any]] = []
    for rid in run_ids or []:
        path = RUNS_DIR / f"{rid}.json"
        rec = _read_json(path)
        if rec is not None:
            runs.append({"run_id": rid, "path": str(path), "record": rec})

    events = _list_event_summaries(proc)
    history_count = len(list(hist.glob("*.json"))) if hist.exists() else 0

    bundle: dict[str, Any] = {
        "schema": BUNDLE_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "synthetic": synthetic,
        "disclaimer": (
            "Синтетические/тестовые данные. Не является инвестиционной "
            "рекомендацией по реальному портфелю. Количественные поля "
            "должны совпадать с артефактами CLI; качественные оценки "
            "радара — отдельный блок без пересчёта ожидаемой доходности."
        ),
        "holdings": {
            "path": str(holdings_path()),
            "file_status": holdings.get("file_status"),
            "as_of": holdings.get("as_of"),
            "cash": holdings.get("cash"),
            "positions": holdings.get("positions"),
            "weight_sum_policy": holdings.get("weight_sum_policy"),
            "weight_normalized_on_load": holdings.get("weight_normalized_on_load"),
            "weight_sum_before": holdings.get("weight_sum_before"),
        },
        "validation": validation_payload,
        "target": {
            "path": str(target_file),
            "payload": target,
        },
        "compare": compare_payload,
        "events": {
            "processed_dir": str(proc),
            "history_dir": str(hist),
            "history_files": history_count,
            "items": events,
            "ingest": ingest_payload,
        },
        "runs": runs,
        "notes": notes,
        "analyst_instructions": [
            "Разделяй числа CLI (weights, drift, QC) и качественные оценки радара.",
            "Ссылайся на event_id, run_id и пути артефактов.",
            "Не выдумывай доходности, цены и торговые рекомендации.",
            "Явно укажи ограничения синтетических данных.",
        ],
    }
    return bundle


def write_analyst_bundle(
    bundle: dict[str, Any],
    *,
    out_dir: Path | None = None,
    bundle_id: str | None = None,
) -> dict[str, Path]:
    """Записать bundle JSON (+ краткий MD-указатель)."""
    directory = Path(out_dir) if out_dir else DEFAULT_BUNDLE_DIR
    directory.mkdir(parents=True, exist_ok=True)
    bid = bundle_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = directory / f"{bid}.json"
    md_path = directory / f"{bid}.md"
    json_path.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    lines = [
        f"# Analyst bundle `{bid}`",
        "",
        f"- schema: `{bundle.get('schema')}`",
        f"- synthetic: `{bundle.get('synthetic')}`",
        f"- holdings status: `{((bundle.get('holdings') or {}).get('file_status'))}`",
        f"- events: `{len(((bundle.get('events') or {}).get('items') or []))}`",
        f"- JSON: `{json_path}`",
        "",
        str(bundle.get("disclaimer") or ""),
        "",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Analyst bundle written: %s", json_path)
    return {"json": json_path, "md": md_path}
