"""Тесты модели Мертона."""


from moex_portfolio.merton import (
    distance_to_default,
    full_merton_analysis,
    implied_asset_value,
    merton_credit_spread,
    merton_debt_value,
    merton_equity_value,
    probability_of_default,
    recovery_rate,
)


def test_merton_equity_value():
    equity = merton_equity_value(
        assets_value=1000, debt_face_value=800,
        volatility_assets=0.3, risk_free_rate=0.05, time_to_maturity=1.0,
    )
    assert equity > 0
    assert equity < 1000


def test_merton_debt_value():
    debt = merton_debt_value(
        assets_value=1000, debt_face_value=800,
        volatility_assets=0.3, risk_free_rate=0.05, time_to_maturity=1.0,
    )
    assert debt > 0
    assert debt <= 800


def test_distance_to_default_high_quality():
    dd = distance_to_default(
        assets_value=2000, debt_face_value=800,
        volatility_assets=0.2, risk_free_rate=0.05, time_to_maturity=1.0,
    )
    assert dd > 2.0


def test_distance_to_default_low_quality():
    dd = distance_to_default(
        assets_value=900, debt_face_value=800,
        volatility_assets=0.5, risk_free_rate=0.05, time_to_maturity=0.5,
    )
    assert dd < 2.0


def test_probability_of_default_safe():
    pd_val = probability_of_default(
        assets_value=2000, debt_face_value=800,
        volatility_assets=0.2, risk_free_rate=0.05, time_to_maturity=1.0,
    )
    assert 0 <= pd_val < 0.05


def test_probability_of_default_risky():
    pd_val = probability_of_default(
        assets_value=850, debt_face_value=800,
        volatility_assets=0.6, risk_free_rate=0.05, time_to_maturity=0.5,
    )
    assert pd_val > 0.05


def test_credit_spread():
    spread = merton_credit_spread(
        assets_value=1000, debt_face_value=800,
        volatility_assets=0.3, risk_free_rate=0.05, time_to_maturity=1.0,
    )
    assert spread >= 0


def test_recovery_rate():
    rr = recovery_rate(
        assets_value=1000, debt_face_value=800,
        volatility_assets=0.3, risk_free_rate=0.05, time_to_maturity=1.0,
    )
    assert 0 <= rr <= 1.0


def test_implied_asset_value():
    V, sigma_V = implied_asset_value(
        equity_value=200, debt_face_value=800,
        volatility_equity=0.5, risk_free_rate=0.05, time_to_maturity=1.0,
    )
    assert V > 0
    assert sigma_V > 0


def test_full_merton_analysis():
    result = full_merton_analysis(
        equity_value=300, debt_face_value=700,
        volatility_equity=0.4, risk_free_rate=0.05, time_to_maturity=2.0,
    )
    assert "distance_to_default" in result
    assert "probability_of_default" in result
    assert "credit_spread_bps" in result
    assert "recovery_rate" in result
    assert 0 <= result["probability_of_default"] <= 1
    assert 0 <= result["recovery_rate"] <= 1


def test_defaults_return_zero():
    assert distance_to_default(0, 800, 0.3, 0.05, 1.0) == 0.0
    assert distance_to_default(1000, 0, 0.3, 0.05, 1.0) == 0.0
    assert distance_to_default(1000, 800, 0.3, 0.05, 0.0) == 0.0
