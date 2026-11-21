# engine/strategy.py
# ═══════════════════════════════════════════════════════════════
#  Торговая логика: Stocashi (цвет свечи) + MACD (фильтр по нулю)
#
#  Правила (согласованы с пользователем):
#    • Позиция ЗАКРЫВАЕТСЯ всегда при смене цвета Stocashi,
#      независимо от MACD.
#    • Позиция ОТКРЫВАЕТСЯ в новом направлении только если MACD
#      подтверждает сигнал:
#        Stocashi bearish → bullish  AND  MACD > 0   →  BUY  (открыть LONG)
#        Stocashi bullish → bearish  AND  MACD < 0   →  SELL (открыть SHORT)
#      Если цвет сменился, а MACD НЕ подтвердил — позиция остаётся
#      плоской (flat) до следующей смены цвета (сделка не открывается
#      «задним числом» по старому флипу).
#    • Одновременно может быть открыта только одна позиция (long ИЛИ short).
#      Текущее состояние позиции определяется наличием открытой записи
#      в таблице trades — отдельного хранилища состояния не требуется.
# ═══════════════════════════════════════════════════════════════
from __future__ import annotations
import pandas as pd

import config
from indicators.stocashi import StocashiIndicator
from indicators.macd import MACDIndicator
from . import storage

_stocashi = StocashiIndicator(**config.INDICATOR_PARAMS["stocashi"])
_macd = MACDIndicator(**config.INDICATOR_PARAMS["macd"])


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = _stocashi.calculate(df)
    df = _macd.calculate(df)
    return df


def current_state() -> str:
    """'flat' / 'long' / 'short' — определяется по открытой сделке в БД."""
    t = storage.get_open_trade()
    return t.direction if t is not None else "flat"


def process_bar(df: pd.DataFrame) -> dict:
    """Обрабатывает ПОСЛЕДНЮЮ ЗАКРЫТУЮ свечу df и применяет правила выше.
    Пишет сигнал в лог и, при необходимости, открывает/закрывает сделку.
    Возвращает словарь с описанием события — для отображения/отладки."""
    if len(df) < 2 or "stocashi_color" not in df.columns:
        return {"event": "not_enough_data"}

    last = df.iloc[-1]
    prev = df.iloc[-2]
    ts = df.index[-1]

    if pd.isna(last.get("stocashi_ha_close")) or pd.isna(last.get("macd_line")):
        return {"event": "indicators_warming_up"}

    price = float(last["close"])
    macd_now = float(last["macd_line"])
    color_now = last["stocashi_color"]
    color_prev = prev["stocashi_color"]

    flipped_to_bull = (color_prev == "bearish") and (color_now == "bullish")
    flipped_to_bear = (color_prev == "bullish") and (color_now == "bearish")

    state = current_state()
    action_parts: list[str] = []
    signal_type = "none"

    qty = (config.START_BALANCE * config.POSITION_PCT) / price if price > 0 else 0.0

    if flipped_to_bull:
        if state == "short":
            storage.close_open_trade("short", ts, price, reason="stocashi_flip_bull")
            state = "flat"
            action_parts.append("close_short")

        if state == "flat" and macd_now > 0:
            storage.open_trade("long", ts, price, qty)
            state = "long"
            action_parts.append("open_long")
            signal_type = "buy"
        elif not action_parts:
            signal_type = "none"
        elif state == "flat":  # цвет сменился, но MACD не подтвердил
            signal_type = "flat_no_confirm"

    elif flipped_to_bear:
        if state == "long":
            storage.close_open_trade("long", ts, price, reason="stocashi_flip_bear")
            state = "flat"
            action_parts.append("close_long")

        if state == "flat" and macd_now < 0:
            storage.open_trade("short", ts, price, qty)
            state = "short"
            action_parts.append("open_short")
            signal_type = "sell"
        elif not action_parts:
            signal_type = "none"
        elif state == "flat":
            signal_type = "flat_no_confirm"

    storage.log_signal(
        ts=ts.to_pydatetime(),
        symbol=config.SYMBOL,
        interval=config.INTERVAL,
        stocashi_color=color_now,
        stocashi_ha_close=float(last["stocashi_ha_close"]),
        macd_line=macd_now,
        signal_type=signal_type,
        note="+".join(action_parts),
    )

    return {
        "ts": ts, "price": price, "macd": macd_now, "color": color_now,
        "state_after": state, "action": "+".join(action_parts) or None,
        "signal_type": signal_type,
    }
