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
