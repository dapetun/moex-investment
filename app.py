"""Streamlit Dashboard — интерактивный подбор портфеля MOEX."""

import sys
from pathlib import Path

# Добавляем src в путь для импорта модулей
sys.path.insert(0, str(Path(__file__).parent / "src"))

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
import streamlit as st

from moex_portfolio.analytics import (
    cvar_historical,
    equity_curve,
    monte_carlo_simulation,
    var_historical,
)
from moex_portfolio.config import (
    CORR_THRESHOLD,
    MAX_WEIGHT,
    MIN_OBSERVATIONS,
    MIN_TURNOVER,
    MIN_WEIGHT,
    RISK_FREE_RATE,
)
from moex_portfolio.correlation import compute_correlation_matrix, plot_correlation_heatmap
from moex_portfolio.data_loader import get_all_shares, load_all_data
from moex_portfolio.filters import prepare_returns
from moex_portfolio.graph_analysis import build_correlation_graph, find_max_clique
from moex_portfolio.metrics import portfolio_metrics
from moex_portfolio.optimizer import efficient_frontier, max_sharpe_portfolio, min_variance_portfolio
from moex_portfolio.risk_models import covariance_matrix
from moex_portfolio.visualization import (
    plot_clique_heatmap,
    plot_clique_on_graph,
    plot_clique_separate,
    plot_full_graph,
    plot_total_returns,
)

st.set_page_config(page_title="MOEX Portfolio Optimizer", layout="wide")
st.title("MOEX Portfolio Optimizer")
st.markdown("Автоматический подбор оптимального инвестиционного портфеля акций MOEX")

# ─── Sidebar: параметры ───────────────────────────────────────────────
st.sidebar.header("Parameters")

corr_threshold = st.sidebar.slider(
    "Correlation threshold",
    min_value=0.0,
    max_value=1.0,
    value=CORR_THRESHOLD,
    step=0.05,
    help="Акции с корреляцией ниже этого порога считаются 'слабо связанными'",
)

min_turnover_m = st.sidebar.number_input(
    "Min daily turnover (M RUB)",
    min_value=1,
    value=int(MIN_TURNOVER / 1_000_000),
    step=5,
)
min_turnover = min_turnover_m * 1_000_000

max_weight_pct = st.sidebar.slider(
    "Max weight per asset (%)",
    min_value=5,
    value=int(MAX_WEIGHT * 100),
    max_value=100,
    step=5,
)
max_weight = max_weight_pct / 100.0

risk_free = st.sidebar.number_input(
    "Risk-free rate (annual, %)",
    min_value=0.0,
    value=RISK_FREE_RATE * 100,
    step=0.5,
) / 100.0

cov_method = st.sidebar.selectbox(
    "Covariance method",
    options=["sample", "ledoit_wolf", "ewma"],
    index=0,
    help="Sample: обычная ковариация. Ledoit-Wolf: сжатие (стабильнее). EWMA: экспоненциальное сглаживание.",
)

mc_sims = st.sidebar.number_input(
    "Monte Carlo simulations",
    min_value=1000,
    value=10_000,
    step=1000,
)

use_cache = st.sidebar.checkbox("Use cached data", value=True)

