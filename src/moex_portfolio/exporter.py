"""Экспорт результатов в Excel и PDF."""

import logging
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def export_portfolio_to_excel(
    filepath: str | Path,
    clique: list[str],
    opt_result: dict,
    min_var_result: dict,
    mc_results: pd.DataFrame | None = None,
    returns: pd.DataFrame | None = None,
    metrics: dict | None = None,
    params: dict | None = None,
    rebalance_result=None,
    stress_results: list | None = None,
    buy_hold_result=None,
    bl_result: dict | None = None,
    hrp_result: dict | None = None,
) -> Path:
    """Экспорт результатов оптимизации в Excel.

    Args:
        filepath: Путь к файлу.
        clique: Список тикеров клики.
        opt_result: Результат max_sharpe_portfolio.
        min_var_result: Результат min_variance_portfolio.
        mc_results: Результаты Monte Carlo (опционально).
        returns: DataFrame с доходностями (опционально).
        metrics: Словарь с метриками (опционально).
        params: Словарь с параметрами (опционально).

    Returns:
        Path к созданному файлу.
    """
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
        # Sheet 1: Max Sharpe Portfolio
        ms_df = pd.DataFrame({
            "Asset": clique,
            "Weight": opt_result["weights"],
            "Weight (%)": [f"{w:.2%}" for w in opt_result["weights"]],
        }).sort_values("Weight", ascending=False)
        ms_df.to_excel(writer, sheet_name="Max Sharpe Portfolio", index=False)

        # Sheet 2: Min Variance Portfolio
        mv_df = pd.DataFrame({
            "Asset": clique,
            "Weight": min_var_result["weights"],
            "Weight (%)": [f"{w:.2%}" for w in min_var_result["weights"]],
        }).sort_values("Weight", ascending=False)
        mv_df.to_excel(writer, sheet_name="Min Variance Portfolio", index=False)

        # Sheet 3: Summary Metrics
        summary = {
            "Metric": [
                "Annual Return",
                "Annual Volatility",
                "Sharpe Ratio",
                "Risk-free Rate",
            ],
            "Max Sharpe": [
                f"{opt_result['return']:.2%}",
                f"{opt_result['volatility']:.2%}",
                f"{opt_result['sharpe']:.3f}",
                f"{params.get('risk_free_rate', 0.0):.2%}" if params else "0.00%",
            ],
            "Min Variance": [
                f"{min_var_result['return']:.2%}",
                f"{min_var_result['volatility']:.2%}",
                f"{min_var_result['sharpe']:.3f}",
                "",
            ],
        }
        if metrics:
            summary["Metric"].extend(["Sortino Ratio", "Max Drawdown", "Calmar Ratio"])
            summary["Max Sharpe"].extend([
                f"{metrics.get('sortino', 0):.3f}" if metrics.get('sortino') is not None else "N/A",
                f"{metrics.get('max_drawdown', 0):.2%}" if metrics.get('max_drawdown') is not None else "N/A",
                f"{metrics.get('calmar', 0):.3f}" if metrics.get('calmar') is not None else "N/A",
            ])
            summary["Min Variance"].extend(["", "", ""])

        pd.DataFrame(summary).to_excel(writer, sheet_name="Summary", index=False)

        # Sheet 4: Monte Carlo Percentiles
        if mc_results is not None:
            percentiles = [5, 10, 25, 50, 75, 90, 95]
            mc_pct = pd.DataFrame({
                "Percentile": [f"{p}%" for p in percentiles],
                "Annual Return": [f"{np.percentile(mc_results['annual_return'], p):.2%}" for p in percentiles],
                "Annual Volatility": [f"{np.percentile(mc_results['annual_volatility'], p):.2%}" for p in percentiles],
                "Max Drawdown": [f"{np.percentile(mc_results['max_drawdown'], p):.2%}" for p in percentiles],
                "Sharpe": [f"{np.percentile(mc_results['sharpe'], p):.3f}" for p in percentiles],
            })
            mc_pct.to_excel(writer, sheet_name="Monte Carlo", index=False)

        # Sheet 5: Parameters
        if params:
            params_df = pd.DataFrame({
                "Parameter": list(params.keys()),
                "Value": [str(v) for v in params.values()],
            })
            params_df.to_excel(writer, sheet_name="Parameters", index=False)

        # Sheet 6: Historical Returns
        if returns is not None:
            returns[clique].to_excel(writer, sheet_name="Returns")

        # Sheet 7: Rebalancing Results
        if rebalance_result is not None:
            rebal_df = pd.DataFrame({
                "Date": rebalance_result.dates,
                "Portfolio Value": rebalance_result.portfolio_values,
            })

            if buy_hold_result is not None:
                bh_df = pd.DataFrame({
                    "Date": buy_hold_result.dates,
                    "Buy & Hold Value": buy_hold_result.portfolio_values,
                })
                merged = rebal_df.merge(bh_df, on="Date", how="outer")
                merged.to_excel(writer, sheet_name="Rebalancing", index=False)
            else:
                rebal_df.to_excel(writer, sheet_name="Rebalancing", index=False)

        # Sheet 8: Stress Test Results
        if stress_results:
            from .stress_test import stress_results_to_dataframe
            stress_df = stress_results_to_dataframe(stress_results)
            stress_df.to_excel(writer, sheet_name="Stress Test", index=False)

        # Sheet 9: Black-Litterman
        if bl_result is not None:
            bl_df = pd.DataFrame({
                "Asset": clique,
                "BL Weight": bl_result["weights"],
                "BL Weight (%)": [f"{w:.2%}" for w in bl_result["weights"]],
            }).sort_values("BL Weight", ascending=False)
            bl_df.to_excel(writer, sheet_name="Black-Litterman", index=False)

        # Sheet 10: HRP
        if hrp_result is not None:
            hrp_df = pd.DataFrame({
                "Asset": clique,
                "HRP Weight": hrp_result["weights"],
                "HRP Weight (%)": [f"{w:.2%}" for w in hrp_result["weights"]],
            }).sort_values("HRP Weight", ascending=False)
            hrp_df.to_excel(writer, sheet_name="HRP", index=False)

    return filepath


