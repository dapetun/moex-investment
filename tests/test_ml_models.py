"""Tests for ml_models module."""

import numpy as np
import pandas as pd
import pytest

from moex_portfolio.ml_models import (
    MLResult,
    build_features,
    compare_ml_models,
    train_ml_model,
    walk_forward_predict,
)


@pytest.fixture
def sample_returns():
    np.random.seed(42)
    n = 400
    dates = pd.bdate_range("2023-01-01", periods=n)
    data = np.random.randn(n, 5) * 0.02
    tickers = ["A", "B", "C", "D", "E"]
    return pd.DataFrame(data, index=dates, columns=tickers)


@pytest.fixture
def sample_volume():
    np.random.seed(123)
    n = 400
    dates = pd.bdate_range("2023-01-01", periods=n)
    data = np.random.uniform(1e6, 1e8, (n, 5))
    tickers = ["A", "B", "C", "D", "E"]
    return pd.DataFrame(data, index=dates, columns=tickers)


def test_build_features(sample_returns):
    features = build_features(sample_returns)
    assert len(features) == len(sample_returns)
    assert features.shape[1] > 10
    assert not features.empty


def test_build_features_with_volume(sample_returns, sample_volume):
    features = build_features(sample_returns, volume=sample_volume)
    assert "volume_lag_1" in features.columns
    assert "volume_ratio_5_21" in features.columns


def test_build_features_custom_params(sample_returns):
    features = build_features(sample_returns, lags=[1, 5], windows=[10, 21])
    assert "return_lag_1" in features.columns
    assert "return_lag_5" in features.columns
    assert "rolling_mean_10" in features.columns


def test_train_ridge(sample_returns):
    result = train_ml_model(sample_returns, model_name="ridge")
    assert isinstance(result, MLResult)
    assert result.model_name == "ridge"
    assert len(result.predictions) > 0
    assert len(result.predictions) == len(result.actuals)
    assert result.rmse >= 0
    assert result.mae >= 0
    assert 0 <= result.direction_accuracy <= 1.0
    assert result.train_size > 0
    assert result.test_size > 0


def test_train_lasso(sample_returns):
    result = train_ml_model(sample_returns, model_name="lasso")
    assert result.model_name == "lasso"
    assert result.rmse >= 0


def test_train_rf(sample_returns):
    result = train_ml_model(sample_returns, model_name="rf")
    assert result.model_name == "rf"
    assert len(result.feature_importance) > 0


def test_train_gbr(sample_returns):
    result = train_ml_model(sample_returns, model_name="gbr")
    assert result.model_name == "gbr"
    assert len(result.feature_importance) > 0


def test_invalid_model(sample_returns):
    with pytest.raises(ValueError, match="Unknown model"):
        train_ml_model(sample_returns, model_name="invalid")


def test_insufficient_data():
    tiny = pd.DataFrame(np.random.randn(50, 3), columns=["A", "B", "C"])
    with pytest.raises(ValueError, match="Insufficient data"):
        train_ml_model(tiny, model_name="ridge")


def test_walk_forward(sample_returns):
    result = walk_forward_predict(
        sample_returns, model_name="ridge",
        train_window=200, retrain_freq=21,
    )
    assert "walk_forward" in result.model_name
    assert len(result.predictions) > 0
    assert result.rmse >= 0


def test_walk_forward_insufficient_data():
    tiny = pd.DataFrame(np.random.randn(100, 3), columns=["A", "B", "C"])
    with pytest.raises(ValueError, match="Insufficient data"):
        walk_forward_predict(tiny, train_window=200, retrain_freq=21)


def test_compare_models(sample_returns):
    df = compare_ml_models(sample_returns, model_names=["ridge", "lasso"], method="split")
    assert len(df) == 2
    assert "Model" in df.columns
    assert "RMSE" in df.columns
    assert "Direction Accuracy" in df.columns


def test_compare_models_walk_forward(sample_returns):
    df = compare_ml_models(
        sample_returns, model_names=["ridge"],
        method="walk_forward", train_window=200, retrain_freq=21,
    )
    assert len(df) == 1
    assert df.iloc[0]["Model"] == "ridge"


# --- AutoML (FLAML) tests ---


