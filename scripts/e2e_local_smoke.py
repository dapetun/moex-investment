"""Локальный сквозной smoke Test A/B (синтетика). Не для CI."""

from __future__ import annotations

import contextlib
import json
import os
import sys
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import moex_portfolio.cli as cli  # noqa: E402
import moex_portfolio.events as events  # noqa: E402
import moex_portfolio.locks as locks  # noqa: E402
import moex_portfolio.portfolio_state as ps  # noqa: E402
import moex_portfolio.reporting as reporting  # noqa: E402
import moex_portfolio.run_journal as rj  # noqa: E402


def main() -> int:
    root = Path(os.environ["E2E_ROOT"])
    fixture = ROOT / "data" / "fixtures" / "synthetic_prices.csv"
    os.environ["MOEX_ISS_ENABLED"] = "false"
    os.environ["MOEX_DATA_SOURCE"] = "fixture"
    os.environ["MOEX_FIXTURE_PATH"] = str(fixture)

    ps.HOLDINGS_DIR = root / "portfolio"
    rj.RUNS_DIR = root / "runs"
    locks.LOCKS_DIR = root / "locks"
    reporting.REPORTS_DIR = root / "reports"
    cli.LAST_TARGET_PATH = root / "outbox" / "last_target.json"
    events.INBOX_DIR = root / "inbox"
    events.PROCESSED_DIR = root / "processed"
    events.REJECTED_DIR = root / "rejected"
    for d in [
        ps.HOLDINGS_DIR,
        rj.RUNS_DIR,
        locks.LOCKS_DIR,
        reporting.REPORTS_DIR,
        events.INBOX_DIR,
        events.PROCESSED_DIR,
        events.REJECTED_DIR,
        cli.LAST_TARGET_PATH.parent,
    ]:
        d.mkdir(parents=True, exist_ok=True)

    results: dict = {}
    results["show_empty"] = cli.main(["show-portfolio"])
    results["validate"] = cli.main(["validate-data", "--max-staleness-days", "5"])
    results["optimize"] = cli.main(
        ["optimize", "--allow-optimize", "--mode", "universe", "--max-weight", "0.5"]
    )
    target = json.loads(cli.LAST_TARGET_PATH.read_text(encoding="utf-8"))
    results["target_success"] = target.get("success") is True
    results["weight_sum"] = round(sum(target["weights"].values()), 6)
    results["reports_after_opt"] = len(list(reporting.REPORTS_DIR.glob("*.json")))
    results["runs_after_opt"] = len(list(rj.RUNS_DIR.glob("*.json")))

    first = next(iter(target["weights"]))
    ps.save_holdings(
        {
            "as_of": "2026-10-10",
            "cash": 0.0,
            "positions": [{"ticker": first, "weight": 1.0}],
        }
    )
    results["compare"] = cli.main(["compare", "--min-drift", "0.05"])

    ps.save_holdings({"as_of": None, "cash": 0.0, "positions": []})
    buf = StringIO()
    with contextlib.redirect_stdout(buf):
        code = cli.main(["compare", "--min-drift", "0.05"])
    cmp = json.loads(buf.getvalue())
    results["compare_empty_code"] = code
    results["allocation_kind"] = cmp.get("allocation_kind")
    results["needs_rebalance_empty"] = cmp.get("needs_rebalance")

    prev = json.loads(cli.LAST_TARGET_PATH.read_text(encoding="utf-8"))
    orig = cli.run_optimize

    def fail(*_a, **_k):
        return {
            **prev,
            "success": False,
            "message": "forced",
            "weights": prev["weights"],
            "tickers": prev.get("tickers", []),
            "return": 0,
            "volatility": 0,
            "sharpe": 0,
            "mode": "universe",
            "risk_free_rate": 0,
            "max_weight": 0.5,
            "cov_method": "x",
        }

    cli.run_optimize = fail  # type: ignore[assignment]
    results["failed_opt"] = cli.main(["optimize", "--allow-optimize", "--mode", "universe"])
    after = json.loads(cli.LAST_TARGET_PATH.read_text(encoding="utf-8"))
    results["target_preserved"] = after == prev
    cli.run_optimize = orig

    results["bad_max_weight"] = cli.main(
        ["optimize", "--allow-optimize", "--max-weight", "-1"]
    )

    os.environ["MOEX_DATA_SOURCE"] = "iss"
    os.environ["MOEX_ISS_ENABLED"] = "false"
    results["iss_blocked"] = cli.main(["update-data"])

    os.environ["MOEX_DATA_SOURCE"] = "fixture"
    radar = (ROOT / "tests" / "fixtures" / "radar_batch_sample.json").read_text(
        encoding="utf-8"
    )
    (events.INBOX_DIR / "batch.json").write_text(radar, encoding="utf-8")
    results["ingest1"] = cli.main(["ingest-events"])
    n_proc = len(list(events.PROCESSED_DIR.glob("*.json")))
    (events.INBOX_DIR / "batch.json").write_text(radar, encoding="utf-8")
    results["ingest2"] = cli.main(["ingest-events"])
    n_proc2 = len(list(events.PROCESSED_DIR.glob("*.json")))
    results["events_accepted_stable"] = n_proc == n_proc2 == 2

    print(json.dumps(results, ensure_ascii=False, indent=2))
    assert results["show_empty"] == 0
    assert results["validate"] == 0
    assert results["optimize"] == 0
    assert results["target_success"] is True
    assert results["weight_sum"] == 1.0
    assert results["compare"] == 0
    assert results["allocation_kind"] == "initial_allocation"
    assert results["needs_rebalance_empty"] is False
    assert results["failed_opt"] == 2
    assert results["target_preserved"] is True
    assert results["bad_max_weight"] == 2
    assert results["iss_blocked"] == 4
    assert results["events_accepted_stable"] is True
    print("E2E_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
