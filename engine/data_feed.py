# engine/data_feed.py
# ═══════════════════════════════════════════════════════════════
#  Загрузка OHLCV-свечей с Binance (публичный REST, без ключей)
# ═══════════════════════════════════════════════════════════════
from __future__ import annotations
import requests
import pandas as pd
from datetime import timezone

import config

_KLINE_COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_asset_volume", "trades",
    "taker_buy_base", "taker_buy_quote", "ignore",
]


def fetch_klines(symbol: str | None = None, interval: str | None = None,
                  limit: int | None = None) -> pd.DataFrame:
    """Тянет последние `limit` свечей symbol/interval с Binance.
    Перебирает несколько хостов на случай гео-ограничений/сбоев."""
    symbol = symbol or config.SYMBOL
    interval = interval or config.INTERVAL
    limit = limit or config.HISTORY_LIMIT

    last_err: Exception | None = None
    raw = None
    for host in config.BINANCE_HOSTS:
        try:
            url = f"{host}/api/v3/klines"
            resp = requests.get(
                url,
                params={"symbol": symbol, "interval": interval, "limit": limit},
                timeout=10,
            )
            resp.raise_for_status()
            raw = resp.json()
            break
        except Exception as e:  # пробуем следующий хост
            last_err = e
            continue

    if raw is None:
        raise RuntimeError(f"Не удалось получить данные с Binance ни с одного хоста: {last_err}")

    df = pd.DataFrame(raw, columns=_KLINE_COLUMNS)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = df[col].astype(float)

    df = df.set_index("open_time")[["open", "high", "low", "close", "volume", "close_time"]]
    return df


def fetch_closed_klines(symbol: str | None = None, interval: str | None = None,
                         limit: int | None = None) -> pd.DataFrame:
    """Только ЗАКРЫТЫЕ свечи (исключает текущую формирующуюся),
    чтобы индикаторы и сигналы не «перерисовывались» на неполном баре."""
    df = fetch_klines(symbol, interval, limit)
    now = pd.Timestamp.now(tz=timezone.utc)
    closed = df[df["close_time"] <= now]
    return closed
