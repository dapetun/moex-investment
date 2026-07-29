"""Тесты кривой доходности."""

from datetime import date, timedelta

import numpy as np
import pandas as pd

from moex_portfolio.yield_curve import (
    build_yield_curve,
    compute_forward_rates,
    forward_rate,
    interpolate_yield_curve,
    spot_spread,
    term_structure_analysis,
    zero_coupon_yield,
)


def _make_ofz_data():
    today = date.today()
    return pd.DataFrame({
        "SECID": ["SU26208RMFS9", "SU26210RMFS7", "SU26228RMFS6", "SU26238RMFS0"],
        "YIELDTOOFFER": [12.5, 13.0, 14.0, 14.5],
        "MATDATE": [
            (today + timedelta(days=365)).isoformat(),
            (today + timedelta(days=365 * 2)).isoformat(),
            (today + timedelta(days=365 * 5)).isoformat(),
            (today + timedelta(days=365 * 10)).isoformat(),
        ],
    })


def test_build_yield_curve():
    curve = build_yield_curve(_make_ofz_data())
    assert len(curve) == 4
    assert "maturity_years" in curve.columns
    assert "yield_pct" in curve.columns


def test_build_yield_curve_empty():
    curve = build_yield_curve(pd.DataFrame())
    assert len(curve) == 0


def test_interpolate_yield_curve():
    curve = build_yield_curve(_make_ofz_data())
    interp = interpolate_yield_curve(curve, target_maturities=np.array([1, 2, 5, 10]))
    assert len(interp) == 4
    assert "yield_pct" in interp.columns


def test_interpolate_single_point():
    curve = pd.DataFrame({"maturity_years": [1.0], "yield_pct": [12.0]})
    result = interpolate_yield_curve(curve)
    assert len(result) == 1


def test_zero_coupon_yield():
    zcy = zero_coupon_yield(
        coupon_rate=0.08, face_value=1000, ytm=0.08, maturity_years=5,
    )
    assert isinstance(zcy, float)


def test_forward_rate():
    fr = forward_rate(spot_rate_1=0.05, spot_rate_2=0.06, maturity_1=1.0, maturity_2=2.0)
    assert fr > 0


def test_forward_rate_equal_maturities():
    fr = forward_rate(0.05, 0.06, 2.0, 1.0)
    assert fr == 0.0


def test_compute_forward_rates():
    curve = build_yield_curve(_make_ofz_data())
    forwards = compute_forward_rates(curve)
    assert len(forwards) > 0
    assert "forward_rate_pct" in forwards.columns


def test_spot_spread():
    spread = spot_spread(bond_yield=8.0, risk_free_yield=6.0)
    assert abs(spread - 2.0) < 0.001


def test_term_structure_analysis_normal():
    curve = pd.DataFrame({
        "maturity_years": [1, 5, 10],
        "yield_pct": [5.0, 7.0, 9.0],
    })
    result = term_structure_analysis(curve)
    assert result["shape"] == "normal"
    assert result["term_spread_pct"] > 0


def test_term_structure_analysis_inverted():
    curve = pd.DataFrame({
        "maturity_years": [1, 5, 10],
        "yield_pct": [9.0, 7.0, 5.0],
    })
    result = term_structure_analysis(curve)
    assert result["shape"] == "inverted"


def test_term_structure_analysis_flat():
    curve = pd.DataFrame({
        "maturity_years": [1, 5, 10],
        "yield_pct": [7.0, 7.1, 7.2],
    })
    result = term_structure_analysis(curve)
    assert result["shape"] == "flat"


def test_term_structure_insufficient():
    result = term_structure_analysis(pd.DataFrame({"maturity_years": [1], "yield_pct": [5.0]}))
    assert result["shape"] == "insufficient_data"
