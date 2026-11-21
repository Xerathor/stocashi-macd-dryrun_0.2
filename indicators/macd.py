# indicators/macd.py
# ═══════════════════════════════════════════════════════════════
#  MACD — Moving Average Convergence Divergence (классический)
#    macd_line   = EMA(close, fast) − EMA(close, slow)
#    macd_signal = EMA(macd_line, signal)
#    macd_hist   = macd_line − macd_signal
#
#  Знак macd_line относительно нуля используется как фильтр
#  в связке со Stocashi (см. engine/strategy.py).
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations
import pandas as pd

from .base import BaseIndicator


class MACDIndicator(BaseIndicator):

    name = "macd"

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9):
        self.fast = fast
        self.slow = slow
        self.signal = signal

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        close = df["close"]
        ema_fast = close.ewm(span=self.fast, adjust=False).mean()
        ema_slow = close.ewm(span=self.slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=self.signal, adjust=False).mean()
        hist = macd_line - signal_line

        df["macd_line"] = macd_line
        df["macd_signal"] = signal_line
        df["macd_hist"] = hist
        return df
