"""ML-модели для прогнозирования доходности акций.

Реализует:
- Обучение с train/test split (Ridge, Lasso, RF, GBR)
- Walk-forward прогнозирование с переобучением
- FLAML AutoML (автоматический подбор алгоритма)
- Инкрементальное дообучение (partial_fit): SGD, Passive-Aggressive

Фичи: lagged returns, rolling statistics, volume, momentum.
Цель: прогноз направления/величины доходности на следующий день.
"""

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Lasso, Ridge, SGDRegressor
from sklearn.metrics import (
    accuracy_score,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)


@dataclass
class MLResult:
    """Результат ML-модели."""

    model_name: str
    predictions: pd.Series
    actuals: pd.Series
    rmse: float
    mae: float
    r2: float
    direction_accuracy: float
    feature_importance: dict[str, float] = field(default_factory=dict)
    train_size: int = 0
    test_size: int = 0


def build_features(
    returns: pd.DataFrame,
    volume: pd.DataFrame | None = None,
    lags: list[int] | None = None,
    windows: list[int] | None = None,
) -> pd.DataFrame:
    """Построение фичей для ML-модели.

    Создаёт:
    - Lagged returns (1, 2, 3, 5, 10, 21 дней)
    - Rolling mean / std (5, 10, 21, 63 дней)
    - Momentum (5/21, 10/63)
    - Кросс-секционные фичи (mean, rank)

    Args:
        returns: DataFrame с дневными доходностями (столбцы = тикеры).
        volume: DataFrame с объёмами (опционально).
        lags: Список лагов для滞后 доходностей.
        windows: Список окон для скользящих статистик.

    Returns:
        DataFrame с фичами (только числовые столбцы).
    """
    if lags is None:
        lags = [1, 2, 3, 5, 10, 21]
    if windows is None:
        windows = [5, 10, 21, 63]

    features = pd.DataFrame(index=returns.index)

    for lag in lags:
        features[f"return_lag_{lag}"] = returns.mean(axis=1).shift(lag)

    for w in windows:
        mean_ret = returns.mean(axis=1)
        features[f"rolling_mean_{w}"] = mean_ret.rolling(w).mean()
        features[f"rolling_std_{w}"] = mean_ret.rolling(w).std()
        features[f"rolling_skew_{w}"] = mean_ret.rolling(w).skew()

    if 5 in windows and 21 in windows:
        mean_ret = returns.mean(axis=1)
        features["momentum_5_21"] = mean_ret.rolling(5).mean() / mean_ret.rolling(21).mean().replace(0, np.nan)
    if 10 in windows and 63 in windows:
        mean_ret = returns.mean(axis=1)
        features["momentum_10_63"] = mean_ret.rolling(10).mean() / mean_ret.rolling(63).mean().replace(0, np.nan)

    features["cross_mean"] = returns.mean(axis=1)
    features["cross_std"] = returns.std(axis=1)
    features["cross_min"] = returns.min(axis=1)
    features["cross_max"] = returns.max(axis=1)
    features["cross_median"] = returns.median(axis=1)
    features["n_positive"] = (returns > 0).sum(axis=1) / returns.shape[1]

    if volume is not None and not volume.empty:
        vol_mean = volume.mean(axis=1)
        features["volume_lag_1"] = vol_mean.shift(1)
        features["volume_ratio_5_21"] = vol_mean.rolling(5).mean() / vol_mean.rolling(21).mean().replace(0, np.nan)

    return features


