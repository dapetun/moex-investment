"""Streamlit Dashboard — MOEX Portfolio Optimizer (RU/EN, Windows 11 design)."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

from moex_portfolio.analytics import (
    cvar_historical,
    equity_curve,
    monte_carlo_simulation,
    rolling_correlation,
    var_historical,
)
from moex_portfolio.backtesting import (
    buy_and_hold_backtest,
    compare_backtests,
    walk_forward_backtest,
)
from moex_portfolio.benchmark import (
    compute_benchmark_metrics,
    get_index_history,
    summary_table,
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
from moex_portfolio.correlation import compute_correlation_matrix
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
from moex_portfolio.drawdown_analysis import analyze_drawdowns, drawdown_summary_table
from moex_portfolio.exporter import export_portfolio_to_excel, export_portfolio_to_pdf
from moex_portfolio.filters import prepare_returns
from moex_portfolio.fundamental import compute_multiplicators, get_fundamental_data
from moex_portfolio.glossary import get_glossary_entry
from moex_portfolio.graph_analysis import build_correlation_graph, find_max_clique
from moex_portfolio.hrp import optimize_hrp
from moex_portfolio.i18n import t
from moex_portfolio.merton import full_merton_analysis
from moex_portfolio.metrics import portfolio_metrics
from moex_portfolio.multi_asset import (
    combine_asset_returns,
    efficient_frontier_multi_asset,
    min_variance_multi_asset,
    optimize_multi_asset,
)
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
from moex_portfolio.risk_budget import (
    compute_risk_budget,
    equal_risk_contribution,
    risk_budget_summary,
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

# ─── Windows 11-inspired CSS ─────────────────────────────────────
WIN11_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Segoe+UI:wght@300;400;600;700&display=swap');

    /* Global */
    .stApp {
        font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
        background-color: #f5f5f5;
    }

    /* Main header */
    .main .block-container {
        padding-top: 1.5rem;
        padding-bottom: 1rem;
        max-width: 1200px;
    }

    /* Card style for metrics */
    [data-testid="stMetric"] {
        background: white;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 12px 16px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
        transition: box-shadow 0.2s ease;
    }
    [data-testid="stMetric"]:hover {
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.8rem !important;
        color: #616161 !important;
        font-weight: 400 !important;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.3rem !important;
        font-weight: 600 !important;
        color: #1a1a1a !important;
    }

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background-color: #fafafa;
        border-left: 1px solid #e8e8e8;
    }
    section[data-testid="stSidebar"] .block-container {
        padding-top: 1rem;
    }

    /* Tabs */
    button[data-baseweb="tab"] {
        font-family: 'Segoe UI', sans-serif;
        font-size: 0.85rem;
        font-weight: 500;
        border-radius: 6px 6px 0 0;
    }

    /* Subheaders */
    .stMarkdown h2, .stMarkdown h3 {
        font-family: 'Segoe UI', sans-serif;
        font-weight: 600;
        color: #1a1a1a;
    }

    /* DataFrames */
    [data-testid="stDataFrame"] {
        border-radius: 8px;
        overflow: hidden;
        border: 1px solid #e0e0e0;
    }

    /* Expanders */
    .streamlit-expanderHeader {
        font-family: 'Segoe UI', sans-serif;
        font-weight: 500;
    }

    /* Info/Warning boxes */
    .stAlert {
        border-radius: 8px;
    }

    /* Divider */
    hr {
        border: none;
        border-top: 1px solid #e0e0e0;
        margin: 1rem 0;
    }

    /* Download buttons */
    .stDownloadButton > button {
        border-radius: 6px;
        font-family: 'Segoe UI', sans-serif;
        font-weight: 500;
        border: 1px solid #d1d1d1;
        background: white;
        transition: all 0.15s ease;
    }
    .stDownloadButton > button:hover {
        background: #f0f0f0;
        border-color: #0078D4;
    }

    /* Primary button */
    .stButton > button[kind="primary"] {
        background-color: #0078D4;
        border-color: #0078D4;
        border-radius: 6px;
        font-family: 'Segoe UI', sans-serif;
        font-weight: 600;
        transition: background-color 0.15s ease;
    }
    .stButton > button[kind="primary"]:hover {
        background-color: #106EBE;
    }

    /* Glossary tooltip via help param */
    .glossary-note {
        font-size: 0.75rem;
        color: #888;
        font-style: italic;
        margin-top: -8px;
        margin-bottom: 8px;
    }
</style>
"""


def _g(term: str, lang: str) -> str:
    """Shorthand for glossary tooltip text (truncated to 1 sentence for metric help)."""
    entry = get_glossary_entry(term, lang)
    if entry is None:
        return ""
    return entry.split(". ")[0] + "."


