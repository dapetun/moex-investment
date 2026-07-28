"""Тесты модуля stress_test."""

import numpy as np
import pandas as pd

from moex_portfolio.stress_test import (
    StressScenario,
    run_all_scenarios,
    run_stress_test,
    stress_results_to_dataframe,
)


def _sample_returns_with_crisis():
    """Генерация данных с��拟ным кризисом."""
    np.random.seed(42)
    dates = pd.bdate_range("2019-01-01", "2021-12-31")
    n = len(dates)
    tickers = ["A", "B", "C"]

    # Нормальный рост
    returns = np.random.normal(0.0005, 0.015, (n, 3))

    # Кризис в марте 2020
    crisis_start = None
    crisis_end = None
    for i, d in enumerate(dates):
        if d.year == 2020 and d.month == 2:
            crisis_start = i
        if d.year == 2020 and d.month == 4:
            crisis_end = i
            break

    if crisis_start and crisis_end:
        returns[crisis_start:crisis_end] = np.random.normal(-0.03, 0.05, (crisis_end - crisis_start, 3))

    return pd.DataFrame(returns, index=dates, columns=tickers)


def _equal_weights():
    return np.array([1 / 3, 1 / 3, 1 / 3])


def test_run_stress_test():
    returns = _sample_returns_with_crisis()
    weights = _equal_weights()

    scenario = StressScenario(
        name="Test Crisis",
        description="Test",
        start_date="2020-02-01",
        end_date="2020-06-30",
        peak_to_trough=-0.30,
    )

    result = run_stress_test(returns, weights, scenario)

    assert result.scenario_name == "Test Crisis"
    assert result.portfolio_return != 0.0 or result.portfolio_max_drawdown == 0.0
    assert result.portfolio_max_drawdown <= 0
    assert result.worst_day <= 0


def test_run_stress_test_no_data():
    returns = _sample_returns_with_crisis()
    weights = _equal_weights()

    scenario = StressScenario(
        name="Empty",
        description="No data",
        start_date="2015-01-01",
        end_date="2015-12-31",
        peak_to_trough=-0.10,
    )

    result = run_stress_test(returns, weights, scenario)
    assert result.portfolio_return == 0.0
    assert result.portfolio_max_drawdown == 0.0


def test_run_all_scenarios():
    returns = _sample_returns_with_crisis()
    weights = _equal_weights()

    results = run_all_scenarios(returns, weights)

    assert len(results) == 5
    assert all(r.scenario_name for r in results)


def test_stress_results_to_dataframe():
    returns = _sample_returns_with_crisis()
    weights = _equal_weights()

    results = run_all_scenarios(returns, weights)
    df = stress_results_to_dataframe(results)

    assert len(df) == 5
    assert "Scenario" in df.columns
    assert "Max Drawdown" in df.columns
