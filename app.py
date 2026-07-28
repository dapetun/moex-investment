"""Streamlit Dashboard — интерактивный подбор портфеля MOEX."""

import sys
import tempfile
from pathlib import Path

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
from moex_portfolio.charts import (
    plot_efficient_frontier_plotly,
    plot_equity_curve_plotly,
    plot_mc_percentiles_table,
    plot_monte_carlo_plotly,
    plot_weights_bar_plotly,
)
from moex_portfolio.config import (
    CORR_THRESHOLD,
    MAX_WEIGHT,
    MIN_OBSERVATIONS,
    MIN_TURNOVER,
    MIN_WEIGHT,
    RISK_FREE_RATE,
    REBALANCE_FREQ_DAYS,
    TRANSACTION_COST_BPS,
    MIN_DRIFT,
)
from moex_portfolio.correlation import compute_correlation_matrix, plot_correlation_heatmap
from moex_portfolio.data_loader import get_all_shares, load_all_data
from moex_portfolio.exporter import export_portfolio_to_excel
from moex_portfolio.filters import prepare_returns
from moex_portfolio.graph_analysis import build_correlation_graph, find_max_clique
from moex_portfolio.metrics import portfolio_metrics
from moex_portfolio.optimizer import efficient_frontier, max_sharpe_portfolio, min_variance_portfolio
from moex_portfolio.rebalancing import RebalanceConfig, compare_strategies, simulate_rebalancing, simulate_buy_and_hold
from moex_portfolio.risk_models import covariance_matrix
from moex_portfolio.stress_test import run_all_scenarios, stress_results_to_dataframe
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
    min_value=0.0, max_value=1.0,
    value=CORR_THRESHOLD, step=0.05,
)

min_turnover_m = st.sidebar.number_input(
    "Min daily turnover (M RUB)",
    min_value=1, value=int(MIN_TURNOVER / 1_000_000), step=5,
)
min_turnover = min_turnover_m * 1_000_000

max_weight_pct = st.sidebar.slider(
    "Max weight per asset (%)",
    min_value=5, value=int(MAX_WEIGHT * 100), max_value=100, step=5,
)
max_weight = max_weight_pct / 100.0

risk_free = st.sidebar.number_input(
    "Risk-free rate (annual, %)",
    min_value=0.0, value=RISK_FREE_RATE * 100, step=0.5,
) / 100.0

cov_method = st.sidebar.selectbox(
    "Covariance method",
    options=["sample", "ledoit_wolf", "ewma"],
    index=0,
)

mc_sims = st.sidebar.number_input(
    "Monte Carlo simulations",
    min_value=1000, value=10_000, step=1000,
)

rebalance_freq = st.sidebar.number_input(
    "Rebalance frequency (days)",
    min_value=5, value=REBALANCE_FREQ_DAYS, step=5,
)

transaction_cost_bps = st.sidebar.number_input(
    "Transaction cost (bps)",
    min_value=0, value=int(TRANSACTION_COST_BPS), step=1,
)

use_cache = st.sidebar.checkbox("Use cached data", value=True)

