"""Регрессии: NaN/Inf/overflow не проходят в holdings/compare/target."""

import pytest

from moex_portfolio.cli import TargetValidationError, _require_successful_target
from moex_portfolio.compare import compare_weights
from moex_portfolio.numeric import NumericValidationError
from moex_portfolio.portfolio_state import HoldingsValidationError, validate_holdings


def test_holdings_reject_nan_weight():
    with pytest.raises(HoldingsValidationError):
        validate_holdings(
            {
                "cash": 0.0,
                "positions": [{"ticker": "A", "weight": float("nan")}],
            }
        )


def test_holdings_reject_inf_shares():
    with pytest.raises(HoldingsValidationError):
        validate_holdings(
            {
                "cash": 0.0,
                "positions": [{"ticker": "A", "shares": float("inf")}],
            }
        )


def test_holdings_reject_overflow_literal():
    with pytest.raises(HoldingsValidationError):
        validate_holdings(
            {
                "cash": 0.0,
                "positions": [{"ticker": "A", "shares": 1e309}],
            }
        )


def test_holdings_reject_negative_weight():
    with pytest.raises(HoldingsValidationError):
        validate_holdings(
            {
                "cash": 0.0,
                "positions": [
                    {"ticker": "A", "weight": -0.1},
                    {"ticker": "B", "weight": 1.1},
                ],
            }
        )


def test_compare_reject_nan_current():
    with pytest.raises(NumericValidationError):
        compare_weights({"A": float("nan")}, {"A": 1.0}, min_drift=0.05)


def test_compare_reject_inf_min_drift():
    with pytest.raises(NumericValidationError):
        compare_weights({"A": 1.0}, {"A": 1.0}, min_drift=float("inf"))


def test_compare_reject_negative_min_drift():
    with pytest.raises(NumericValidationError):
        compare_weights({"A": 1.0}, {"A": 1.0}, min_drift=-0.01)


def test_compare_reject_bad_target_sum():
    with pytest.raises(NumericValidationError):
        compare_weights({"A": 0.5}, {"A": 0.5, "B": 0.6}, min_drift=0.05)


def test_target_reject_nan_weight(tmp_path):
    path = tmp_path / "t.json"
    with pytest.raises(TargetValidationError, match="finite"):
        _require_successful_target(
            {
                "success": True,
                "weights": {"A": float("nan")},
            },
            path,
        )


def test_target_reject_wrong_sum(tmp_path):
    path = tmp_path / "t.json"
    with pytest.raises(TargetValidationError, match="TARGET_WEIGHT_SUM"):
        _require_successful_target(
            {
                "success": True,
                "weights": {"A": 0.4, "B": 0.4},
            },
            path,
        )


def test_nan_does_not_yield_false_no_rebalance():
    """Контроль: NaN не должен тихо дать needs_rebalance=False."""
    with pytest.raises(NumericValidationError):
        compare_weights(
            {"A": float("nan"), "B": 0.0},
            {"A": 0.5, "B": 0.5},
            min_drift=0.05,
        )