def test_automl_train(sample_returns):
    from moex_portfolio.ml_models import automl_train

    result = automl_train(sample_returns, time_budget=10)
    assert isinstance(result, MLResult)
    assert "automl_" in result.model_name
    assert len(result.predictions) > 0
    assert len(result.predictions) == len(result.actuals)
    assert result.rmse >= 0
    assert result.mae >= 0
    assert 0 <= result.direction_accuracy <= 1.0
    assert result.train_size > 0
    assert result.test_size > 0


def test_automl_train_with_volume(sample_returns, sample_volume):
    from moex_portfolio.ml_models import automl_train

    result = automl_train(sample_returns, volume=sample_volume, time_budget=10)
    assert "automl_" in result.model_name
    assert result.rmse >= 0


def test_automl_train_insufficient_data():
    from moex_portfolio.ml_models import automl_train

    tiny = pd.DataFrame(np.random.randn(50, 3), columns=["A", "B", "C"])
    with pytest.raises(ValueError, match="Insufficient data"):
        automl_train(tiny, time_budget=5)


def test_automl_walk_forward(sample_returns):
    from moex_portfolio.ml_models import automl_walk_forward

    result = automl_walk_forward(
        sample_returns, time_budget=5,
        train_window=200, retrain_freq=21,
    )
    assert result.model_name == "walk_forward_automl"
    assert len(result.predictions) > 0
    assert result.rmse >= 0


def test_compare_with_automl(sample_returns):
    from moex_portfolio.ml_models import compare_with_automl

    df = compare_with_automl(sample_returns, time_budget=10)
    assert len(df) >= 4
    assert "Model" in df.columns
    automl_rows = df[df["Model"].str.contains("AutoML")]
    assert len(automl_rows) == 1
    assert automl_rows.iloc[0]["RMSE"] >= 0


def test_compare_models_with_automl_key(sample_returns):
    df = compare_ml_models(
        sample_returns, model_names=["ridge", "automl"],
        time_budget=10,
    )
    assert len(df) == 2
    model_names = df["Model"].tolist()
    assert any("automl" in m for m in model_names)


# --- Incremental learning tests ---


def test_incremental_sgd(sample_returns):
    from moex_portfolio.ml_models import IncrementalResult, incremental_train

    result = incremental_train(
        sample_returns, model_name="sgd",
        initial_window=200, update_freq=5,
    )
    assert isinstance(result, IncrementalResult)
    assert result.model_name == "incremental_sgd"
    assert len(result.predictions) > 0
    assert len(result.predictions) == len(result.actuals)
    assert result.rmse >= 0
    assert result.mae >= 0
    assert 0 <= result.direction_accuracy <= 1.0
    assert result.n_updates > 1
    assert result.train_size == 200
    assert result.test_size > 0


def test_incremental_pa(sample_returns):
    from moex_portfolio.ml_models import incremental_train

    result = incremental_train(
        sample_returns, model_name="pa",
        initial_window=200, update_freq=10,
    )
    assert result.model_name == "incremental_pa"
    assert result.rmse >= 0
    assert result.n_updates > 1


def test_incremental_invalid_model(sample_returns):
    from moex_portfolio.ml_models import incremental_train

    with pytest.raises(ValueError, match="Unknown incremental model"):
        incremental_train(sample_returns, model_name="invalid")


def test_incremental_insufficient_data():
    from moex_portfolio.ml_models import incremental_train

    tiny = pd.DataFrame(np.random.randn(50, 3), columns=["A", "B", "C"])
    with pytest.raises(ValueError, match="Insufficient data"):
        incremental_train(tiny, model_name="sgd", initial_window=200)


def test_incremental_vs_full(sample_returns):
    from moex_portfolio.ml_models import incremental_vs_full_retrain

    df = incremental_vs_full_retrain(
        sample_returns, model_name="sgd",
        initial_window=200, retrain_freq=21,
    )
    assert len(df) >= 1
    assert "Model" in df.columns
    assert "RMSE" in df.columns


def test_get_incremental_model():
    from moex_portfolio.ml_models import get_incremental_model

    model, scaler = get_incremental_model("sgd")
    assert hasattr(model, "partial_fit")
    assert hasattr(scaler, "partial_fit")

    model2, scaler2 = get_incremental_model("pa")
    assert hasattr(model2, "partial_fit")

    with pytest.raises(ValueError, match="Unknown incremental model"):
        get_incremental_model("invalid")