def train_ml_model(
    returns: pd.DataFrame,
    volume: pd.DataFrame | None = None,
    model_name: str = "ridge",
    train_ratio: float = 0.7,
    lags: list[int] | None = None,
    windows: list[int] | None = None,
) -> MLResult:
    """Обучение ML-модели с train/test split.

    Args:
        returns: DataFrame с дневными доходностями.
        volume: DataFrame с объёмами (опционально).
        model_name: 'ridge', 'lasso', 'rf', 'gbr'.
        train_ratio: Доля данных для обучения.
        lags: Lag параметры для build_features.
        windows: Window параметры для build_features.

    Returns:
        MLResult с предсказаниями и метриками.
    """
    features = build_features(returns, volume, lags=lags, windows=windows)
    target = returns.mean(axis=1).shift(-1)

    valid_mask = features.notna().all(axis=1) & target.notna()
    features = features[valid_mask]
    target = target[valid_mask]

    if len(features) < 100:
        raise ValueError(f"Insufficient data: {len(features)} samples (need >= 100)")

    split_idx = int(len(features) * train_ratio)
    X_train, X_test = features.iloc[:split_idx], features.iloc[split_idx:]
    y_train, y_test = target.iloc[:split_idx], target.iloc[split_idx:]

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    models = {
        "ridge": Ridge(alpha=1.0),
        "lasso": Lasso(alpha=0.001),
        "rf": RandomForestRegressor(n_estimators=100, max_depth=5, random_state=42, n_jobs=-1),
        "gbr": GradientBoostingRegressor(n_estimators=100, max_depth=3, learning_rate=0.1, random_state=42),
    }

    if model_name not in models:
        raise ValueError(f"Unknown model: {model_name}. Use one of: {list(models.keys())}")

    model = models[model_name]
    model.fit(X_train_s, y_train)

    predictions = pd.Series(model.predict(X_test_s), index=X_test.index, name="predicted")
    actuals = y_test.rename("actual")

    rmse = float(np.sqrt(mean_squared_error(actuals, predictions)))
    mae = float(mean_absolute_error(actuals, predictions))
    r2 = float(r2_score(actuals, predictions))

    actual_dir = np.sign(actuals.values)
    pred_dir = np.sign(predictions.values)
    direction_accuracy = float(accuracy_score(actual_dir, pred_dir))

    feat_imp = {}
    if hasattr(model, "feature_importances_"):
        feat_imp = dict(zip(features.columns, model.feature_importances_))
    elif hasattr(model, "coef_"):
        feat_imp = dict(zip(features.columns, np.abs(model.coef_)))
        total = sum(feat_imp.values())
        if total > 0:
            feat_imp = {k: v / total for k, v in feat_imp.items()}

    logger.info(
        "ML model '%s': RMSE=%.6f, MAE=%.6f, R²=%.4f, Direction=%.1f%%",
        model_name, rmse, mae, r2, direction_accuracy * 100,
    )

    return MLResult(
        model_name=model_name,
        predictions=predictions,
        actuals=actuals,
        rmse=rmse,
        mae=mae,
        r2=r2,
        direction_accuracy=direction_accuracy,
        feature_importance=dict(sorted(feat_imp.items(), key=lambda x: x[1], reverse=True)[:15]),
        train_size=len(X_train),
        test_size=len(X_test),
    )


