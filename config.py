# config.py
# ═══════════════════════════════════════════════════════════════
#  Общая конфигурация Dry-Run системы Stocashi + MACD
# ═══════════════════════════════════════════════════════════════
import os

# ── Рынок / данные ────────────────────────────────────────────
SYMBOL        = os.getenv("SYMBOL", "ETHUSDT")
INTERVAL      = os.getenv("INTERVAL", "1h")            # таймфрейм Binance klines
HISTORY_LIMIT = int(os.getenv("HISTORY_LIMIT", 500))   # сколько свечей истории тянуть
POLL_SECONDS  = int(os.getenv("POLL_SECONDS", 60))     # период опроса биржи фоновым потоком

# Публичные market-data хосты Binance (без авторизации).
# data-api.binance.vision — выделенный домен только для маркет-данных,
# как правило не подвержен гео-блокировкам в отличие от api.binance.com.
BINANCE_HOSTS = [
    "https://data-api.binance.vision",
    "https://api.binance.com",
]

# ── Параметры индикаторов ───────────────────────────────────────
INDICATOR_PARAMS = {
    "stocashi": dict(smooth_k=8, smooth_d=3, length_rsi=14, length_stoch=14),
    "macd":     dict(fast=12, slow=26, signal=9),
}

# ── Параметры dry-run торговли ───────────────────────────────────
START_BALANCE = float(os.getenv("START_BALANCE", 10_000.0))  # виртуальный баланс, USD
POSITION_PCT  = float(os.getenv("POSITION_PCT", 1.0))        # доля баланса на одну сделку (1.0 = 100%)

# ── Хранилище ─────────────────────────────────────────────────
# Если задана переменная окружения DATABASE_URL (например, строка подключения
# Neon Postgres вида postgresql://user:pass@host/db?sslmode=require) —
# используется она. Иначе — локальный SQLite-файл (данные живут в контейнере
# Space и могут сбрасываться при пересборке/перезапуске Space).
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/stocashi_dryrun.db")

# ── UI / обновление ──────────────────────────────────────────────
UI_REFRESH_SECONDS = int(os.getenv("UI_REFRESH_SECONDS", 15))  # автообновление страницы
