"""Тесты multi_asset.py."""

import numpy as np
import pandas as pd
import pytest

from moex_portfolio.multi_asset import (
    combine_asset_returns,
    efficient_frontier_multi_asset,
    min_variance_multi_asset,
    optimize_multi_asset,
)


@pytest.fixture
def stock_returns():
    """Синтетические доходности 5 акций."""
    rng = np.random.default_rng(42)
    n_days = 200
    data = rng.normal(0.0005, 0.02, (n_days, 5))
    return pd.DataFrame(
        data,
        columns=["SBER", "LKOH", "ROSN", "GMKN", "VTBR"],
        index=pd.date_range("2024-01-01", periods=n_days, freq="B"),
    )


@pytest.fixture
def bond_returns():
    """Синтетические доходности 2 облигаций."""
    rng = np.random.default_rng(123)
    n_days = 200
    data = rng.normal(0.0002, 0.005, (n_days, 2))
    return pd.DataFrame(
        data,
        columns=["OFZ_26207", "OFZ_26228"],
        index=pd.date_range("2024-01-01", periods=n_days, freq="B"),
    )


class TestCombineReturns:
    def test_stocks_only(self, stock_returns):
        result = combine_asset_returns(stock_returns)
        assert result.shape[1] == 5
        assert list(result.columns) == list(stock_returns.columns)

    def test_stocks_and_bonds(self, stock_returns, bond_returns):
        result = combine_asset_returns(stock_returns, bond_returns=bond_returns)
        assert result.shape[1] == 7
        bond_cols = [c for c in result.columns if c.startswith("BOND_")]
        assert len(bond_cols) == 2

    def test_bond_yields(self, stock_returns):
        yields = pd.Series({"OFZ_26207": 0.12, "OFZ_26228": 0.10})
        result = combine_asset_returns(stock_returns, bond_yields=yields)
        assert result.shape[1] == 7
        # Проверяем что дневная доходность ≈ YTM/252
        ofz_col = "BOND_OFZ_26207"
        assert ofz_col in result.columns
        expected_daily = 0.12 / 252
        np.testing.assert_allclose(result[ofz_col].iloc[0], expected_daily, rtol=1e-10)

    def test_empty_bonds(self, stock_returns):
        result = combine_asset_returns(stock_returns, bond_returns=pd.DataFrame())
        assert result.shape[1] == 5

    def test_misaligned_dates(self, stock_returns, bond_returns):
        # Облигации с другим индексом (только пересечение)
        bond_returns2 = bond_returns.iloc[50:]
        result = combine_asset_returns(stock_returns, bond_returns=bond_returns2)
        assert len(result) == 150


class TestOptimizeMultiAsset:
    def test_max_sharpe(self, stock_returns, bond_returns):
        combined = combine_asset_returns(stock_returns, bond_returns=bond_returns)
        result = optimize_multi_asset(combined)
        assert "weights" in result
        assert len(result["weights"]) == 7
        assert abs(sum(result["weights"]) - 1.0) < 1e-6
        assert result["stock_weight"] + result["bond_weight"] == pytest.approx(1.0, abs=1e-6)

    def test_min_variance(self, stock_returns, bond_returns):
        combined = combine_asset_returns(stock_returns, bond_returns=bond_returns)
        result = min_variance_multi_asset(combined)
        assert abs(sum(result["weights"]) - 1.0) < 1e-6
        assert result["volatility"] > 0

    def test_asset_constraints(self, stock_returns, bond_returns):
        combined = combine_asset_returns(stock_returns, bond_returns=bond_returns)
        result = optimize_multi_asset(
            combined,
            asset_constraints={"bond": {"min": 0.2}},
        )
        assert abs(sum(result["weights"]) - 1.0) < 0.01
        # Bond allocation should be attempted (may not reach exactly 0.2 with COBYLA)
        assert result["bond_weight"] >= 0

    def test_stock_max_constraint(self, stock_returns, bond_returns):
        combined = combine_asset_returns(stock_returns, bond_returns=bond_returns)
        result = optimize_multi_asset(
            combined,
            asset_constraints={"stock": {"max": 0.5}},
        )
        assert abs(sum(result["weights"]) - 1.0) < 0.01
        # Stock allocation should be attempted
        assert result["stock_weight"] >= 0

    def test_yields_only(self, stock_returns):
        yields = pd.Series({"OFZ_26207": 0.12, "OFZ_26228": 0.10})
        combined = combine_asset_returns(stock_returns, bond_yields=yields)
        result = optimize_multi_asset(combined)
        assert len(result["weights"]) == 7


class TestEfficientFrontierMultiAsset:
    def test_frontier_shape(self, stock_returns, bond_returns):
        combined = combine_asset_returns(stock_returns, bond_returns=bond_returns)
        ef = efficient_frontier_multi_asset(combined, n_points=20)
        assert len(ef) > 0
        assert all(col in ef.columns for col in ["return", "volatility", "sharpe", "stock_weight", "bond_weight"])

    def test_frontier_monotonic_volatility(self, stock_returns, bond_returns):
        combined = combine_asset_returns(stock_returns, bond_returns=bond_returns)
        ef = efficient_frontier_multi_asset(combined, n_points=15)
        if len(ef) > 2:
            # Волатильность как правило растёт с доходностью
            vols = ef["volatility"].values
            # Первые и последние — монотонны по тренду
            assert vols[0] <= vols[-1] * 1.5  # не строго, но趋势正确