def walk_forward_predict(
    returns: pd.DataFrame,
    volume: pd.DataFrame | None = None,
    model_name: str = "ridge",
    train_window: int = 252,
    retrain_freq: int = 21,
    lags: list[int] | None = None,
    windows: list[int] | None = None,
) -> MLResult:
    """Walk-forward прогнозирование: переобучение модели каждые retrain_freq дней.

    Args:
        returns: DataFrame с дневными доходностями.
        volume: DataFrame с объёмами (опционально).
        model_name: Название модели.
        train_window: Размер обучающего окна (дней).
        retrain_freq: Частота переобучения (дней).
        lags: Lag параметры.
        windows: Window параметры.

    Returns:
        MLResult с walk-forward предсказаниями.
    """
    features = build_features(returns, volume, lags=lags, windows=windows)
    target = returns.mean(axis=1).shift(-1)

    valid_mask = features.notna().all(axis=1) & target.notna()
    features = features[valid_mask]
    target = target[valid_mask]

    if len(features) < train_window + 21:
        raise ValueError(
            f"Insufficient data for walk-forward: {len(features)} samples, "
            f"need {train_window + 21}"
        )

    models_dict = {
        "ridge": Ridge(alpha=1.0),
        "lasso": Lasso(alpha=0.001),
        "rf": RandomForestRegressor(n_estimators=100, max_depth=5, random_state=42, n_jobs=-1),
        "gbr": GradientBoostingRegressor(n_estimators=100, max_depth=3, learning_rate=0.1, random_state=42),
    }

    predictions_list = []
    actuals_list = []
    scaler = StandardScaler()

    start_idx = train_window
    step = 0

    while start_idx < len(features):
        train_end = start_idx
        test_end = min(start_idx + retrain_freq, len(features))

        X_train = features.iloc[:train_end]
        y_train = target.iloc[:train_end]
        X_test = features.iloc[train_end:test_end]
        y_test = target.iloc[train_end:test_end]

        if X_test.empty:
            break

        X_train_s = scaler.fit_transform(X_train)
        X_test_s = scaler.transform(X_test)

        model = models_dict[model_name]
        model.fit(X_train_s, y_train)

        preds = model.predict(X_test_s)
        predictions_list.extend(preds)
        actuals_list.extend(y_test.values)

        start_idx = test_end
        step += 1

    predictions = pd.Series(predictions_list, index=features.index[train_window:train_window + len(predictions_list)])
    actuals = pd.Series(actuals_list, index=features.index[train_window:train_window + len(actuals_list)])

    rmse = float(np.sqrt(mean_squared_error(actuals, predictions)))
    mae = float(mean_absolute_error(actuals, predictions))
    r2 = float(r2_score(actuals, predictions))

    actual_dir = np.sign(actuals.values)
    pred_dir = np.sign(predictions.values)
    direction_accuracy = float(accuracy_score(actual_dir, pred_dir))

    final_model = models_dict[model_name]
    X_all_s = scaler.fit_transform(features.iloc[:len(features) - retrain_freq])
    final_model.fit(X_all_s, target.iloc[:len(features) - retrain_freq])

    feat_imp = {}
    if hasattr(final_model, "feature_importances_"):
        feat_imp = dict(zip(features.columns, final_model.feature_importances_))
    elif hasattr(final_model, "coef_"):
        feat_imp = dict(zip(features.columns, np.abs(final_model.coef_)))
        total = sum(feat_imp.values())
        if total > 0:
            feat_imp = {k: v / total for k, v in feat_imp.items()}

    logger.info(
        "Walk-forward '%s': %d retrainings, RMSE=%.6f, R²=%.4f, Direction=%.1f%%",
        model_name, step, rmse, r2, direction_accuracy * 100,
    )

    return MLResult(
        model_name=f"walk_forward_{model_name}",
        predictions=predictions,
        actuals=actuals,
        rmse=rmse,
        mae=mae,
        r2=r2,
        direction_accuracy=direction_accuracy,
        feature_importance=dict(sorted(feat_imp.items(), key=lambda x: x[1], reverse=True)[:15]),
        train_size=train_window,
        test_size=len(predictions_list),
    )


def compare_ml_models(
    returns: pd.DataFrame,
    volume: pd.DataFrame | None = None,
    model_names: list[str] | None = None,
    method: str = "split",
    **kwargs,
) -> pd.DataFrame:
    """Сравнение нескольких ML-моделей.

    Args:
        returns: DataFrame с доходностями.
        volume: DataFrame с объёмами.
        model_names: Список моделей для сравнения.
        method: 'split' (train/test) или 'walk_forward'.
        **kwargs: Дополнительные параметры для train_ml_model / walk_forward_predict.

    Returns:
        DataFrame со сравнением моделей.
    """
    if model_names is None:
        model_names = ["ridge", "lasso", "rf", "gbr"]

    results = []
    for name in model_names:
        try:
            if name == "automl":
                result = automl_train(returns, volume, **kwargs)
            elif name in INCREMENTAL_MODELS:
                inc = incremental_train(returns, volume, model_name=name, **kwargs)
                result = MLResult(
                    model_name=inc.model_name, predictions=inc.predictions,
                    actuals=inc.actuals, rmse=inc.rmse, mae=inc.mae, r2=inc.r2,
                    direction_accuracy=inc.direction_accuracy,
                    feature_importance=inc.feature_importance,
                    train_size=inc.train_size, test_size=inc.test_size,
                )
            elif method == "walk_forward":
                result = walk_forward_predict(returns, volume, model_name=name, **kwargs)
            else:
                result = train_ml_model(returns, volume, model_name=name, **kwargs)
            results.append({
                "Model": result.model_name.replace("walk_forward_", ""),
                "RMSE": result.rmse,
                "MAE": result.mae,
                "R²": result.r2,
                "Direction Accuracy": result.direction_accuracy,
                "Train Size": result.train_size,
                "Test Size": result.test_size,
            })
        except Exception as exc:
            logger.warning("Model '%s' failed: %s", name, exc)
            results.append({
                "Model": name,
                "RMSE": np.nan,
                "MAE": np.nan,
                "R²": np.nan,
                "Direction Accuracy": np.nan,
                "Train Size": 0,
                "Test Size": 0,
            })

    return pd.DataFrame(results)


