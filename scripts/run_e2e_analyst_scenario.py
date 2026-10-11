#!/usr/bin/env python3
"""Сквозной сценарий CLI → analyst bundle (синтетика, изолированный tmp).

Запуск из корня репо:

    MOEX_ISS_ENABLED=false MOEX_DATA_SOURCE=fixture \\
      python scripts/run_e2e_analyst_scenario.py

Пишет JSON-отчёт в stdout. Код 0 только при полном успехе.
Не трогает /workspace/invest, optimizer.yaml, профили ботов.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "tests" / "fixtures" / "e2e_multi_account_portfolio.csv"
EVENTS = ROOT / "tests" / "fixtures" / "e2e_radar_test_batch.json"
PRICES = ROOT / "data" / "fixtures" / "synthetic_prices.csv"


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


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fp_repo() -> dict[str, str]:
    out: dict[str, str] = {}
    base = ROOT / "data"
    if not base.exists():
        return out
    for path in sorted(base.rglob("*")):
        if path.is_file():
            rel = str(path.relative_to(ROOT)).replace("\\", "/")
            out[rel] = _sha(path)[:16]
    return out


def main() -> int:
    os.chdir(ROOT)
    sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    before = _fp_repo()

    work = Path(tempfile.mkdtemp(prefix="moex-e2e-analyst-"))
    report: dict = {
        "scenario": "e2e_analyst",
        "sha": sha,
        "work_dir": str(work),
        "steps": [],
        "passed": [],
        "failed": [],
    }

    def note(step: str, ok: bool, **extra: object) -> None:
        entry = {"step": step, "ok": ok, **extra}
        report["steps"].append(entry)
        (report["passed"] if ok else report["failed"]).append(step)

    clone = work / "repo"
    subprocess.check_call(["git", "clone", "--quiet", str(ROOT), str(clone)], cwd=work)
    subprocess.check_call(["git", "checkout", "--quiet", sha], cwd=clone)
    # Подмешать незакоммиченные правки рабочей копии (src/tests/scripts/docs/fixtures).
    for rel in (
        "src",
        "scripts",
        "tests/fixtures",
        "docs",
        "data/fixtures",
        "data/inbox",
        "data/portfolio",
        "pyproject.toml",
    ):
        src_path = ROOT / rel
        dst_path = clone / rel
        if not src_path.exists():
            continue
        if src_path.is_dir():
            if dst_path.exists():
                shutil.rmtree(dst_path)
            shutil.copytree(src_path, dst_path)
        else:
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dst_path)

    env = os.environ.copy()
    env["MOEX_ISS_ENABLED"] = "false"
    env["MOEX_DATA_SOURCE"] = "fixture"
    env["MOEX_FIXTURE_PATH"] = str(clone / "data" / "fixtures" / "synthetic_prices.csv")
    env["MOEX_EVENT_DATA_ROOT"] = str(clone / "data")
    env["PYTHONPATH"] = str(clone / "src") + os.pathsep + env.get("PYTHONPATH", "")
    py = sys.executable

    # 1) adapt multi-account portfolio
    code, out, err = _run(
        [
            py,
            "-m",
            "moex_portfolio",
            "adapt-portfolio",
            "--csv",
            str(CSV),
            "--panel-tickers",
            "AAA,BBB,CCC",
            "--write-holdings",
        ],
        clone,
        env,
    )
    note("adapt-portfolio", code == 0, exit=code, stdout=out[-500:], stderr=err[-500:])
    if code != 0:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    adapt = json.loads(out)
    note(
        "adapt-consolidation",
        any(p.get("accounts") for p in adapt.get("positions", [])),
        positions=len(adapt.get("positions", [])),
    )

    # 2) validate-data
    code, out, err = _run(
        [py, "-m", "moex_portfolio", "validate-data", "--max-staleness-days", "5"],
        clone,
        env,
    )
    note("validate-data", code == 0, exit=code)
    validation_path = work / "validation.json"
    validation_path.write_text(out if out.strip() else err, encoding="utf-8")

    # 3) optimize
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
    note("optimize", code == 0, exit=code, stderr=err[-300:])
    if code != 0:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1
    opt = json.loads(out)
    opt_run = Path(opt["report_json"]).stem
    target_path = clone / "data" / "outbox" / "last_target.json"
    target = json.loads(target_path.read_text(encoding="utf-8"))
    note(
        "last_target",
        target.get("success") is True
        and abs(sum(target["weights"].values()) - 1.0) < 1e-6,
        weights=target.get("weights"),
    )

    # 4) compare
    code, out, err = _run(
        [py, "-m", "moex_portfolio", "compare", "--min-drift", "0.05"],
        clone,
        env,
    )
    note("compare", code == 0, exit=code)
    if code != 0:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1
    compare = json.loads(out)
    compare_path = work / "compare.json"
    compare_path.write_text(out, encoding="utf-8")
    cmp_run = Path(compare["report_json"]).stem

    # 5) ingest test radar (must use --test-events)
    code, out, err = _run(
        [
            py,
            "-m",
            "moex_portfolio",
            "ingest-events",
            "--source",
            str(EVENTS),
            "--test-events",
        ],
        clone,
        env,
    )
    note("ingest-test-events", code == 0, exit=code, stderr=err[-400:])
    if code != 0:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1
    ingest_path = work / "ingest.json"
    ingest_path.write_text(out, encoding="utf-8")
    ingest_payload = json.loads(out)
    if (
        ingest_payload.get("accepted", 0) < 1
        and ingest_payload.get("duplicate_skipped", 0) < 1
    ):
        note("ingest-payload", False, reason="no accepted/duplicate events")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1
    prod_events = clone / "data" / "processed" / "events"
    test_events = clone / "data" / "processed" / "events_test"
    note(
        "test-storage-isolation",
        test_events.exists()
        and len(list(test_events.glob("*.json"))) >= 1
        and (not prod_events.exists() or len(list(prod_events.glob("*.json"))) == 0),
        test_count=len(list(test_events.glob("*.json"))) if test_events.exists() else 0,
        prod_count=len(list(prod_events.glob("*.json"))) if prod_events.exists() else 0,
    )

    # 5b) negative: test release without --test-events
    code, out, err = _run(
        [py, "-m", "moex_portfolio", "ingest-events", "--source", str(EVENTS)],
        clone,
        env,
    )
    gate = {}
    try:
        gate = json.loads(err or out)
    except json.JSONDecodeError:
        pass
    gate_ok = code == 2 and "EVENT_TEST_MODE_REQUIRED" in (err + out)
    note(
        "ingest-test-without-flag",
        gate_ok,
        exit=code,
        code=gate.get("code"),
        stderr_snip=(err + out)[-300:],
    )

    # 6) idempotent re-ingest
    code, out, err = _run(
        [
            py,
            "-m",
            "moex_portfolio",
            "ingest-events",
            "--source",
            str(EVENTS),
            "--test-events",
        ],
        clone,
        env,
    )
    ingest2 = json.loads(out) if code == 0 else {}
    note(
        "ingest-idempotent",
        code == 0
        and ingest2.get("duplicate_skipped", 0) >= 1
        and ingest2.get("accepted", 0) == 0,
        exit=code,
        duplicate_skipped=ingest2.get("duplicate_skipped"),
    )

    # 7) build analyst bundle
    code, out, err = _run(
        [
            py,
            "-m",
            "moex_portfolio",
            "build-analyst-bundle",
            "--target",
            str(target_path),
            "--compare-json",
            str(compare_path),
            "--validation-json",
            str(validation_path),
            "--ingest-json",
            str(ingest_path),
            "--run-ids",
            f"{opt_run},{cmp_run}",
            "--test-events",
            "--out-dir",
            str(work / "bundle"),
            "--notes",
            "E2E synthetic scenario for Portfolio Analyst one-shot handoff",
        ],
        clone,
        env,
    )
    note("build-analyst-bundle", code == 0, exit=code, stderr=err[-400:])
    if code != 0:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1
    bun = json.loads(out)
    bundle_json = Path(bun["bundle_json"])
    bundle = json.loads(bundle_json.read_text(encoding="utf-8"))
    # copy bundle to stable path under work for handoff
    handoff_bundle = work / "analyst_bundle.json"
    shutil.copy2(bundle_json, handoff_bundle)
    note(
        "bundle-content",
        bundle.get("schema") == "moex_analyst_bundle.v1"
        and bundle.get("synthetic") is True
        and len((bundle.get("events") or {}).get("items") or []) >= 1
        and (bundle.get("target") or {}).get("payload", {}).get("success") is True,
        events=len((bundle.get("events") or {}).get("items") or []),
        bundle_path=str(handoff_bundle),
    )

    after = _fp_repo()
    note("repo-data-unchanged", before == after)

    report["ok"] = len(report["failed"]) == 0
    report["bundle_path"] = str(handoff_bundle)
    report["bundle_sha256"] = _sha(handoff_bundle)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
