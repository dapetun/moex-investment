"""Тесты inbox событий и адаптера Корпоративного радара."""

import json
from pathlib import Path

import pytest

from moex_portfolio.events import (
    EventValidationError,
    canonicalize_event_type,
    ingest_events,
    normalize_event,
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


def test_radar_batch_full_cycle(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    rejected = tmp_path / "rejected"
    inbox.mkdir()
    monkeypatch.setattr("moex_portfolio.events.INBOX_DIR", inbox)
    monkeypatch.setattr("moex_portfolio.events.PROCESSED_DIR", processed)
    monkeypatch.setattr("moex_portfolio.events.REJECTED_DIR", rejected)

    payload = json.loads(RADAR_FIXTURE.read_text(encoding="utf-8"))
    (inbox / "radar_batch.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )

    report = ingest_events()
    assert report["accepted"] == 2
    assert report["rejected"] == 0
    assert not (inbox / "radar_batch.json").exists()
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


def test_duplicate_event_id_skipped(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    rejected = tmp_path / "rejected"
    inbox.mkdir()
    processed.mkdir()
    monkeypatch.setattr("moex_portfolio.events.INBOX_DIR", inbox)
    monkeypatch.setattr("moex_portfolio.events.PROCESSED_DIR", processed)
    monkeypatch.setattr("moex_portfolio.events.REJECTED_DIR", rejected)

    event = {
        "event_id": "same-id",
        "event_type": "dividend_declared",
        "title": "T",
        "url": "https://example.com/t",
        "published_at": "2026-01-01",
        "source": "x",
    }
    (processed / "same-id.json").write_text(
        json.dumps(event, ensure_ascii=False), encoding="utf-8"
    )
    (inbox / "again.json").write_text(json.dumps(event), encoding="utf-8")

    report = ingest_events()
    assert report["duplicate_skipped"] == 1
    assert report["accepted"] == 0
    assert report["conflict"] == 0


def test_same_filename_different_content_conflict(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    rejected = tmp_path / "rejected"
    inbox.mkdir()
    processed.mkdir()
    monkeypatch.setattr("moex_portfolio.events.INBOX_DIR", inbox)
    monkeypatch.setattr("moex_portfolio.events.PROCESSED_DIR", processed)
    monkeypatch.setattr("moex_portfolio.events.REJECTED_DIR", rejected)

    existing = {
        "event_id": "same-id",
        "event_type": "dividend_declared",
        "title": "OLD",
        "url": "https://example.com/old",
        "published_at": "2026-01-01",
        "source": "x",
    }
    incoming = {
        **existing,
        "title": "NEW",
        "url": "https://example.com/new",
    }
    (processed / "same-id.json").write_text(
        json.dumps(existing, ensure_ascii=False), encoding="utf-8"
    )
    (inbox / "collision.json").write_text(json.dumps(incoming), encoding="utf-8")

    report = ingest_events()
    assert report["conflict"] == 1
    assert report["rejected"] == 1
    assert list(rejected.glob("*conflict*"))


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
