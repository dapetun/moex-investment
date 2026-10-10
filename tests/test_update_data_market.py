"""update-data в режиме market не должен делать ложный self-refresh."""

import json

from moex_portfolio.cli import main


def test_update_data_market_blocked(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("moex_portfolio.run_journal.RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr("moex_portfolio.locks.LOCKS_DIR", tmp_path / "locks")
    monkeypatch.setenv("MOEX_DATA_SOURCE", "market")
    monkeypatch.setenv("MOEX_ISS_ENABLED", "false")
    cache = tmp_path / "runtime_prices.csv"
    cache.write_text("TRADEDATE;AAA;AAA_VALUE\n2026-01-02;1;1e8\n", encoding="utf-8")
    monkeypatch.setenv("MOEX_RUNTIME_CACHE", str(cache))

    code = main(["update-data"])
    assert code == 4
    err = capsys.readouterr().err
    payload = json.loads(err)
    assert "MARKET_UPDATE_NO_UPSTREAM" in payload["error"]
