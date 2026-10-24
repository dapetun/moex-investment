"""check-portfolio-ready без optimize."""

from __future__ import annotations

from pathlib import Path

from moex_portfolio.portfolio_ready import check_portfolio_ready

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "tests" / "fixtures" / "e2e_multi_account_portfolio.csv"


def test_ready_ok_for_e2e_csv() -> None:
    report = check_portfolio_ready(
        csv_path=CSV,
        panel_tickers={"AAA", "BBB", "CCC"},
    )
    assert report["ok"] is True
    assert report["ready_for_optimize"] is True
    assert report["n_positions"] == 3
    assert any(c["name"] == "weight_vs_mv" and c["ok"] for c in report["checks"])


def test_missing_panel_ticker_blocks() -> None:
    report = check_portfolio_ready(
        csv_path=CSV,
        panel_tickers={"AAA", "BBB"},  # CCC отсутствует
    )
    assert report["ok"] is False
    assert any("CCC" in b for b in report["blockers"])


def test_panel_tickers_required_for_ready() -> None:
    report = check_portfolio_ready(csv_path=CSV, panel_tickers=None)
    assert report["ok"] is False
    assert report["ready_for_optimize"] is False
    assert any("panel_coverage" in b for b in report["blockers"])