def automl_train(
    returns: pd.DataFrame,
    volume: pd.DataFrame | None = None,
    time_budget: int = 60,
    max_iter: int | None = None,
    train_ratio: float = 0.7,
    lags: list[int] | None = None,
    windows: list[int] | None = None,
) -> MLResult:
    """Обучение через FLAML AutoML с автоматическим подбором алгоритма и гиперпараметров.

    FLAML перебирает: Ridge, Lasso, LightGBM, XGBoost, RandomForest, ExtraTrees
    и подбирает лучший по RMSE на кросс-валидации.

    Args:
        returns: DataFrame с дневными доходностями.
        volume: DataFrame с объёмами (опционально).
        time_budget: Максимальное время подбора (секунды).
        max_iter: Максимальное число итераций (None = без ограничений).
        train_ratio: Доля данных для обучения.
        lags: Lag параметры для build_features.
        windows: Window параметры для build_features.

    Returns:
        MLResult с предсказаниями лучшей найденной модели.
    """
    from flaml import AutoML

    features = build_features(returns, volume, lags=lags, windows=windows)
    target = returns.mean(axis=1).shift(-1)

    valid_mask = features.notna().all(axis=1) & target.notna()
    features = features[valid_mask]
    target = target[valid_mask]

    if len(features) < 100:
        raise ValueError(f"Insufficient data: {len(features)} samples (need >= 100)")

    split_idx = int(len(features) * train_ratio)
    X_train, X_test = features.iloc[:split_idx], features.iloc[split_idx:]
    y_train, y_test = target.iloc[:split_idx], target.iloc[split_idx:]

    automl = AutoML()
    automl_settings = {
        "time_budget": time_budget,
        "metric": "rmse",
        "task": "regression",
        "log_file_name": None,
        "seed": 42,
        "estimator_list": ["xgboost", "extra_tree", "sgd"],
    }
    if max_iter is not None:
        automl_settings["max_iter"] = max_iter

    automl.fit(X_train, y_train, **automl_settings)

    predictions = pd.Series(automl.predict(X_test), index=X_test.index, name="predicted")
    actuals = y_test.rename("actual")

    rmse = float(np.sqrt(mean_squared_error(actuals, predictions)))
    mae = float(mean_absolute_error(actuals, predictions))
    r2 = float(r2_score(actuals, predictions))

    actual_dir = np.sign(actuals.values)
    pred_dir = np.sign(predictions.values)
    direction_accuracy = float(accuracy_score(actual_dir, pred_dir))

    feat_imp = {}
    best_model = automl.model
    if hasattr(best_model, "feature_importances_"):
        feat_imp = dict(zip(features.columns, best_model.feature_importances_))
        total = sum(feat_imp.values())
        if total > 0:
            feat_imp = {k: v / total for k, v in feat_imp.items()}
    elif hasattr(best_model, "coef_"):
        feat_imp = dict(zip(features.columns, np.abs(best_model.coef_)))
        total = sum(feat_imp.values())
        if total > 0:
            feat_imp = {k: v / total for k, v in feat_imp.items()}

    logger.info(
        "AutoML: best estimator=%s, RMSE=%.6f, MAE=%.6f, R²=%.4f, Direction=%.1f%%",
        automl.best_estimator, rmse, mae, r2, direction_accuracy * 100,
    )

    return MLResult(
        model_name=f"automl_{automl.best_estimator}",
        predictions=predictions,
        actuals=actuals,
        rmse=rmse,
        mae=mae,
        r2=r2,
        direction_accuracy=direction_accuracy,
        feature_importance=dict(sorted(feat_imp.items(), key=lambda x: x[1], reverse=True)[:15]),
        train_size=len(X_train),
        test_size=len(X_test),
    )


