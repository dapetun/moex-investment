"""Hierarchical Risk Parity (HRP) — Lopez de Prado, 2016."""

import logging

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage
from scipy.spatial.distance import squareform

logger = logging.getLogger(__name__)


def _correlation_distance(corr: pd.DataFrame) -> pd.DataFrame:
    """Преобразование корреляции в расстояние: d = sqrt(0.5 * (1 - ρ)).

    Args:
        corr: Матрица корреляций.

    Returns:
        Матрица расстояний.
    """
    return np.sqrt(0.5 * (1 - corr))


def _quasi_diag(link: np.ndarray) -> list[int]:
    """Рекурсивная квази-диагонализация: сортировка активов по кластеризации.

    Args:
        link: Результат scipy.cluster.hierarchy.linkage.

    Returns:
        Отсортированные индексы активов.
    """
    link = link.astype(int)
    sort_ix = pd.Series([link[-1, 0], link[-1, 1]])
    num_items = link[-1, 3]

    while sort_ix.max() >= num_items:
        sort_ix.index = range(0, sort_ix.shape[0] * 2, 2)
        df0 = sort_ix[sort_ix >= num_items]
        i = df0.index
        j = df0.values - num_items
        sort_ix[i] = link[j, 0]
        df1 = pd.Series(link[j, 1], index=i + 1)
        sort_ix = pd.concat([sort_ix, df1])
        sort_ix = sort_ix.sort_index()
        sort_ix.index = range(sort_ix.shape[0])

    return sort_ix.tolist()


def _get_cluster_var(
    cov: pd.DataFrame,
    cluster_indices: list[int],
) -> float:
    """Расчёт дисперсии кластера через inverse-variance weights.

    Args:
        cov: Ковариационная матрица.
        cluster_indices: Индексы активов в кластере.

    Returns:
        Дисперсия кластера.
    """
    cov_slice = cov.iloc[cluster_indices, cluster_indices]
    inv_diag = 1.0 / np.diag(cov_slice)
    inv_diag_sum = inv_diag.sum()
    if inv_diag_sum == 0:
        return 0.0
    w = inv_diag / inv_diag_sum
    return np.dot(w, np.dot(cov_slice, w))


def hierarchical_risk_parity(
    returns: pd.DataFrame,
    method: str = "single",
) -> pd.Series:
    """HRP: Hierarchical Risk Parity.

    Алгоритм (Lopez de Prado, 2016):
    1. Кластеризация активов по корреляционному расстоянию
    2. Квази-диагонализация (сортировка по кластерам)
    3. Рекурсивное бинарное деление портфеля
    4. Инверсно-дисперсионное распределение весов в кластерах

    Args:
        returns: DataFrame с доходностями (столбцы = активы).
        method: Метод кластеризации ('single', 'complete', 'average').

    Returns:
        Series с весами активов (сумма = 1).
    """
    tickers = returns.columns.tolist()
    n = len(tickers)
    cov = returns.cov()
    corr = returns.corr()

    # Шаг 1: Расстояние и кластеризация
    dist = _correlation_distance(corr)
    dist_condensed = squareform(dist.values, checks=False)
    link = linkage(dist_condensed, method=method)

    # Шаг 2: Квази-диагонализация
    sorted_ix = _quasi_diag(link)
    sorted_tickers = [tickers[i] for i in sorted_ix]

    # Шаг 3: Рекурсивное деление
    weights = pd.Series(1.0, index=sorted_tickers)

    clusters = [sorted_ix]

    while clusters:
        new_clusters = []
        for cluster in clusters:
            if len(cluster) <= 1:
                continue

            # Делим кластер пополам
            mid = len(cluster) // 2
            left = cluster[:mid]
            right = cluster[mid:]

            # Дисперсия каждого подкластера
            var_left = _get_cluster_var(cov, left)
            var_right = _get_cluster_var(cov, right)

            # Веса обратно пропорциональны дисперсии
            total = var_left + var_right
            if total > 0:
                alpha = 1 - var_left / total
            else:
                alpha = 0.5

            # Обновляем веса
            left_tickers = [tickers[i] for i in left]
            right_tickers = [tickers[i] for i in right]

            for t in left_tickers:
                weights[t] *= alpha
            for t in right_tickers:
                weights[t] *= (1 - alpha)

            if len(left) > 1:
                new_clusters.append(left)
            if len(right) > 1:
                new_clusters.append(right)

        clusters = new_clusters

    # Нормализация
    weights = weights / weights.sum()

    logger.info("HRP: %d assets, %d clusters", n, len(link))
    return weights


def optimize_hrp(
    returns: pd.DataFrame,
    min_weight: float = 0.0,
    max_weight: float = 0.3,
) -> dict:
    """Оптимизация портфеля через HRP с ограничениями на веса.

    Args:
        returns: DataFrame с доходностями.
        min_weight: Минимальный вес.
        max_weight: Максимальный вес.

    Returns:
        Словарь с: weights, return, volatility, sharpe.
    """
    from .metrics import portfolio_return, portfolio_volatility, sharpe_ratio

    weights = hierarchical_risk_parity(returns)
    tickers = weights.index.tolist()
    n = len(tickers)
    cov = returns.cov()
    mean_ret = returns.mean()

    # Iterative clip + renormalize to enforce bounds
    for _ in range(50):
        below = weights < min_weight
        above = weights > max_weight
        if not below.any() and not above.any():
            break
        weights[below] = min_weight
        weights[above] = max_weight
        weights = weights / weights.sum()

    w_arr = weights.values

    return {
        "weights": w_arr,
        "return": portfolio_return(w_arr, mean_ret),
        "volatility": portfolio_volatility(w_arr, cov),
        "sharpe": sharpe_ratio(w_arr, mean_ret, cov),
        "weights_dict": dict(zip(tickers, w_arr)),
    }
