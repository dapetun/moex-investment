"""Интерактивные графики Plotly для дашборда."""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def plot_efficient_frontier_plotly(
    ef: pd.DataFrame,
    opt_result: dict,
    min_var_result: dict,
) -> go.Figure:
    """Интерактивный Efficient Frontier.

    Args:
        ef: DataFrame с efficient frontier данными.
        opt_result: Результат max_sharpe_portfolio.
        min_var_result: Результат min_variance_portfolio.

    Returns:
        Plotly Figure.
    """
    fig = go.Figure()

    # Efficient frontier scatter
    fig.add_trace(go.Scatter(
        x=ef["volatility"] * 100,
        y=ef["return"] * 100,
        mode="markers",
        marker=dict(
            size=6,
            color=ef["sharpe"],
            colorscale="Viridis",
            colorbar=dict(title="Sharpe"),
            showscale=True,
        ),
        text=[f"Sharpe: {s:.3f}<br>Return: {r:.1f}%<br>Vol: {v:.1f}%"
              for s, r, v in zip(ef["sharpe"], ef["return"] * 100, ef["volatility"] * 100)],
        hovertemplate="%{text}<extra></extra>",
        name="Frontier",
    ))

    # Max Sharpe star
    fig.add_trace(go.Scatter(
        x=[opt_result["volatility"] * 100],
        y=[opt_result["return"] * 100],
        mode="markers",
        marker=dict(size=18, symbol="star", color="red"),
        name=f"Max Sharpe (SR={opt_result['sharpe']:.3f})",
        hovertemplate=(
            f"<b>Max Sharpe</b><br>"
            f"Return: {opt_result['return']:.2%}<br>"
            f"Volatility: {opt_result['volatility']:.2%}<br>"
            f"Sharpe: {opt_result['sharpe']:.3f}"
            "<extra></extra>"
        ),
    ))

    # Min Variance star
    fig.add_trace(go.Scatter(
        x=[min_var_result["volatility"] * 100],
        y=[min_var_result["return"] * 100],
        mode="markers",
        marker=dict(size=18, symbol="star", color="blue"),
        name=f"Min Variance (SR={min_var_result['sharpe']:.3f})",
        hovertemplate=(
            f"<b>Min Variance</b><br>"
            f"Return: {min_var_result['return']:.2%}<br>"
            f"Volatility: {min_var_result['volatility']:.2%}<br>"
            f"Sharpe: {min_var_result['sharpe']:.3f}"
            "<extra></extra>"
        ),
    ))

    fig.update_layout(
        title="Efficient Frontier",
        xaxis_title="Annual Volatility (%)",
        yaxis_title="Annual Return (%)",
        template="plotly_white",
        legend=dict(x=0.01, y=0.99),
        height=500,
    )

    return fig


def plot_monte_carlo_plotly(mc_results: pd.DataFrame) -> go.Figure:
    """Интерактивные гистограммы Monte Carlo.

    Args:
        mc_results: DataFrame с результатами симуляции.

    Returns:
        Plotly Figure.
    """
    fig = make_subplots(
        rows=1, cols=3,
        subplot_titles=("Return Distribution", "Volatility Distribution", "Drawdown Distribution"),
    )

    fig.add_trace(go.Histogram(
        x=mc_results["annual_return"] * 100,
        nbinsx=80,
        name="Return",
        marker_color="#1f77b4",
        opacity=0.7,
    ), row=1, col=1)

    fig.add_trace(go.Histogram(
        x=mc_results["annual_volatility"] * 100,
        nbinsx=80,
        name="Volatility",
        marker_color="#ff7f0e",
        opacity=0.7,
    ), row=1, col=2)

    fig.add_trace(go.Histogram(
        x=mc_results["max_drawdown"] * 100,
        nbinsx=80,
        name="Drawdown",
        marker_color="#2ca02c",
        opacity=0.7,
    ), row=1, col=3)

    # Mean lines
    for col, data, color in [
        (1, "annual_return", "red"),
        (2, "annual_volatility", "red"),
        (3, "max_drawdown", "red"),
    ]:
        mean_val = mc_results[data].mean() * 100
        fig.add_vline(
            x=mean_val, line_dash="dash", line_color=color,
            annotation_text=f"Mean: {mean_val:.1f}%",
            row=1, col=col,
        )

    fig.update_xaxes(title_text="Annual Return (%)", row=1, col=1)
    fig.update_xaxes(title_text="Annual Volatility (%)", row=1, col=2)
    fig.update_xaxes(title_text="Max Drawdown (%)", row=1, col=3)
    fig.update_yaxes(title_text="Frequency", row=1, col=1)

    fig.update_layout(
        title="Monte Carlo Simulation",
        template="plotly_white",
        height=400,
        showlegend=False,
    )

    return fig