# ─── Init ─────────────────────────────────────────────────────
st.set_page_config(
    page_title="MOEX Portfolio Optimizer",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(WIN11_CSS, unsafe_allow_html=True)

if "lang" not in st.session_state:
    st.session_state.lang = "en"

lang = st.session_state.lang


# ─── Language selector (top of sidebar) ───────────────────────
with st.sidebar:
    lang_options = {"English": "en", "Русский": "ru"}
    lang_label = st.selectbox(
        t("language", lang=lang),
        options=list(lang_options.keys()),
        index=0 if lang == "en" else 1,
        key="_lang_select",
    )
    lang = lang_options[lang_label]
    st.session_state.lang = lang

st.title(t("app_title", lang=lang))
st.markdown(t("app_subtitle", lang=lang))

# ─── Sidebar: parameters ─────────────────────────────────────
st.sidebar.header(t("sidebar_params", lang=lang))

corr_threshold = st.sidebar.slider(
    t("corr_threshold", lang=lang),
    min_value=0.0, max_value=1.0,
    value=CORR_THRESHOLD, step=0.05,
    help=_g("Correlation", lang),
)

min_turnover_m = st.sidebar.number_input(
    t("min_turnover", lang=lang),
    min_value=1, value=int(MIN_TURNOVER / 1_000_000), step=5,
)
min_turnover = min_turnover_m * 1_000_000

max_weight_pct = st.sidebar.slider(
    t("max_weight", lang=lang),
    min_value=5, value=int(MAX_WEIGHT * 100), max_value=100, step=5,
)
max_weight = max_weight_pct / 100.0

risk_free = st.sidebar.number_input(
    t("risk_free", lang=lang),
    min_value=0.0, value=RISK_FREE_RATE * 100, step=0.5,
) / 100.0

cov_method = st.sidebar.selectbox(
    t("cov_method", lang=lang),
    options=["sample", "ledoit_wolf", "ewma"],
    index=0,
    help=_g("sample", lang),
)

mc_sims = st.sidebar.number_input(
    t("mc_sims", lang=lang),
    min_value=1000, value=10_000, step=1000,
    help=_g("Monte Carlo", lang),
)

rebalance_freq = st.sidebar.number_input(
    t("rebal_freq", lang=lang),
    min_value=5, value=REBALANCE_FREQ_DAYS, step=5,
    help=_g("Rebalancing", lang),
)

transaction_cost_bps = st.sidebar.number_input(
    t("trans_cost", lang=lang),
    min_value=0, value=int(TRANSACTION_COST_BPS), step=1,
)

bl_tau = st.sidebar.slider(t("bl_tau", lang=lang), 0.01, 0.5, 0.05, 0.01)
bl_n_views = st.sidebar.slider(t("bl_views", lang=lang), 1, 10, 5, 1)
hrp_method = st.sidebar.selectbox(t("hrp_method", lang=lang), ["single", "complete", "average"], index=0)

use_cache = st.sidebar.checkbox(t("use_cache", lang=lang), value=True)

# ─── Main pipeline ────────────────────────────────────────────
if st.sidebar.button(t("run_optimization", lang=lang), type="primary"):
    with st.spinner(t("loading_shares", lang=lang)):
        tickers = get_all_shares()
    st.info(t("found_shares", len(tickers), lang=lang))

    with st.spinner(t("loading_prices", lang=lang)):
        raw_data = load_all_data(tickers, use_cache=use_cache)

    with st.spinner(t("filtering", lang=lang)):
        returns, valid_tickers = prepare_returns(raw_data, min_turnover=min_turnover)
    st.info(t("after_filter", len(valid_tickers), len(returns), lang=lang))

    corr = compute_correlation_matrix(returns)
    G = build_correlation_graph(corr, threshold=corr_threshold)
    clique = find_max_clique(G)

    if not clique:
        st.error(t("no_clique", lang=lang))
        st.stop()

    st.success(t("found_clique", len(clique), ", ".join(clique), lang=lang))

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

    P, Q = create_views_from_correlation(clique_returns, corr.loc[clique, clique], top_n=bl_n_views)
    bl_result = optimize_black_litterman(clique_returns, P, Q, tau=bl_tau, max_weight=max_weight)
    hrp_result = optimize_hrp(clique_returns, max_weight=max_weight)

    # ─── Tabs ─────────────────────────────────────────────
    tab_keys = [
        "tab_portfolio", "tab_frontier", "tab_mc", "tab_graphs", "tab_analysis",
        "tab_rebal", "tab_stress", "tab_bl", "tab_hrp", "tab_rolling",
        "tab_dividends", "tab_fundamental", "tab_bonds", "tab_merton",
        "tab_backtest", "tab_risk_budget", "tab_drawdowns", "tab_multi", "tab_benchmark",
    ]
    tab_labels = [t(k, lang=lang) for k in tab_keys]
    tabs = st.tabs(tab_labels)

    # ═══════════════════════════════════════════════════════
    # TAB 1: PORTFOLIO
    # ═══════════════════════════════════════════════════════
    with tabs[0]:
        st.subheader(t("opt_portfolio", lang=lang))
        st.plotly_chart(plot_weights_bar_plotly(clique, opt_result["weights"]), use_container_width=True)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric(t("ann_return", lang=lang), f"{opt_result['return']:.2%}", help=_g("Annual Return", lang))
        c2.metric(t("ann_vol", lang=lang), f"{opt_result['volatility']:.2%}", help=_g("Annual Volatility", lang))
        c3.metric(t("sharpe", lang=lang), f"{opt_result['sharpe']:.3f}", help=_g("Sharpe Ratio", lang))
        c4.metric(t("rf_rate", lang=lang), f"{risk_free:.2%}", help=_g("Risk-free Rate", lang))

        c5, c6, c7, c8 = st.columns(4)
        c5.metric(t("var_95", lang=lang), f"{var_95:.2%}", help=_g("VaR (95%)", lang))
        c6.metric(t("cvar_95", lang=lang), f"{cvar_95:.2%}", help=_g("CVaR (95%)", lang))
        c7.metric(t("sortino", lang=lang), f"{metrics.get('sortino', 0):.3f}", help=_g("Sortino Ratio", lang))
        c8.metric(t("cov_method_label", lang=lang), cov_method.upper())

        st.subheader(t("portfolio_growth", lang=lang))
        st.plotly_chart(plot_equity_curve_plotly(eq), use_container_width=True)

        st.subheader(t("min_var_portfolio", lang=lang))
        st.plotly_chart(plot_weights_bar_plotly(clique, min_var_result["weights"], title=t("min_var_weights", lang=lang)), use_container_width=True)
        mc1, mc2, mc3 = st.columns(3)
        mc1.metric(t("ann_return", lang=lang), f"{min_var_result['return']:.2%}")
        mc2.metric(t("ann_vol", lang=lang), f"{min_var_result['volatility']:.2%}")
        mc3.metric(t("sharpe", lang=lang), f"{min_var_result['sharpe']:.3f}")

    # ═══════════════════════════════════════════════════════
    # TAB 2: EFFICIENT FRONTIER
    # ═══════════════════════════════════════════════════════
    with tabs[1]:
        st.subheader(t("frontier_title", lang=lang))
        st.plotly_chart(plot_efficient_frontier_plotly(ef, opt_result, min_var_result), use_container_width=True)

    # ═══════════════════════════════════════════════════════
    # TAB 3: MONTE CARLO
    # ═══════════════════════════════════════════════════════
    with tabs[2]:
        st.subheader(t("mc_title", lang=lang))
        col_a, col_b, col_c, col_d = st.columns(4)
        col_a.metric(t("mc_mean_return", lang=lang), f"{mc_results['annual_return'].mean():.2%}")
        col_b.metric(t("mc_mean_vol", lang=lang), f"{mc_results['annual_volatility'].mean():.2%}")
        col_c.metric(t("mc_mean_dd", lang=lang), f"{mc_results['max_drawdown'].mean():.2%}")
        col_d.metric(t("mc_sims_label", lang=lang), f"{mc_sims:,}")

        st.plotly_chart(plot_monte_carlo_plotly(mc_results), use_container_width=True)

        st.subheader(t("mc_confidence", lang=lang))
        st.dataframe(plot_mc_percentiles_table(mc_results), use_container_width=True)

    # ═══════════════════════════════════════════════════════
    # TAB 4: GRAPH ANALYSIS
    # ═══════════════════════════════════════════════════════
    with tabs[3]:
        st.subheader(t("graph_title", lang=lang))
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

    # ═══════════════════════════════════════════════════════
    # TAB 5: DETAILED ANALYSIS
    # ═══════════════════════════════════════════════════════
    with tabs[4]:
        st.subheader(t("analysis_title", lang=lang))
        fig_returns = plot_total_returns(returns, clique)
        st.pyplot(fig_returns)
        plt.close(fig_returns)

        st.subheader(t("returns_stats", lang=lang))
        stats_df = pd.DataFrame({
            "Mean Daily Return": clique_returns.mean(),
            "Annual Return": clique_returns.mean() * 252,
            "Daily Volatility": clique_returns.std(),
            "Annual Volatility": clique_returns.std() * (252 ** 0.5),
            "Min Daily Return": clique_returns.min(),
            "Max Daily Return": clique_returns.max(),
        }).round(6)
        st.dataframe(stats_df, use_container_width=True)

    # ═══════════════════════════════════════════════════════
    # TAB 6: REBALANCING
    # ═══════════════════════════════════════════════════════
    with tabs[5]:
        st.subheader(t("rebal_title", lang=lang))

        rebal_config = RebalanceConfig(
            target_weights={t_: opt_result["weights"][i] for i, t_ in enumerate(clique)},
            rebalance_freq_days=rebalance_freq,
            transaction_cost_bps=transaction_cost_bps,
            min_drift=MIN_DRIFT,
        )

        rebal_result = simulate_rebalancing(clique_returns, rebal_config, cov_method=cov_method)
        bh_result = simulate_buy_and_hold(clique_returns, rebal_config.target_weights)

        col1, col2, col3, col4 = st.columns(4)
        col1.metric(t("rebal_return", lang=lang), f"{rebal_result.annual_return:.2%}")
        col2.metric(t("rebal_sharpe", lang=lang), f"{rebal_result.sharpe:.3f}", help=_g("Sharpe Ratio", lang))
        col3.metric(t("rebal_cost", lang=lang), f"{rebal_result.total_cost:,.0f} RUB")
        col4.metric(t("rebal_count", lang=lang), str(rebal_result.n_rebalances))

        col5, col6, col7, col8 = st.columns(4)
        col5.metric(t("bh_return", lang=lang), f"{bh_result.annual_return:.2%}")
        col6.metric(t("bh_sharpe", lang=lang), f"{bh_result.sharpe:.3f}")
        col7.metric(t("bh_maxdd", lang=lang), f"{bh_result.max_drawdown:.2%}", help=_g("Max Drawdown", lang))
        col8.metric(t("rebal_maxdd", lang=lang), f"{rebal_result.max_drawdown:.2%}", help=_g("Max Drawdown", lang))

        rebal_df = pd.DataFrame({
            "Date": rebal_result.dates,
            "Rebalancing": rebal_result.portfolio_values,
            "Buy & Hold": bh_result.portfolio_values[:len(rebal_result.portfolio_values)],
        }).set_index("Date")
        st.line_chart(rebal_df)

        st.subheader(t("strategy_comp", lang=lang))
        comparison = compare_strategies(clique_returns, rebal_config, cov_method=cov_method)
        st.dataframe(comparison, use_container_width=True)

    # ═══════════════════════════════════════════════════════
    # TAB 7: STRESS TEST
    # ═══════════════════════════════════════════════════════
    with tabs[6]:
        st.subheader(t("stress_title", lang=lang))

        stress_results = run_all_scenarios(clique_returns, opt_result["weights"])
        stress_df = stress_results_to_dataframe(stress_results)
        st.dataframe(stress_df, use_container_width=True)

        st.markdown("---")
        st.subheader(t("stress_details", lang=lang))
        for r in stress_results:
            with st.expander(f"{r.scenario_name} ({r.start_date} — {r.end_date})"):
                st.write(f"**{r.description}**")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric(t("stress_return", lang=lang), f"{r.portfolio_return:.2%}")
                c2.metric(t("dd_max", lang=lang), f"{r.portfolio_max_drawdown:.2%}")
                c3.metric(t("stress_worst", lang=lang), f"{r.worst_day:.2%} on {r.worst_day_date}")
                c4.metric(t("stress_recovery", lang=lang), f"{r.recovery_days} days" if r.recovery_days else ("Не восстановлен" if lang == "ru" else "Not recovered"))

    # ═══════════════════════════════════════════════════════
    # TAB 8: BLACK-LITTERMAN
    # ═══════════════════════════════════════════════════════
    with tabs[7]:
        st.subheader(t("bl_title", lang=lang))
        st.markdown(t("bl_desc", lang=lang))

        col1, col2, col3, col4 = st.columns(4)
        col1.metric(t("ann_return", lang=lang), f"{bl_result['return']:.2%}")
        col2.metric(t("ann_vol", lang=lang), f"{bl_result['volatility']:.2%}")
        col3.metric(t("sharpe", lang=lang), f"{bl_result['sharpe']:.3f}", help=_g("Sharpe Ratio", lang))
        col4.metric(t("bl_views_count", lang=lang), bl_n_views)

        st.plotly_chart(plot_weights_bar_plotly(clique, bl_result["weights"], title="Black-Litterman"), use_container_width=True)

        st.subheader(t("bl_views_matrix", lang=lang))
        p_df = pd.DataFrame(P, columns=clique, index=[f"View {i+1}" for i in range(P.shape[0])])
        st.dataframe(p_df, use_container_width=True)

        st.subheader(t("bl_view_returns", lang=lang))
        q_df = pd.DataFrame({"View": [f"View {i+1}" for i in range(len(Q))], "Expected Return (daily)": Q})
        st.dataframe(q_df, use_container_width=True)

        st.subheader(t("bl_comparison", lang=lang))
        comp_df = pd.DataFrame({
            "Metric": ["Return", "Volatility", "Sharpe"],
            "Markowitz (Max Sharpe)": [f"{opt_result['return']:.2%}", f"{opt_result['volatility']:.2%}", f"{opt_result['sharpe']:.3f}"],
            "Black-Litterman": [f"{bl_result['return']:.2%}", f"{bl_result['volatility']:.2%}", f"{bl_result['sharpe']:.3f}"],
        })
        st.dataframe(comp_df, use_container_width=True)

    # ═══════════════════════════════════════════════════════
    # TAB 9: HRP
    # ═══════════════════════════════════════════════════════
    with tabs[8]:
        st.subheader(t("hrp_title", lang=lang))
        st.markdown(t("hrp_desc", lang=lang))

        col1, col2, col3, col4 = st.columns(4)
        col1.metric(t("ann_return", lang=lang), f"{hrp_result['return']:.2%}")
        col2.metric(t("ann_vol", lang=lang), f"{hrp_result['volatility']:.2%}")
        col3.metric(t("sharpe", lang=lang), f"{hrp_result['sharpe']:.3f}", help=_g("Sharpe Ratio", lang))
        col4.metric(t("hrp_method_label", lang=lang), hrp_method)

        st.plotly_chart(plot_weights_bar_plotly(clique, hrp_result["weights"], title="HRP"), use_container_width=True)

        st.subheader(t("hrp_weight_dist", lang=lang))
        weights_df = pd.DataFrame({
            "Asset": clique,
            "HRP Weight": hrp_result["weights"],
            "Markowitz Weight": opt_result["weights"],
            "BL Weight": bl_result["weights"],
        }).sort_values("HRP Weight", ascending=False)
        st.dataframe(weights_df, use_container_width=True)

        st.subheader(t("hrp_strategy_comp", lang=lang))
        strat_comp = pd.DataFrame({
            "Strategy": ["Markowitz (Max Sharpe)", "Min Variance", "Black-Litterman", "HRP"],
            "Return": [f"{opt_result['return']:.2%}", f"{min_var_result['return']:.2%}", f"{bl_result['return']:.2%}", f"{hrp_result['return']:.2%}"],
            "Volatility": [f"{opt_result['volatility']:.2%}", f"{min_var_result['volatility']:.2%}", f"{bl_result['volatility']:.2%}", f"{hrp_result['volatility']:.2%}"],
            "Sharpe": [f"{opt_result['sharpe']:.3f}", f"{min_var_result['sharpe']:.3f}", f"{bl_result['sharpe']:.3f}", f"{hrp_result['sharpe']:.3f}"],
        })
        st.dataframe(strat_comp, use_container_width=True)

    # ═══════════════════════════════════════════════════════
    # TAB 10: ROLLING CORRELATION
    # ═══════════════════════════════════════════════════════
    with tabs[9]:
        st.subheader(t("rolling_title", lang=lang))
        roll_window = st.slider(t("rolling_window", lang=lang), 20, 120, 60, 5, key="roll_window")
        roll_corr = rolling_correlation(returns[clique], window=roll_window)

        st.info(f"{len(roll_corr)} pairs, window={roll_window} days")
        roll_df = pd.DataFrame(roll_corr)
        st.line_chart(roll_df, height=400)

        st.subheader(t("rolling_beta", lang=lang))
        from moex_portfolio.analytics import rolling_beta as rb
        roll_beta_df = rb(returns[clique], market_returns, window=roll_window)
        st.line_chart(roll_beta_df, height=400)

    # ═══════════════════════════════════════════════════════
    # TAB 11: DIVIDENDS
    # ═══════════════════════════════════════════════════════
    with tabs[10]:
        st.subheader(t("div_title", lang=lang))
        st.markdown(t("div_desc", lang=lang))

        with st.spinner(t("loading_prices", lang=lang)):
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
            st.dataframe(dy_display.style.format({"Dividend Yield": "{:.2%}"}), use_container_width=True)
        else:
            st.warning("No real dividend data found for clique stocks. Using market-wide estimates.")
            price_cols_all = [c for c in raw_data.columns if not c.endswith("_VALUE")]
            all_prices_full = raw_data[price_cols_all]
            dy = get_dividend_yields(list(all_prices_full.columns), all_prices_full)
            dy = dy[dy.index.isin(clique)]

        col1, col2 = st.columns(2)
        with col1:
            n_dogs = st.slider(t("div_dogs_n", lang=lang), 3, 20, 10, key="n_dogs")
        with col2:
            hd_percentile = st.slider(t("div_hd_pct", lang=lang), 50, 95, 75, key="hd_pct")

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

    # ═══════════════════════════════════════════════════════
    # TAB 12: FUNDAMENTAL
    # ═══════════════════════════════════════════════════════
    with tabs[11]:
        st.subheader(t("fund_title", lang=lang))
        st.markdown(t("fund_desc", lang=lang))

        mult = compute_multiplicators(returns)

        with st.spinner(t("loading_prices", lang=lang)):
            fund_data = get_fundamental_data(clique)

        if not fund_data.empty:
            st.info(f"Loaded fundamental data for {len(fund_data)} stocks")
            merged = mult.merge(fund_data.set_index("ticker"), left_index=True, right_index=True, how="left")
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

        st.subheader(t("fund_composite", lang=lang))
        top_n_fund = st.slider(t("fund_top_n", lang=lang), 5, len(merged), min(10, len(merged)), key="top_n_fund")
        top_stocks = merged.head(top_n_fund)
        st.bar_chart(top_stocks["composite_score"])

    # ═══════════════════════════════════════════════════════
    # TAB 13: BONDS
    # ═══════════════════════════════════════════════════════
    with tabs[12]:
        st.subheader(t("bonds_title", lang=lang))
        st.markdown(t("bonds_desc", lang=lang))

        try:
            ofz_df = get_ofz_list()
            if ofz_df is not None and len(ofz_df) > 0:
                st.info(f"Loaded {len(ofz_df)} OFZ bonds from MOEX")

                ofz_display = ofz_df[["SECID", "NAME", "YIELDTOOFFER", "MATDATE"]].copy() if "NAME" in ofz_df.columns else ofz_df[["SECID", "YIELDTOOFFER", "MATDATE"]].copy()
                st.dataframe(ofz_display, use_container_width=True)

                curve = build_yield_curve(ofz_df)
                if len(curve) > 0:
                    st.subheader(t("bonds_yield_curve", lang=lang))
                    st.line_chart(curve.set_index("maturity_years")["yield_pct"])

                    interp = interpolate_yield_curve(curve)
                    if len(interp) > 0:
                        st.subheader(t("bonds_interp", lang=lang))
                        st.line_chart(interp.set_index("maturity_years")["yield_pct"])

                    ts = term_structure_analysis(curve)
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric(t("bonds_shape", lang=lang), ts.get("shape", "N/A"))
                    c2.metric(t("bonds_short", lang=lang), f"{ts.get('short_yield', 0):.2f}%", help=_g("Yield Curve", lang))
                    c3.metric(t("bonds_long", lang=lang), f"{ts.get('long_yield', 0):.2f}%")
                    c4.metric(t("bonds_spread", lang=lang), f"{ts.get('term_spread_pct', 0):.2f}%")
                else:
                    st.warning("Could not build yield curve from OFZ data.")
            else:
                st.warning("No OFZ data available from MOEX ISS.")
        except Exception as e:
            st.error(f"Error loading bond data: {e}")

    # ═══════════════════════════════════════════════════════
    # TAB 14: MERTON
    # ═══════════════════════════════════════════════════════
    with tabs[13]:
        st.subheader(t("merton_title", lang=lang))
        st.markdown(t("merton_desc", lang=lang))

        col1, col2 = st.columns(2)
        with col1:
            equity_val = st.number_input(t("merton_eq", lang=lang), min_value=10.0, value=300.0, step=10.0, key="merton_eq")
            debt_val = st.number_input(t("merton_debt", lang=lang), min_value=10.0, value=700.0, step=10.0, key="merton_debt")
        with col2:
            vol_eq = st.number_input(t("merton_vol", lang=lang), min_value=1.0, value=40.0, step=5.0, key="merton_vol") / 100.0
            rf_rate = st.number_input(t("merton_rf", lang=lang), min_value=0.0, value=12.0, step=0.5, key="merton_rf") / 100.0
            ttm = st.number_input(t("merton_ttm", lang=lang), min_value=0.25, value=2.0, step=0.25, key="merton_ttm")

        if st.button(t("merton_run", lang=lang), key="run_merton"):
            result = full_merton_analysis(equity_val, debt_val, vol_eq, rf_rate, ttm)

            c1, c2, c3, c4 = st.columns(4)
            c1.metric(t("merton_dd", lang=lang), f"{result['distance_to-default']:.2f}", help=_g("Distance to Default", lang))
            c2.metric(t("merton_pd", lang=lang), f"{result['probability_of_default']:.2%}", help=_g("Probability of Default", lang))
            c3.metric(t("merton_spread", lang=lang), f"{result['credit_spread_bps']:.0f} bps", help=_g("Credit Spread", lang))
            c4.metric(t("merton_recovery", lang=lang), f"{result['recovery_rate']:.1%}")

            c5, c6, c7, c8 = st.columns(4)
            c5.metric(t("merton_implied", lang=lang), f"{result['implied_assets_value']:.1f} M")
            c6.metric(t("merton_vol_a", lang=lang), f"{result['implied_assets_volatility']:.2%}")
            c7.metric(t("merton_leverage", lang=lang), f"{result['leverage']:.2f}")
            c8.metric(t("merton_model_eq", lang=lang), f"{result['equity_value_model']:.1f} M")

            st.json(result)

    # ═══════════════════════════════════════════════════════
    # TAB 15: BACKTESTING
    # ═══════════════════════════════════════════════════════
    with tabs[14]:
        st.subheader(t("bt_title", lang=lang))
        st.markdown(t("bt_desc", lang=lang))

        col1, col2 = st.columns(2)
        with col1:
            lookback = st.number_input(t("bt_lookback", lang=lang), 63, 504, 252, 21, key="bt_lookback")
        with col2:
            bt_rebal_freq = st.number_input(t("bt_rebal_freq", lang=lang), 5, 63, 21, 5, key="bt_rebal")

        bt_opt = st.selectbox(t("bt_optimizer", lang=lang), ["max_sharpe", "min_variance"], key="bt_opt")

        if st.button(t("bt_run", lang=lang), key="run_bt"):
            with st.spinner(t("bt_run", lang=lang) + "..."):
                bt_result = walk_forward_backtest(
                    clique_returns, lookback_days=lookback,
                    rebalance_freq_days=bt_rebal_freq, optimizer=bt_opt,
                    max_weight=max_weight, risk_free_rate=risk_free,
                )
                bh = buy_and_hold_backtest(clique_returns, opt_result["weights"])

            col1, col2, col3, col4 = st.columns(4)
            col1.metric(t("bt_total_ret", lang=lang), f"{bt_result.total_return:.2%}")
            col2.metric(t("bt_ann_ret", lang=lang), f"{bt_result.annual_return:.2%}")
            col3.metric(t("bt_sharpe", lang=lang), f"{bt_result.sharpe:.3f}")
            col4.metric(t("bt_maxdd", lang=lang), f"{bt_result.max_drawdown_val:.2%}", help=_g("Max Drawdown", lang))

            col5, col6, col7, col8 = st.columns(4)
            col5.metric(t("bt_rebalances", lang=lang), str(bt_result.n_rebalances))
            col6.metric(t("bt_turnover", lang=lang), f"{bt_result.turnover_per_rebal:.3f}")
            col7.metric(t("bt_total_ret", lang=lang), f"{bh.total_return:.2%}")
            col8.metric(t("bt_sharpe", lang=lang), f"{bh.sharpe:.3f}")

            st.subheader(t("bt_growth", lang=lang))
            bt_chart = pd.DataFrame({
                "Walk-Forward": bt_result.portfolio_values[:len(bh.portfolio_values)],
                "Buy & Hold": bh.portfolio_values[:len(bt_result.portfolio_values)],
            })
            st.line_chart(bt_chart)

            comp = compare_backtests([bt_result, bh])
            st.subheader(t("bt_comparison", lang=lang))
            st.dataframe(comp.style.format({
                "Total Return": "{:.2%}", "Annual Return": "{:.2%}",
                "Annual Volatility": "{:.2%}", "Sharpe": "{:.3f}",
                "Max Drawdown": "{:.2%}", "Avg Turnover": "{:.4f}",
            }), use_container_width=True)

    # ═══════════════════════════════════════════════════════
    # TAB 16: RISK BUDGET
    # ═══════════════════════════════════════════════════════
    with tabs[15]:
        st.subheader(t("rb_title", lang=lang))
        st.markdown(t("rb_desc", lang=lang))

        rb_result = compute_risk_budget(opt_result["weights"], cov)
        rb_df = risk_budget_summary(rb_result)

        col1, col2, col3 = st.columns(3)
        col1.metric(t("rb_port_vol", lang=lang), f"{rb_result.portfolio_volatility:.2%}", help=_g("Annual Volatility", lang))
        col2.metric(t("rb_max_contrib", lang=lang), rb_df.iloc[0]["Ticker"])
        col3.metric(t("rb_max_pct", lang=lang), f"{rb_df.iloc[0]['Risk Contribution %']:.1%}")

        st.plotly_chart(plot_weights_bar_plotly(
            rb_df["Ticker"].tolist(), rb_df["Risk Contribution %"].values,
            title="Risk Contribution",
        ), use_container_width=True)

        st.dataframe(rb_df.style.format({
            "Weight": "{:.2%}", "Marginal Risk": "{:.4f}",
            "Component Risk": "{:.6f}", "Risk Contribution %": "{:.1%}",
            "Risk/Return Ratio": "{:.4f}",
        }), use_container_width=True)

        st.subheader(t("rb_erc_title", lang=lang))
        erc_weights = equal_risk_contribution(cov)
        erc_result = compute_risk_budget(erc_weights, cov)
        erc_df = risk_budget_summary(erc_result)

        st.plotly_chart(plot_weights_bar_plotly(clique, erc_weights, title="ERC Weights"), use_container_width=True)
        st.dataframe(erc_df.style.format({"Weight": "{:.2%}", "Risk Contribution %": "{:.1%}"}), use_container_width=True)

    # ═══════════════════════════════════════════════════════
    # TAB 17: DRAWDOWNS
    # ═══════════════════════════════════════════════════════
    with tabs[16]:
        st.subheader(t("dd_title", lang=lang))
        st.markdown(t("dd_desc", lang=lang))

        eq_series = equity_curve(clique_returns, opt_result["weights"])
        dd_result = analyze_drawdowns(eq_series)

        col1, col2, col3, col4 = st.columns(4)
        col1.metric(t("dd_max", lang=lang), f"{dd_result.max_drawdown:.2%}", help=_g("Max Drawdown", lang))
        col2.metric(t("dd_avg", lang=lang), f"{dd_result.avg_drawdown:.2%}")
        col3.metric(t("dd_recovery", lang=lang), f"{dd_result.avg_recovery:.0f}")
        col4.metric(t("dd_periods", lang=lang), str(dd_result.n_drawdowns))

        if dd_result.worst_drawdown:
            st.subheader(t("dd_worst", lang=lang))
            wd = dd_result.worst_drawdown
            c1, c2, c3, c4 = st.columns(4)
            c1.metric(t("dd_peak", lang=lang), wd.peak_date)
            c2.metric(t("dd_trough", lang=lang), wd.trough_date)
            c3.metric(t("dd_max", lang=lang), f"{wd.drawdown_pct:.2%}")
            c4.metric(t("dd_recovery_date", lang=lang), wd.recovery_date or ("Не восстановлен" if lang == "ru" else "Not recovered"))

        st.subheader(t("dd_underwater", lang=lang))
        st.line_chart(dd_result.underwater_series)

        if dd_result.drawdown_periods:
            st.subheader(t("dd_top_periods", lang=lang))
            dd_table = drawdown_summary_table(dd_result, top_n=10)
            st.dataframe(dd_table.style.format({"Drawdown": "{:.2%}"}), use_container_width=True)

    # ═══════════════════════════════════════════════════════
    # TAB 18: MULTI-ASSET
    # ═══════════════════════════════════════════════════════
    with tabs[17]:
        st.subheader(t("ma_title", lang=lang))
        st.markdown(t("ma_desc", lang=lang))

        st.markdown("---")
        st.markdown(f"#### {t('ma_bond_alloc', lang=lang)}")

        use_ofz_yields = st.checkbox(t("ma_ofz_use", lang=lang), value=True, key="use_ofz")

        bond_yields_input = {}
        if use_ofz_yields:
            try:
                ofz_df = get_ofz_list()
                if ofz_df is not None and len(ofz_df) > 0:
                    ofz_tickers = ofz_df["SECID"].tolist()[:5] if "SECID" in ofz_df.columns else []
                    st.info(f"Loaded {len(ofz_df)} OFZ bonds. Using top {len(ofz_tickers)} by yield.")

                    for ticker in ofz_tickers:
                        ytm_col = "YIELDTOOFFER" if "YIELDTOOFFER" in ofz_df.columns else None
                        if ytm_col:
                            val = pd.to_numeric(ofz_df.loc[ofz_df["SECID"] == ticker, ytm_col].iloc[0], errors="coerce")
                            if pd.notna(val) and val > 0:
                                bond_yields_input[ticker] = val / 100.0

                    if bond_yields_input:
                        yields_df = pd.DataFrame({
                            "OFZ Ticker": bond_yields_input.keys(),
                            "YTM (%)": [f"{v*100:.2f}" for v in bond_yields_input.values()],
                        })
                        st.dataframe(yields_df, use_container_width=True)
                else:
                    st.warning("Could not load OFZ data.")
            except Exception as exc:
                st.warning(f"OFZ load error: {exc}")

        if not bond_yields_input:
            st.markdown("Enter bond yields manually:")
            n_bonds = st.number_input("Number of bonds", 0, 10, 2, key="n_bonds_manual")
            for i in range(n_bonds):
                col1, col2 = st.columns(2)
                with col1:
                    bond_name = st.text_input(f"Bond {i+1} name", value=f"BOND_{i+1}", key=f"bond_name_{i}")
                with col2:
                    ytm_val = st.number_input(f"YTM for {bond_name} (%)", 0.0, 30.0, 12.0, 0.5, key=f"bond_ytm_{i}")
                bond_yields_input[bond_name] = ytm_val / 100.0

        st.markdown("---")
        st.markdown(f"#### {t('ma_constraints', lang=lang)}")
        col1, col2 = st.columns(2)
        with col1:
            max_stock_pct = st.slider(t("ma_max_stock", lang=lang), 10, 100, 80, 5, key="max_stock")
        with col2:
            min_bond_pct = st.slider(t("ma_min_bond", lang=lang), 0, 50, 10, 5, key="min_bond")

        asset_constraints = {
            "stock": {"max": max_stock_pct / 100.0},
            "bond": {"min": min_bond_pct / 100.0},
        }

        if st.button(t("ma_run", lang=lang), key="run_multi"):
            bond_yields_series = pd.Series(bond_yields_input) if bond_yields_input else None
            combined = combine_asset_returns(clique_returns, bond_yields=bond_yields_series)

            ma_sharpe = optimize_multi_asset(combined, risk_free_rate=risk_free, max_weight=max_weight, asset_constraints=asset_constraints)
            ma_minvar = min_variance_multi_asset(combined, max_weight=max_weight, asset_constraints=asset_constraints)
            ma_ef = efficient_frontier_multi_asset(combined, n_points=30, max_weight=max_weight, asset_constraints=asset_constraints)

            st.success(f"Multi-asset portfolio: {combined.shape[1]} assets ({clique_returns.shape[1]} stocks + {combined.shape[1] - clique_returns.shape[1]} bonds)")

            st.markdown("#### Max Sharpe Portfolio")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric(t("ann_return", lang=lang), f"{ma_sharpe['return']:.2%}")
            c2.metric(t("ann_vol", lang=lang), f"{ma_sharpe['volatility']:.2%}")
            c3.metric(t("sharpe", lang=lang), f"{ma_sharpe['sharpe']:.3f}")
            c4.metric(t("ma_stock_bond", lang=lang), f"{ma_sharpe['stock_weight']:.0%} / {ma_sharpe['bond_weight']:.0%}")

            tickers_ma = ma_sharpe["tickers"]
            weights_ma = ma_sharpe["weights"]
            display_labels = [f"{tk} ({'S' if not tk.startswith('BOND_') else 'B'})" for tk in tickers_ma]
            st.plotly_chart(plot_weights_bar_plotly(display_labels, weights_ma, title="Multi-Asset Weights"), use_container_width=True)

            st.markdown("#### Min Variance Portfolio")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric(t("ann_return", lang=lang), f"{ma_minvar['return']:.2%}")
            c2.metric(t("ann_vol", lang=lang), f"{ma_minvar['volatility']:.2%}")
            c3.metric(t("sharpe", lang=lang), f"{ma_minvar['sharpe']:.3f}")
            c4.metric(t("ma_stock_bond", lang=lang), f"{ma_minvar['stock_weight']:.0%} / {ma_minvar['bond_weight']:.0%}")

            st.plotly_chart(plot_weights_bar_plotly(display_labels, ma_minvar["weights"], title="Min Variance Weights"), use_container_width=True)

            if len(ma_ef) > 0:
                st.markdown("#### Efficient Frontier (Multi-Asset)")
                ef_display = pd.DataFrame({
                    "Return": ma_ef["return"],
                    "Volatility": ma_ef["volatility"],
                    "Sharpe": ma_ef["sharpe"],
                    "Stock%": ma_ef["stock_weight"],
                    "Bond%": ma_ef["bond_weight"],
                })
                st.line_chart(ef_display.set_index("Volatility")["Return"])

    # ═══════════════════════════════════════════════════════
    # TAB 19: BENCHMARK
    # ═══════════════════════════════════════════════════════
    with tabs[18]:
        st.subheader(t("bm_title", lang=lang))
        st.markdown(t("bm_desc", lang=lang))

        benchmark_ticker = st.selectbox(t("bm_index", lang=lang), ["IMOEX", "RGBI"], key="bench_idx")

        with st.spinner(f"Loading {benchmark_ticker} index history..."):
            bench_returns = get_index_history(benchmark_ticker)

        if len(bench_returns) > 0:
            st.info(f"Loaded {len(bench_returns)} days of {benchmark_ticker} data")

            port_eq = equity_curve(clique_returns, opt_result["weights"])
            common_idx = port_eq.index.intersection(bench_returns.index)

            if len(common_idx) < 50:
                st.warning(f"Only {len(common_idx)} overlapping days. Need at least 50.")
            else:
                port_ret_series = port_eq.loc[common_idx].pct_change().dropna()
                bench_ret_series = bench_returns.loc[common_idx].loc[port_ret_series.index]

                bm_metrics = compute_benchmark_metrics(port_ret_series, bench_ret_series, risk_free=risk_free)
                bm_summary = summary_table(port_ret_series, bench_ret_series, risk_free)

                c1, c2, c3, c4 = st.columns(4)
                c1.metric(t("bm_port_ret", lang=lang), f"{bm_metrics['portfolio_return']:.2%}")
                c2.metric(t("bm_index_ret", lang=lang), f"{bm_metrics['benchmark_return']:.2%}")
                c3.metric(t("bm_excess", lang=lang), f"{bm_metrics['excess_return']:.2%}")
                c4.metric(t("bm_te", lang=lang), f"{bm_metrics['tracking_error']:.2%}", help=_g("Tracking Error", lang))

                c5, c6, c7, c8 = st.columns(4)
                c5.metric(t("bm_ir", lang=lang), f"{bm_metrics['information_ratio']:.3f}", help=_g("Information Ratio", lang))
                c6.metric(t("bm_r2", lang=lang), f"{bm_metrics['r_squared']:.4f}", help=_g("R²", lang))
                c7.metric(t("bm_beta", lang=lang), f"{bm_metrics['beta']:.3f}", help=_g("Beta", lang))
                c8.metric(t("bm_alpha", lang=lang), f"{bm_metrics['alpha']:.2%}", help=_g("Jensen's Alpha", lang))

                st.markdown(f"#### {t('bm_full_table', lang=lang)}")
                st.dataframe(bm_summary, use_container_width=True)

                st.markdown(f"#### {t('bm_cumulative', lang=lang)}")
                cum_port = pd.Series(np.cumprod(1 + port_ret_series.values), index=port_ret_series.index, name="Portfolio")
                cum_bench = pd.Series(np.cumprod(1 + bench_ret_series.values), index=bench_ret_series.index, name=benchmark_ticker)
                cum_df = pd.concat([cum_port, cum_bench], axis=1)
                st.line_chart(cum_df)

                st.markdown(f"#### {t('bm_active', lang=lang)}")
                if "active_returns" in bm_metrics:
                    st.line_chart(bm_metrics["active_returns"])

                if "rolling_ir" in bm_metrics and len(bm_metrics["rolling_ir"]) > 0:
                    st.markdown(f"#### {t('bm_rolling_ir', lang=lang)}")
                    st.line_chart(bm_metrics["rolling_ir"])
        else:
            st.warning(f"Could not load {benchmark_ticker} index data from MOEX.")

    # ─── Export ──────────────────────────────────────────
    st.markdown("---")
    st.subheader(t("export_results", lang=lang))

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
                label=t("export_excel", lang=lang),
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
                label=t("export_pdf", lang=lang),
                data=f.read(),
                file_name="portfolio_report.pdf",
                mime="application/pdf",
            )
        pdf_path.unlink(missing_ok=True)

    # ─── Profile Save/Load ──────────────────────────────
    st.markdown("---")
    st.subheader(t("profiles", lang=lang))

    col_p1, col_p2 = st.columns(2)
    with col_p1:
        profile_name = st.text_input(t("profile_name", lang=lang), value="my_portfolio")
        if st.button(t("profile_save", lang=lang)):
            save_profile(
                name=profile_name,
                clique=clique,
                weights={tk: float(w) for tk, w in zip(clique, opt_result["weights"])},
                metrics=metrics,
                params=params,
            )
            st.success(t("profile_saved", profile_name, lang=lang))

    with col_p2:
        saved_profiles = list_profiles()
        if saved_profiles:
            selected_profile = st.selectbox(t("profile_load", lang=lang), saved_profiles)
            if st.button(t("profile_load_btn", lang=lang)):
                loaded = load_profile(selected_profile)
                st.json(loaded)
        else:
            st.info(t("profile_none", lang=lang))

else:
    st.info(t("configure_hint", lang=lang))
    st.markdown("---")
    st.subheader(t("how_title", lang=lang))
    for step_key in ["how_step1", "how_step2", "how_step3", "how_step4", "how_step5", "how_step6", "how_step7"]:
        st.markdown(t(step_key, lang=lang))
