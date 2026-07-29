"""Tests for defaults module."""

from moex_portfolio.defaults import DEFAULTS, Defaults, get_defaults_dict


def test_defaults_singleton():
    d1 = DEFAULTS
    d2 = DEFAULTS
    assert d1 is d2


def test_defaults_are_immutable():
    assert isinstance(DEFAULTS, Defaults)
    assert DEFAULTS.corr_threshold == 0.25


def test_defaults_theory_values():
    assert 0.0 <= DEFAULTS.corr_threshold <= 1.0
    assert 0 < DEFAULTS.min_turnover_m <= 500
    assert 0.0 < DEFAULTS.max_weight <= 1.0
    assert 0.0 <= DEFAULTS.risk_free_rate <= 30.0
    assert DEFAULTS.cov_method in ("sample", "ledoit_wolf", "ewma")
    assert DEFAULTS.mc_simulations >= 1000
    assert DEFAULTS.rebalance_freq_days >= 1
    assert 0.0 <= DEFAULTS.min_drift <= 1.0
    assert DEFAULTS.bl_tau > 0.0
    assert 1 <= DEFAULTS.bl_n_views <= 100
    assert DEFAULTS.hrp_method in ("single", "complete", "average")


def test_get_defaults_dict():
    d = get_defaults_dict()
    assert isinstance(d, dict)
    assert "corr_threshold" in d
    assert "max_weight" in d
    assert "risk_free_rate" in d
    assert "cov_method" in d
    assert "bl_tau" in d
    assert len(d) >= 10


def test_defaults_dict_matches_singleton():
    d = get_defaults_dict()
    assert d["corr_threshold"] == DEFAULTS.corr_threshold
    assert d["max_weight"] == DEFAULTS.max_weight
    assert d["cov_method"] == DEFAULTS.cov_method
