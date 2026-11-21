from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import ccxt
import pandas as pd


LOGGER = logging.getLogger(__name__)
CACHE_DIR = Path(__file__).resolve().parent / "cache"


def _make_exchange():
    venue = os.getenv("EXCHANGE", "binance").lower()
    if venue == "bybit":
        exchange = ccxt.bybit({
            "enableRateLimit": True,
            "options": {"defaultType": "linear"},
        })
    else:
        exchange = ccxt.binance({
            "enableRateLimit": True,
            "options": {"defaultType": "future"},
        })
    return exchange


def _cache_path(symbol: str, timeframe: str) -> Path:
    name = symbol.replace("/", "_").replace(":", "_")
    return CACHE_DIR / f"{name}_{timeframe}.parquet"


def _to_dataframe(raw_rows: list[list[object]]) -> pd.DataFrame:
    if not raw_rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    df = pd.DataFrame(
        raw_rows,
        columns=["ts", "open", "high", "low", "close", "volume"],
    )
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.set_index("ts")
    for column in ("open", "high", "low", "close", "volume"):
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="last")]
    df = df.astype(float)
    return df


def _validate_index(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    if df.empty:
        return df
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("OHLCV index must be DatetimeIndex")

    if timeframe == "2h":
        expected = pd.Timedelta(hours=2)
    else:
        try:
            expected = pd.to_timedelta(timeframe)
        except ValueError as exc:
            raise ValueError(f"Unsupported timeframe: {timeframe}") from exc

    diffs = df.index.to_series().diff().dropna()
    gaps = diffs[diffs > expected]
    if not gaps.empty:
        LOGGER.warning("Detected %d market-data gap(s): %s", len(gaps), gaps.to_dict())
    return df


def fetch_ohlcv_history(
    symbol: str,
    timeframe: str = "2h",
    since_days: int = 730,
) -> pd.DataFrame:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = _cache_path(symbol, timeframe)
    cached = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    if cache_path.exists():
        cached = pd.read_parquet(cache_path)
        cached.index = pd.to_datetime(cached.index, utc=True)
        cached = cached.sort_index()
        cached = cached[~cached.index.duplicated(keep="last")]

    exchange = _make_exchange()
    exchange.load_markets()
    target_start = datetime.now(timezone.utc) - timedelta(days=since_days)
    since_ms = int(target_start.timestamp() * 1000)
    if not cached.empty:
        since_ms = max(since_ms, int(cached.index[-1].timestamp() * 1000) + 1)

    rows: list[list[object]] = []
    while True:
        try:
            batch = exchange.fetch_ohlcv(
                symbol,
                timeframe=timeframe,
                since=since_ms,
                limit=1000,
            )
        except (ccxt.NetworkError, ccxt.RateLimitExceeded) as exc:
            LOGGER.warning("Transient exchange error; retrying: %s", exc)
            time.sleep(exchange.rateLimit / 1000.0 + 1.0)
            continue

        if not batch:
            break
        rows.extend(batch)
        next_since = int(batch[-1][0]) + 1
        if next_since <= since_ms:
            break
        since_ms = next_since
        if len(batch) < 1000:
            break
        if len(rows) >= 20000:
            LOGGER.warning("Pagination safety limit reached for %s", symbol)
            break

    fetched = _to_dataframe(rows)
    combined = pd.concat([cached, fetched], axis=0)
    combined = combined.sort_index()
    combined = combined[~combined.index.duplicated(keep="last")]
    combined = combined[
        combined.index >= pd.Timestamp(target_start).tz_convert("UTC")
    ]
    combined = _validate_index(combined, timeframe)
    combined.to_parquet(cache_path)
    return combined


def fetch_latest_closed_bars(
    symbol: str,
    timeframe: str = "2h",
    limit: int = 300,
) -> pd.DataFrame:
    exchange = _make_exchange()
    exchange.load_markets()
    rows = exchange.fetch_ohlcv(
        symbol,
        timeframe=timeframe,
        limit=limit + 1,
    )
    df = _to_dataframe(rows)
    if timeframe != "2h":
        raise ValueError("Live implementation requires timeframe='2h'")

    now = pd.Timestamp.now(tz="UTC")
    df = df[df.index + pd.Timedelta(hours=2) <= now]
    df = df.tail(limit)
    df = _validate_index(df, timeframe)
    return df
