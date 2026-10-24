"""Машиночитаемые и Markdown-отчёты прогона."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .config import DATA_DIR

logger = logging.getLogger(__name__)

REPORTS_DIR = DATA_DIR / "outbox" / "reports"


def write_report(
    run_id: str,
    title: str,
    payload: dict[str, Any],
) -> dict[str, Path]:
    """Записать ``{run_id}.json`` и ``{run_id}.md``."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORTS_DIR / f"{run_id}.json"
    md_path = REPORTS_DIR / f"{run_id}.md"

    doc = {"run_id": run_id, "title": title, **payload}
    json_path.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )

    lines = [
        f"# {title}",
        "",
        f"- run_id: `{run_id}`",
        f"- success: `{payload.get('success')}`",
        f"- source: `{payload.get('source')}`",
        "",
        "## Weights",
        "",
    ]
    weights = payload.get("weights") or {}
    if weights:
        lines.append("| ticker | weight |")
        lines.append("|---|---|")
        for t, w in sorted(weights.items(), key=lambda x: -float(x[1])):
            lines.append(f"| {t} | {float(w):.6f} |")
    else:
        lines.append("_no weights_")

    if payload.get("compare"):
        lines.extend(["", "## Compare", "", "```json", json.dumps(payload["compare"], ensure_ascii=False, indent=2), "```"])

    if payload.get("notes"):
        lines.extend(["", "## Notes", "", str(payload["notes"])])

    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Report written: %s / %s", json_path, md_path)
    return {"json": json_path, "md": md_path}
