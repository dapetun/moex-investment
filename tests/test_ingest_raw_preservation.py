"""Сырые байты inbox не исчезают при ошибке разбора или сбое rejected/archive.

Изолированные временные каталоги. Без ISS, сети и оптимизатора.
"""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from moex_portfolio.events import ingest_events

_MARKER_A = b'{"broken": RAW-PRESERVE-A}\n'
_MARKER_B = b'{"broken": RAW-PRESERVE-B}\n'


def _dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    rejected = tmp_path / "rejected"
    archive = tmp_path / "archive"
    batches = tmp_path / "batches"
    history = tmp_path / "history"
    for directory in (inbox, processed, rejected, archive, batches, history):
        directory.mkdir()
    monkeypatch.setattr("moex_portfolio.events.INBOX_DIR", inbox)
    monkeypatch.setattr("moex_portfolio.events.PROCESSED_DIR", processed)
    monkeypatch.setattr("moex_portfolio.events.REJECTED_DIR", rejected)
    monkeypatch.setattr("moex_portfolio.events.INBOX_ARCHIVE_DIR", archive)
    monkeypatch.setattr("moex_portfolio.events.BATCH_META_DIR", batches)
    monkeypatch.setattr("moex_portfolio.events.HISTORY_DIR", history)
    return inbox, processed, rejected, archive


def _freeze(directory: Path):
    directory.chmod(stat.S_IRUSR | stat.S_IXUSR)


def _thaw(directory: Path):
    directory.chmod(stat.S_IRWXU)


def _copies_of(raw: bytes, *roots: Path) -> list[Path]:
    found: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.read_bytes() == raw:
                found.append(path)
    return found


def test_malformed_json_kept_when_rejected_dir_not_writable(tmp_path, monkeypatch):
    inbox, _processed, rejected, archive = _dirs(tmp_path, monkeypatch)
    raw = _MARKER_A
    src = inbox / "broken.json"
    src.write_bytes(raw)
    _freeze(rejected)
    try:
        report = ingest_events()
    finally:
        _thaw(rejected)

    assert report["rejected"] == 1
    assert report["partial"] is True
    assert _copies_of(raw, inbox, rejected, archive), "raw bytes lost"


def test_malformed_json_kept_when_rejected_and_archive_not_writable(
    tmp_path, monkeypatch
):
    inbox, _processed, rejected, archive = _dirs(tmp_path, monkeypatch)
    raw = _MARKER_A
    src = inbox / "broken.json"
    src.write_bytes(raw)
    _freeze(rejected)
    _freeze(archive)
    try:
        report = ingest_events()
    finally:
        _thaw(rejected)
        _thaw(archive)

    assert report["rejected"] == 1
    assert report["partial"] is True
    assert src.is_file()
    assert src.read_bytes() == raw


def test_second_parse_error_does_not_overwrite_first_raw_bytes(tmp_path, monkeypatch):
    inbox, _processed, rejected, archive = _dirs(tmp_path, monkeypatch)
    src = inbox / "broken.json"
    src.write_bytes(_MARKER_A)
    first = ingest_events()
    assert first["rejected"] == 1

    src.write_bytes(_MARKER_B)
    second = ingest_events()
    assert second["rejected"] == 1

    assert _copies_of(_MARKER_A, inbox, rejected, archive)
    assert _copies_of(_MARKER_B, inbox, rejected, archive)


def test_valid_inbox_kept_when_archive_copy_fails(tmp_path, monkeypatch):
    inbox, _processed, _rejected, archive = _dirs(tmp_path, monkeypatch)
    payload = {
        "event_id": "evt-preserve-1",
        "event_type": "dividend_declared",
        "title": "Synthetic",
        "url": "https://example.invalid/evt",
        "published_at": "2026-11-21",
        "source": "synthetic-fixture",
        "ticker": "AAA",
    }
    raw = (json.dumps(payload) + "\n").encode("utf-8")
    src = inbox / "good.json"
    src.write_bytes(raw)
    _freeze(archive)
    try:
        with pytest.raises(OSError):
            ingest_events()
    finally:
        _thaw(archive)

    assert src.is_file()
    assert src.read_bytes() == raw


def test_success_archives_exact_bytes_and_redelivery_keeps_both(tmp_path, monkeypatch):
    inbox, processed, rejected, archive = _dirs(tmp_path, monkeypatch)
    payload = {
        "event_id": "evt-preserve-2",
        "event_type": "dividend_declared",
        "title": "Synthetic",
        "url": "https://example.invalid/evt-2",
        "published_at": "2026-11-21",
        "source": "synthetic-fixture",
        "ticker": "BBB",
    }
    raw = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
    src = inbox / "good.json"
    src.write_bytes(raw)

    first = ingest_events()
    assert first["accepted"] == 1
    assert first["rejected"] == 0
    assert first["partial"] is False
    assert not src.exists()
    assert (processed / "evt-preserve-2.json").is_file()
    assert _copies_of(raw, archive)

    src.write_bytes(raw)
    second = ingest_events()
    assert second["duplicate_skipped"] == 1
    assert second["accepted"] == 0
    assert second["rejected"] == 0
    assert second["partial"] is False
    assert len(_copies_of(raw, archive)) >= 2
    assert not list(rejected.glob("*.json"))