def automl_walk_forward(
    returns: pd.DataFrame,
    volume: pd.DataFrame | None = None,
    time_budget: int = 30,
    train_window: int = 252,
    retrain_freq: int = 21,
    lags: list[int] | None = None,
    windows: list[int] | None = None,
) -> MLResult:
    """Walk-forward прогнозирование с FLAML AutoML.

    Переобучает AutoML каждые retrain_freq дней с скользящим окном.

    Args:
        returns: DataFrame с дневными доходностями.
        volume: DataFrame с объёмами (опционально).
        time_budget: Время подбора на каждом шаге (секунды).
        train_window: Размер обучающего окна (дней).
        retrain_freq: Частота переобучения (дней).
        lags: Lag параметры.
        windows: Window параметры.

    Returns:
        MLResult с walk-forward предсказаниями.
    """
    from flaml import AutoML

    features = build_features(returns, volume, lags=lags, windows=windows)
    target = returns.mean(axis=1).shift(-1)

    valid_mask = features.notna().all(axis=1) & target.notna()
    features = features[valid_mask]
    target = target[valid_mask]

    if len(features) < train_window + 21:
        raise ValueError(
            f"Insufficient data for walk-forward: {len(features)} samples, "
            f"need {train_window + 21}"
        )

    predictions_list = []
    actuals_list = []

    start_idx = train_window
    step = 0

    while start_idx < len(features):
        train_end = start_idx
        test_end = min(start_idx + retrain_freq, len(features))

        X_train = features.iloc[:train_end]
        y_train = target.iloc[:train_end]
        X_test = features.iloc[train_end:test_end]
        y_test = target.iloc[train_end:test_end]

        if X_test.empty:
            break

        automl = AutoML()
        automl_settings = {
            "time_budget": time_budget,
            "metric": "rmse",
            "task": "regression",
            "log_file_name": None,
            "seed": 42,
            "estimator_list": ["xgboost", "extra_tree", "sgd"],
        }
        automl.fit(X_train, y_train, **automl_settings)

        preds = automl.predict(X_test)
        predictions_list.extend(preds)
        actuals_list.extend(y_test.values)

        start_idx = test_end
        step += 1

    predictions = pd.Series(
        predictions_list,
        index=features.index[train_window:train_window + len(predictions_list)],
    )
    actuals = pd.Series(
        actuals_list,
        index=features.index[train_window:train_window + len(actuals_list)],
    )

    rmse = float(np.sqrt(mean_squared_error(actuals, predictions)))
    mae = float(mean_absolute_error(actuals, predictions))
    r2 = float(r2_score(actuals, predictions))

    actual_dir = np.sign(actuals.values)
    pred_dir = np.sign(predictions.values)
    direction_accuracy = float(accuracy_score(actual_dir, pred_dir))

    logger.info(
        "AutoML walk-forward: %d retrainings, RMSE=%.6f, R²=%.4f, Direction=%.1f%%",
        step, rmse, r2, direction_accuracy * 100,
    )

    return MLResult(
        model_name="walk_forward_automl",
        predictions=predictions,
        actuals=actuals,
        rmse=rmse,
        mae=mae,
        r2=r2,
        direction_accuracy=direction_accuracy,
        feature_importance={},
        train_size=train_window,
        test_size=len(predictions_list),
    )


def compare_with_automl(
    returns: pd.DataFrame,
    volume: pd.DataFrame | None = None,
    time_budget: int = 60,
    train_ratio: float = 0.7,
    **kwargs,
) -> pd.DataFrame:
    """Сравнение ручных моделей с AutoML.

    Запускает все ручные модели (ridge, lasso, rf, gbr) + AutoML
    и возвращает общую таблицу сравнения.

    Args:
        returns: DataFrame с доходностями.
        volume: DataFrame с объёмами.
        time_budget: Время подбора AutoML (секунды).
        train_ratio: Доля данных для обучения.
        **kwargs: Дополнительные параметры для train_ml_model.

    Returns:
        DataFrame со сравнением моделей (включая AutoML).
    """
    manual_results = compare_ml_models(
        returns, volume,
        model_names=["ridge", "lasso", "rf", "gbr"],
        method="split",
        train_ratio=train_ratio,
        **kwargs,
    )

    try:
        automl_result = automl_train(
            returns, volume,
            time_budget=time_budget,
            train_ratio=train_ratio,
        )
        automl_row = pd.DataFrame([{
            "Model": f"AutoML ({automl_result.model_name.replace('automl_', '')})",
            "RMSE": automl_result.rmse,
            "MAE": automl_result.mae,
            "R²": automl_result.r2,
            "Direction Accuracy": automl_result.direction_accuracy,
            "Train Size": automl_result.train_size,
            "Test Size": automl_result.test_size,
        }])
        return pd.concat([manual_results, automl_row], ignore_index=True)
    except Exception as e:
        logger.warning("AutoML failed: %s", e)
        return manual_results