# ─── Основной пайплайн ───────────────────────────────────────────────
if st.sidebar.button("Run Optimization", type="primary"):
    # Шаг 1: Загрузка данных
    with st.spinner("Loading stock list from MOEX..."):
        tickers = get_all_shares()
    st.info(f"Found {len(tickers)} stocks on MOEX")

    with st.spinner("Loading price data..."):
        raw_data = load_all_data(tickers, use_cache=use_cache)

    # Шаг 2: Фильтрация
    with st.spinner("Filtering and computing returns..."):
        returns, valid_tickers = prepare_returns(
            raw_data, min_turnover=min_turnover
        )
    st.info(f"After filtering: {len(valid_tickers)} stocks, {len(returns)} periods")

    # Шаг 3: Корреляции
    corr = compute_correlation_matrix(returns)

    # Шаг 4: Граф и клика
    G = build_correlation_graph(corr, threshold=corr_threshold)
    clique = find_max_clique(G)

    if not clique:
        st.error("No clique found. Try increasing the correlation threshold.")
        st.stop()

    st.success(f"Found clique with {len(clique)} stocks: {', '.join(clique)}")

    # Шаг 5: Оптимизация
    clique_returns = returns[clique]
    mean_ret = clique_returns.mean()
    cov = covariance_matrix(clique_returns, method=cov_method)

    opt_result = max_sharpe_portfolio(
        mean_ret, cov, risk_free_rate=risk_free, max_weight=max_weight
    )
    min_var_result = min_variance_portfolio(
        mean_ret, cov, max_weight=max_weight
    )
    ef = efficient_frontier(
        mean_ret, cov, n_points=50, max_weight=max_weight
    )

    # VaR/CVaR
    var_95 = var_historical(clique_returns, opt_result["weights"], confidence=0.95)
    cvar_95 = cvar_historical(clique_returns, opt_result["weights"], confidence=0.95)

    # Monte Carlo
    mc_results = monte_carlo_simulation(
        mean_ret, cov, opt_result["weights"],
        n_simulations=int(mc_sims), seed=42,
    )

    # Equity curve
    eq = equity_curve(clique_returns, opt_result["weights"])

    # ─── Результаты ───────────────────────────────────────────────
    tab_overview, tab_frontier, tab_mc, tab_graphs, tab_analysis = st.tabs(
        ["Portfolio", "Efficient Frontier", "Monte Carlo", "Graph Analysis", "Detailed Analysis"]
    )

    with tab_overview:
        st.subheader("Optimal Portfolio (Max Sharpe)")

        portfolio_df = pd.DataFrame({
            "Asset": clique,
            "Weight": [f"{w:.2%}" for w in opt_result["weights"]],
        }).sort_values("Weight", ascending=False)
        st.dataframe(portfolio_df, use_container_width=True)

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Annual Return", f"{opt_result['return']:.2%}")
        col2.metric("Annual Volatility", f"{opt_result['volatility']:.2%}")
        col3.metric("Sharpe Ratio", f"{opt_result['sharpe']:.3f}")
        col4.metric("Risk-free Rate", f"{risk_free:.2%}")

        col5, col6, col7, col8 = st.columns(4)
        col5.metric("VaR (95%)", f"{var_95:.2%}", help="Суточные потери с 5% вероятностью")
        col6.metric("CVaR (95%)", f"{cvar_95:.2%}", help="Средние потери за VaR")
        col7.metric("Sortino", f"{opt_result.get('sortino', 0):.3f}")
        col8.metric("Cov Method", cov_method.upper())

        st.subheader("Equity Curve (Max Sharpe Portfolio)")
        fig_eq, ax_eq = plt.subplots(figsize=(12, 4))
        ax_eq.plot(eq.index, eq.values, linewidth=1.5, color="#1f77b4")
        ax_eq.axhline(y=1.0, color="gray", linestyle="--", alpha=0.5)
        ax_eq.set_title("Portfolio Growth")
        ax_eq.set_ylabel("Cumulative Return")
        ax_eq.grid(True, alpha=0.3)
        plt.tight_layout()
        st.pyplot(fig_eq)
        plt.close(fig_eq)

        st.subheader("Min Variance Portfolio")
        min_var_df = pd.DataFrame({
            "Asset": clique,
            "Weight": [f"{w:.2%}" for w in min_var_result["weights"]],
        }).sort_values("Weight", ascending=False)
        st.dataframe(min_var_df, use_container_width=True)

        mc1, mc2, mc3 = st.columns(3)
        mc1.metric("Return", f"{min_var_result['return']:.2%}")
        mc2.metric("Volatility", f"{min_var_result['volatility']:.2%}")
        mc3.metric("Sharpe", f"{min_var_result['sharpe']:.3f}")

    with tab_frontier:
        st.subheader("Efficient Frontier")

        fig, ax = plt.subplots(figsize=(10, 6))
        ax.scatter(ef["volatility"], ef["return"], c=ef["sharpe"], cmap="viridis", s=10)
        ax.scatter(
            opt_result["volatility"],
            opt_result["return"],
            marker="*",
            s=300,
            c="red",
            label="Max Sharpe",
            zorder=5,
        )
        ax.scatter(
            min_var_result["volatility"],
            min_var_result["return"],
            marker="*",
            s=300,
            c="blue",
            label="Min Variance",
            zorder=5,
        )
        ax.set_xlabel("Annual Volatility")
        ax.set_ylabel("Annual Return")
        ax.set_title("Efficient Frontier")
        ax.legend()
        plt.colorbar(ax.collections[0], ax=ax, label="Sharpe Ratio")
        plt.tight_layout()
        st.pyplot(fig)
        plt.close(fig)

    with tab_mc:
        st.subheader("Monte Carlo Simulation")

        col_a, col_b, col_c, col_d = st.columns(4)
        col_a.metric("Mean Annual Return", f"{mc_results['annual_return'].mean():.2%}")
        col_b.metric("Mean Annual Volatility", f"{mc_results['annual_volatility'].mean():.2%}")
        col_c.metric("Mean Max Drawdown", f"{mc_results['max_drawdown'].mean():.2%}")
        col_d.metric("Simulations", f"{mc_sims:,}")

        # Distribution of annual returns
        fig_mc, axes = plt.subplots(1, 3, figsize=(15, 4))

        axes[0].hist(mc_results["annual_return"] * 100, bins=80, color="#1f77b4", alpha=0.7, edgecolor="white")
        axes[0].axvline(x=mc_results["annual_return"].mean() * 100, color="red", linestyle="--", label="Mean")
        axes[0].set_xlabel("Annual Return (%)")
        axes[0].set_ylabel("Frequency")
        axes[0].set_title("Return Distribution")
        axes[0].legend()

        axes[1].hist(mc_results["annual_volatility"] * 100, bins=80, color="#ff7f0e", alpha=0.7, edgecolor="white")
        axes[1].axvline(x=mc_results["annual_volatility"].mean() * 100, color="red", linestyle="--", label="Mean")
        axes[1].set_xlabel("Annual Volatility (%)")
        axes[1].set_title("Volatility Distribution")
        axes[1].legend()

        axes[2].hist(mc_results["max_drawdown"] * 100, bins=80, color="#2ca02c", alpha=0.7, edgecolor="white")
        axes[2].axvline(x=mc_results["max_drawdown"].mean() * 100, color="red", linestyle="--", label="Mean")
        axes[2].set_xlabel("Max Drawdown (%)")
        axes[2].set_title("Drawdown Distribution")
        axes[2].legend()

        plt.tight_layout()
        st.pyplot(fig_mc)
        plt.close(fig_mc)

        # Percentiles
        st.subheader("Confidence Intervals")
        percentiles = [5, 25, 50, 75, 95]
        pct_df = pd.DataFrame({
            "Percentile": [f"{p}%" for p in percentiles],
            "Annual Return": [f"{np.percentile(mc_results['annual_return'], p):.2%}" for p in percentiles],
            "Annual Volatility": [f"{np.percentile(mc_results['annual_volatility'], p):.2%}" for p in percentiles],
            "Max Drawdown": [f"{np.percentile(mc_results['max_drawdown'], p):.2%}" for p in percentiles],
        })
        st.dataframe(pct_df, use_container_width=True)

    with tab_graphs:
        st.subheader("Correlation Graph Analysis")

        col_left, col_right = st.columns(2)

        with col_left:
            fig_full = plot_full_graph(G, clique=clique)
            st.pyplot(fig_full)
            plt.close(fig_full)

        with col_right:
            fig_clique = plot_clique_on_graph(G, clique)
            st.pyplot(fig_clique)
            plt.close(fig_clique)

        col_l2, col_r2 = st.columns(2)

        with col_l2:
            fig_sep = plot_clique_separate(G, clique)
            st.pyplot(fig_sep)
            plt.close(fig_sep)

        with col_r2:
            fig_heat = plot_clique_heatmap(returns, clique)
            st.pyplot(fig_heat)
            plt.close(fig_heat)

    with tab_analysis:
        st.subheader("Individual Stock Analysis")

        fig_returns = plot_total_returns(returns, clique)
        st.pyplot(fig_returns)
        plt.close(fig_returns)

        st.subheader("Returns Statistics")
        stats_df = pd.DataFrame({
            "Mean Daily Return": clique_returns.mean(),
            "Annual Return": clique_returns.mean() * 252,
            "Daily Volatility": clique_returns.std(),
            "Annual Volatility": clique_returns.std() * (252 ** 0.5),
            "Min Daily Return": clique_returns.min(),
            "Max Daily Return": clique_returns.max(),
        }).round(6)
        st.dataframe(stats_df, use_container_width=True)

else:
    st.info("Configure parameters in the sidebar and click **Run Optimization** to start.")

    st.markdown("---")
    st.markdown("### How it works")
    st.markdown("""
    1. **Data Loading**: Downloads price history for all MOEX stocks via ISS API
    2. **Filtering**: Removes illiquid stocks (below turnover threshold) and anomalous data
    3. **Correlation Graph**: Builds a graph where edges connect weakly correlated stocks
    4. **Clique Detection**: Finds the largest group of mutually uncorrelated stocks
    5. **Optimization**: Applies Markowitz Mean-Variance optimization to find optimal weights
    6. **Risk Analysis**: Monte Carlo simulation, VaR/CVaR, equity curve
    """)
