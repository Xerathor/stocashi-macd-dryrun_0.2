# indicators/stocashi.py
# ═══════════════════════════════════════════════════════════════
#  STOCASHI — Stochastic RSI + Heikin-Ashi Candles
#  Порт индикатора Stocashi_Gem_0.1.mq5 → Python
#  (алгоритм идентичен исходному stocashi_gem.py пользователя;
#   убрана только Plotly-обвязка под мульти-панельный дашборд —
#   график строится отдельно в app.py)
#
#  Алгоритм:
#    1. RSI(close, length_rsi) по сглаживанию Уайлдера
#    2. Stochastic на RSI: 100*(RSI−min_RSI)/(max_RSI−min_RSI) по окну length_stoch
#    3. %K = SMA(stoch, smooth_k) − 50
#    4. %D = SMA(%K, smooth_d)
#    5. Heikin-Ashi свечи из K/D:
#         ha_close = (K + D) / 2
#         ha_open  = (K[i-1] + D[i-1]) / 2
#         ha_high  = max(K, ha_open, ha_close)
#         ha_low   = min(K, ha_open, ha_close)
#    6. Цвет: bullish если ha_close >= ha_open, иначе bearish
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations
import pandas as pd
import numpy as np

from .base import BaseIndicator


class StocashiIndicator(BaseIndicator):

    name = "stocashi"

    def __init__(
        self,
        smooth_k: int = 8,
        smooth_d: int = 3,
        length_rsi: int = 14,
        length_stoch: int = 14,
    ):
        self.smooth_k = smooth_k
        self.smooth_d = smooth_d
        self.length_rsi = length_rsi
        self.length_stoch = length_stoch

    # ── RSI по Уайлдеру (EWM с alpha=1/period) ───────────────
    @staticmethod
    def _wilder_rsi(series: pd.Series, period: int) -> pd.Series:
        delta = series.diff()
        gain = delta.clip(lower=0.0)
        loss = (-delta).clip(lower=0.0)
        avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0.0, np.nan)
        rsi = 100.0 - (100.0 / (1.0 + rs))
        return rsi

    # ── Расчёт ───────────────────────────────────────────────
    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        close = df["close"]

        # 1. RSI
        rsi = self._wilder_rsi(close, self.length_rsi)

        # 2. Stochastic на RSI
        high_rsi = rsi.rolling(self.length_stoch, min_periods=self.length_stoch).max()
        low_rsi = rsi.rolling(self.length_stoch, min_periods=self.length_stoch).min()
        denom = (high_rsi - low_rsi).replace(0.0, np.nan)
        stoch = 100.0 * (rsi - low_rsi) / denom
        stoch = stoch.fillna(0.0)  # защита от деления на 0 (как в MQL5)

        # 3. %K = SMA(stoch, smooth_k) − 50
        K = stoch.rolling(self.smooth_k, min_periods=self.smooth_k).mean() - 50.0

        # 4. %D = SMA(K, smooth_d)
        D = K.rolling(self.smooth_d, min_periods=self.smooth_d).mean()

        # 5. Heikin-Ashi свечи
        ha_close = (K + D) / 2.0
        ha_open = (K.shift(1) + D.shift(1)) / 2.0
        ha_high = pd.concat([K, ha_open, ha_close], axis=1).max(axis=1)
        ha_low = pd.concat([K, ha_open, ha_close], axis=1).min(axis=1)

        # 6. Цвет свечи
        color = np.where(ha_close >= ha_open, "bullish", "bearish")

        df["stocashi_rsi"] = rsi
        df["stocashi_stoch"] = stoch
        df["stocashi_K"] = K
        df["stocashi_D"] = D
        df["stocashi_ha_open"] = ha_open
        df["stocashi_ha_high"] = ha_high
        df["stocashi_ha_low"] = ha_low
        df["stocashi_ha_close"] = ha_close
        df["stocashi_color"] = color

        return df
