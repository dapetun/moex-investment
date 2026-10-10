"""Тесты модели фактических позиций портфеля (holdings)."""

import pytest

from moex_portfolio.portfolio_state import (
    HoldingsValidationError,
    empty_holdings,
    load_holdings,
    save_holdings,
    validate_holdings,
    weights_from_holdings,
)


def test_empty_holdings_is_valid():
    h = empty_holdings()
    validate_holdings(h)
    assert h["positions"] == []
    assert h["cash"] == 0.0


def test_save_and_load_empty(tmp_path, monkeypatch):
    monkeypatch.setattr("moex_portfolio.portfolio_state.HOLDINGS_DIR", tmp_path)
    path = save_holdings(empty_holdings())
    assert path.exists()
    loaded = load_holdings()
    assert loaded["positions"] == []
    assert loaded["cash"] == 0.0


def test_save_and_load_with_positions(tmp_path, monkeypatch):
    monkeypatch.setattr("moex_portfolio.portfolio_state.HOLDINGS_DIR", tmp_path)
    data = {
        "as_of": "2026-10-10",
        "cash": 1000.0,
        "positions": [
            {"ticker": "SBER", "shares": 10, "weight": 0.4, "note": ""},
            {"ticker": "GAZP", "shares": 5, "weight": 0.6, "note": "test"},
        ],
    }
    save_holdings(data)
    loaded = load_holdings()
    assert loaded["as_of"] == "2026-10-10"
    assert len(loaded["positions"]) == 2
    assert loaded["positions"][0]["ticker"] == "SBER"


def test_missing_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr("moex_portfolio.portfolio_state.HOLDINGS_DIR", tmp_path)
    loaded = load_holdings()
    assert loaded["positions"] == []


def test_invalid_weights_sum_raises():
    data = {
        "as_of": None,
        "cash": 0.0,
        "positions": [
            {"ticker": "A", "weight": 0.5},
            {"ticker": "B", "weight": 0.6},
        ],
    }
    with pytest.raises(HoldingsValidationError):
        validate_holdings(data)


def test_duplicate_ticker_raises():
    data = {
        "as_of": None,
        "cash": 0.0,
        "positions": [
            {"ticker": "SBER", "shares": 1},
            {"ticker": "SBER", "shares": 2},
        ],
    }
    with pytest.raises(HoldingsValidationError):
        validate_holdings(data)


def test_empty_ticker_raises():
    data = {
        "as_of": None,
        "cash": 0.0,
        "positions": [{"ticker": "", "shares": 1}],
    }
    with pytest.raises(HoldingsValidationError):
        validate_holdings(data)


def test_weights_from_holdings_explicit():
    data = {
        "as_of": None,
        "cash": 0.0,
        "positions": [
            {"ticker": "A", "weight": 0.3},
            {"ticker": "B", "weight": 0.7},
        ],
    }
    w = weights_from_holdings(data)
    assert w == {"A": 0.3, "B": 0.7}


def test_weights_from_empty_is_empty_dict():
    assert weights_from_holdings(empty_holdings()) == {}


def test_weights_from_shares_without_prices_raises():
    data = {
        "as_of": None,
        "cash": 0.0,
        "positions": [{"ticker": "A", "shares": 10}],
    }
    with pytest.raises(HoldingsValidationError):
        weights_from_holdings(data)
