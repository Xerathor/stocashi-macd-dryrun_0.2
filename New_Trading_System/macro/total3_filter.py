from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import ccxt
import numpy as np
import pandas as pd


BASKET = (
    ("SOLUSDT", 520_000_000),
    ("BNBUSDT", 141_000_000),
    ("XRPUSDT", 58_500_000_000),
    ("DOGEUSDT", 149_000_000_000),
    ("ADAUSDT", 35_300_000_000),
    ("TRXUSDT", 94_800_000_000),
    ("AVAXUSDT", 416_000_000),
    ("LINKUSDT", 657_000_000),
    ("SUIUSDT", 3_300_000_000),
    ("TONUSDT", 2_500_000_000),
    ("DOTUSDT", 1_560_000_000),
    ("LTCUSDT", 75_800_000),
    ("XLMUSDT", 30_800_000_000),
    ("HBARUSDT", 42_200_000_000),
    ("UNIUSDT", 600_000_000),
    ("BCHUSDT", 19_850_000),
    ("NEARUSDT", 1_210_000_000),
    ("AAVEUSDT", 15_100_000),
)

CACHE_DIR = Path(__file__).resolve().parent / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _wilder_rma(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def supertrend(
    df: pd.DataFrame,
    atr_period: int = 10,
    multiplier: float = 3.0,
) -> pd.DataFrame:
    out = df.copy()
    high = out["high"].astype(float)
    low = out["low"].astype(float)
    close = out["close"].astype(float)
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = _wilder_rma(tr, atr_period)

    final_upper = pd.Series(np.nan, index=out.index)
    final_lower = pd.Series(np.nan, index=out.index)
    direction = pd.Series(np.nan, index=out.index)

    for i in range(atr_period - 1, len(out)):
        if i == atr_period - 1:
            hl2 = (high.iloc[i] + low.iloc[i]) / 2.0
            final_upper.iloc[i] = hl2 + multiplier * atr.iloc[i]
            final_lower.iloc[i] = hl2 - multiplier * atr.iloc[i]
            direction.iloc[i] = 1 if close.iloc[i] >= hl2 else -1
            continue

        hl2 = (high.iloc[i] + low.iloc[i]) / 2.0
        basic_upper = hl2 + multiplier * atr.iloc[i]
        basic_lower = hl2 - multiplier * atr.iloc[i]
        prev_close_value = close.iloc[i - 1]
        prev_upper = final_upper.iloc[i - 1]
        prev_lower = final_lower.iloc[i - 1]

        final_upper.iloc[i] = (
            basic_upper
            if basic_upper < prev_upper or prev_close_value > prev_upper
            else prev_upper
        )
        final_lower.iloc[i] = (
            basic_lower
            if basic_lower > prev_lower or prev_close_value < prev_lower
            else prev_lower
        )

        prev_direction = direction.iloc[i - 1]
        if prev_direction == 1 and close.iloc[i] < final_lower.iloc[i]:
            direction.iloc[i] = -1
        elif prev_direction == -1 and close.iloc[i] > final_upper.iloc[i]:
            direction.iloc[i] = 1
        else:
            direction.iloc[i] = prev_direction

    out["supertrend"] = np.where(
        direction == 1,
        final_lower,
        np.where(direction == -1, final_upper, np.nan),
    )
    out["supertrend_direction"] = direction
    return out


def fetch_synthetic_total3(
    days: int = 730,
    timeframe: str = "2h",
) -> pd.DataFrame:
    cache_path = CACHE_DIR / f"synthetic_total3_{timeframe}_{days}.parquet"
    if cache_path.exists():
        try:
            cached = pd.read_parquet(cache_path)
            cached.index = pd.to_datetime(cached.index, utc=True)
            return cached.sort_index()
        except Exception:
            pass

    exchange = ccxt.binance({"enableRateLimit": True})
    exchange.load_markets()
    since_ms = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)
    combined: Optional[pd.DataFrame] = None

    for symbol, supply in BASKET:
        market_symbol = f"{symbol[:-4]}/USDT"
        try:
            rows = []
            next_since = since_ms
            for _ in range(20):
                batch = exchange.fetch_ohlcv(
                    market_symbol,
                    timeframe=timeframe,
                    since=next_since,
                    limit=1000,
                )
                if not batch:
                    break
                rows.extend(batch)
                new_since = int(batch[-1][0]) + 1
                if new_since <= next_since or len(batch) < 1000:
                    break
                next_since = new_since
        except (ccxt.NetworkError, ccxt.RateLimitExceeded, ccxt.BadSymbol):
            continue

        if not rows:
            continue
        frame = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
        frame["ts"] = pd.to_datetime(frame["ts"], unit="ms", utc=True)
        frame = frame.set_index("ts")
        for column in ("open", "high", "low", "close"):
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame = frame[["open", "high", "low", "close"]] * float(supply)

        if combined is None:
            combined = frame.rename(columns={
                "open": "_open",
                "high": "_high",
                "low": "_low",
                "close": "_close",
            })
            combined["_open"] = frame["open"]
            combined["_high"] = frame["high"]
            combined["_low"] = frame["low"]
            combined["_close"] = frame["close"]
        else:
            combined = combined.join(
                frame.rename(columns={
                    "open": f"_open_{symbol}",
                    "high": f"_high_{symbol}",
                    "low": f"_low_{symbol}",
                    "close": f"_close_{symbol}",
                }),
                how="outer",
            )

    if combined is None or combined.empty:
        raise RuntimeError("Could not load any symbols for Synthetic TOTAL3")

    open_cols = [c for c in combined.columns if c.startswith("_open")]
    high_cols = [c for c in combined.columns if c.startswith("_high")]
    low_cols = [c for c in combined.columns if c.startswith("_low")]
    close_cols = [c for c in combined.columns if c.startswith("_close")]
    total3 = pd.DataFrame({
        "open": combined[open_cols].sum(axis=1, skipna=False),
        "high": combined[high_cols].sum(axis=1, skipna=False),
        "low": combined[low_cols].sum(axis=1, skipna=False),
        "close": combined[close_cols].sum(axis=1, skipna=False),
        "volume": 0.0,
    }).dropna()
    total3 = total3.sort_index()
    total3 = total3[~total3.index.duplicated(keep="last")]
    total3.to_parquet(cache_path)
    return total3