# ─── Основной пайплайн ───────────────────────────────────────────────
if st.sidebar.button("Run Optimization", type="primary"):
    with st.spinner("Loading stock list from MOEX..."):
        tickers = get_all_shares()
    st.info(f"Found {len(tickers)} stocks on MOEX")

    with st.spinner("Loading price data..."):
        raw_data = load_all_data(tickers, use_cache=use_cache)

    with st.spinner("Filtering and computing returns..."):
        returns, valid_tickers = prepare_returns(raw_data, min_turnover=min_turnover)
    st.info(f"After filtering: {len(valid_tickers)} stocks, {len(returns)} periods")

    corr = compute_correlation_matrix(returns)
    G = build_correlation_graph(corr, threshold=corr_threshold)
    clique = find_max_clique(G)

    if not clique:
        st.error("No clique found. Try increasing the correlation threshold.")
        st.stop()

    st.success(f"Found clique with {len(clique)} stocks: {', '.join(clique)}")

    clique_returns = returns[clique]
    mean_ret = clique_returns.mean()
    cov = covariance_matrix(clique_returns, method=cov_method)

    opt_result = max_sharpe_portfolio(mean_ret, cov, risk_free_rate=risk_free, max_weight=max_weight)
    min_var_result = min_variance_portfolio(mean_ret, cov, max_weight=max_weight)
    ef = efficient_frontier(mean_ret, cov, n_points=50, max_weight=max_weight)

    var_95 = var_historical(clique_returns, opt_result["weights"], confidence=0.95)
    cvar_95 = cvar_historical(clique_returns, opt_result["weights"], confidence=0.95)

    mc_results = monte_carlo_simulation(
        mean_ret, cov, opt_result["weights"],
        n_simulations=int(mc_sims), seed=42,
    )
    eq = equity_curve(clique_returns, opt_result["weights"])

    metrics = portfolio_metrics(opt_result["weights"], mean_ret, cov, returns=clique_returns)

    # ─── Tabs ─────────────────────────────────────────────────────
    tab_overview, tab_frontier, tab_mc, tab_graphs, tab_analysis, tab_rebal, tab_stress = st.tabs(
        ["Portfolio", "Efficient Frontier", "Monte Carlo", "Graph Analysis", "Detailed Analysis", "Rebalancing", "Stress Test"]
    )

    with tab_overview:
        st.subheader("Optimal Portfolio (Max Sharpe)")
        st.plotly_chart(plot_weights_bar_plotly(clique, opt_result["weights"]), use_container_width=True)

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Annual Return", f"{opt_result['return']:.2%}")
        col2.metric("Annual Volatility", f"{opt_result['volatility']:.2%}")
        col3.metric("Sharpe Ratio", f"{opt_result['sharpe']:.3f}")
        col4.metric("Risk-free Rate", f"{risk_free:.2%}")

        col5, col6, col7, col8 = st.columns(4)
        col5.metric("VaR (95%)", f"{var_95:.2%}")
        col6.metric("CVaR (95%)", f"{cvar_95:.2%}")
        col7.metric("Sortino", f"{metrics.get('sortino', 0):.3f}")
        col8.metric("Cov Method", cov_method.upper())

        st.subheader("Portfolio Growth")
        st.plotly_chart(plot_equity_curve_plotly(eq), use_container_width=True)

        st.subheader("Min Variance Portfolio")
        st.plotly_chart(plot_weights_bar_plotly(clique, min_var_result["weights"], title="Min Variance Weights"), use_container_width=True)
        mc1, mc2, mc3 = st.columns(3)
        mc1.metric("Return", f"{min_var_result['return']:.2%}")
        mc2.metric("Volatility", f"{min_var_result['volatility']:.2%}")
        mc3.metric("Sharpe", f"{min_var_result['sharpe']:.3f}")

    with tab_frontier:
        st.subheader("Efficient Frontier")
        st.plotly_chart(plot_efficient_frontier_plotly(ef, opt_result, min_var_result), use_container_width=True)

    with tab_mc:
        st.subheader("Monte Carlo Simulation")
        col_a, col_b, col_c, col_d = st.columns(4)
        col_a.metric("Mean Return", f"{mc_results['annual_return'].mean():.2%}")
        col_b.metric("Mean Volatility", f"{mc_results['annual_volatility'].mean():.2%}")
        col_c.metric("Mean Max DD", f"{mc_results['max_drawdown'].mean():.2%}")
        col_d.metric("Simulations", f"{mc_sims:,}")

        st.plotly_chart(plot_monte_carlo_plotly(mc_results), use_container_width=True)

        st.subheader("Confidence Intervals")
        st.dataframe(plot_mc_percentiles_table(mc_results), use_container_width=True)

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

    with tab_rebal:
        st.subheader("Rebalancing Simulation")

        rebal_config = RebalanceConfig(
            target_weights={t: opt_result["weights"][i] for i, t in enumerate(clique)},
            rebalance_freq_days=rebalance_freq,
            transaction_cost_bps=transaction_cost_bps,
            min_drift=MIN_DRIFT,
        )

        rebal_result = simulate_rebalancing(clique_returns, rebal_config, cov_method=cov_method)
        bh_result = simulate_buy_and_hold(clique_returns, rebal_config.target_weights)

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Rebalancing Return", f"{rebal_result.annual_return:.2%}")
        col2.metric("Rebalancing Sharpe", f"{rebal_result.sharpe:.3f}")
        col3.metric("Total Cost", f"{rebal_result.total_cost:,.0f} RUB")
        col4.metric("Rebalances", str(rebal_result.n_rebalances))

        col5, col6, col7, col8 = st.columns(4)
        col5.metric("B&H Return", f"{bh_result.annual_return:.2%}")
        col6.metric("B&H Sharpe", f"{bh_result.sharpe:.3f}")
        col7.metric("B&H Max DD", f"{bh_result.max_drawdown:.2%}")
        col8.metric("Rebalancing Max DD", f"{rebal_result.max_drawdown:.2%}")

        rebal_df = pd.DataFrame({
            "Date": rebal_result.dates,
            "Rebalancing": rebal_result.portfolio_values,
            "Buy & Hold": bh_result.portfolio_values[:len(rebal_result.portfolio_values)],
        }).set_index("Date")
        st.line_chart(rebal_df)

        st.subheader("Strategy Comparison")
        comparison = compare_strategies(clique_returns, rebal_config, cov_method=cov_method)
        st.dataframe(comparison, use_container_width=True)

    with tab_stress:
        st.subheader("Stress Testing on Historical Crises")

        stress_results = run_all_scenarios(clique_returns, opt_result["weights"])
        stress_df = stress_results_to_dataframe(stress_results)
        st.dataframe(stress_df, use_container_width=True)

        st.markdown("---")
        st.subheader("Scenario Details")
        for r in stress_results:
            with st.expander(f"{r.scenario_name} ({r.start_date} — {r.end_date})"):
                st.write(f"**{r.description}**")
                st.metric("Portfolio Return", f"{r.portfolio_return:.2%}")
                st.metric("Max Drawdown", f"{r.portfolio_max_drawdown:.2%}")
                st.metric("Worst Day", f"{r.worst_day:.2%} on {r.worst_day_date}")
                st.metric("Recovery", f"{r.recovery_days} days" if r.recovery_days else "Not recovered")

    # ─── Excel Export ──────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Export Results")

    params = {
        "corr_threshold": corr_threshold,
        "min_turnover": min_turnover,
        "max_weight": max_weight,
        "risk_free_rate": risk_free,
        "cov_method": cov_method,
        "mc_simulations": mc_sims,
        "n_stocks": len(clique),
        "clique": ", ".join(clique),
        "rebalance_freq_days": rebalance_freq,
        "transaction_cost_bps": transaction_cost_bps,
    }

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    export_path = export_portfolio_to_excel(
        tmp_path, clique, opt_result, min_var_result,
        mc_results=mc_results, returns=returns,
        metrics=metrics, params=params,
        rebalance_result=rebal_result,
        stress_results=stress_results,
        buy_hold_result=bh_result,
    )

    with open(export_path, "rb") as f:
        st.download_button(
            label="Download Excel Report",
            data=f.read(),
            file_name="portfolio_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    export_path.unlink(missing_ok=True)

else:
    st.info("Configure parameters in the sidebar and click **Run Optimization** to start.")
    st.markdown("---")
    st.markdown("### How it works")
    st.markdown("""
    1. **Data Loading**: Downloads price history for all MOEX stocks via ISS API
    2. **Filtering**: Removes illiquid stocks and anomalous data
    3. **Correlation Graph**: Builds a graph where edges connect weakly correlated stocks
    4. **Clique Detection**: Finds the largest group of mutually uncorrelated stocks
    5. **Optimization**: Markowitz Mean-Variance with Ledoit-Wolf covariance shrinkage
    6. **Risk Analysis**: Monte Carlo simulation, VaR/CVaR, equity curve
    7. **Export**: Download full Excel report with all results
    """)