# ---------------------------------------------------------------------------
# Инкрементальное дообучение (partial_fit)
# ---------------------------------------------------------------------------

INCREMENTAL_MODELS = {
    "sgd": lambda: SGDRegressor(
        loss="squared_error", penalty="l2", alpha=0.001,
        max_iter=2000, tol=1e-4, random_state=42,
    ),
    "pa": lambda: SGDRegressor(
        loss="epsilon_insensitive", penalty=None, learning_rate="pa1",
        eta0=1.0, max_iter=2000, tol=1e-4, random_state=42,
    ),
}


@dataclass
class IncrementalResult:
    """Результат инкрементального обучения."""

    model_name: str
    predictions: pd.Series
    actuals: pd.Series
    rmse: float
    mae: float
    r2: float
    direction_accuracy: float
    n_updates: int
    feature_importance: dict[str, float] = field(default_factory=dict)
    train_size: int = 0
    test_size: int = 0


def incremental_train(
    returns: pd.DataFrame,
    volume: pd.DataFrame | None = None,
    model_name: str = "sgd",
    initial_window: int = 252,
    update_freq: int = 1,
    lags: list[int] | None = None,
    windows: list[int] | None = None,
) -> IncrementalResult:
    """Инкрементальное обучение через partial_fit.

    Модели обучаются порциями: начальное обучение на initial_window,
    затем обновление по update_freq дней. Scaler тоже обновляется
    через partial_fit — нет переобучения на исторических данных.

    Args:
        returns: DataFrame с дневными доходностями.
        volume: DataFrame с объёмами (опционально).
        model_name: 'sgd' (SGDRegressor) или 'pa' (PassiveAggressiveRegressor).
        initial_window: Начальное окно обучения (дней).
        update_freq: Частота обновления модели (дней).
        lags: Lag параметры для build_features.
        windows: Window параметры для build_features.

    Returns:
        IncrementalResult с предсказаниями и метриками.
    """
    if model_name not in INCREMENTAL_MODELS:
        raise ValueError(
            f"Unknown incremental model: {model_name}. "
            f"Use one of: {list(INCREMENTAL_MODELS.keys())}"
        )

    features = build_features(returns, volume, lags=lags, windows=windows)
    target = returns.mean(axis=1).shift(-1)

    valid_mask = features.notna().all(axis=1) & target.notna()
    features = features[valid_mask]
    target = target[valid_mask]

    if len(features) < initial_window + 21:
        raise ValueError(
            f"Insufficient data for incremental learning: {len(features)} samples, "
            f"need {initial_window + 21}"
        )

    model = INCREMENTAL_MODELS[model_name]()
    scaler = StandardScaler()

    X_init = features.iloc[:initial_window]
    y_init = target.iloc[:initial_window]
    X_init_s = scaler.fit_transform(X_init)
    model.partial_fit(X_init_s, y_init)

    predictions_list = []
    actuals_list = []

    i = initial_window
    n_updates = 1

    while i < len(features):
        chunk_end = min(i + update_freq, len(features))
        X_chunk = features.iloc[i:chunk_end]
        y_chunk = target.iloc[i:chunk_end]

        X_chunk_s = scaler.transform(X_chunk)
        preds = model.predict(X_chunk_s)

        predictions_list.extend(preds)
        actuals_list.extend(y_chunk.values)

        model.partial_fit(X_chunk_s, y_chunk)
        n_updates += 1

        i = chunk_end

    idx = features.index[initial_window:initial_window + len(predictions_list)]
    predictions = pd.Series(predictions_list, index=idx, name="predicted")
    actuals = pd.Series(actuals_list, index=idx, name="actual")

    rmse = float(np.sqrt(mean_squared_error(actuals, predictions)))
    mae = float(mean_absolute_error(actuals, predictions))
    r2 = float(r2_score(actuals, predictions))

    actual_dir = np.sign(actuals.values)
    pred_dir = np.sign(predictions.values)
    direction_accuracy = float(accuracy_score(actual_dir, pred_dir))

    feat_imp = {}
    if hasattr(model, "coef_"):
        feat_imp = dict(zip(features.columns, np.abs(model.coef_)))
        total = sum(feat_imp.values())
        if total > 0:
            feat_imp = {k: v / total for k, v in feat_imp.items()}

    logger.info(
        "Incremental '%s': %d updates, RMSE=%.6f, R²=%.4f, Direction=%.1f%%",
        model_name, n_updates, rmse, r2, direction_accuracy * 100,
    )

    return IncrementalResult(
        model_name=f"incremental_{model_name}",
        predictions=predictions,
        actuals=actuals,
        rmse=rmse,
        mae=mae,
        r2=r2,
        direction_accuracy=direction_accuracy,
        n_updates=n_updates,
        feature_importance=dict(sorted(feat_imp.items(), key=lambda x: x[1], reverse=True)[:15]),
        train_size=initial_window,
        test_size=len(predictions_list),
    )


