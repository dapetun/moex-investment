"""Тесты для модуля risk_models."""

import numpy as np
import pandas as pd
import pytest

from moex_portfolio.risk_models import (
    compute_alpha,
    compute_beta,
    covariance_matrix,
    ewma_covariance,
    ledoit_wolf_covariance,
)


@pytest.fixture
def sample_returns():
    np.random.seed(42)
    n = 200
    dates = pd.bdate_range("2024-01-01", periods=n)
    return pd.DataFrame(
        {
            "A": np.random.normal(0.001, 0.02, n),
            "B": np.random.normal(0.0005, 0.015, n),
            "C": np.random.normal(-0.001, 0.025, n),
        },
        index=dates,
    )


@pytest.fixture
def market_returns(sample_returns):
    return sample_returns.mean(axis=1)


def test_ledoit_wolf_covariance(sample_returns):
    cov = ledoit_wolf_covariance(sample_returns)
    assert cov.shape == (3, 3)
    assert list(cov.columns) == ["A", "B", "C"]
    assert (cov.values == cov.values.T).all()  # Симметричная


def test_ewma_covariance(sample_returns):
    cov = ewma_covariance(sample_returns, span=30)
    assert cov.shape == (3, 3)
    assert list(cov.columns) == ["A", "B", "C"]


def test_ewma_different_spans(sample_returns):
    cov1 = ewma_covariance(sample_returns, span=10)
    cov3 = ewma_covariance(sample_returns, span=60)
    # Разные span дают разные результаты
    assert not np.allclose(cov1.values, cov3.values)


def test_compute_beta(sample_returns, market_returns):
    beta = compute_beta(sample_returns, market_returns)
    assert len(beta) == 3
    assert "A" in beta.index
    # Бета рынка сам к себе ≈ 1.0
    mkt_beta = compute_beta(
        pd.DataFrame({"market": market_returns}),
        market_returns,
    )
    assert abs(mkt_beta.iloc[0] - 1.0) < 0.01


def test_compute_alpha(sample_returns, market_returns):
    alpha = compute_alpha(sample_returns, market_returns)
    assert len(alpha) == 3
    assert "A" in alpha.index
    # Альфа — число
    assert np.isfinite(alpha).all()


def test_covariance_matrix_sample(sample_returns):
    cov = covariance_matrix(sample_returns, method="sample")
    assert cov.shape == (3, 3)


def test_covariance_matrix_ledoit_wolf(sample_returns):
    cov = covariance_matrix(sample_returns, method="ledoit_wolf")
    assert cov.shape == (3, 3)


def test_covariance_matrix_ewma(sample_returns):
    cov = covariance_matrix(sample_returns, method="ewma", ewma_span=30)
    assert cov.shape == (3, 3)
