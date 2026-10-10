"""Тесты сравнения текущих и целевых весов."""

from moex_portfolio.compare import compare_weights


def test_compare_identical():
    w = {"A": 0.5, "B": 0.5}
    report = compare_weights(w, w, min_drift=0.05)
    assert report["needs_rebalance"] is False
    assert report["max_abs_drift"] == 0.0
    assert report["tickers"] == ["A", "B"]


def test_compare_drift_triggers():
    current = {"A": 0.7, "B": 0.3}
    target = {"A": 0.5, "B": 0.5}
    report = compare_weights(current, target, min_drift=0.05)
    assert report["needs_rebalance"] is True
    assert abs(report["max_abs_drift"] - 0.2) < 1e-9
    drifts = {d["ticker"]: d["drift"] for d in report["diffs"]}
    assert abs(drifts["A"] - 0.2) < 1e-9


def test_compare_empty_current():
    report = compare_weights({}, {"A": 1.0}, min_drift=0.05)
    assert report["needs_rebalance"] is True
    assert report["max_abs_drift"] == 1.0
