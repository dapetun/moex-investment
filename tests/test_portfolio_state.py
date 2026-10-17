"""Тесты модели фактических позиций портфеля (holdings)."""

import json

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


def test_save_preserves_position_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr("moex_portfolio.portfolio_state.HOLDINGS_DIR", tmp_path)
    data = {
        "as_of": "2026-10-10",
        "cash": 0.0,
        "positions": [
            {
                "ticker": "TSTA",
                "shares": 15,
                "weight": 0.4,
                "note": "merged",
                "isin": "RU00TEST0001",
                "secid": "TSTA",
                "board": "TQBR",
                "security_type": "share",
                "accounts": [
                    {"account_label": "a", "weight": 0.2, "shares": 10},
                    {"account_label": "b", "weight": 0.2, "shares": 5},
                ],
            },
            {"ticker": "TSTB", "weight": 0.6, "note": ""},
        ],
    }
    save_holdings(data)
    loaded = load_holdings()
    pos = loaded["positions"][0]
    assert pos["isin"] == "RU00TEST0001"
    assert pos["secid"] == "TSTA"
    assert pos["board"] == "TQBR"
    assert pos["security_type"] == "share"
    assert len(pos["accounts"]) == 2


def test_canonical_weight_tolerance_is_tight():
    data = {
        "as_of": None,
        "cash": 0.0,
        "positions": [
            {"ticker": "A", "weight": 0.40},
            {"ticker": "B", "weight": 0.35},
            {"ticker": "C", "weight": 0.248},
        ],
    }
    with pytest.raises(HoldingsValidationError, match="weights sum"):
        validate_holdings(data)


def test_missing_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr("moex_portfolio.portfolio_state.HOLDINGS_DIR", tmp_path)
    loaded = load_holdings()
    assert loaded["positions"] == []
    assert loaded["file_status"] == "missing"


def test_empty_file_status_empty(tmp_path, monkeypatch):
    monkeypatch.setattr("moex_portfolio.portfolio_state.HOLDINGS_DIR", tmp_path)
    save_holdings(empty_holdings())
    loaded = load_holdings()
    assert loaded["positions"] == []
    assert loaded["file_status"] == "empty"


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
    with pytest.raises(HoldingsValidationError, match="HOLDINGS_SHARES_WITHOUT_WEIGHTS"):
        weights_from_holdings(data)


def test_legacy_policy_normalizes_on_load_without_rewrite(tmp_path, monkeypatch):
    monkeypatch.setattr("moex_portfolio.portfolio_state.HOLDINGS_DIR", tmp_path)
    path = tmp_path / "holdings.json"
    raw = {
        "as_of": "2026-10-10",
        "cash": 0.0,
        "weight_sum_policy": "legacy_analyst",
        "positions": [
            {"ticker": "A", "weight": 0.40},
            {"ticker": "B", "weight": 0.35},
            {"ticker": "C", "weight": 0.248},
        ],
    }
    path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    before = path.read_text(encoding="utf-8")
    loaded = load_holdings()
    assert loaded["weight_normalized_on_load"] is True
    assert abs(loaded["weight_sum_before"] - 0.998) < 1e-9
    assert abs(sum(p["weight"] for p in loaded["positions"]) - 1.0) < 1e-6
    assert path.read_text(encoding="utf-8") == before


def test_non_legacy_wrong_sum_still_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr("moex_portfolio.portfolio_state.HOLDINGS_DIR", tmp_path)
    path = tmp_path / "holdings.json"
    path.write_text(
        json.dumps(
            {
                "as_of": None,
                "cash": 0.0,
                "positions": [
                    {"ticker": "A", "weight": 0.40},
                    {"ticker": "B", "weight": 0.35},
                    {"ticker": "C", "weight": 0.248},
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(HoldingsValidationError, match="HOLDINGS_WEIGHT_SUM"):
        load_holdings()


def test_save_holdings_does_not_keep_legacy_policy(tmp_path, monkeypatch):
    monkeypatch.setattr("moex_portfolio.portfolio_state.HOLDINGS_DIR", tmp_path)
    data = {
        "as_of": None,
        "cash": 0.0,
        "weight_sum_policy": "legacy_analyst",
        "positions": [
            {"ticker": "A", "weight": 0.5},
            {"ticker": "B", "weight": 0.5},
        ],
    }
    save_holdings(data)
    on_disk = json.loads((tmp_path / "holdings.json").read_text(encoding="utf-8"))
    assert "weight_sum_policy" not in on_disk
