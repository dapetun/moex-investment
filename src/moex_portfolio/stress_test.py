"""Стресс-тестирование портфеля на исторических кризисах."""

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .metrics import max_drawdown

logger = logging.getLogger(__name__)


@dataclass
class StressScenario:
    """Описание стресс-сценария."""

    name: str
    description: str
    start_date: str
    end_date: str
    peak_to_trough: float  # Ожидаемое падение (для валидации)


@dataclass
class StressTestResult:
    """Результат стресс-теста."""

    scenario_name: str
    description: str
    start_date: str
    end_date: str
    portfolio_return: float
    portfolio_max_drawdown: float
    portfolio_volatility: float
    worst_day: float
    worst_day_date: str
    recovery_days: int | None  # Дней до восстановления (None если не восстановился)
    max_drawdown: float  # alias для совместимости


# Исторические кризисы MOEX / российского рынка
PREDEFINED_SCENARIOS = [
    StressScenario(
        name="COVID Crash",
        description="Пандемия COVID-19: обвал рынков в марте 2020",
        start_date="2020-02-20",
        end_date="2020-05-31",
        peak_to_trough=-0.30,
    ),
    StressScenario(
        name="2022 Geopolitical Crisis",
        description="Геополитический кризис: санкции и война",
        start_date="2022-02-21",
        end_date="2022-06-30",
        peak_to_trough=-0.45,
    ),
    StressScenario(
        name="2018 Russian Crisis",
        description="Торговые войны и уход инвесторов",
        start_date="2018-01-29",
        end_date="2018-04-30",
        peak_to_trough=-0.15,
    ),
    StressScenario(
        name="2014 Oil Crash",
        description="Падение цен на нефть и девальвация рубля",
        start_date="2014-06-01",
        end_date="2015-01-31",
        peak_to_trough=-0.40,
    ),
    StressScenario(
        name="2008 Global Financial Crisis",
        description="Глобальный финансовый кризис",
        start_date="2008-06-01",
        end_date="2009-03-31",
        peak_to_trough=-0.70,
    ),
]


def run_stress_test(
    returns: pd.DataFrame,
    weights: np.ndarray,
    scenario: StressScenario,
) -> StressTestResult:
    """Запуск стресс-теста для одного сценария.

    Args:
        returns: DataFrame с дневными доходностями (индекс — даты).
        weights: Веса портфеля.
        scenario: Стресс-сценарий.

    Returns:
        StressTestResult.
    """
    start = pd.Timestamp(scenario.start_date)
    end = pd.Timestamp(scenario.end_date)

    # Фильтруем данные по датам сценария
    mask = (returns.index >= start) & (returns.index <= end)
    scenario_returns = returns.loc[mask]

    if len(scenario_returns) == 0:
        logger.warning("No data for scenario '%s' in range %s - %s",
                       scenario.name, scenario.start_date, scenario.end_date)
        return StressTestResult(
            scenario_name=scenario.name,
            description=scenario.description,
            start_date=scenario.start_date,
            end_date=scenario.end_date,
            portfolio_return=0.0,
            portfolio_max_drawdown=0.0,
            portfolio_volatility=0.0,
            worst_day=0.0,
            worst_day_date="N/A",
            recovery_days=None,
            max_drawdown=0.0,
        )

    # Доходность портфеля
    port_returns = scenario_returns.values @ weights
    port_series = pd.Series(port_returns, index=scenario_returns.index)

    # Кумулятивная доходность
    cumulative = (1 + port_series).cumprod()
    total_return = cumulative.iloc[-1] - 1

    # Максимальная просадка
    running_max = cumulative.cummax()
    drawdown = (cumulative - running_max) / running_max
    max_dd = drawdown.min()

    # Худший день
    worst_day = port_returns.min()
    worst_day_idx = port_returns.argmin()
    worst_day_date = str(scenario_returns.index[worst_day_idx])[:10]

    # Дней до восстановления
    recovery_days = None
    peak_idx = cumulative[:drawdown.idxmin()].idxmax() if len(cumulative) > 1 else None
    if peak_idx is not None:
        after_peak = cumulative.loc[peak_idx:]
        recovered = after_peak[after_peak >= running_max.loc[peak_idx]]
        if len(recovered) > 0:
            recovery_days = len(after_peak.loc[:recovered.index[0]])

    # Волатильность
    vol = port_returns.std() * np.sqrt(252)

    return StressTestResult(
        scenario_name=scenario.name,
        description=scenario.description,
        start_date=scenario.start_date,
        end_date=scenario.end_date,
        portfolio_return=total_return,
        portfolio_max_drawdown=max_dd,
        portfolio_volatility=vol,
        worst_day=worst_day,
        worst_day_date=worst_day_date,
        recovery_days=recovery_days,
        max_drawdown=max_dd,
    )


def run_all_scenarios(
    returns: pd.DataFrame,
    weights: np.ndarray,
    scenarios: list[StressScenario] | None = None,
) -> list[StressTestResult]:
    """Запуск всех стресс-сценариев.

    Args:
        returns: DataFrame с доходностями.
        weights: Веса портфеля.
        scenarios: Список сценариев (если None — используются предопределённые).

    Returns:
        Список StressTestResult.
    """
    if scenarios is None:
        scenarios = PREDEFINED_SCENARIOS

    results = []
    for scenario in scenarios:
        result = run_stress_test(returns, weights, scenario)
        results.append(result)
        logger.info(
            "Stress test '%s': return=%.2f%%, max_dd=%.2f%%",
            scenario.name,
            result.portfolio_return * 100,
            result.portfolio_max_drawdown * 100,
        )

    return results


def stress_results_to_dataframe(results: list[StressTestResult]) -> pd.DataFrame:
    """Конвертация результатов стресс-тестов в DataFrame.

    Args:
        results: Список StressTestResult.

    Returns:
        DataFrame для отображения.
    """
    rows = []
    for r in results:
        rows.append({
            "Scenario": r.scenario_name,
            "Description": r.description,
            "Period": f"{r.start_date} — {r.end_date}",
            "Return": f"{r.portfolio_return:.2%}",
            "Max Drawdown": f"{r.portfolio_max_drawdown:.2%}",
            "Volatility": f"{r.portfolio_volatility:.2%}",
            "Worst Day": f"{r.worst_day:.2%}",
            "Worst Day Date": r.worst_day_date,
            "Recovery (days)": str(r.recovery_days) if r.recovery_days else "N/A",
        })

    return pd.DataFrame(rows)
