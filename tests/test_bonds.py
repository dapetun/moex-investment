"""Тесты модуля bonds."""


from datetime import date, timedelta

from moex_portfolio.bonds import (
    bond_analysis,
    bond_price,
    bond_ytm,
    convexity,
    macaulay_duration,
    modified_duration,
    price_change_approximation,
    years_between,
)


def test_bond_price():
    price = bond_price(
        coupon_rate=0.08, face_value=1000, ytm=0.08,
        years_to_maturity=5, coupons_per_year=2,
    )
    assert abs(price - 1000.0) < 1.0


def test_bond_price_coupon_above_ytm():
    price = bond_price(
        coupon_rate=0.10, face_value=1000, ytm=0.08,
        years_to_maturity=5, coupons_per_year=2,
    )
    assert price > 1000.0


def test_bond_price_coupon_below_ytm():
    price = bond_price(
        coupon_rate=0.06, face_value=1000, ytm=0.08,
        years_to_maturity=5, coupons_per_year=2,
    )
    assert price < 1000.0


def test_bond_ytm():
    target_price = 950.0
    ytm = bond_ytm(
        price=target_price, coupon_rate=0.08, face_value=1000,
        years_to_maturity=5, coupons_per_year=2,
    )
    assert 0.05 < ytm < 0.15


def test_bond_ytm_roundtrip():
    coupon = 0.07
    face = 1000
    ytm_target = 0.06
    T = 10
    price = bond_price(coupon, face, ytm_target, T, 2)
    ytm_calc = bond_ytm(price, coupon, face, T, 2)
    assert abs(ytm_calc - ytm_target) < 0.001


def test_macaulay_duration():
    mac_d = macaulay_duration(
        coupon_rate=0.08, face_value=1000, ytm=0.08,
        years_to_maturity=5, coupons_per_year=2,
    )
    assert 3.0 < mac_d < 5.0


def test_modified_duration():
    mac_d = macaulay_duration(0.08, 1000, 0.08, 5, 2)
    mod_d = modified_duration(0.08, 1000, 0.08, 5, 2)
    assert mod_d < mac_d
    assert mod_d > 0


def test_convexity():
    conv = convexity(0.08, 1000, 0.08, 5, 2)
    assert conv > 0


def test_price_change_approximation():
    mod_d = 4.0
    conv_val = 20.0
    price = 1000.0
    new_price = price_change_approximation(mod_d, conv_val, price, 0.01)
    assert new_price < price
    new_price_up = price_change_approximation(mod_d, conv_val, price, -0.01)
    assert new_price_up > price


def test_years_between():
    d1 = date(2024, 1, 1)
    d2 = date(2025, 1, 1)
    years = years_between(d1, d2)
    assert abs(years - 1.0) < 0.01


def test_bond_analysis():
    result = bond_analysis(
        ticker="TEST",
        price=950.0,
        coupon_rate=0.08,
        face_value=1000,
        maturity_date=date.today() + timedelta(days=365 * 5),
        coupons_per_year=2,
    )
    assert "ytm" in result
    assert "modified_duration" in result
    assert "convexity" in result
    assert result["ytm"] > 0


def test_bond_analysis_matured():
    result = bond_analysis(
        ticker="OLD",
        price=1000.0,
        coupon_rate=0.08,
        face_value=1000,
        maturity_date=date.today() - timedelta(days=10),
    )
    assert "error" in result
