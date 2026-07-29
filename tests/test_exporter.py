"""Тесты для модуля exporter."""

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from moex_portfolio.exporter import export_portfolio_to_excel, export_portfolio_to_pdf


@pytest.fixture
def sample_data():
    np.random.seed(42)
    clique = ["A", "B", "C"]
    opt_result = {
        "weights": np.array([0.5, 0.3, 0.2]),
        "return": 0.25,
        "volatility": 0.18,
        "sharpe": 1.39,
    }
    min_var_result = {
        "weights": np.array([0.2, 0.5, 0.3]),
        "return": 0.15,
        "volatility": 0.12,
        "sharpe": 1.25,
    }
    returns = pd.DataFrame(
        np.random.normal(0.001, 0.02, (100, 3)),
        columns=clique,
    )
    metrics = {
        "sortino": 2.1,
        "max_drawdown": -0.12,
        "calmar": 2.08,
    }
    params = {
        "corr_threshold": 0.25,
        "min_turnover": 50_000_000,
        "risk_free_rate": 0.0,
    }
    return clique, opt_result, min_var_result, returns, metrics, params


def test_export_basic(sample_data):
    clique, opt, mv, _returns, metrics, params = sample_data
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "portfolio.xlsx"
        result = export_portfolio_to_excel(
            path, clique, opt, mv, metrics=metrics, params=params,
        )
        assert result.exists()
        assert result.stat().st_size > 0


def test_export_with_mc(sample_data):
    clique, opt, mv, returns, metrics, params = sample_data
    mc = pd.DataFrame({
        "annual_return": np.random.normal(0.2, 0.1, 1000),
        "annual_volatility": np.random.normal(0.18, 0.05, 1000),
        "max_drawdown": np.random.normal(-0.15, 0.05, 1000),
        "sharpe": np.random.normal(1.2, 0.3, 1000),
    })
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "portfolio_mc.xlsx"
        result = export_portfolio_to_excel(
            path, clique, opt, mv, mc_results=mc, returns=returns,
            metrics=metrics, params=params,
        )
        assert result.exists()


def test_export_creates_parent_dirs():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "subdir" / "portfolio.xlsx"
        clique = ["A"]
        opt = {"weights": np.array([1.0]), "return": 0.1, "volatility": 0.1, "sharpe": 1.0}
        mv = {"weights": np.array([1.0]), "return": 0.1, "volatility": 0.1, "sharpe": 1.0}
        result = export_portfolio_to_excel(path, clique, opt, mv)
        assert result.exists()


def test_export_pdf(sample_data):
    clique, opt, mv, _returns, metrics, params = sample_data
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "report.pdf"
        result = export_portfolio_to_pdf(
            path, clique, opt, mv, metrics=metrics, params=params,
        )
        assert result.exists()
        assert result.stat().st_size > 0


def test_export_pdf_with_stress(sample_data):
    clique, opt, mv, _returns, metrics, params = sample_data
    from moex_portfolio.stress_test import StressTestResult
    stress = [
        StressTestResult(
            scenario_name="Test", description="Test scenario",
            start_date="2020-01-01", end_date="2020-06-01",
            portfolio_return=-0.10, portfolio_max_drawdown=-0.15,
            portfolio_volatility=0.20, worst_day=-0.05,
            worst_day_date="2020-03-12", recovery_days=30,
            max_drawdown=-0.15,
        )
    ]
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "report_stress.pdf"
        result = export_portfolio_to_pdf(
            path, clique, opt, mv, metrics=metrics, params=params,
            stress_results=stress,
        )
        assert result.exists()
