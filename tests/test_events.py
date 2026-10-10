"""Тесты inbox событий и адаптера Корпоративного радара."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from moex_portfolio.events import (
    EventValidationError,
    canonicalize_event_type,
    ingest_events,
    normalize_event,
    parse_published_at,
    stable_event_filename,
    validate_event,
)

RADAR_FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "radar_batch_sample.json"
)


def test_validate_ok_dividend_event():
    event = {
        "event_type": "dividend_declared",
        "title": "SBER dividend",
        "url": "https://example.com/1",
        "published_at": "2026-10-01T12:00:00Z",
        "source": "smart-lab",
        "ticker": "SBER",
        "summary": "test",
    }
    validate_event(event)


def test_validate_missing_url():
    event = {
        "event_type": "disclosure_report",
        "title": "x",
        "published_at": "2026-10-01T12:00:00Z",
        "source": "e-disclosure",
    }
    with pytest.raises(EventValidationError):
        validate_event(event)


def test_published_at_unknown_rejected():
    with pytest.raises(EventValidationError, match="PUBLISHED_AT_INVALID"):
        parse_published_at("unknown")
    with pytest.raises(EventValidationError, match="PUBLISHED_AT_INVALID"):
        validate_event(
            {
                "event_type": "dividend_declared",
                "title": "t",
                "url": "https://example.com/x",
                "published_at": "unknown",
                "source": "x",
            }
        )


def test_unmapped_event_type_rejected():
    with pytest.raises(EventValidationError, match="EVENT_TYPE_UNMAPPED"):
        canonicalize_event_type("random_news_blurb")


def test_radar_normalize_preserves_fields():
    raw = {
        "event_id": "e-1",
        "issuer_name": "Issuer",
        "event_type": "dividend",
        "source_name": "finam",
        "source_url": "https://example.com/d",
        "factual_summary": "Fact text",
        "published_at": "2026-01-01",
        "facts": {"a": 1},
    }
    event = normalize_event(raw)
    assert event["event_type"] == "dividend_declared"
    assert event["url"] == "https://example.com/d"
    assert event["source"] == "finam"
    assert event["company"] == "Issuer"
    assert event["summary"] == "Fact text"
    assert event["facts"] == {"a": 1}
    assert event["radar_original"] == raw
    assert event["event_id"] == "e-1"


def _patch_event_dirs(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    rejected = tmp_path / "rejected"
    archive = tmp_path / "archive"
    batches = tmp_path / "batches"
    history = tmp_path / "history"
    for d in (inbox, processed, rejected, archive, batches, history):
        d.mkdir(exist_ok=True)
    monkeypatch.setattr("moex_portfolio.events.INBOX_DIR", inbox)
    monkeypatch.setattr("moex_portfolio.events.PROCESSED_DIR", processed)
    monkeypatch.setattr("moex_portfolio.events.REJECTED_DIR", rejected)
    monkeypatch.setattr("moex_portfolio.events.INBOX_ARCHIVE_DIR", archive)
    monkeypatch.setattr("moex_portfolio.events.BATCH_META_DIR", batches)
    monkeypatch.setattr("moex_portfolio.events.HISTORY_DIR", history)
    return inbox, processed, rejected, archive, history


def test_radar_batch_full_cycle(tmp_path, monkeypatch):
    inbox, processed, rejected, archive, _history = _patch_event_dirs(
        tmp_path, monkeypatch
    )

    payload = json.loads(RADAR_FIXTURE.read_text(encoding="utf-8"))
    (inbox / "radar_batch.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )

    report = ingest_events()
    assert report["accepted"] == 2
    assert report["rejected"] == 0
    assert not (inbox / "radar_batch.json").exists()
    assert list(archive.glob("*.json")), "inbox file must be archived"
    assert (processed / "radar-2026-001.json").exists()
    assert (processed / "radar-2026-002.json").exists()

    e1 = json.loads((processed / "radar-2026-001.json").read_text(encoding="utf-8"))
    assert e1["event_type"] == "disclosure_material_fact"
    assert e1["url"].startswith("https://www.e-disclosure.ru")
    assert e1["facts"]["currency"] == "RUB"
    assert e1["equity_score"] == 0.72
    assert e1["bond_score"] == 0.15
    assert e1["scores"]["equity"] == 0.72
    assert "radar_original" in e1

    # повторная доставка того же выпуска — без дублей и без порчи
    (inbox / "radar_batch.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    report2 = ingest_events()
    assert report2["accepted"] == 0
    assert report2["duplicate_skipped"] == 2
    assert report2["conflict"] == 0
    assert report2["rejected"] == 0
    assert report2["updated"] == 0


def test_duplicate_event_id_skipped(tmp_path, monkeypatch):
    inbox, processed, rejected, _archive, _history = _patch_event_dirs(
        tmp_path, monkeypatch
    )

    event = {
        "event_id": "same-id",
        "event_type": "dividend_declared",
        "title": "T",
        "url": "https://example.com/t",
        "document_url": "https://example.com/t.pdf",
        "published_at": "2026-01-01",
        "source": "x",
        "ticker": "SBER",
        "event_date": "2026-01-01",
    }
    (processed / "same-id.json").write_text(
        json.dumps(event, ensure_ascii=False), encoding="utf-8"
    )
    (inbox / "again.json").write_text(json.dumps(event), encoding="utf-8")

    report = ingest_events()
    assert report["duplicate_skipped"] == 1
    assert report["accepted"] == 0
    assert report["conflict"] == 0
    assert report["updated"] == 0


def test_document_url_change_is_soft_revision(tmp_path, monkeypatch):
    inbox, processed, rejected, _archive, history = _patch_event_dirs(
        tmp_path, monkeypatch
    )

    existing = {
        "event_id": "same-id",
        "event_type": "dividend_declared",
        "title": "OLD",
        "url": "https://example.com/old",
        "document_url": "https://example.com/old.pdf",
        "published_at": "2026-01-01",
        "source": "x",
        "ticker": "SBER",
        "event_date": "2026-01-01",
        "radar_batch": {"generated_at": "2026-10-10T11:00:00+03:00"},
    }
    incoming = {
        **existing,
        "title": "NEW",
        "url": "https://example.com/new",
        "document_url": "https://example.com/new.pdf",
        "radar_batch": {"generated_at": "2026-10-10T12:00:00+03:00"},
    }
    (processed / "same-id.json").write_text(
        json.dumps(existing, ensure_ascii=False), encoding="utf-8"
    )
    (inbox / "collision.json").write_text(json.dumps(incoming), encoding="utf-8")

    report = ingest_events()
    assert report["updated"] == 1
    assert report["conflict"] == 0
    detail = next(d for d in report["details"] if d["status"] == "updated")
    assert "document_url" in detail.get("soft_identity_changed", [])
    assert list(history.glob("same-id__*.json"))
    cur = json.loads((processed / "same-id.json").read_text(encoding="utf-8"))
    assert cur["document_url"] == "https://example.com/new.pdf"


def test_hard_identity_mismatch_conflict(tmp_path, monkeypatch):
    inbox, processed, rejected, _archive, _history = _patch_event_dirs(
        tmp_path, monkeypatch
    )
    existing = {
        "event_id": "same-id",
        "event_type": "dividend_declared",
        "title": "OLD",
        "url": "https://example.com/old",
        "document_url": "https://example.com/old.pdf",
        "published_at": "2026-01-01",
        "source": "x",
        "ticker": "SBER",
        "event_date": "2026-01-01",
    }
    incoming = {**existing, "ticker": "GAZP", "title": "NEW"}
    (processed / "same-id.json").write_text(
        json.dumps(existing, ensure_ascii=False), encoding="utf-8"
    )
    (inbox / "collision.json").write_text(json.dumps(incoming), encoding="utf-8")
    report = ingest_events()
    assert report["conflict"] == 1
    assert report["rejected"] == 1
    assert report["details"][0]["error"] == "EVENT_IDENTITY_MISMATCH"
    cur = json.loads((processed / "same-id.json").read_text(encoding="utf-8"))
    assert cur["ticker"] == "SBER"


def test_reassessment_updates_with_history(tmp_path, monkeypatch):
    inbox, processed, rejected, _archive, history = _patch_event_dirs(
        tmp_path, monkeypatch
    )

    base = {
        "event_id": "EV-20261010-TSTA-001",
        "event_type": "dividend_recommendation",
        "title": "Board rec",
        "url": "https://example.invalid/tsta/doc",
        "document_url": "https://example.invalid/tsta/doc.pdf",
        "published_at": "2026-10-10T09:15:00+03:00",
        "source": "test",
        "ticker": "TSTA",
        "event_date": "2026-10-09",
        "materiality": "medium",
        "equity_assessment": {"materiality": "medium", "direction": "positive"},
        "bond_assessment": {"materiality": "unknown", "credit_direction": "uncertain"},
        "radar_batch": {"generated_at": "2026-10-10T11:00:00+03:00"},
    }
    (processed / "EV-20261010-TSTA-001.json").write_text(
        json.dumps(base, ensure_ascii=False), encoding="utf-8"
    )
    incoming = {
        **base,
        "materiality": "high",
        "equity_assessment": {"materiality": "high", "direction": "positive"},
        "bond_assessment": {
            "materiality": "low",
            "credit_direction": "negative",
        },
        "revision": {"number": 2, "at": "2026-10-10T12:00:00+03:00", "reason": "re-score"},
        "radar_batch": {"generated_at": "2026-10-10T12:00:00+03:00"},
    }
    (inbox / "rev.json").write_text(json.dumps(incoming), encoding="utf-8")

    report = ingest_events()
    assert report["updated"] == 1
    assert report["accepted"] == 0
    assert report["conflict"] == 0
    assert report["rejected"] == 0
    detail = next(d for d in report["details"] if d["status"] == "updated")
    assert "equity_assessment" in detail["changed_fields"]
    assert "bond_assessment" in detail["changed_fields"]
    assert list(history.glob("EV-20261010-TSTA-001__*.json"))
    cur = json.loads(
        (processed / "EV-20261010-TSTA-001.json").read_text(encoding="utf-8")
    )
    assert cur["equity_assessment"]["materiality"] == "high"
    assert cur["revision"]["number"] == 2

    # повтор после обновления — без нового update
    (inbox / "rev2.json").write_text(json.dumps(incoming), encoding="utf-8")
    report2 = ingest_events()
    assert report2["updated"] == 0
    assert report2["duplicate_skipped"] == 1


def test_stale_batch_does_not_overwrite(tmp_path, monkeypatch):
    inbox, processed, rejected, _archive, _history = _patch_event_dirs(
        tmp_path, monkeypatch
    )
    existing = {
        "event_id": "EV-1",
        "event_type": "dividend_recommendation",
        "title": "new",
        "url": "https://example.com/d",
        "document_url": "https://example.com/d.pdf",
        "published_at": "2026-10-10",
        "source": "x",
        "ticker": "AAA",
        "event_date": "2026-10-09",
        "materiality": "high",
        "radar_batch": {"generated_at": "2026-10-10T18:00:00+03:00"},
    }
    stale = {
        **existing,
        "materiality": "low",
        "radar_batch": {"generated_at": "2026-10-10T10:00:00+03:00"},
    }
    (processed / "EV-1.json").write_text(
        json.dumps(existing, ensure_ascii=False), encoding="utf-8"
    )
    (inbox / "old.json").write_text(json.dumps(stale), encoding="utf-8")
    report = ingest_events()
    assert report["stale_skipped"] == 1
    assert report["updated"] == 0
    assert report["conflict"] == 0
    assert report["rejected"] == 0
    assert report["partial"] is False
    cur = json.loads((processed / "EV-1.json").read_text(encoding="utf-8"))
    assert cur["materiality"] == "high"


def test_update_io_failure_keeps_current(tmp_path, monkeypatch):
    inbox, processed, rejected, _archive, history = _patch_event_dirs(
        tmp_path, monkeypatch
    )
    existing = {
        "event_id": "EV-IO",
        "event_type": "dividend_recommendation",
        "title": "t",
        "url": "https://example.com/d",
        "document_url": "https://example.com/d.pdf",
        "published_at": "2026-10-10",
        "source": "x",
        "ticker": "AAA",
        "event_date": "2026-10-09",
        "materiality": "medium",
        "radar_batch": {"generated_at": "2026-10-10T11:00:00+03:00"},
    }
    incoming = {
        **existing,
        "materiality": "high",
        "radar_batch": {"generated_at": "2026-10-10T12:00:00+03:00"},
    }
    (processed / "EV-IO.json").write_text(
        json.dumps(existing, ensure_ascii=False), encoding="utf-8"
    )
    (inbox / "io.json").write_text(json.dumps(incoming), encoding="utf-8")

    with patch(
        "moex_portfolio.events._atomic_write_json",
        side_effect=OSError("disk full"),
    ):
        report = ingest_events()

    assert report["updated"] == 0
    assert report["rejected"] == 1
    cur = json.loads((processed / "EV-IO.json").read_text(encoding="utf-8"))
    assert cur["materiality"] == "medium"


def test_stable_filename_uses_event_id():
    assert (
        stable_event_filename(
            {
                "event_id": "abc/def",
                "event_type": "dividend_declared",
                "title": "t",
                "url": "u",
                "published_at": "p",
                "source": "s",
            }
        )
        == "abc_def.json"
    )
