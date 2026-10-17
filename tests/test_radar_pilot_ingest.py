"""Регрессия: пакет радара schema 1.1 (форма пилота, 6 событий)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from moex_portfolio.cli import main
from moex_portfolio.events import (
    apply_event_dirs,
    ingest_events,
    normalize_event,
    stable_event_filename,
)

PILOT = (
    Path(__file__).resolve().parent / "fixtures" / "radar_events_latest_v1_1_pilot.json"
)

# Боевые / production-shaped ID (в т.ч. прежние значения фикстуры до namespace).
# Тестовая фикстура не должна пересекаться с этим множеством.
KNOWN_PRODUCTION_EVENT_IDS = frozenset(
    {
        "EV-20261009-SBER-001",
        "EV-20261009-SBER-002",
        "EV-20261008-GAZP-001",
        "EV-20261009-LKOH-001",
        "EV-20261009-ROSN-001",
        "EV-20261009-VTBR-001",
        "EV-20261009-CHMF-001",
        "EV-20260918-SBER-001",
        "EV-20260918-LKOH-001",
    }
)

TEST_EVENT_ID_PREFIX = "TEST-EV-"


@pytest.fixture
def event_dirs(tmp_path):
    """Изолированные *_test каталоги через apply_event_dirs."""
    dirs = apply_event_dirs(test_mode=True, data_root=tmp_path)
    for d in dirs.values():
        Path(d).mkdir(parents=True, exist_ok=True)
    yield {
        "inbox": dirs["inbox"],
        "processed": dirs["processed"],
        "rejected": dirs["rejected"],
        "archive": dirs["inbox_archive"],
        "batches": dirs["batches"],
        "history": dirs["history"],
        "root": tmp_path,
    }
    apply_event_dirs(test_mode=False)


def test_pilot_package_accepts_radar_types_and_skips_semantics(event_dirs):
    src = event_dirs["root"] / "events_latest.json"
    src.write_text(PILOT.read_text(encoding="utf-8"), encoding="utf-8")

    report = ingest_events(
        source_path=src, keep_source=True, test_mode=True, data_root=event_dirs["root"]
    )

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
        (
            event_dirs["processed"] / "TEST-EV-20261009-SBER-001.json"
        ).read_text(encoding="utf-8")
    )
    assert sber["event_type"] == "dividend_recommendation"
    assert sber["equity_assessment"]["materiality"] == "high"
    assert sber["bond_assessment"]["materiality"] == "unknown"
    assert sber["radar_batch"]["generated_at"] == "2026-10-10T11:28:52+03:00"
    assert "event_date" in sber
    assert sber["published_at"].startswith("2026-10-09")
    assert sber["event_id"] == "TEST-EV-20261009-SBER-001"

    gazp = json.loads(
        (
            event_dirs["processed"] / "TEST-EV-20261008-GAZP-001.json"
        ).read_text(encoding="utf-8")
    )
    assert gazp["event_type"] == "financial_statements_ras"

    statuses = {d["status"] for d in report["details"]}
    assert "skipped_novelty_duplicate" in statuses
    assert "skipped_materiality_ignore" in statuses


def test_pilot_event_ids_test_namespace_no_production_collision():
    raw = json.loads(PILOT.read_text(encoding="utf-8"))
    assert raw["is_test"] is True
    ids = [e["event_id"] for e in raw["events"]]
    assert ids
    assert all(isinstance(i, str) and i.startswith(TEST_EVENT_ID_PREFIX) for i in ids)
    assert not (set(ids) & KNOWN_PRODUCTION_EVENT_IDS)
    # Имена processed-файлов тоже в тестовом namespace.
    for eid in ids:
        assert stable_event_filename({"event_id": eid}) == f"{eid}.json"
        assert not eid.startswith("EV-")


def test_pilot_redelivery_no_dupes_no_source_loss(event_dirs):
    src = event_dirs["root"] / "events_latest.json"
    src.write_text(PILOT.read_text(encoding="utf-8"), encoding="utf-8")

    r1 = ingest_events(
        source_path=src, keep_source=True, test_mode=True, data_root=event_dirs["root"]
    )
    assert r1["accepted"] == 4
    n1 = len(list(event_dirs["processed"].glob("*.json")))
    names1 = sorted(p.name for p in event_dirs["processed"].glob("*.json"))

    r2 = ingest_events(
        source_path=src, keep_source=True, test_mode=True, data_root=event_dirs["root"]
    )
    assert r2["accepted"] == 0
    assert r2["duplicate_skipped"] == 4
    assert r2["updated"] == 0
    assert r2["conflict"] == 0
    assert r2["rejected"] == 0
    assert r2["ok"] is True
    assert r2["partial"] is False
    assert src.exists()
    n2 = len(list(event_dirs["processed"].glob("*.json")))
    names2 = sorted(p.name for p in event_dirs["processed"].glob("*.json"))
    assert n1 == n2 == 4
    assert names1 == names2
    assert all(n.startswith(TEST_EVENT_ID_PREFIX) for n in names1)


def test_identity_mismatch_does_not_overwrite_processed(event_dirs):
    eid = "TEST-EV-20261009-SBER-001"
    existing = {
        "event_id": eid,
        "event_type": "dividend_recommendation",
        "title": "OLD",
        "url": "https://example.invalid/old",
        "published_at": "2026-10-01T00:00:00+03:00",
        "source": "x",
        "ticker": "SBER",
        "event_date": "2026-10-09",
        "isin": "RU0009029540",
    }
    (event_dirs["processed"] / f"{eid}.json").write_text(
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
                "event_id": eid,
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
    report = ingest_events(test_mode=True, data_root=event_dirs["root"])
    assert report["conflict"] == 1
    assert report["rejected"] == 1
    assert report["partial"] is True
    assert report["details"][0]["error"] == "EVENT_IDENTITY_MISMATCH"
    saved = json.loads(
        (event_dirs["processed"] / f"{eid}.json").read_text(encoding="utf-8")
    )
    assert saved["title"] == "OLD"
    assert list(event_dirs["archive"].glob("*.json"))


def test_cli_ingest_source_partial_exit(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("moex_portfolio.config.DATA_DIR", tmp_path)
    monkeypatch.setattr("moex_portfolio.portfolio_state.HOLDINGS_DIR", tmp_path / "p")
    monkeypatch.setattr("moex_portfolio.run_journal.RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr("moex_portfolio.locks.LOCKS_DIR", tmp_path / "locks")
    monkeypatch.setattr("moex_portfolio.reporting.REPORTS_DIR", tmp_path / "reports")
    apply_event_dirs(test_mode=True, data_root=tmp_path)
    for d in ("runs", "locks", "p"):
        (tmp_path / d).mkdir(parents=True, exist_ok=True)

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

    code = main(["ingest-events", "--source", str(src), "--test-events"])
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
