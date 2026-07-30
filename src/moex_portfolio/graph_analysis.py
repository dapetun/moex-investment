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


def _greedy_max_clique(G: nx.Graph, max_starts: int = 30) -> list[str]:
    """Жадный эвристический поиск максимальной клики.

    Для каждого узла (из max_starts с наибольшей степенью) строим клику,
    последовательно добавляя соседей, связанных со всеми текущими членами.
    Возвращаем largest. Сложность O(max_starts * n * d) вместо экспоненциальной.

    Args:
        G: NetworkX Graph.
        max_starts: Макс. кол-во стартовых узлов для перебора.
    """
    best: list[str] = []
    neighbor_sets = {n: set(G.neighbors(n)) for n in G.nodes()}
    top_nodes = sorted(G.nodes(), key=lambda n: G.degree(n), reverse=True)[:max_starts]

    for node in top_nodes:
        clique = [node]
        candidates = neighbor_sets[node].copy()
        while candidates:
            next_node = max(candidates, key=lambda n: len(neighbor_sets[n] & candidates))
            clique.append(next_node)
            candidates &= neighbor_sets[next_node]
        if len(clique) > len(best):
            best = clique
    return best


def find_max_clique(G: nx.Graph) -> list[str]:
    """Поиск максимальной клики в графе.

    Для малых графов (<100 узлов) используется точный Bron-Kerbosch.
    Для больших графов — жадная эвристика O(n*m) для предотвращения
    экспоненциального зависания.

    Args:
        G: NetworkX Graph.

    Returns:
        Список тикеров максимальной клики.
    """
    n = G.number_of_nodes()

    if n == 0:
        return []

    if n < 100:
        cliques = list(nx.find_cliques(G))
        if not cliques:
            logger.warning("No cliques found. Try increasing CORR_THRESHOLD.")
            return []
        max_clique = max(cliques, key=len)
    else:
        logger.info(
            "Graph has %d nodes — using greedy heuristic to avoid Bron-Kerbosch timeout",
            n,
        )
        max_clique = _greedy_max_clique(G)
        if not max_clique:
            logger.warning("No cliques found. Try increasing CORR_THRESHOLD.")
            return []

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
