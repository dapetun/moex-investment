"""Тесты журнала запусков."""

from moex_portfolio.run_journal import (
    finish_run,
    list_runs,
    load_run,
    start_run,
)


def test_start_and_finish_run(tmp_path, monkeypatch):
    monkeypatch.setattr("moex_portfolio.run_journal.RUNS_DIR", tmp_path)
    run = start_run(command="show-portfolio", params={"x": 1})
    assert run["status"] == "running"
    assert "run_id" in run
    assert (tmp_path / f"{run['run_id']}.json").exists()

    finished = finish_run(run["run_id"], status="ok", result={"n": 0})
    assert finished["status"] == "ok"
    assert finished["result"]["n"] == 0
    assert finished["finished_at"] is not None


def test_list_runs(tmp_path, monkeypatch):
    monkeypatch.setattr("moex_portfolio.run_journal.RUNS_DIR", tmp_path)
    start_run(command="a")
    start_run(command="b")
    runs = list_runs()
    assert len(runs) == 2


def test_load_run(tmp_path, monkeypatch):
    monkeypatch.setattr("moex_portfolio.run_journal.RUNS_DIR", tmp_path)
    run = start_run(command="show-portfolio")
    loaded = load_run(run["run_id"])
    assert loaded["command"] == "show-portfolio"
