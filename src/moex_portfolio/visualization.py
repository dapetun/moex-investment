"""Визуализация графов, корреляций и доходностей."""

import logging

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
import seaborn as sns

logger = logging.getLogger(__name__)


def plot_full_graph(
    G: nx.Graph,
    clique: list[str] | None = None,
    figsize: tuple[int, int] = (16, 12),
    save_path: str | None = None,
) -> plt.Figure:
    """Визуализация полного графа корреляций с выделением клики.

    Args:
        G: NetworkX Graph.
        clique: Список тикеров клики для выделения.
        figsize: Размер фигуры.
        save_path: Путь для сохранения.

    Returns:
        matplotlib Figure.
    """
    fig, ax = plt.subplots(figsize=figsize)
    pos = nx.spring_layout(G, seed=12345)

    nx.draw_networkx_nodes(G, pos, node_size=500, ax=ax)
    nx.draw_networkx_edges(G, pos, alpha=0.3, ax=ax)

    if clique:
        clique_subgraph = G.subgraph(clique)
        nx.draw_networkx_nodes(
            clique_subgraph, pos, node_size=600, node_color="orange", ax=ax
        )
        nx.draw_networkx_edges(
            clique_subgraph, pos, edge_color="red", width=1, ax=ax
        )

    nx.draw_networkx_labels(G, pos, font_size=7, ax=ax)

    title = f"Correlation Graph ({G.number_of_nodes()} vertices, {G.number_of_edges()} edges)"
    if clique:
        title += f"\nMax clique: {len(clique)} stocks"
    ax.set_title(title, fontsize=20)
    ax.axis("off")
    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        transparent_path = save_path.replace(".png", "_transparent.png")
        fig.savefig(transparent_path, dpi=150, bbox_inches="tight", transparent=True)
        logger.info("Saved full graph to %s", save_path)

    return fig


def plot_clique_on_graph(
    G: nx.Graph,
    clique: list[str],
    pos: dict | None = None,
    figsize: tuple[int, int] = (16, 12),
    save_path: str | None = None,
) -> plt.Figure:
    """Визуализация клики на фоне полного графа.

    Args:
        G: Полный граф.
        clique: Список тикеров клики.
        pos: Позиции вершин (если None — spring layout).
        figsize: Размер фигуры.
        save_path: Путь для сохранения.

    Returns:
        matplotlib Figure.
    """
    if pos is None:
        pos = nx.spring_layout(G, seed=12345)

    fig, ax = plt.subplots(figsize=figsize)

    # Полный граф на фоне
    nx.draw_networkx_nodes(G, pos, node_size=400, node_color="lightgray", ax=ax)
    nx.draw_networkx_edges(G, pos, alpha=0.2, ax=ax)

    # Клика поверх
    clique_subgraph = G.subgraph(clique)
    nx.draw_networkx_nodes(
        clique_subgraph, pos, node_size=600, node_color="orange", ax=ax
    )
    nx.draw_networkx_edges(
        clique_subgraph, pos, edge_color="red", width=1, ax=ax
    )
    nx.draw_networkx_labels(G, pos, font_size=8, ax=ax)

    ax.set_title(f"Max Clique (size {len(clique)})", fontsize=30)
    ax.axis("off")
    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        transparent_path = save_path.replace(".png", "_transparent.png")
        fig.savefig(transparent_path, dpi=150, bbox_inches="tight", transparent=True)
        logger.info("Saved clique-on-graph to %s", save_path)

    return fig


def plot_clique_separate(
    G: nx.Graph,
    clique: list[str],
    pos: dict | None = None,
    figsize: tuple[int, int] = (12, 9),
    save_path: str | None = None,
) -> plt.Figure:
    """Визуализация только клики.

    Args:
        G: Полный граф (для позиций).
        clique: Список тикеров клики.
        pos: Позиции вершин.
        figsize: Размер фигуры.
        save_path: Путь для сохранения.

    Returns:
        matplotlib Figure.
    """
    if pos is None:
        pos = nx.spring_layout(G, seed=12345)

    fig, ax = plt.subplots(figsize=figsize)
    clique_subgraph = G.subgraph(clique)

    nx.draw_networkx_nodes(
        clique_subgraph, pos, node_size=1000, node_color="orange", ax=ax
    )
    nx.draw_networkx_edges(
        clique_subgraph, pos, edge_color="red", width=1.5, ax=ax
    )
    nx.draw_networkx_labels(clique_subgraph, pos, font_size=10, ax=ax)

    ax.set_title(f"Clique Only (size {len(clique)})", fontsize=20)
    ax.axis("off")
    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        transparent_path = save_path.replace(".png", "_transparent.png")
        fig.savefig(transparent_path, dpi=150, bbox_inches="tight", transparent=True)
        logger.info("Saved clique-separate to %s", save_path)

    return fig


def plot_clique_heatmap(
    returns: pd.DataFrame,
    clique: list[str],
    figsize: tuple[int, int] = (12, 10),
    save_path: str | None = None,
) -> plt.Figure:
    """Тепловая карта корреляций внутри клики.

    Args:
        returns: DataFrame с доходностями.
        clique: Список тикеров клики.
        figsize: Размер фигуры.
        save_path: Путь для сохранения.

    Returns:
        matplotlib Figure.
    """
    clique_returns = returns[clique]
    corr = clique_returns.corr()
    mask = np.triu(np.ones_like(corr, dtype=bool))

    fig, ax = plt.subplots(figsize=figsize)
    sns.heatmap(
        corr,
        mask=mask,
        cmap="coolwarm",
        annot=True,
        fmt=".2f",
        center=0,
        vmin=-1,
        vmax=1,
        square=True,
        linewidths=0.5,
        cbar_kws={"shrink": 0.8},
        ax=ax,
    )

    ax.set_title("Clique Correlation Matrix", fontsize=20)
    plt.xticks(rotation=45)
    plt.yticks(rotation=0)
    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        transparent_path = save_path.replace(".png", "_transparent.png")
        fig.savefig(transparent_path, dpi=150, bbox_inches="tight", transparent=True)
        logger.info("Saved clique heatmap to %s", save_path)

    return fig


def plot_total_returns(
    returns: pd.DataFrame,
    clique: list[str],
    figsize: tuple[int, int] = (12, 8),
    save_path: str | None = None,
) -> plt.Figure:
    """Бар-чарт суммарных доходностей акций клики.

    Args:
        returns: DataFrame с доходностями.
        clique: Список тикеров клики.
        figsize: Размер фигуры.
        save_path: Путь для сохранения.

    Returns:
        matplotlib Figure.
    """
    clique_returns = returns[clique]
    total_returns = ((1 + clique_returns).prod() - 1).sort_values(ascending=False)

    fig, ax = plt.subplots(figsize=figsize)
    sns.barplot(x=total_returns.values, y=total_returns.index, palette="crest", ax=ax)

    ax.set_title("Total Return by Stock", fontsize=20)
    ax.set_xlabel("Return")
    ax.set_ylabel("Stock")
    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        transparent_path = save_path.replace(".png", "_transparent.png")
        fig.savefig(transparent_path, dpi=150, bbox_inches="tight", transparent=True)
        logger.info("Saved total returns to %s", save_path)

    return fig
