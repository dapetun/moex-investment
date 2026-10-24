"""Журнал запусков CLI (машиночитаемый JSON в data/outbox/runs/)."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import DATA_DIR

logger = logging.getLogger(__name__)

RUNS_DIR = DATA_DIR / "outbox" / "runs"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_path(run_id: str) -> Path:
    return RUNS_DIR / f"{run_id}.json"


def start_run(command: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Создать запись запуска со статусом running."""
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    record = {
        "run_id": run_id,
        "command": command,
        "params": params or {},
        "status": "running",
        "started_at": _now_iso(),
        "finished_at": None,
        "error": None,
        "result": None,
    }
    path = _run_path(run_id)
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    logger.info("Run started: %s (%s)", run_id, command)
    return record


def finish_run(
    run_id: str,
    status: str,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """Завершить запуск (ok / error / blocked)."""
    path = _run_path(run_id)
    if not path.exists():
        raise FileNotFoundError(f"run not found: {run_id}")

    record = json.loads(path.read_text(encoding="utf-8"))
    record["status"] = status
    record["finished_at"] = _now_iso()
    record["result"] = result
    record["error"] = error
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    logger.info("Run finished: %s status=%s", run_id, status)
    return record


def load_run(run_id: str) -> dict[str, Any]:
    """Загрузить запись запуска."""
    path = _run_path(run_id)
    if not path.exists():
        raise FileNotFoundError(f"run not found: {run_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def list_runs() -> list[str]:
    """Список run_id (по имени файла, новые в конце при сортировке)."""
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(p.stem for p in RUNS_DIR.glob("*.json"))
