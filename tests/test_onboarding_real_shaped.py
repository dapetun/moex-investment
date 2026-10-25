"""Onboarding: искусственный портфель той же структуры, что ожидают от пользователя."""

from __future__ import annotations

from pathlib import Path

import pytest

from moex_portfolio.portfolio_adapter import PortfolioAdapterError, adapt_analyst_csv
from moex_portfolio.portfolio_ready import check_portfolio_ready

HDR = (
    "as_of_date,account_label,ticker,isin,secid,board,security_type,"
    "quantity,market_value,weight,notes"
)


def _write(tmp: Path, rows: list[str]) -> Path:
    p = tmp / "portfolio.csv"
    p.write_text("\n".join([HDR, *rows]) + "\n", encoding="utf-8")
    return p


def test_multi_account_ready(tmp_path: Path) -> None:
    csv = _write(
        tmp_path,
        [
            "2026-10-10,a,RSH1,RU00RSH10001,RSH1,TQBR,share,100,200000,0.20,x",
            "2026-10-10,b,RSH1,RU00RSH10001,RSH1,TQBR,share,50,100000,0.10,x",
            "2026-10-10,a,RSH2,RU00RSH20002,RSH2,TQBR,share,200,250000,0.25,x",
            "2026-10-10,a,RSH3,RU00RSH30003,RSH3,TQBR,share,300,450000,0.45,x",
        ],
    )
    report = check_portfolio_ready(
        csv_path=csv, panel_tickers={"RSH1", "RSH2", "RSH3"}
    )
    assert report["ok"] is True
    assert report["n_positions"] == 3
    h = adapt_analyst_csv(csv, panel_tickers={"RSH1", "RSH2", "RSH3"})
    assert any(p.get("accounts") for p in h["positions"])


def test_bad_weight_sum_rejected(tmp_path: Path) -> None:
    csv = _write(
        tmp_path,
        [
            "2026-10-10,a,RSH1,RU00RSH10001,RSH1,TQBR,share,100,500000,0.50,x",
            "2026-10-10,a,RSH2,RU00RSH20002,RSH2,TQBR,share,100,500000,0.60,x",
        ],
    )
    with pytest.raises(PortfolioAdapterError, match="PORTFOLIO_WEIGHT_SUM"):
        adapt_analyst_csv(csv)


def test_mixed_weight_basis_across_accounts_rejected(tmp_path: Path) -> None:
    """Один SECID: у одного счёта weight, у другого только MV — неоднозначность."""
    csv = _write(
        tmp_path,
        [
            "2026-10-10,a,RSH1,RU00RSH10001,RSH1,TQBR,share,100,200000,0.5,x",
            "2026-10-10,b,RSH1,RU00RSH10001,RSH1,TQBR,share,100,200000,,x",
        ],
    )
    with pytest.raises(PortfolioAdapterError, match="PORTFOLIO_"):
        adapt_analyst_csv(csv)


def test_panel_missing_blocks_ready(tmp_path: Path) -> None:
    csv = _write(
        tmp_path,
        [
            "2026-10-10,a,RSH1,RU00RSH10001,RSH1,TQBR,share,100,500000,0.50,x",
            "2026-10-10,a,RSH2,RU00RSH20002,RSH2,TQBR,share,100,500000,0.50,x",
        ],
    )
    report = check_portfolio_ready(csv_path=csv, panel_tickers={"RSH1"})
    assert report["ok"] is False
    assert any("RSH2" in b for b in report["blockers"])