def build_daily_total3_direction(
    total3: pd.DataFrame,
) -> pd.Series:
    if total3.empty:
        return pd.Series(dtype="object")

    daily = total3.resample("1D").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna()
    daily["ema20"] = daily["close"].ewm(span=20, adjust=False, min_periods=20).mean()
    daily["ema50"] = daily["close"].ewm(span=50, adjust=False, min_periods=50).mean()
    daily = supertrend(daily)

    direction = pd.Series("neutral", index=daily.index, dtype="object")
    bullish = (
        (daily["supertrend_direction"] == 1)
        & (daily["close"] > daily["ema20"])
        & (daily["ema20"] > daily["ema50"])
    )
    bearish = (
        (daily["supertrend_direction"] == -1)
        & (daily["close"] < daily["ema20"])
        & (daily["ema20"] < daily["ema50"])
    )
    direction.loc[bullish] = "bullish"
    direction.loc[bearish] = "bearish"

    # Только закрытая дневная свеча используется на следующие UTC-дни.
    return direction.shift(1).dropna()


def lock_daily_direction(
    direction_1d: pd.Series,
    target_index: pd.DatetimeIndex,
) -> pd.Series:
    if direction_1d.empty:
        return pd.Series("neutral", index=target_index, dtype="object")
    locked = direction_1d.reindex(target_index, method="ffill")
    locked = locked.fillna("neutral")
    return locked
