"""Граф корреляций и поиск максимальной клики."""

import logging

import networkx as nx
import pandas as pd

from .config import CORR_THRESHOLD

logger = logging.getLogger(__name__)


def build_correlation_graph(
    corr: pd.DataFrame,
    threshold: float = CORR_THRESHOLD,
) -> nx.Graph:
    """Построение графа корреляций.

    Ребро добавляется, если |correlation| < threshold (акции слабо связаны).

    Args:
        corr: Матрица корреляций.
        threshold: Порог корреляции.

    Returns:
        NetworkX Graph.
    """
    G = nx.Graph()

    for ticker in corr.columns:
        G.add_node(ticker)

    for i in range(len(corr.columns)):
        for j in range(i + 1, len(corr.columns)):
            correlation = corr.iloc[i, j]
            if correlation < threshold:
                G.add_edge(corr.columns[i], corr.columns[j])

    logger.info(
        "Graph: %d vertices, %d edges (threshold=%.2f)",
        G.number_of_nodes(),
        G.number_of_edges(),
        threshold,
    )
    return G


def find_max_clique(G: nx.Graph) -> list[str]:
    """Поиск максимальной клики в графе (алгоритм Bron-Kerbosch).

    Args:
        G: NetworkX Graph.

    Returns:
        Список тикеров максимальной клики.
    """
    cliques = list(nx.find_cliques(G))

    if not cliques:
        logger.warning("No cliques found. Try increasing CORR_THRESHOLD.")
        return []

    max_clique = max(cliques, key=len)
    logger.info("Max clique size: %d", len(max_clique))
    return max_clique


def get_clique_subgraph(G: nx.Graph, clique: list[str]) -> nx.Graph:
    """Извлечение подграфа клики.

    Args:
        G: Исходный граф.
        clique: Список тикеров клики.

    Returns:
        Subgraph клики.
    """
    return G.subgraph(clique)
