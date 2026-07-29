"""Параметры и конфигурация проекта.

Содержит только константы, используемые напрямую модулями.
UI-параметры и дефолты для дашборда живут в defaults.py (Defaults frozen dataclass).
"""

from datetime import date
from pathlib import Path

from dateutil.relativedelta import relativedelta

# Paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
FIGURES_DIR = PROJECT_ROOT / "figures"


def get_today() -> date:
    """Текущая дата. Вызывать вместо module-level TODAY/END_DATE."""
    return date.today()


def get_date_range(years: int = 2) -> tuple[date, date]:
    """Кортеж (start_date, end_date) за последние N лет."""
    end = date.today()
    start = end - relativedelta(years=years)
    return start, end


# Legacy совместимость: END_DATE/START_DATE вычисляются при import time,
# но рекомендуется использовать get_today() / get_date_range().
END_DATE = date.today()
START_DATE = END_DATE - relativedelta(years=2)

# Filtering
CORR_THRESHOLD = 0.25
MIN_OBSERVATIONS = 500
MIN_TURNOVER = 50_000_000  # 50M RUB

# API
MOEX_ISS_BASE = "https://iss.moex.com/iss"
REQUEST_DELAY = 0.3  # seconds between API calls
MAX_RETRIES = 3
RETRY_BACKOFF = 2  # exponential backoff multiplier

# Anomaly detection
MAX_DAILY_CHANGE = 0.80  # 80%

# Portfolio optimization
RISK_FREE_RATE = 0.0
MIN_WEIGHT = 0.0
MAX_WEIGHT = 0.3

# Rebalancing
MIN_DRIFT = 0.05  # 5% — min weight drift to trigger rebalance
