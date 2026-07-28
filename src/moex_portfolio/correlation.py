"""Корреляционный анализ."""

import logging

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

logger = logging.getLogger(__name__)


def compute_correlation_matrix(returns: pd.DataFrame) -> pd.DataFrame:
    """Вычисление матрицы корреляций Пирсона.

    Args:
        returns: DataFrame с доходностями.

    Returns:
        Матрица корреляций.
    """
    return returns.corr()


def plot_correlation_heatmap(
    corr: pd.DataFrame,
    title: str = "Correlation Matrix",
    annotate: bool = False,
    figsize: tuple[int, int] = (16, 14),
    save_path: str | None = None,
) -> plt.Figure:
    """Тепловая карта корреляций (треугольная маска).

    Args:
        corr: Матрица корреляций.
        title: Заголовок графика.
        annotate: Показывать значения в ячейках.
        figsize: Размер фигуры.
        save_path: Путь для сохранения (если None — не сохранять).

    Returns:
        matplotlib Figure.
    """
    mask = np.triu(np.ones_like(corr, dtype=bool))

    fig, ax = plt.subplots(figsize=figsize)
    sns.heatmap(
        corr,
        mask=mask,
        cmap="coolwarm",
        center=0,
        vmin=-1,
        vmax=1,
        square=True,
        linewidths=0.5,
        annot=annotate,
        fmt=".2f" if annotate else None,
        cbar_kws={"shrink": 0.8},
        ax=ax,
    )

    ax.set_title(title, fontsize=18)
    plt.xticks(rotation=45)
    plt.yticks(rotation=0)
    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        transparent_path = save_path.replace(".png", "_transparent.png")
        fig.savefig(transparent_path, dpi=150, bbox_inches="tight", transparent=True)
        logger.info("Saved correlation heatmap to %s", save_path)

    return fig
