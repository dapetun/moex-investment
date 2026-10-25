"""Тесты файловой блокировки пайплайна."""

import pytest

from moex_portfolio.locks import PipelineLockError, pipeline_lock


def test_lock_acquire_and_release(tmp_path, monkeypatch):
    monkeypatch.setattr("moex_portfolio.locks.LOCKS_DIR", tmp_path)
    with pipeline_lock("test"):
        lock_file = tmp_path / "test.lock"
        assert lock_file.exists()
    assert not lock_file.exists()


def test_lock_blocks_second_process(tmp_path, monkeypatch):
    monkeypatch.setattr("moex_portfolio.locks.LOCKS_DIR", tmp_path)
    with pipeline_lock("test"):
        with pytest.raises(PipelineLockError):
            with pipeline_lock("test"):
                pass
