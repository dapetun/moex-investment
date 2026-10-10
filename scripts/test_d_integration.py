#!/usr/bin/env python3
"""Сквозной Test D (синтетика, offline). Запуск из корня репо:

    MOEX_ISS_ENABLED=false MOEX_DATA_SOURCE=fixture \\
      python scripts/test_d_integration.py

Не трогает /workspace/invest, реальные holdings, optimizer.yaml.
Печатает JSON-отчёт в stdout; код выхода 0 только если все шаги ok.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_EVENTS = ROOT / "tests" / "fixtures" / "radar_events_latest_v1_1_pilot.json"
FIXTURE_CSV = ROOT / "tests" / "fixtures" / "synthetic_analyst_portfolio.csv"


def _run(cmd: list[str], cwd: Path, env: dict[str, str]) -> tuple[int, str, str]:
    p = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return p.returncode, p.stdout, p.stderr


def main() -> int:
    os.chdir(ROOT)
    sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()

    work = Path(tempfile.mkdtemp(prefix="moex-test-d-"))
    report: dict = {
        "test": "D",
        "sha": sha,
        "work_dir": str(work),
        "steps": [],
        "passed": [],
        "failed": [],
        "unchecked": [
            "live MOEX ISS",
            "broker orders",
            "real holdings /workspace/invest portfolio.csv",
            "bot profile/skill changes",
            "optimizer.yaml enablement",
        ],
    }

    def note(step: str, ok: bool, **extra: object) -> None:
        entry = {"step": step, "ok": ok, **extra}
        report["steps"].append(entry)
        (report["passed"] if ok else report["failed"]).append(step)

    env = os.environ.copy()
    env["MOEX_ISS_ENABLED"] = "false"
    env["MOEX_DATA_SOURCE"] = "fixture"
    py = sys.executable

    # изолируем data/* через временный clone структуры: копируем только нужное
    # и ставим PYTHONPATH на src; DATA_DIR зашит в пакет — работаем в clone.
    clone = work / "repo"
    subprocess.check_call(
        ["git", "clone", "--quiet", str(ROOT), str(clone)],
        cwd=work,
    )
    subprocess.check_call(
        ["git", "checkout", "--quiet", sha],
        cwd=clone,
    )
    # editable install in venv would be heavy; use PYTHONPATH
    env["PYTHONPATH"] = str(clone / "src") + os.pathsep + env.get("PYTHONPATH", "")

    # 1) adapt portfolio → holdings (write in clone data/)
    code, out, err = _run(
        [
            py,
            "-m",
            "moex_portfolio",
            "adapt-portfolio",
            "--csv",
            str(FIXTURE_CSV),
            "--panel-tickers",
            "TSTA,TSTB,TSTC,AAA,BBB,CCC",
            "--write-holdings",
        ],
        clone,
        env,
    )
    if code != 0:
        note(
            "adapt-portfolio",
            False,
            exit=code,
            stderr=err[:500],
            stdout=out[:300],
        )
    else:
        payload = json.loads(out)
        note(
            "adapt-portfolio",
            True,
            exit=code,
            n_positions=len(payload.get("positions", [])),
            file_status=payload.get("file_status"),
        )
        # для compare/optimize дальше нужны веса на fixture-панели
        hp = clone / "data" / "portfolio" / "holdings.json"
        if hp.exists():
            h = json.loads(hp.read_text(encoding="utf-8"))
            # если адаптер записал TSTA…, дополним AAA/BBB/CCC для offline compare
            if not any(p.get("ticker") in {"AAA", "BBB", "CCC"} for p in h.get("positions", [])):
                h = {
                    "as_of": "2026-10-10",
                    "cash": 0.0,
                    "positions": [
                        {"ticker": "AAA", "weight": 0.4},
                        {"ticker": "BBB", "weight": 0.35},
                        {"ticker": "CCC", "weight": 0.25},
                    ],
                }
                hp.write_text(json.dumps(h, indent=2) + "\n", encoding="utf-8")

    # 2) ingest pilot + revision
    src = work / "events_latest.json"
    shutil.copy2(FIXTURE_EVENTS, src)
    code, out, err = _run(
        [py, "-m", "moex_portfolio", "ingest-events", "--source", str(src)],
        clone,
        env,
    )
    body = out if out.strip() else err
    try:
        ingest1 = json.loads(body)
    except json.JSONDecodeError:
        ingest1 = {"raw_out": out, "raw_err": err}
    note(
        "ingest-new",
        code == 0 and ingest1.get("accepted", 0) >= 1,
        exit=code,
        accepted=ingest1.get("accepted"),
        skipped_semantics=ingest1.get("skipped_semantics"),
        source_exists=src.exists(),
    )

    # revision of SBER-like first accepted event if present
    processed = clone / "data" / "processed" / "events"
    targets = sorted(processed.glob("EV-*.json"))
    if targets:
        cur = json.loads(targets[0].read_text(encoding="utf-8"))
        rev = dict(cur)
        rev["materiality"] = "critical"
        ea = dict(rev.get("equity_assessment") or {})
        ea["materiality"] = "critical"
        rev["equity_assessment"] = ea
        rev["revision"] = {
            "number": 2,
            "at": "2026-10-10T19:00:00+03:00",
            "reason": "test-d re-score",
        }
        batch = dict(rev.get("radar_batch") or {})
        batch["generated_at"] = "2026-10-10T19:00:00+03:00"
        rev["radar_batch"] = batch
        # strip nested originals for clean normalize
        for k in ("radar_original",):
            rev.pop(k, None)
        rev_path = work / "revision_batch.json"
        rev_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.1",
                    "generated_at": "2026-10-10T19:00:00+03:00",
                    "coverage_from": "2026-10-08T00:00:00+03:00",
                    "coverage_to": "2026-10-10T19:00:00+03:00",
                    "generated_by": "test-d",
                    "is_test": True,
                    "sources_checked": [],
                    "events": [rev.get("radar_original") or rev],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        # rebuild event from radar_original if present else flat
        ev = rev.get("radar_original")
        if not isinstance(ev, dict):
            ev = {
                k: rev[k]
                for k in rev
                if k
                not in {
                    "radar_batch",
                    "radar_original",
                    "company",
                    "summary",
                    "title",
                    "source",
                    "url",
                }
            }
            ev.setdefault("issuer_name", rev.get("company") or "X")
            ev.setdefault("source_name", rev.get("source") or "x")
            ev.setdefault("source_url", rev.get("url") or rev.get("document_url"))
            ev.setdefault("factual_summary", rev.get("summary") or rev.get("title"))
            ev["materiality"] = "critical"
            ev["equity_assessment"] = ea
            ev["revision"] = rev["revision"]
        else:
            ev = dict(ev)
            ev["materiality"] = "critical"
            ev["equity_assessment"] = ea
            ev["revision"] = rev["revision"]
        rev_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.1",
                    "generated_at": "2026-10-10T19:00:00+03:00",
                    "coverage_from": "2026-10-08T00:00:00+03:00",
                    "coverage_to": "2026-10-10T19:00:00+03:00",
                    "generated_by": "test-d",
                    "is_test": True,
                    "sources_checked": [],
                    "events": [ev],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        code, out, err = _run(
            [py, "-m", "moex_portfolio", "ingest-events", "--source", str(rev_path)],
            clone,
            env,
        )
        body = out if out.strip() else err
        try:
            ingest2 = json.loads(body)
        except json.JSONDecodeError:
            ingest2 = {}
        note(
            "ingest-revision",
            code == 0 and ingest2.get("updated", 0) >= 1,
            exit=code,
            updated=ingest2.get("updated"),
            conflict=ingest2.get("conflict"),
            details=ingest2.get("details"),
        )
    else:
        note("ingest-revision", False, reason="no processed events")

    # 3) partial reject
    bad = {
        "schema_version": "1.1",
        "generated_at": "2026-10-10T19:10:00+03:00",
        "coverage_from": "2026-10-08T00:00:00+03:00",
        "coverage_to": "2026-10-10T19:10:00+03:00",
        "generated_by": "test-d",
        "is_test": True,
        "sources_checked": [],
        "events": [
            {
                "event_id": "EV-20261010-TSTA-901",
                "issuer_name": "T",
                "ticker": "TSTA",
                "isin": "RU00TEST0001",
                "published_at": "unknown",
                "event_date": "2026-10-09",
                "source_name": "s",
                "source_url": "https://example.invalid/t",
                "event_type": "dividend_recommendation",
                "factual_summary": "bad date",
                "materiality": "high",
                "direction": "positive",
                "time_horizon": "short_term",
                "affected_securities": [],
                "impact_rationale": "t",
                "confidence": {"fact": "high", "assessment": "high"},
                "document_url": "https://example.invalid/t.pdf",
                "collected_at": "2026-10-10T10:00:00+03:00",
                "validation_status": "unverified",
                "duplicate_of": None,
            }
        ],
    }
    bad_path = work / "bad_published.json"
    bad_path.write_text(json.dumps(bad), encoding="utf-8")
    code, out, err = _run(
        [py, "-m", "moex_portfolio", "ingest-events", "--source", str(bad_path)],
        clone,
        env,
    )
    note(
        "partial-reject-published_at",
        code == 2 and "PUBLISHED_AT_INVALID" in (err + out),
        exit=code,
        stderr_snip=err[:400],
    )

    # 4) optimize + compare
    code, out, err = _run(
        [
            py,
            "-m",
            "moex_portfolio",
            "optimize",
            "--allow-optimize",
            "--mode",
            "universe",
            "--max-weight",
            "0.5",
        ],
        clone,
        env,
    )
    try:
        opt = json.loads(out or err)
    except json.JSONDecodeError:
        opt = {}
    target = clone / "data" / "outbox" / "last_target.json"
    weights = {}
    if target.exists():
        weights = json.loads(target.read_text(encoding="utf-8")).get("weights") or {}
    wsum = sum(weights.values()) if weights else 0.0
    note(
        "optimize",
        code == 0 and opt.get("success") is True and abs(wsum - 1.0) < 1e-6,
        exit=code,
        weight_sum=wsum,
        success=opt.get("success"),
    )

    prev_target = target.read_text(encoding="utf-8") if target.exists() else ""
    code_f, out_f, err_f = _run(
        [
            py,
            "-m",
            "moex_portfolio",
            "optimize",
            "--allow-optimize",
            "--mode",
            "universe",
            "--max-weight",
            "0.01",
        ],
        clone,
        env,
    )
    after = target.read_text(encoding="utf-8") if target.exists() else ""
    note(
        "optimize-infeasible-keeps-target",
        after == prev_target,
        exit=code_f,
        stderr_snip=(err_f or out_f)[:300],
    )

    code, out, err = _run(
        [py, "-m", "moex_portfolio", "compare", "--min-drift", "0.05"],
        clone,
        env,
    )
    try:
        cmp_ = json.loads(out or err)
    except json.JSONDecodeError:
        cmp_ = {}
    note(
        "compare",
        code == 0 and "diffs" in cmp_,
        exit=code,
        allocation_kind=cmp_.get("allocation_kind"),
        holdings_empty=cmp_.get("holdings_empty"),
    )

    # 5) redelivery idempotent
    code, out, err = _run(
        [py, "-m", "moex_portfolio", "ingest-events", "--source", str(src)],
        clone,
        env,
    )
    body = out if out.strip() else err
    try:
        ingest3 = json.loads(body)
    except json.JSONDecodeError:
        ingest3 = {}
    note(
        "redeploy-idempotent",
        code == 0
        and ingest3.get("updated", 0) == 0
        and ingest3.get("accepted", 0) == 0,
        exit=code,
        duplicate_skipped=ingest3.get("duplicate_skipped"),
        updated=ingest3.get("updated"),
    )

    report["ok"] = len(report["failed"]) == 0
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