def plot_equity_curve_plotly(eq: pd.Series) -> go.Figure:
    """Интерактивная кривая роста капитала.

    Args:
        eq: Series с кумулятивной доходностью.

    Returns:
        Plotly Figure.
    """
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=eq.index,
        y=eq.values,
        mode="lines",
        line=dict(width=2, color="#1f77b4"),
        name="Portfolio",
        hovertemplate="Date: %{x|%Y-%m-%d}<br>Value: %{y:.4f}<extra></extra>",
    ))

    fig.add_hline(y=1.0, line_dash="dash", line_color="gray", opacity=0.5)

    # Max drawdown annotation
    cumulative = eq.values
    running_max = np.maximum.accumulate(cumulative)
    drawdown = (cumulative - running_max) / running_max
    max_dd_idx = np.argmin(drawdown)
    max_dd_val = drawdown[max_dd_idx]

    fig.add_trace(go.Scatter(
        x=[eq.index[max_dd_idx]],
        y=[cumulative[max_dd_idx]],
        mode="markers",
        marker=dict(size=10, color="red", symbol="triangle-down"),
        name=f"Max Drawdown ({max_dd_val:.2%})",
        hovertemplate=(
            f"<b>Max Drawdown</b><br>"
            f"Date: {eq.index[max_dd_idx].strftime('%Y-%m-%d')}<br>"
            f"Value: {cumulative[max_dd_idx]:.4f}<br>"
            f"Drawdown: {max_dd_val:.2%}"
            "<extra></extra>"
        ),
    ))

    fig.update_layout(
        title="Portfolio Growth",
        xaxis_title="Date",
        yaxis_title="Cumulative Return",
        template="plotly_white",
        height=400,
        legend=dict(x=0.01, y=0.99),
    )

    return fig


def plot_weights_bar_plotly(
    clique: list[str],
    weights: np.ndarray,
    title: str = "Portfolio Weights",
) -> go.Figure:
    """Интерактивный бар-чарт весов портфеля.

    Args:
        clique: Список тикеров.
        weights: Веса активов.
        title: Заголовок графика.

    Returns:
        Plotly Figure.
    """
    sorted_pairs = sorted(zip(clique, weights), key=lambda x: -x[1])
    tickers_sorted = [t for t, _ in sorted_pairs]
    weights_sorted = [w * 100 for _, w in sorted_pairs]

    fig = go.Figure(go.Bar(
        x=tickers_sorted,
        y=weights_sorted,
        text=[f"{w:.1f}%" for w in weights_sorted],
        textposition="outside",
        marker_color=px.colors.qualitative.Set2[:len(clique)],
    ))

    fig.update_layout(
        title=title,
        xaxis_title="Asset",
        yaxis_title="Weight (%)",
        template="plotly_white",
        height=400,
    )

    return fig


def plot_mc_percentiles_table(mc_results: pd.DataFrame) -> pd.DataFrame:
    """Таблица процентилей Monte Carlo.

    Args:
        mc_results: DataFrame с результатами симуляции.

    Returns:
        DataFrame с процентилями.
    """
    percentiles = [5, 10, 25, 50, 75, 90, 95]
    return pd.DataFrame({
        "Percentile": [f"{p}%" for p in percentiles],
        "Annual Return": [f"{np.percentile(mc_results['annual_return'], p):.2%}" for p in percentiles],
        "Annual Volatility": [f"{np.percentile(mc_results['annual_volatility'], p):.2%}" for p in percentiles],
        "Max Drawdown": [f"{np.percentile(mc_results['max_drawdown'], p):.2%}" for p in percentiles],
        "Sharpe": [f"{np.percentile(mc_results['sharpe'], p):.3f}" for p in percentiles],
    })
