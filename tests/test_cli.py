"""Тесты headless CLI (офлайн, без сети)."""

import json

from moex_portfolio.cli import main


def test_show_portfolio_empty(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("moex_portfolio.portfolio_state.HOLDINGS_DIR", tmp_path)
    monkeypatch.setattr("moex_portfolio.run_journal.RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr("moex_portfolio.locks.LOCKS_DIR", tmp_path / "locks")

    code = main(["show-portfolio"])
    assert code == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["positions"] == []


def test_cli_help_returns_zero():
    code = main(["--help"])
    # argparse help exits via SystemExit(0) — handled in main
    assert code == 0


def test_report_does_not_overwrite_source_run_report(tmp_path, monkeypatch, capsys):
    """report --run-id пишет новый файл; исходный отчёт optimize сохраняется."""
    from moex_portfolio.reporting import write_report
    from moex_portfolio.run_journal import finish_run, start_run

    runs = tmp_path / "runs"
    reports = tmp_path / "reports"
    locks = tmp_path / "locks"
    monkeypatch.setattr("moex_portfolio.run_journal.RUNS_DIR", runs)
    monkeypatch.setattr("moex_portfolio.reporting.REPORTS_DIR", reports)
    monkeypatch.setattr("moex_portfolio.locks.LOCKS_DIR", locks)

    src = start_run("optimize", params={})
    write_report(
        run_id=src["run_id"],
        title="Optimization report",
        payload={"success": True, "weights": {"AAA": 1.0}},
    )
    finish_run(src["run_id"], status="ok", result={"success": True, "weights": {"AAA": 1.0}})
    before = (reports / f"{src['run_id']}.md").read_text(encoding="utf-8")

    code = main(["report", "--run-id", src["run_id"]])
    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["from_run_id"] == src["run_id"]
    assert out["run_id"] != src["run_id"]
    assert (reports / f"{src['run_id']}.md").read_text(encoding="utf-8") == before
    assert "Optimization report" in before
    new_md = (reports / f"{out['run_id']}.md").read_text(encoding="utf-8")
    assert f"Report for {src['run_id']}" in new_md