def incremental_vs_full_retrain(
    returns: pd.DataFrame,
    volume: pd.DataFrame | None = None,
    model_name: str = "sgd",
    initial_window: int = 252,
    retrain_freq: int = 21,
    lags: list[int] | None = None,
    windows: list[int] | None = None,
) -> pd.DataFrame:
    """Сравнение инкрементального обучения и полного переобучения.

    Для каждой модели строит два варианта:
    - incremental: partial_fit на новых данных (быстрое обновление)
    - full_retrain: полное переобучение на всём окне (каждые retrain_freq)

    Args:
        returns: DataFrame с доходностями.
        volume: DataFrame с объёмами.
        model_name: 'sgd' или 'pa'.
        initial_window: Начальное окно.
        retrain_freq: Частота переобучения для полного варианта.
        lags: Lag параметры.
        windows: Window параметры.

    Returns:
        DataFrame с сравнением двух подходов.
    """
    results = []

    try:
        inc = incremental_train(
            returns, volume, model_name=model_name,
            initial_window=initial_window, update_freq=1,
            lags=lags, windows=windows,
        )
        results.append({
            "Model": f"Incremental {model_name}",
            "RMSE": inc.rmse,
            "MAE": inc.mae,
            "R²": inc.r2,
            "Direction Accuracy": inc.direction_accuracy,
            "Train Size": inc.train_size,
            "Test Size": inc.test_size,
            "Updates": inc.n_updates,
        })
    except Exception as exc:
        logger.warning("Incremental model '%s' failed: %s", model_name, exc)

    sgd_models = {
        "sgd": lambda: SGDRegressor(
            loss="squared_error", penalty="l2", alpha=0.001,
            max_iter=2000, tol=1e-4, random_state=42,
        ),
    }
    if model_name in sgd_models:
        try:
            full = walk_forward_predict(
                returns, volume, model_name="ridge",
                train_window=initial_window, retrain_freq=retrain_freq,
                lags=lags, windows=windows,
            )
            results.append({
                "Model": f"Full retrain ({model_name})",
                "RMSE": full.rmse,
                "MAE": full.mae,
                "R²": full.r2,
                "Direction Accuracy": full.direction_accuracy,
                "Train Size": full.train_size,
                "Test Size": full.test_size,
                "Updates": 0,
            })
        except Exception as exc:
            logger.warning("Full retrain for '%s' failed: %s", model_name, exc)

    if not results:
        return pd.DataFrame()

    return pd.DataFrame(results)


def get_incremental_model(model_name: str):
    """Получить инкрементальную модель и scaler по имени.

    Удобно для последовательного обновления в продакшене.

    Args:
        model_name: 'sgd' или 'pa'.

    Returns:
        Кортеж (model, scaler).
    """
    if model_name not in INCREMENTAL_MODELS:
        raise ValueError(
            f"Unknown incremental model: {model_name}. "
            f"Use one of: {list(INCREMENTAL_MODELS.keys())}"
        )
    return INCREMENTAL_MODELS[model_name](), StandardScaler()
