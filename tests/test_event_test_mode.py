"""P0-A: изоляция тестовых событий (is_test / TEST-EV-)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from moex_portfolio.cli import main
from moex_portfolio.events import (
    EventIngestGateError,
    apply_event_dirs,
    classify_release,
    ingest_events,
)

PILOT = (
    Path(__file__).resolve().parent / "fixtures" / "radar_events_latest_v1_1_pilot.json"
)
E2E_BATCH = Path(__file__).resolve().parent / "fixtures" / "e2e_radar_test_batch.json"
PROD_SAMPLE = Path(__file__).resolve().parent / "fixtures" / "radar_batch_sample.json"


@pytest.fixture
def event_root(tmp_path, monkeypatch):
    data = tmp_path / "data"
    apply_event_dirs(test_mode=False, data_root=data)
    # также патчим модуль для cli.main путей через apply внутри ingest
    return data


def test_classify_pilot_is_test():
    raw = json.loads(PILOT.read_text(encoding="utf-8"))
    assert classify_release(raw) == "test"


def test_classify_is_test_string_is_invalid():
    raw = {
        "schema_version": "1.1",
        "generated_at": "2026-10-11T00:00:00Z",
        "is_test": "true",
        "events": [],
    }
    assert classify_release(raw) == "invalid"


def test_is_test_string_rejected_before_write(event_root, tmp_path):
    src = tmp_path / "bad.json"
    src.write_text(
        json.dumps(
            {
                "schema_version": "1.1",
                "generated_at": "2026-10-11T00:00:00Z",
                "coverage_from": "2026-10-01",
                "coverage_to": "2026-10-11",
                "generated_by": "test",
                "is_test": "true",
                "sources_checked": [],
                "events": [
                    {
                        "event_id": "EV-1",
                        "ticker": "AAA",
                        "event_type": "unknown",
                        "factual_summary": "a",
                        "source_name": "x",
                        "source_url": "https://example.invalid/a",
                        "published_at": "2026-10-10",
                        "event_date": "2026-10-10",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(EventIngestGateError, match="EVENT_IS_TEST_INVALID"):
        ingest_events(source_path=src, test_mode=False, data_root=event_root)
    assert list((event_root / "processed").rglob("*.json")) == []


def test_classify_mixed_ids():
    raw = {
        "schema_version": "1.1",
        "generated_at": "2026-10-11T00:00:00Z",
        "is_test": False,
        "events": [
            {
                "event_id": "TEST-EV-1",
                "event_type": "unknown",
                "factual_summary": "a",
                "source_name": "x",
                "source_url": "https://example.invalid/a",
                "published_at": "2026-10-10",
            },
            {
                "event_id": "EV-1",
                "event_type": "unknown",
                "factual_summary": "b",
                "source_name": "x",
                "source_url": "https://example.invalid/b",
                "published_at": "2026-10-10",
            },
        ],
    }
    assert classify_release(raw) == "mixed"


def test_test_release_blocked_without_flag(event_root, tmp_path):
    src = tmp_path / "pilot.json"
    src.write_text(PILOT.read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(EventIngestGateError, match="EVENT_TEST_MODE_REQUIRED"):
        ingest_events(source_path=src, test_mode=False, data_root=event_root)
    prod = event_root / "processed" / "events"
    assert not prod.exists() or list(prod.glob("*.json")) == []


def test_test_release_writes_only_test_dirs(event_root, tmp_path):
    src = tmp_path / "batch.json"
    src.write_text(E2E_BATCH.read_text(encoding="utf-8"), encoding="utf-8")
    report = ingest_events(source_path=src, test_mode=True, data_root=event_root)
    assert report["ok"] is True
    assert report["test_mode"] is True
    assert report["accepted"] >= 1
    test_dir = event_root / "processed" / "events_test"
    prod_dir = event_root / "processed" / "events"
    assert list(test_dir.glob("*.json"))
    assert not prod_dir.exists() or list(prod_dir.glob("*.json")) == []


def test_mixed_release_rejected_before_write(event_root, tmp_path):
    src = tmp_path / "mixed.json"
    src.write_text(
        json.dumps(
            {
                "schema_version": "1.1",
                "generated_at": "2026-10-11T00:00:00Z",
                "is_test": False,
                "coverage_from": "2026-10-01",
                "coverage_to": "2026-10-11",
                "generated_by": "test",
                "sources_checked": [],
                "events": [
                    {
                        "event_id": "TEST-EV-X",
                        "ticker": "AAA",
                        "event_type": "unknown",
                        "factual_summary": "a",
                        "source_name": "x",
                        "source_url": "https://example.invalid/a",
                        "published_at": "2026-10-10",
                        "event_date": "2026-10-10",
                    },
                    {
                        "event_id": "EV-Y",
                        "ticker": "BBB",
                        "event_type": "unknown",
                        "factual_summary": "b",
                        "source_name": "x",
                        "source_url": "https://example.invalid/b",
                        "published_at": "2026-10-10",
                        "event_date": "2026-10-10",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    with pytest.raises(EventIngestGateError, match="EVENT_TEST_PROD_MIXED"):
        ingest_events(source_path=src, test_mode=True, data_root=event_root)
    assert list((event_root / "processed").rglob("*.json")) == []


def test_cli_test_events_flag(tmp_path, monkeypatch):
    monkeypatch.setattr("moex_portfolio.config.DATA_DIR", tmp_path)
    monkeypatch.setattr("moex_portfolio.portfolio_state.HOLDINGS_DIR", tmp_path / "p")
    monkeypatch.setattr("moex_portfolio.run_journal.RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr("moex_portfolio.locks.LOCKS_DIR", tmp_path / "locks")
    monkeypatch.setattr("moex_portfolio.reporting.REPORTS_DIR", tmp_path / "reports")
    for d in ("p", "runs", "locks", "reports"):
        (tmp_path / d).mkdir(parents=True, exist_ok=True)
    apply_event_dirs(test_mode=False, data_root=tmp_path)

    src = tmp_path / "batch.json"
    src.write_text(E2E_BATCH.read_text(encoding="utf-8"), encoding="utf-8")

    code = main(["ingest-events", "--source", str(src)])
    assert code == 2

    code = main(["ingest-events", "--source", str(src), "--test-events"])
    assert code == 0
    assert list((tmp_path / "processed" / "events_test").glob("*.json"))
    apply_event_dirs(test_mode=False)
