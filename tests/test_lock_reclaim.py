"""Восстановление после аварийного завершения с оставшимся lock."""

from __future__ import annotations

from moex_portfolio.locks import pipeline_lock


def test_reclaim_dead_pid_lock(tmp_path, monkeypatch):
    monkeypatch.setattr("moex_portfolio.locks.LOCKS_DIR", tmp_path)
    stale = tmp_path / "pipeline.lock"
    # заведомо мёртвый PID на большинстве ОС
    stale.write_text("pid=99999999\n", encoding="utf-8")

    with pipeline_lock("pipeline") as path:
        assert path.exists()
        assert "pid=" in path.read_text(encoding="utf-8")
    assert not stale.exists()
