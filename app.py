"""Streamlit Dashboard — интерактивный подбор портфеля MOEX."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from moex_portfolio.analytics import (
    cvar_historical,
    equity_curve,
    monte_carlo_simulation,
    rolling_correlation,
    var_historical,
)
from moex_portfolio.black_litterman import (
    create_views_from_correlation,
    optimize_black_litterman,
)
from moex_portfolio.bonds_loader import get_ofz_list
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
    MIN_DRIFT,
    MIN_TURNOVER,
    REBALANCE_FREQ_DAYS,
    RISK_FREE_RATE,
    TRANSACTION_COST_BPS,
)
from moex_portfolio.correlation import (
    compute_correlation_matrix,
)
from moex_portfolio.data_loader import (
    get_all_shares,
    get_dividend_yields,
    load_all_data,
)
from moex_portfolio.dividend_strategies import (
    compare_dividend_strategies,
    dogs_of_the_dow,
    high_dividend_yield,
)
from moex_portfolio.exporter import export_portfolio_to_excel, export_portfolio_to_pdf
from moex_portfolio.filters import prepare_returns
from moex_portfolio.fundamental import (
    compute_multiplicators,
    get_fundamental_data,
)
from moex_portfolio.graph_analysis import build_correlation_graph, find_max_clique
from moex_portfolio.hrp import optimize_hrp
from moex_portfolio.merton import full_merton_analysis
from moex_portfolio.metrics import portfolio_metrics
from moex_portfolio.optimizer import (
    efficient_frontier,
    max_sharpe_portfolio,
    min_variance_portfolio,
)
from moex_portfolio.profiles import list_profiles, load_profile, save_profile
from moex_portfolio.rebalancing import (
    RebalanceConfig,
    compare_strategies,
    simulate_buy_and_hold,
    simulate_rebalancing,
)
from moex_portfolio.risk_models import covariance_matrix
from moex_portfolio.stress_test import run_all_scenarios, stress_results_to_dataframe
from moex_portfolio.visualization import (
    plot_clique_heatmap,
    plot_clique_on_graph,
    plot_clique_separate,
    plot_full_graph,
    plot_total_returns,
)
from moex_portfolio.yield_curve import (
    build_yield_curve,
    interpolate_yield_curve,
    term_structure_analysis,
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

bl_tau = st.sidebar.slider("Black-Litterman tau", 0.01, 0.5, 0.05, 0.01)
bl_n_views = st.sidebar.slider("BL: auto-views count", 1, 10, 5, 1)
hrp_method = st.sidebar.selectbox("HRP clustering", ["single", "complete", "average"], index=0)

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
    market_returns = returns.mean(axis=1)
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

    # Black-Litterman
    P, Q = create_views_from_correlation(clique_returns, corr.loc[clique, clique], top_n=bl_n_views)
    bl_result = optimize_black_litterman(
        clique_returns, P, Q,
        tau=bl_tau, max_weight=max_weight,
    )

    # HRP
    hrp_result = optimize_hrp(clique_returns, max_weight=max_weight)

    # ─── Tabs ─────────────────────────────────────────────────────
    tab_overview, tab_frontier, tab_mc, tab_graphs, tab_analysis, tab_rebal, tab_stress, tab_bl, tab_hrp, tab_rolling, tab_dividends, tab_fundamental, tab_bonds, tab_merton = st.tabs(
        ["Portfolio", "Efficient Frontier", "Monte Carlo", "Graph Analysis", "Detailed Analysis", "Rebalancing", "Stress Test", "Black-Litterman", "HRP", "Rolling Correlation", "Dividends", "Fundamental", "Bonds", "Merton Model"]
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

    with tab_bl:
        st.subheader("Black-Litterman Model")
        st.markdown("Combines market equilibrium with investor views for more stable portfolio weights.")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Annual Return", f"{bl_result['return']:.2%}")
        col2.metric("Annual Volatility", f"{bl_result['volatility']:.2%}")
        col3.metric("Sharpe Ratio", f"{bl_result['sharpe']:.3f}")
        col4.metric("Views Used", bl_n_views)

        st.plotly_chart(plot_weights_bar_plotly(clique, bl_result["weights"], title="Black-Litterman Weights"), use_container_width=True)

        st.subheader("Views Matrix (P)")
        p_df = pd.DataFrame(P, columns=clique, index=[f"View {i+1}" for i in range(P.shape[0])])
        st.dataframe(p_df, use_container_width=True)

        st.subheader("View Returns (Q)")
        q_df = pd.DataFrame({"View": [f"View {i+1}" for i in range(len(Q))], "Expected Return (daily)": Q})
        st.dataframe(q_df, use_container_width=True)

        st.subheader("Comparison: Markowitz vs Black-Litterman")
        comp_df = pd.DataFrame({
            "Metric": ["Return", "Volatility", "Sharpe"],
            "Markowitz (Max Sharpe)": [f"{opt_result['return']:.2%}", f"{opt_result['volatility']:.2%}", f"{opt_result['sharpe']:.3f}"],
            "Black-Litterman": [f"{bl_result['return']:.2%}", f"{bl_result['volatility']:.2%}", f"{bl_result['sharpe']:.3f}"],
        })
        st.dataframe(comp_df, use_container_width=True)

    with tab_hrp:
        st.subheader("Hierarchical Risk Parity (HRP)")
        st.markdown("Clustering-based portfolio allocation — no need for matrix inversion.")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Annual Return", f"{hrp_result['return']:.2%}")
        col2.metric("Annual Volatility", f"{hrp_result['volatility']:.2%}")
        col3.metric("Sharpe Ratio", f"{hrp_result['sharpe']:.3f}")
        col4.metric("Method", hrp_method)

        st.plotly_chart(plot_weights_bar_plotly(clique, hrp_result["weights"], title="HRP Weights"), use_container_width=True)

        st.subheader("Weight Distribution")
        weights_df = pd.DataFrame({
            "Asset": clique,
            "HRP Weight": hrp_result["weights"],
            "Markowitz Weight": opt_result["weights"],
            "BL Weight": bl_result["weights"],
        }).sort_values("HRP Weight", ascending=False)
        st.dataframe(weights_df, use_container_width=True)

        st.subheader("Strategy Comparison")
        strat_comp = pd.DataFrame({
            "Strategy": ["Markowitz (Max Sharpe)", "Min Variance", "Black-Litterman", "HRP"],
            "Return": [f"{opt_result['return']:.2%}", f"{min_var_result['return']:.2%}", f"{bl_result['return']:.2%}", f"{hrp_result['return']:.2%}"],
            "Volatility": [f"{opt_result['volatility']:.2%}", f"{min_var_result['volatility']:.2%}", f"{bl_result['volatility']:.2%}", f"{hrp_result['volatility']:.2%}"],
            "Sharpe": [f"{opt_result['sharpe']:.3f}", f"{min_var_result['sharpe']:.3f}", f"{bl_result['sharpe']:.3f}", f"{hrp_result['sharpe']:.3f}"],
        })
        st.dataframe(strat_comp, use_container_width=True)

    with tab_rolling:
        st.subheader("Rolling Correlation Analysis")
        roll_window = st.slider("Rolling window (days)", 20, 120, 60, 5, key="roll_window")
        roll_corr = rolling_correlation(returns[clique], window=roll_window)

        st.info(f"{len(roll_corr)} pairs, window={roll_window} days")
        roll_df = pd.DataFrame(roll_corr)
        st.line_chart(roll_df, height=400)

        st.subheader("Rolling Beta")
        from moex_portfolio.analytics import rolling_beta as rb
        roll_beta_df = rb(returns[clique], market_returns, window=roll_window)
        st.line_chart(roll_beta_df, height=400)

    with tab_dividends:
        st.subheader("Dividend Strategies")
        st.markdown("Dogs of the Dow, High Dividend Yield, and Equal Weight benchmark — using real MOEX dividend data.")

        with st.spinner("Loading dividend data from MOEX ISS..."):
            price_cols = [c for c in raw_data.columns if not c.endswith("_VALUE")]
            all_prices = raw_data[price_cols]
            dy = get_dividend_yields(clique, all_prices)

        nonzero_dy = dy[dy > 0]
        if len(nonzero_dy) > 0:
            st.info(f"Real dividend data loaded: {len(nonzero_dy)} of {len(clique)} stocks pay dividends")
            dy_display = pd.DataFrame({
                "Ticker": nonzero_dy.index,
                "Dividend Yield": nonzero_dy.values,
            }).sort_values("Dividend Yield", ascending=False)
            st.dataframe(
                dy_display.style.format({"Dividend Yield": "{:.2%}"}),
                use_container_width=True,
            )
        else:
            st.warning("No real dividend data found for clique stocks. Using market-wide estimates.")
            price_cols_all = [c for c in raw_data.columns if not c.endswith("_VALUE")]
            all_prices_full = raw_data[price_cols_all]
            dy = get_dividend_yields(list(all_prices_full.columns), all_prices_full)
            dy = dy[dy.index.isin(clique)]

        col1, col2 = st.columns(2)
        with col1:
            n_dogs = st.slider("Dogs of the Dow: N stocks", 3, 20, 10, key="n_dogs")
        with col2:
            hd_percentile = st.slider("High Div: percentile", 50, 95, 75, key="hd_pct")

        dogs_result = dogs_of_the_dow(returns, dy, n_stocks=n_dogs)
        hd_result = high_dividend_yield(returns, dy, percentile=hd_percentile)
        comp_div = compare_dividend_strategies(returns, dy)

        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Dogs: Stocks", str(len(dogs_result["selected_tickers"])))
        col_b.metric("Dogs: Sharpe", f"{dogs_result['sharpe']:.3f}")
        col_c.metric("Dogs: Annual Return", f"{dogs_result['annual_return']:.2%}")

        st.dataframe(comp_div, use_container_width=True)

        if dogs_result["selected_tickers"]:
            st.subheader("Selected Stocks (Dogs)")
            st.write(", ".join(dogs_result["selected_tickers"]))

    with tab_fundamental:
        st.subheader("Fundamental Analysis")
        st.markdown("Stock ranking with real MOEX data (P/E, P/B, Market Cap) + returns-based metrics.")

        mult = compute_multiplicators(returns)

        with st.spinner("Loading fundamental data from MOEX ISS..."):
            fund_data = get_fundamental_data(clique)

        if not fund_data.empty:
            st.info(f"Loaded fundamental data for {len(fund_data)} stocks")
            merged = mult.merge(
                fund_data.set_index("ticker"),
                left_index=True, right_index=True, how="left",
            )
        else:
            st.warning("Could not load fundamental data from MOEX. Using returns-based metrics only.")
            merged = mult

        display_cols = ["annual_return", "annual_volatility", "sharpe", "skewness", "kurtosis"]
        if "issuecapitalization" in merged.columns:
            display_cols.insert(0, "issuecapitalization")
        display_cols = [c for c in display_cols if c in merged.columns]
        st.dataframe(
            merged[display_cols].style.format({
                "annual_return": "{:.2%}",
                "annual_volatility": "{:.2%}",
                "sharpe": "{:.3f}",
                "skewness": "{:.3f}",
                "kurtosis": "{:.3f}",
                "issuecapitalization": "{:,.0f}",
            }),
            use_container_width=True,
        )

        st.subheader("Composite Ranking")
        top_n_fund = st.slider("Top N stocks by score", 5, len(merged), min(10, len(merged)), key="top_n_fund")
        top_stocks = merged.head(top_n_fund)
        st.bar_chart(top_stocks["composite_score"])

    with tab_bonds:
        st.subheader("Bond Analysis (OFZ)")
        st.markdown("Yield curve, duration, convexity — based on MOEX ISS bond data.")

        try:
            ofz_df = get_ofz_list()
            if ofz_df is not None and len(ofz_df) > 0:
                st.info(f"Loaded {len(ofz_df)} OFZ bonds from MOEX")

                ofz_display = ofz_df[["SECID", "NAME", "YIELDTOOFFER", "MATDATE"]].copy() if "NAME" in ofz_df.columns else ofz_df[["SECID", "YIELDTOOFFER", "MATDATE"]].copy()
                st.dataframe(ofz_display, use_container_width=True)

                curve = build_yield_curve(ofz_df)
                if len(curve) > 0:
                    st.subheader("Yield Curve (OFZ)")
                    st.line_chart(curve.set_index("maturity_years")["yield_pct"])

                    interp = interpolate_yield_curve(curve)
                    if len(interp) > 0:
                        st.subheader("Interpolated Yield Curve")
                        st.line_chart(interp.set_index("maturity_years")["yield_pct"])

                    ts = term_structure_analysis(curve)
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("Shape", ts.get("shape", "N/A"))
                    col2.metric("Short Yield", f"{ts.get('short_yield', 0):.2f}%")
                    col3.metric("Long Yield", f"{ts.get('long_yield', 0):.2f}%")
                    col4.metric("Term Spread", f"{ts.get('term_spread_pct', 0):.2f}%")
                else:
                    st.warning("Could not build yield curve from OFZ data.")
            else:
                st.warning("No OFZ data available from MOEX ISS.")
        except Exception as e:
            st.error(f"Error loading bond data: {e}")

    with tab_merton:
        st.subheader("Merton Structural Credit Risk Model")
        st.markdown("Estimate probability of default using Black-Scholes framework.")

        col1, col2 = st.columns(2)
        with col1:
            equity_val = st.number_input("Equity Value (M RUB)", min_value=10.0, value=300.0, step=10.0, key="merton_eq")
            debt_val = st.number_input("Debt Face Value (M RUB)", min_value=10.0, value=700.0, step=10.0, key="merton_debt")
        with col2:
            vol_eq = st.number_input("Equity Volatility (%)", min_value=1.0, value=40.0, step=5.0, key="merton_vol") / 100.0
            rf_rate = st.number_input("Risk-Free Rate (%)", min_value=0.0, value=12.0, step=0.5, key="merton_rf") / 100.0
            ttm = st.number_input("Time to Maturity (years)", min_value=0.25, value=2.0, step=0.25, key="merton_ttm")

        if st.button("Run Merton Analysis", key="run_merton"):
            result = full_merton_analysis(equity_val, debt_val, vol_eq, rf_rate, ttm)

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Distance to Default", f"{result['distance_to_default']:.2f}")
            col2.metric("Probability of Default", f"{result['probability_of_default']:.2%}")
            col3.metric("Credit Spread", f"{result['credit_spread_bps']:.0f} bps")
            col4.metric("Recovery Rate", f"{result['recovery_rate']:.1%}")

            col5, col6, col7, col8 = st.columns(4)
            col5.metric("Implied Assets", f"{result['implied_assets_value']:.1f} M")
            col6.metric("Assets Volatility", f"{result['implied_assets_volatility']:.2%}")
            col7.metric("Leverage", f"{result['leverage']:.2f}")
            col8.metric("Model Equity", f"{result['equity_value_model']:.1f} M")

            st.json(result)

    # ─── Export ──────────────────────────────────────────────
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

    col_exp1, col_exp2 = st.columns(2)

    with col_exp1:
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        export_path = export_portfolio_to_excel(
            tmp_path, clique, opt_result, min_var_result,
            mc_results=mc_results, returns=returns,
            metrics=metrics, params=params,
            rebalance_result=rebal_result,
            stress_results=stress_results,
            buy_hold_result=bh_result,
            bl_result=bl_result,
            hrp_result=hrp_result,
        )
        with open(export_path, "rb") as f:
            st.download_button(
                label="Download Excel Report",
                data=f.read(),
                file_name="portfolio_report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        export_path.unlink(missing_ok=True)

    with col_exp2:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_pdf = Path(tmp.name)
        pdf_path = export_portfolio_to_pdf(
            tmp_pdf, clique, opt_result, min_var_result,
            metrics=metrics, params=params,
            stress_results=stress_results,
            bl_result=bl_result, hrp_result=hrp_result,
            mc_results=mc_results,
        )
        with open(pdf_path, "rb") as f:
            st.download_button(
                label="Download PDF Report",
                data=f.read(),
                file_name="portfolio_report.pdf",
                mime="application/pdf",
            )
        pdf_path.unlink(missing_ok=True)

    # ─── Profile Save/Load ──────────────────────────────────
    st.markdown("---")
    st.subheader("Portfolio Profiles")

    col_p1, col_p2 = st.columns(2)
    with col_p1:
        profile_name = st.text_input("Profile name", value="my_portfolio")
        if st.button("Save Profile"):
            save_profile(
                name=profile_name,
                clique=clique,
                weights={t: float(w) for t, w in zip(clique, opt_result["weights"])},
                metrics=metrics,
                params=params,
            )
            st.success(f"Profile '{profile_name}' saved!")

    with col_p2:
        saved_profiles = list_profiles()
        if saved_profiles:
            selected_profile = st.selectbox("Load profile", saved_profiles)
            if st.button("Load Profile"):
                loaded = load_profile(selected_profile)
                st.json(loaded)
        else:
            st.info("No saved profiles yet.")

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
