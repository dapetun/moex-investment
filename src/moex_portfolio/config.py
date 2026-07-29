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

# Date range
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
