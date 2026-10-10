"""Регрессия: пакет радара schema 1.1 (форма пилота, 6 событий)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from moex_portfolio.cli import main
from moex_portfolio.events import ingest_events, normalize_event

PILOT = (
    Path(__file__).resolve().parent / "fixtures" / "radar_events_latest_v1_1_pilot.json"
)


@pytest.fixture
def event_dirs(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    rejected = tmp_path / "rejected"
    archive = tmp_path / "archive"
    batches = tmp_path / "batches"
    history = tmp_path / "history"
    for d in (inbox, processed, rejected, archive, batches, history):
        d.mkdir()
    monkeypatch.setattr("moex_portfolio.events.INBOX_DIR", inbox)
    monkeypatch.setattr("moex_portfolio.events.PROCESSED_DIR", processed)
    monkeypatch.setattr("moex_portfolio.events.REJECTED_DIR", rejected)
    monkeypatch.setattr("moex_portfolio.events.INBOX_ARCHIVE_DIR", archive)
    monkeypatch.setattr("moex_portfolio.events.BATCH_META_DIR", batches)
    monkeypatch.setattr("moex_portfolio.events.HISTORY_DIR", history)
    return {
        "inbox": inbox,
        "processed": processed,
        "rejected": rejected,
        "archive": archive,
        "batches": batches,
        "history": history,
        "root": tmp_path,
    }


def test_pilot_package_accepts_radar_types_and_skips_semantics(event_dirs):
    src = event_dirs["root"] / "events_latest.json"
    src.write_text(PILOT.read_text(encoding="utf-8"), encoding="utf-8")

    report = ingest_events(source_path=src, keep_source=True)

    assert src.exists(), "оригинал --source не должен удаляться"
    assert report["accepted"] == 4
    assert report["rejected"] == 0
    assert report["skipped_semantics"] == 2
    assert report["partial"] is False
    assert report["ok"] is True
    assert len(report["archives"]) == 1
    assert list(event_dirs["archive"].glob("*.json"))

    # batch meta сохранена
    metas = list(event_dirs["batches"].glob("*.json"))
    assert metas
    meta = json.loads(metas[0].read_text(encoding="utf-8"))
    assert meta["schema_version"] == "1.1"
    assert meta["is_test"] is True

    sber = json.loads(
        (event_dirs["processed"] / "EV-20261009-SBER-001.json").read_text(encoding="utf-8")
    )
    assert sber["event_type"] == "dividend_recommendation"
    assert sber["equity_assessment"]["materiality"] == "high"
    assert sber["bond_assessment"]["materiality"] == "unknown"
    assert sber["radar_batch"]["generated_at"] == "2026-10-10T11:28:52+03:00"
    assert "event_date" in sber
    assert sber["published_at"].startswith("2026-10-09")

    gazp = json.loads(
        (event_dirs["processed"] / "EV-20261008-GAZP-001.json").read_text(encoding="utf-8")
    )
    assert gazp["event_type"] == "financial_statements_ras"

    statuses = {d["status"] for d in report["details"]}
    assert "skipped_novelty_duplicate" in statuses
    assert "skipped_materiality_ignore" in statuses


def test_pilot_redelivery_no_dupes_no_source_loss(event_dirs):
    src = event_dirs["root"] / "events_latest.json"
    src.write_text(PILOT.read_text(encoding="utf-8"), encoding="utf-8")

    r1 = ingest_events(source_path=src, keep_source=True)
    assert r1["accepted"] == 4
    n1 = len(list(event_dirs["processed"].glob("*.json")))

    r2 = ingest_events(source_path=src, keep_source=True)
    assert r2["accepted"] == 0
    assert r2["duplicate_skipped"] == 4
    assert r2["conflict"] == 0
    assert r2["rejected"] == 0
    assert src.exists()
    n2 = len(list(event_dirs["processed"].glob("*.json")))
    assert n1 == n2 == 4


def test_identity_mismatch_does_not_overwrite_processed(event_dirs):
    existing = {
        "event_id": "EV-20261009-SBER-001",
        "event_type": "dividend_recommendation",
        "title": "OLD",
        "url": "https://example.invalid/old",
        "published_at": "2026-10-01T00:00:00+03:00",
        "source": "x",
        "ticker": "SBER",
        "event_date": "2026-10-09",
        "isin": "RU0009029540",
    }
    (event_dirs["processed"] / "EV-20261009-SBER-001.json").write_text(
        json.dumps(existing), encoding="utf-8"
    )
    # тот же event_id, но другой ticker → EVENT_IDENTITY_MISMATCH
    payload = {
        "schema_version": "1.1",
        "generated_at": "2026-10-10T11:28:52+03:00",
        "coverage_from": "2026-10-08T00:00:00+03:00",
        "coverage_to": "2026-10-10T11:28:52+03:00",
        "generated_by": "test",
        "is_test": True,
        "sources_checked": [],
        "events": [
            {
                "event_id": "EV-20261009-SBER-001",
                "event_type": "dividend_recommendation",
                "title": "NEW DIFFERENT",
                "url": "https://example.invalid/new",
                "issuer_name": "X",
                "ticker": "GAZP",
                "isin": "RU0009029540",
                "published_at": "2026-10-01T00:00:00+03:00",
                "event_date": "2026-10-09",
                "source_name": "x",
                "source_url": "https://example.invalid/new",
                "factual_summary": "NEW",
                "materiality": "high",
                "direction": "positive",
                "time_horizon": "short_term",
                "affected_securities": [],
                "impact_rationale": "t",
                "confidence": {"fact": "high", "assessment": "high"},
                "document_url": "https://example.invalid/new.pdf",
                "collected_at": "2026-10-10T10:00:00+03:00",
                "validation_status": "unverified",
                "duplicate_of": None,
            }
        ],
    }
    (event_dirs["inbox"] / "collide.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    report = ingest_events()
    assert report["conflict"] == 1
    assert report["rejected"] == 1
    assert report["partial"] is True
    assert report["details"][0]["error"] == "EVENT_IDENTITY_MISMATCH"
    saved = json.loads(
        (event_dirs["processed"] / "EV-20261009-SBER-001.json").read_text(encoding="utf-8")
    )
    assert saved["title"] == "OLD"
    assert list(event_dirs["archive"].glob("*.json"))


def test_cli_ingest_source_partial_exit(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("moex_portfolio.portfolio_state.HOLDINGS_DIR", tmp_path / "p")
    monkeypatch.setattr("moex_portfolio.run_journal.RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr("moex_portfolio.locks.LOCKS_DIR", tmp_path / "locks")
    monkeypatch.setattr("moex_portfolio.reporting.REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr("moex_portfolio.events.INBOX_DIR", tmp_path / "inbox")
    monkeypatch.setattr("moex_portfolio.events.PROCESSED_DIR", tmp_path / "processed")
    monkeypatch.setattr("moex_portfolio.events.REJECTED_DIR", tmp_path / "rejected")
    monkeypatch.setattr("moex_portfolio.events.INBOX_ARCHIVE_DIR", tmp_path / "archive")
    monkeypatch.setattr("moex_portfolio.events.BATCH_META_DIR", tmp_path / "batches")
    monkeypatch.setattr("moex_portfolio.events.HISTORY_DIR", tmp_path / "history")
    for d in (
        "inbox",
        "processed",
        "rejected",
        "archive",
        "batches",
        "history",
        "runs",
        "locks",
    ):
        (tmp_path / d).mkdir()

    bad = {
        "schema_version": "1.1",
        "generated_at": "2026-10-10T11:28:52+03:00",
        "coverage_from": "2026-10-08T00:00:00+03:00",
        "coverage_to": "2026-10-10T11:28:52+03:00",
        "generated_by": "test",
        "is_test": True,
        "sources_checked": [],
        "events": [
            {
                "event_id": "EV-OK-001",
                "issuer_name": "A",
                "ticker": "AAA",
                "isin": "RU0000000001",
                "published_at": "2026-10-09T15:30:00+03:00",
                "event_date": "2026-10-09",
                "source_name": "s",
                "source_url": "https://example.invalid/a",
                "event_type": "dividend_recommendation",
                "factual_summary": "ok",
                "materiality": "high",
                "direction": "positive",
                "time_horizon": "short_term",
                "affected_securities": [],
                "impact_rationale": "t",
                "confidence": {"fact": "high", "assessment": "high"},
                "document_url": "https://example.invalid/a.pdf",
                "collected_at": "2026-10-10T10:00:00+03:00",
                "validation_status": "unverified",
                "duplicate_of": None,
            },
            {
                "event_id": "EV-BAD-001",
                "issuer_name": "B",
                "ticker": "BBB",
                "isin": "RU0000000002",
                "published_at": "2026-10-09T15:30:00+03:00",
                "event_date": "2026-10-09",
                "source_name": "s",
                "source_url": "https://example.invalid/b",
                "event_type": "totally_made_up_type_xyz",
                "factual_summary": "bad",
                "materiality": "low",
                "direction": "unknown",
                "time_horizon": "unclear",
                "affected_securities": [],
                "impact_rationale": "t",
                "confidence": {"fact": "low", "assessment": "low"},
                "document_url": "https://example.invalid/b.pdf",
                "collected_at": "2026-10-10T10:00:00+03:00",
                "validation_status": "unverified",
                "duplicate_of": None,
            },
        ],
    }
    src = tmp_path / "events_latest.json"
    src.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")

    code = main(["ingest-events", "--source", str(src)])
    assert code == 2
    err = capsys.readouterr().err
    payload = json.loads(err)
    assert payload["accepted"] == 1
    assert payload["rejected"] == 1
    assert payload["partial"] is True
    assert src.exists()


def test_assessments_preserved_on_normalize():
    raw = json.loads(PILOT.read_text(encoding="utf-8"))["events"][0]
    event = normalize_event(raw)
    assert event["equity_assessment"] == raw["equity_assessment"]
    assert event["bond_assessment"] == raw["bond_assessment"]
    assert event["event_type"] == "dividend_recommendation"
