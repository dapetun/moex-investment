"""Тесты inbox событий от бота №1."""

import json

import pytest

from moex_portfolio.events import EventValidationError, ingest_events, validate_event


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


def test_ingest_moves_valid(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    inbox.mkdir()
    monkeypatch.setattr("moex_portfolio.events.INBOX_DIR", inbox)
    monkeypatch.setattr("moex_portfolio.events.PROCESSED_DIR", processed)

    good = {
        "event_type": "dividend_forecast",
        "title": "AAA",
        "url": "https://example.com/a",
        "published_at": "2026-10-01",
        "source": "finam",
    }
    (inbox / "e1.json").write_text(json.dumps(good), encoding="utf-8")
    (inbox / "bad.json").write_text("{not json", encoding="utf-8")

    report = ingest_events()
    assert report["accepted"] == 1
    assert report["rejected"] == 1
    assert (processed / "e1.json").exists()
