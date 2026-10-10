"""Тесты адаптера CSV аналитика → holdings.json."""

from pathlib import Path

import pytest

from moex_portfolio.portfolio_adapter import (
    PortfolioAdapterError,
    adapt_analyst_csv,
    holdings_for_compare,
    resolve_ticker,
)

FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "synthetic_analyst_portfolio.csv"
)


def test_adapt_synthetic_csv():
    h = adapt_analyst_csv(FIXTURE, panel_tickers={"TSTA", "TSTB", "TSTC", "AAA"})
    assert h["file_status"] == "ok" or h["adapter"]["file_status"] == "ok"
    assert len(h["positions"]) == 3
    assert abs(sum(p["weight"] for p in h["positions"]) - 1.0) < 1e-6
    assert h["adapter"]["cash_in_weight_sum"] is False
    assert h["adapter"]["missing_from_panel"] == []
    w = holdings_for_compare(h)
    assert set(w) == {"TSTA", "TSTB", "TSTC"}


def test_missing_from_panel_flagged():
    h = adapt_analyst_csv(FIXTURE, panel_tickers={"TSTA"})
    assert set(h["adapter"]["missing_from_panel"]) == {"TSTB", "TSTC"}


def test_ambiguous_isin_without_map_raises(tmp_path):
    p = tmp_path / "p.csv"
    p.write_text("isin,weight\nRU00TEST9999,1.0\n", encoding="utf-8")
    with pytest.raises(PortfolioAdapterError, match="PORTFOLIO_ID_AMBIGUOUS"):
        adapt_analyst_csv(p)


def test_bad_row_fails_whole_file(tmp_path):
    p = tmp_path / "p.csv"
    p.write_text(
        "ticker,weight\nTSTA,0.5\nTSTB,0.5\nTSTC,abc\n",
        encoding="utf-8",
    )
    with pytest.raises(PortfolioAdapterError, match="PORTFOLIO_ROW_ERRORS"):
        adapt_analyst_csv(p)


def test_mixed_weights_rejected(tmp_path):
    p = tmp_path / "p.csv"
    p.write_text(
        "ticker,weight,quantity\nTSTA,0.5,\nTSTB,,10\n",
        encoding="utf-8",
    )
    with pytest.raises(PortfolioAdapterError, match="PORTFOLIO_MIXED_WEIGHTS"):
        adapt_analyst_csv(p)


def test_isin_map_resolves(tmp_path):
    p = tmp_path / "p.csv"
    p.write_text("isin,weight\nRU00TEST0001,1.0\n", encoding="utf-8")
    h = adapt_analyst_csv(p, isin_to_ticker={"RU00TEST0001": "TSTA"})
    assert h["positions"][0]["ticker"] == "TSTA"


def test_resolve_ticker_prefers_secid_over_csv_ticker():
    # облигация: CSV ticker ≠ secid — ключ CLI = secid (RESULT 1936)
    assert (
        resolve_ticker(
            {"ticker": "TSTA-BO1", "secid": "RU00TEST0004", "isin": "RU00TEST0004"}
        )
        == "RU00TEST0004"
    )
    assert resolve_ticker({"secid": "SBER", "isin": "RU0009029540"}) == "SBER"


def test_legacy_weight_sum_normalized_with_flag(tmp_path):
    p = tmp_path / "p.csv"
    p.write_text(
        "ticker,weight\nTSTA,0.40\nTSTB,0.35\nTSTC,0.248\n",
        encoding="utf-8",
    )
    h = adapt_analyst_csv(p)
    assert h["adapter"]["weight_normalized"] is True
    assert abs(h["adapter"]["weight_sum_before"] - 0.998) < 1e-9
    assert abs(sum(x["weight"] for x in h["positions"]) - 1.0) < 1e-6


def test_weight_sum_outside_analyst_tolerance_rejected(tmp_path):
    p = tmp_path / "p.csv"
    p.write_text(
        "ticker,weight\nTSTA,0.40\nTSTB,0.35\nTSTC,0.22\n",
        encoding="utf-8",
    )
    with pytest.raises(PortfolioAdapterError, match="PORTFOLIO_WEIGHT_SUM"):
        adapt_analyst_csv(p)


def test_same_secid_across_accounts_consolidated(tmp_path):
    p = tmp_path / "p.csv"
    p.write_text(
        "secid,account_label,weight,quantity\n"
        "TSTA,broker_a,0.20,10\n"
        "TSTA,broker_b,0.20,5\n"
        "TSTB,broker_a,0.60,3\n",
        encoding="utf-8",
    )
    h = adapt_analyst_csv(p)
    by_ticker = {x["ticker"]: x for x in h["positions"]}
    assert set(by_ticker) == {"TSTA", "TSTB"}
    assert abs(by_ticker["TSTA"]["weight"] - 0.40) < 1e-9
    assert abs(by_ticker["TSTA"]["shares"] - 15.0) < 1e-9
    assert len(by_ticker["TSTA"]["accounts"]) == 2
    assert {a["account_label"] for a in by_ticker["TSTA"]["accounts"]} == {
        "broker_a",
        "broker_b",
    }


def test_consolidation_mixed_basis_rejected(tmp_path):
    p = tmp_path / "p.csv"
    p.write_text(
        "secid,account_label,weight,quantity\n"
        "TSTA,broker_a,0.50,10\n"
        "TSTA,broker_b,,5\n"
        "TSTB,broker_a,0.50,3\n",
        encoding="utf-8",
    )
    with pytest.raises(PortfolioAdapterError, match="PORTFOLIO_MIXED_WEIGHTS"):
        adapt_analyst_csv(p)
