"""Fail-closed сборка moex_analyst_bundle.v1 (runs[] / events)."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from moex_portfolio.analyst_bundle import build_analyst_bundle
from moex_portfolio.cli import main
from moex_portfolio.events import apply_event_dirs, ingest_events
from moex_portfolio.run_journal import finish_run, start_run

FLOW_FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "radar_events_cli_bundle_flow.json"
)


@pytest.fixture
def isolated_data(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    (data / "portfolio").mkdir()
    (data / "outbox" / "runs").mkdir(parents=True)
    (data / "outbox" / "reports").mkdir(parents=True)
    (data / "locks").mkdir()

    import moex_portfolio.analyst_bundle as ab
    import moex_portfolio.cli as cli_mod
    import moex_portfolio.config as cfg
    import moex_portfolio.locks as locks
    import moex_portfolio.portfolio_state as ps
    import moex_portfolio.reporting as reporting
    import moex_portfolio.run_journal as rj

    cfg.DATA_DIR = data
    ab.DATA_DIR = data
    ab.DEFAULT_BUNDLE_DIR = data / "outbox" / "analyst_bundles"
    ab.RUNS_DIR = data / "outbox" / "runs"
    ps.HOLDINGS_DIR = data / "portfolio"
    rj.RUNS_DIR = data / "outbox" / "runs"
    locks.LOCKS_DIR = data / "locks"
    reporting.REPORTS_DIR = data / "outbox" / "reports"
    cli_mod.LAST_TARGET_PATH = data / "outbox" / "last_target.json"
    apply_event_dirs(test_mode=False, data_root=data)
    monkeypatch.setenv("MOEX_ISS_ENABLED", "false")
    monkeypatch.setenv("MOEX_DATA_SOURCE", "fixture")
    return data


def _write_holdings(data: Path) -> None:
    holdings = {
        "as_of": "2026-10-10",
        "cash": 0.0,
        "file_status": "ok",
        "weight_sum_policy": "canonical",
        "positions": [
            {
                "ticker": "AAA",
                "secid": "AAA",
                "account": "broker_a",
                "quantity": 100,
                "market_value": 100000.0,
                "weight": 0.5,
            },
            {
                "ticker": "BBB",
                "secid": "BBB",
                "account": "broker_a",
                "quantity": 50,
                "market_value": 100000.0,
                "weight": 0.5,
            },
        ],
    }
    (data / "portfolio" / "holdings.json").write_text(
        json.dumps(holdings, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _ok_run(command: str) -> str:
    rec = start_run(command, params={"test": True})
    finish_run(rec["run_id"], status="ok", result={"success": True, "command": command})
    return rec["run_id"]


def test_build_refuses_empty_run_ids(isolated_data):
    _write_holdings(isolated_data)
    with pytest.raises(ValueError, match="RUN_IDS_REQUIRED"):
        build_analyst_bundle(run_ids=[])


def test_build_refuses_missing_journal(isolated_data):
    _write_holdings(isolated_data)
    with pytest.raises(FileNotFoundError, match="RUN_NOT_FOUND"):
        build_analyst_bundle(run_ids=["20261018T000000Z-deadbeef"])


def test_cli_empty_run_ids_exit_2(isolated_data):
    _write_holdings(isolated_data)
    buf_o, buf_e = io.StringIO(), io.StringIO()
    with redirect_stdout(buf_o), redirect_stderr(buf_e):
        code = main(["build-analyst-bundle", "--out-dir", str(isolated_data / "bun")])
    assert code == 2
    err = json.loads(buf_e.getvalue())
    assert err["code"] == "RUN_IDS_REQUIRED"


def test_cli_missing_run_exit_2(isolated_data):
    _write_holdings(isolated_data)
    buf_o, buf_e = io.StringIO(), io.StringIO()
    with redirect_stdout(buf_o), redirect_stderr(buf_e):
        code = main(
            [
                "build-analyst-bundle",
                "--run-ids",
                "20261018T000000Z-missing01",
                "--out-dir",
                str(isolated_data / "bun"),
            ]
        )
    assert code == 2
    err = json.loads(buf_e.getvalue())
    assert err["code"] == "RUN_NOT_FOUND"


def test_cli_embeds_runs_and_test_events(isolated_data, tmp_path):
    _write_holdings(isolated_data)
    opt = _ok_run("optimize")
    cmp = _ok_run("compare")

    src = tmp_path / "radar_flow.json"
    src.write_text(FLOW_FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    ingest = ingest_events(source_path=src, test_mode=True, data_root=isolated_data)
    assert ingest["accepted"] == 2
    assert ingest.get("skipped_semantics", 0) >= 1
    assert any(
        d.get("status") == "skipped_novelty_duplicate" for d in ingest.get("details") or []
    )

    prod_processed = isolated_data / "processed" / "events"
    test_processed = isolated_data / "processed" / "events_test"
    assert (not prod_processed.exists()) or list(prod_processed.glob("*.json")) == []
    assert len(list(test_processed.glob("*.json"))) == 2

    ingest_path = tmp_path / "ingest.json"
    ingest_path.write_text(json.dumps(ingest), encoding="utf-8")

    buf_o, buf_e = io.StringIO(), io.StringIO()
    with redirect_stdout(buf_o), redirect_stderr(buf_e):
        code = main(
            [
                "build-analyst-bundle",
                "--run-ids",
                f"{opt},{cmp}",
                "--ingest-json",
                str(ingest_path),
                "--test-events",
                "--out-dir",
                str(isolated_data / "bun"),
            ]
        )
    assert code == 0, buf_e.getvalue()
    summary = json.loads(buf_o.getvalue())
    assert summary["runs_count"] == 2
    assert summary["events_count"] == 2

    bundle = json.loads(Path(summary["bundle_json"]).read_text(encoding="utf-8"))
    assert bundle["schema"] == "moex_analyst_bundle.v1"
    assert {r["run_id"] for r in bundle["runs"]} == {opt, cmp}
    event_ids = {e["event_id"] for e in bundle["events"]["items"]}
    assert "TEST-EV-20261018-AAA-FLOW-001" in event_ids
    assert "TEST-EV-20261018-BBB-FLOW-001" in event_ids
    assert "TEST-EV-20261018-CCC-FLOW-001" not in event_ids
    assert "events_test" in bundle["events"]["processed_dir"].replace("\\", "/")
    aaa = next(
        e for e in bundle["events"]["items"] if e["event_id"] == "TEST-EV-20261018-AAA-FLOW-001"
    )
    assert aaa["equity_assessment"]["direction"] == "positive"
    assert aaa["equity_assessment"]["materiality"] == "medium"

    # повторный ingest — дубликаты
    ingest2 = ingest_events(source_path=src, test_mode=True, data_root=isolated_data)
    assert ingest2["accepted"] == 0
    assert ingest2["duplicate_skipped"] >= 2
    assert len(list(test_processed.glob("*.json"))) == 2
    assert (not prod_processed.exists()) or list(prod_processed.glob("*.json")) == []


def test_events_do_not_change_max_sharpe_weights(isolated_data, tmp_path):
    """События радара — качественный блок; solver их не читает."""
    from moex_portfolio.data_sources import FixtureDataSource
    from moex_portfolio.pipeline import run_optimize

    fixture = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "synthetic_prices.csv"
    prices = FixtureDataSource(fixture).load_prices()
    before = run_optimize(prices, max_weight=0.5, mode="universe")
    assert before["success"] is True

    src = tmp_path / "radar_flow.json"
    src.write_text(FLOW_FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    ingest = ingest_events(source_path=src, test_mode=True, data_root=isolated_data)
    assert ingest["accepted"] == 2

    after = run_optimize(prices, max_weight=0.5, mode="universe")
    assert after["success"] is True
    assert before["weights"] == after["weights"]
    assert before["sharpe"] == after["sharpe"]
    assert abs(sum(before["weights"].values()) - 1.0) < 1e-9
