"""Drawdown Analysis — глубокий анализ просадок портфеля.

Анализ худших периодов, времени восстановления, underwater chart.
"""

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class DrawdownPeriod:
    """Один период просадки."""

    peak_date: str
    trough_date: str
    recovery_date: str | None
    peak_value: float
    trough_value: float
    drawdown_pct: float
    duration_days: int
    recovery_days: int | None


@dataclass
class DrawdownAnalysis:
    """Полный результат анализа просадок."""

    underwater_series: pd.Series
    drawdown_periods: list[DrawdownPeriod]
    max_drawdown: float
    max_drawdown_duration: int
    avg_drawdown: float
    avg_recovery: float
    n_drawdowns: int
    worst_drawdown: DrawdownPeriod | None
    longest_drawdown: DrawdownPeriod | None


def analyze_drawdowns(
    portfolio_values: pd.Series | list[float] | np.ndarray,
    dates: pd.DatetimeIndex | list | None = None,
    min_drawdown_pct: float = 0.01,
) -> DrawdownAnalysis:
    """Полный анализ просадок портфеля.

    Args:
        portfolio_values: Значения портфеля во времени.
        dates: Даты (если None — используются индексы).
        min_drawdown_pct: Минимальная просадка для учёта (по умолчанию 1%).

    Returns:
        DrawdownAnalysis с результатами.
    """
    values = np.asarray(portfolio_values, dtype=float)
    n = len(values)

    if dates is None:
        if isinstance(portfolio_values, pd.Series):
            dates = portfolio_values.index
        else:
            dates = pd.RangeIndex(n)

    running_max = np.maximum.accumulate(values)
    drawdowns = np.where(running_max > 0, (values - running_max) / running_max, 0.0)

    underwater = pd.Series(drawdowns, index=dates[:n])

    periods = _find_drawdown_periods(values, dates[:n], min_drawdown_pct)

    max_dd = float(drawdowns.min()) if len(drawdowns) > 0 else 0.0
    max_dd_duration = max((p.duration_days for p in periods), default=0)
    avg_dd = float(np.mean([p.drawdown_pct for p in periods])) if periods else 0.0
    recovered = [p.recovery_days for p in periods if p.recovery_days is not None]
    avg_recovery = float(np.mean(recovered)) if recovered else 0.0

    worst = min(periods, key=lambda p: p.drawdown_pct) if periods else None
    longest = max(periods, key=lambda p: p.duration_days) if periods else None

    logger.info(
        "Drawdown analysis: max=%.2f%%, worst period=%s–%s, n_periods=%d",
        max_dd * 100,
        worst.peak_date if worst else "N/A",
        worst.trough_date if worst else "N/A",
        len(periods),
    )

    return DrawdownAnalysis(
        underwater_series=underwater,
        drawdown_periods=periods,
        max_drawdown=max_dd,
        max_drawdown_duration=max_dd_duration,
        avg_drawdown=avg_dd,
        avg_recovery=avg_recovery,
        n_drawdowns=len(periods),
        worst_drawdown=worst,
        longest_drawdown=longest,
    )


def drawdown_summary_table(analysis: DrawdownAnalysis, top_n: int = 10) -> pd.DataFrame:
    """Таблица худших просадок.

    Args:
        analysis: Результат analyze_drawdowns.
        top_n: Сколько худших показать.

    Returns:
        DataFrame с топ-N просадками.
    """
    sorted_periods = sorted(analysis.drawdown_periods, key=lambda p: p.drawdown_pct)
    top = sorted_periods[:top_n]

    rows = []
    for i, p in enumerate(top, 1):
        rows.append({
            "Rank": i,
            "Peak Date": p.peak_date,
            "Trough Date": p.trough_date,
            "Recovery Date": p.recovery_date or "Not recovered",
            "Drawdown": p.drawdown_pct,
            "Peak Value": f"{p.peak_value:.4f}",
            "Trough Value": f"{p.trough_value:.4f}",
            "Duration (days)": p.duration_days,
            "Recovery (days)": p.recovery_days or "N/A",
        })

    return pd.DataFrame(rows)


def _find_drawdown_periods(
    values: np.ndarray,
    dates,
    min_dd_pct: float,
) -> list[DrawdownPeriod]:
    """Найти все периоды просадки выше min_dd_pct."""
    periods = []
    running_max = values[0]
    peak_idx = 0
    in_drawdown = False
    trough_idx = None

    for i in range(1, len(values)):
        if values[i] > running_max:
            if in_drawdown and trough_idx is not None:
                dd = (values[trough_idx] - running_max) / running_max
                if abs(dd) >= min_dd_pct:
                    peak_date = str(dates[peak_idx])[:10] if hasattr(dates[peak_idx], "date") else str(dates[peak_idx])
                    trough_date = str(dates[trough_idx])[:10] if hasattr(dates[trough_idx], "date") else str(dates[trough_idx])
                    recovery_date = str(dates[i])[:10] if hasattr(dates[i], "date") else str(dates[i])
                    duration = trough_idx - peak_idx
                    recovery = i - trough_idx

                    periods.append(DrawdownPeriod(
                        peak_date=peak_date,
                        trough_date=trough_date,
                        recovery_date=recovery_date,
                        peak_value=float(running_max),
                        trough_value=float(values[trough_idx]),
                        drawdown_pct=float(dd),
                        duration_days=duration,
                        recovery_days=recovery,
                    ))
                in_drawdown = False
                trough_idx = None

            running_max = values[i]
            peak_idx = i
        elif values[i] < running_max * (1 - min_dd_pct):
            if not in_drawdown:
                in_drawdown = True
            trough_idx = i

    if in_drawdown and trough_idx is not None:
        dd = (values[trough_idx] - running_max) / running_max
        if abs(dd) >= min_dd_pct:
            peak_date = str(dates[peak_idx])[:10] if hasattr(dates[peak_idx], "date") else str(dates[peak_idx])
            trough_date = str(dates[trough_idx])[:10] if hasattr(dates[trough_idx], "date") else str(dates[trough_idx])
            duration = trough_idx - peak_idx

            periods.append(DrawdownPeriod(
                peak_date=peak_date,
                trough_date=trough_date,
                recovery_date=None,
                peak_value=float(running_max),
                trough_value=float(values[trough_idx]),
                drawdown_pct=float(dd),
                duration_days=duration,
                recovery_days=None,
            ))

    return periods
