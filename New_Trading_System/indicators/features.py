from __future__ import annotations

import numpy as np
import pandas as pd

from config import StrategyConfig


def _wilder_rma(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def add_indicators(df: pd.DataFrame, cfg: StrategyConfig) -> pd.DataFrame:
    out = df.copy()
    if not isinstance(out.index, pd.DatetimeIndex):
        raise ValueError("DataFrame index must be a DatetimeIndex")

    high = out["high"].astype(float)
    low = out["low"].astype(float)
    close = out["close"].astype(float)
    open_ = out["open"].astype(float)
    volume = out["volume"].astype(float)

    out["ema_trend"] = close.ewm(
        span=cfg.ema_trend_len,
        adjust=False,
        min_periods=cfg.ema_trend_len,
    ).mean()
    out["dc_high"] = high.rolling(
        cfg.donchian_len,
        min_periods=cfg.donchian_len,
    ).max().shift(1)
    out["dc_low"] = low.rolling(
        cfg.donchian_len,
        min_periods=cfg.donchian_len,
    ).min().shift(1)

    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    out["atr"] = _wilder_rma(tr, cfg.atr_len)

    up_move = high - high.shift(1)
    down_move = low.shift(1) - low
    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
        index=out.index,
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
        index=out.index,
    )

    atr_adx = _wilder_rma(tr, cfg.adx_len).replace(0.0, np.nan)
    plus_di = 100.0 * (_wilder_rma(plus_dm, cfg.adx_len) / atr_adx)
    minus_di = 100.0 * (_wilder_rma(minus_dm, cfg.adx_len) / atr_adx)
    di_sum = (plus_di + minus_di).replace(0.0, np.nan)
    dx = 100.0 * (plus_di - minus_di).abs() / di_sum
    out["adx"] = _wilder_rma(dx, cfg.adx_len)
    if getattr(cfg, "require_rising_adx", False):
        out["adx_prev"] = out["adx"].shift(1)

    out["vol_ma"] = volume.rolling(
        cfg.vol_ma_len,
        min_periods=cfg.vol_ma_len,
    ).mean().shift(1)
    out["body_size"] = (close - open_).abs()
    return out
