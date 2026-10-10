"""Регрессии: неуспешный optimize не портит target; QC до расчёта; compare."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from moex_portfolio.cli import main

FIXTURE = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "synthetic_prices.csv"


def _patch_cli_paths(tmp_path, monkeypatch):
    monkeypatch.setattr("moex_portfolio.portfolio_state.HOLDINGS_DIR", tmp_path / "portfolio")
    monkeypatch.setattr("moex_portfolio.run_journal.RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr("moex_portfolio.locks.LOCKS_DIR", tmp_path / "locks")
    monkeypatch.setattr("moex_portfolio.reporting.REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr("moex_portfolio.cli.LAST_TARGET_PATH", tmp_path / "outbox" / "last_target.json")
    monkeypatch.setenv("MOEX_DATA_SOURCE", "fixture")
    monkeypatch.setenv("MOEX_ISS_ENABLED", "false")
    monkeypatch.setenv("MOEX_FIXTURE_PATH", str(FIXTURE))


def test_failed_optimize_preserves_previous_target(tmp_path, monkeypatch, capsys):
    _patch_cli_paths(tmp_path, monkeypatch)
    target_path = tmp_path / "outbox" / "last_target.json"
    target_path.parent.mkdir(parents=True)
    previous = {
        "weights": {"AAA": 1.0},
        "tickers": ["AAA"],
        "success": True,
        "source": "fixture",
    }
    target_path.write_text(json.dumps(previous), encoding="utf-8")

    def _fail_optimize(*_a, **_k):
        return {
            "mode": "universe",
            "tickers": ["AAA"],
            "weights": {"AAA": 1.0},
            "return": 0.0,
            "volatility": 0.0,
            "sharpe": 0.0,
            "success": False,
            "message": "forced failure",
            "risk_free_rate": 0.0,
            "max_weight": 0.5,
            "cov_method": "ledoit_wolf",
        }

    monkeypatch.setattr("moex_portfolio.cli.run_optimize", _fail_optimize)

    code = main(["optimize", "--allow-optimize", "--mode", "universe"])
    assert code == 2
    saved = json.loads(target_path.read_text(encoding="utf-8"))
    assert saved == previous
    # диагностический отчёт всё же должен появиться
    reports = list((tmp_path / "reports").glob("*.json"))
    assert len(reports) == 1
    assert reports[0].read_text(encoding="utf-8").find("forced failure") >= 0


def test_compare_rejects_unsuccessful_target(tmp_path, monkeypatch, capsys):
    _patch_cli_paths(tmp_path, monkeypatch)
    target_path = tmp_path / "outbox" / "last_target.json"
    target_path.parent.mkdir(parents=True)
    target_path.write_text(
        json.dumps(
            {
                "weights": {"AAA": 1.0},
                "success": False,
                "source": "fixture",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "portfolio").mkdir(parents=True)
    (tmp_path / "portfolio" / "holdings.json").write_text(
        json.dumps(
            {
                "as_of": None,
                "cash": 0.0,
                "positions": [{"ticker": "AAA", "weight": 1.0}],
            }
        ),
        encoding="utf-8",
    )

    code = main(["compare"])
    assert code == 2
    err = capsys.readouterr().err
    assert "success" in err.lower() or "target" in err.lower()


def test_compare_rejects_missing_success_flag(tmp_path, monkeypatch, capsys):
    _patch_cli_paths(tmp_path, monkeypatch)
    target_path = tmp_path / "outbox" / "last_target.json"
    target_path.parent.mkdir(parents=True)
    target_path.write_text(
        json.dumps({"weights": {"AAA": 1.0}, "source": "fixture"}),
        encoding="utf-8",
    )
    code = main(["compare"])
    assert code == 2


def test_optimize_blocked_when_market_data_stale(tmp_path, monkeypatch, capsys):
    """Рыночный режим: устаревшие котировки блокируют optimize и не трогают target."""
    _patch_cli_paths(tmp_path, monkeypatch)
    monkeypatch.setenv("MOEX_DATA_SOURCE", "market")

    stale = pd.DataFrame(
        {
            "AAA": range(30),
            "AAA_VALUE": [1e8] * 30,
            "BBB": range(30),
            "BBB_VALUE": [1e8] * 30,
        },
        index=pd.bdate_range("2020-01-02", periods=30),
    )
    stale.index.name = "TRADEDATE"

    class _StaleMarket:
        name = "market"

        def load_prices(self, tickers=None):
            return stale

    monkeypatch.setattr("moex_portfolio.cli.get_data_source", lambda: _StaleMarket())

    target_path = tmp_path / "outbox" / "last_target.json"
    target_path.parent.mkdir(parents=True)
    previous = {"weights": {"AAA": 1.0}, "success": True, "source": "fixture"}
    target_path.write_text(json.dumps(previous), encoding="utf-8")

    called = {"optimize": False}

    def _should_not_run(*_a, **_k):
        called["optimize"] = True
        raise AssertionError("run_optimize must not be called")

    monkeypatch.setattr("moex_portfolio.cli.run_optimize", _should_not_run)

    code = main(["optimize", "--allow-optimize", "--mode", "universe"])
    assert code == 2
    assert called["optimize"] is False
    assert json.loads(target_path.read_text(encoding="utf-8")) == previous


def test_fixture_optimize_does_not_require_calendar_freshness(tmp_path, monkeypatch):
    """Фикстура не маркируется как актуальный рынок — stale calendar не блокирует."""
    _patch_cli_paths(tmp_path, monkeypatch)
    # фикстура может иметь «старые» даты относительно today — QC структуры должен пройти
    code = main(["optimize", "--allow-optimize", "--mode", "universe"])
    assert code == 0
    target = json.loads((tmp_path / "outbox" / "last_target.json").read_text(encoding="utf-8"))
    assert target["success"] is True
    assert target.get("source") == "fixture"
    assert target.get("is_live_market") is False
