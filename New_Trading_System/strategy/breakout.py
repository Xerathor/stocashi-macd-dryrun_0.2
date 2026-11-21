from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd

from config import StrategyConfig
from core.models import Direction, Position, Signal


class BreakoutStrategy:
    def __init__(self, cfg: StrategyConfig) -> None:
        self.cfg = cfg

    def generate_signal(
        self,
        symbol: str,
        ts: datetime,
        bar: pd.Series,
        macro_bias: Optional[str] = None,
    ) -> Optional[Signal]:
        required = (
            "close", "volume", "ema_trend", "dc_high", "dc_low",
            "atr", "adx", "vol_ma", "body_size",
        )
        if any(pd.isna(bar.get(col)) for col in required):
            return None

        close = float(bar["close"])
        atr = float(bar["atr"])
        adx = float(bar["adx"])
        ema = float(bar["ema_trend"])
        dc_high = float(bar["dc_high"])
        dc_low = float(bar["dc_low"])
        volume = float(bar["volume"])
        vol_ma = float(bar["vol_ma"])
        body = float(bar["body_size"])

        if atr <= 0 or close <= 0 or vol_ma <= 0:
            return None
        if adx < self.cfg.adx_threshold:
            return None
        if getattr(self.cfg, "require_rising_adx", False):
            adx_prev = bar.get("adx_prev")
            if adx_prev is not None and not pd.isna(adx_prev):
                if adx <= float(adx_prev):
                    return None
        if volume < vol_ma * self.cfg.vol_mult:
            return None
        if body > atr * self.cfg.max_body_atr:
            return None
        strict_macro = getattr(self.cfg, "strict_macro_filter", False)
        bias = (macro_bias or "").lower()

        if close > ema and close > dc_high:
            if strict_macro and bias != "bullish":
                return None
            return Signal(
                symbol=symbol,
                ts=ts,
                direction=Direction.LONG,
                entry_price=close,
                stop_loss=close - atr * self.cfg.sl_atr_mult,
                atr=atr,
                adx=adx,
                reason="donchian_breakout_long",
            )

        if close < ema and close < dc_low:
            if strict_macro and bias != "bearish":
                return None
            return Signal(
                symbol=symbol,
                ts=ts,
                direction=Direction.SHORT,
                entry_price=close,
                stop_loss=close + atr * self.cfg.sl_atr_mult,
                atr=atr,
                adx=adx,
                reason="donchian_breakout_short",
            )
        return None

    def compute_updated_stop(
        self,
        pos: Position,
        bar_high: float,
        bar_low: float,
        atr: float,
    ) -> float:
        if pd.isna(atr) or atr <= 0:
            return pos.stop_loss

        be_offset = max(
            self.cfg.be_offset_pct,
            getattr(self.cfg, "min_be_offset_pct", 0.0018),
        )
        new_stop = pos.stop_loss
        if pos.direction == Direction.LONG:
            pos.highest_price = max(pos.highest_price, bar_high)
            max_r = pos.r_multiple(pos.highest_price)
            if not pos.be_moved and max_r >= self.cfg.be_trigger_r:
                pos.stop_loss = max(pos.stop_loss, pos.entry_price * (1.0 + be_offset))
                pos.be_moved = True
            if max_r >= self.cfg.trail_activation_r:
                chandelier = pos.highest_price - atr * self.cfg.trail_atr_mult
                if chandelier > pos.stop_loss:
                    pos.stop_loss = chandelier
                    pos.trailing_moved = True
            new_stop = pos.stop_loss
        else:
            pos.lowest_price = min(pos.lowest_price, bar_low)
            max_r = pos.r_multiple(pos.lowest_price)
            if not pos.be_moved and max_r >= self.cfg.be_trigger_r:
                pos.stop_loss = min(pos.stop_loss, pos.entry_price * (1.0 - be_offset))
                pos.be_moved = True
            if max_r >= self.cfg.trail_activation_r:
                chandelier = pos.lowest_price + atr * self.cfg.trail_atr_mult
                if chandelier < pos.stop_loss:
                    pos.stop_loss = chandelier
                    pos.trailing_moved = True
            new_stop = pos.stop_loss
        return new_stop