def export_portfolio_to_pdf(
    filepath: str | Path,
    clique: list[str],
    opt_result: dict,
    min_var_result: dict,
    metrics: dict | None = None,
    params: dict | None = None,
    stress_results: list | None = None,
    bl_result: dict | None = None,
    hrp_result: dict | None = None,
    mc_results: pd.DataFrame | None = None,
) -> Path:
    """Экспорт результатов оптимизации в PDF (через matplotlib).

    Генерирует многостраничный PDF-отчёт.

    Args:
        filepath: Путь к PDF файлу.
        clique: Список тикеров клики.
        opt_result: Результат max_sharpe_portfolio.
        min_var_result: Результат min_variance_portfolio.
        metrics: Словарь с метриками.
        params: Параметры оптимизации.
        stress_results: Результаты стресс-тестов.
        bl_result: Результат Black-Litterman.
        hrp_result: Результат HRP.
        mc_results: Результаты Monte Carlo.

    Returns:
        Path к созданному файлу.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    with PdfPages(filepath) as pdf:
        # Page 1: Summary
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.axis("off")
        ax.set_title("MOEX Portfolio Optimization Report", fontsize=20, fontweight="bold", pad=20)

        lines = [
            f"Assets: {', '.join(clique)}",
            "",
            "=== Max Sharpe Portfolio ===",
            f"  Return: {opt_result['return']:.2%}",
            f"  Volatility: {opt_result['volatility']:.2%}",
            f"  Sharpe: {opt_result['sharpe']:.3f}",
            "",
            "=== Min Variance Portfolio ===",
            f"  Return: {min_var_result['return']:.2%}",
            f"  Volatility: {min_var_result['volatility']:.2%}",
            f"  Sharpe: {min_var_result['sharpe']:.3f}",
        ]
        if metrics:
            lines.extend([
                "",
                "=== Portfolio Metrics ===",
                f"  Sortino: {metrics.get('sortino', 0):.3f}",
                f"  Max Drawdown: {metrics.get('max_drawdown', 0):.2%}",
                f"  Calmar: {metrics.get('calmar', 0):.3f}" if metrics.get('calmar') else "",
            ])
        if params:
            lines.extend(["", "=== Parameters ==="])
            for k, v in params.items():
                lines.append(f"  {k}: {v}")

        ax.text(0.05, 0.95, "\n".join(lines), transform=ax.transAxes,
                fontsize=10, verticalalignment="top", fontfamily="monospace")
        plt.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)

        # Page 2: Weights
        fig, ax = plt.subplots(figsize=(10, 6))
        tickers_sorted = sorted(zip(clique, opt_result["weights"]), key=lambda x: -x[1])
        names = [t for t, _ in tickers_sorted]
        weights = [w for _, w in tickers_sorted]
        ax.barh(names, weights, color="steelblue")
        ax.set_xlabel("Weight")
        ax.set_title("Max Sharpe Portfolio Weights")
        ax.invert_yaxis()
        plt.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)

        if mc_results is not None:
            fig, axes = plt.subplots(1, 3, figsize=(15, 4))
            axes[0].hist(mc_results["annual_return"] * 100, bins=50, color="steelblue", alpha=0.7)
            axes[0].set_title("Annual Return Distribution")
            axes[0].set_xlabel("Return (%)")
            axes[1].hist(mc_results["annual_volatility"] * 100, bins=50, color="orange", alpha=0.7)
            axes[1].set_title("Volatility Distribution")
            axes[1].set_xlabel("Volatility (%)")
            axes[2].hist(mc_results["max_drawdown"] * 100, bins=50, color="green", alpha=0.7)
            axes[2].set_title("Max Drawdown Distribution")
            axes[2].set_xlabel("Drawdown (%)")
            plt.tight_layout()
            pdf.savefig(fig)
            plt.close(fig)

        # Page 4: Strategy Comparison
        all_strategies = [("Markowitz", opt_result)]
        if bl_result:
            all_strategies.append(("Black-Litterman", bl_result))
        if hrp_result:
            all_strategies.append(("HRP", hrp_result))
        all_strategies.append(("Min Variance", min_var_result))

        fig, ax = plt.subplots(figsize=(10, 5))
        names_s = [s[0] for s in all_strategies]
        returns_s = [s[1]["return"] for s in all_strategies]
        vol_s = [s[1]["volatility"] for s in all_strategies]
        sharpe_s = [s[1]["sharpe"] for s in all_strategies]

        x = np.arange(len(names_s))
        width = 0.25
        ax.bar(x - width, [r * 100 for r in returns_s], width, label="Return (%)", color="steelblue")
        ax.bar(x, [v * 100 for v in vol_s], width, label="Volatility (%)", color="orange")
        ax.bar(x + width, sharpe_s, width, label="Sharpe", color="green")
        ax.set_xticks(x)
        ax.set_xticklabels(names_s)
        ax.set_title("Strategy Comparison")
        ax.legend()
        plt.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)

        # Page 5: Stress Test
        if stress_results:
            from .stress_test import stress_results_to_dataframe
            stress_df = stress_results_to_dataframe(stress_results)
            fig, ax = plt.subplots(figsize=(12, 4))
            ax.axis("off")
            ax.set_title("Stress Test Results", fontsize=14, fontweight="bold")
            table = ax.table(
                cellText=stress_df.values,
                colLabels=stress_df.columns,
                loc="center",
                cellLoc="center",
            )
            table.auto_set_font_size(False)
            table.set_fontsize(8)
            table.scale(1.0, 1.5)
            plt.tight_layout()
            pdf.savefig(fig)
            plt.close(fig)

    logger.info("PDF report saved: %s", filepath)
    return filepath
