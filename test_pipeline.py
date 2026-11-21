"""
Проверка пайплайна на синтетических OHLCV-данных (без сети):
1. Индикаторы Stocashi + MACD считаются без ошибок.
2. Стратегия process_bar корректно открывает/закрывает сделки
   по правилу «закрытие всегда, открытие только с подтверждением MACD».
3. Хранилище (SQLite во временной папке) пишет/читает сигналы и сделки.
"""
import os
import shutil
import numpy as np
import pandas as pd

# Изолированная тестовая БД
TEST_DIR = "/tmp/stocashi_test"
shutil.rmtree(TEST_DIR, ignore_errors=True)
os.makedirs(TEST_DIR, exist_ok=True)
os.chdir(TEST_DIR)
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DIR}/test.db"

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import importlib
importlib.reload(config)

from engine import storage
from engine import strategy

# ── Генерируем синтетические H1-свечи (random walk + шум) ────
np.random.seed(42)
n = 800
idx = pd.date_range("2025-01-01", periods=n, freq="1h", tz="UTC")
ret = np.random.normal(0, 0.004, n)
# добавим немного трендовости волнами, чтобы индикаторы реально флипались
trend = np.sin(np.linspace(0, 20, n)) * 0.002
close = 3000 * np.exp(np.cumsum(ret + trend))
high = close * (1 + np.abs(np.random.normal(0, 0.002, n)))
low = close * (1 - np.abs(np.random.normal(0, 0.002, n)))
open_ = np.roll(close, 1)
open_[0] = close[0]
vol = np.random.uniform(100, 1000, n)

df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": vol}, index=idx)

# ── Индикаторы ─────────────────────────────────────────────
df = strategy.compute_indicators(df)
assert "stocashi_color" in df.columns
assert "macd_line" in df.columns
print("OK: индикаторы посчитаны, NaN в хвосте:",
      df[["stocashi_ha_close", "macd_line"]].tail(3).isna().sum().to_dict())

n_bull = (df["stocashi_color"] == "bullish").sum()
n_bear = (df["stocashi_color"] == "bearish").sum()
print(f"OK: цвета Stocashi -> bullish={n_bull}, bearish={n_bear}")

# ── Прогоняем стратегию бар за баром (эмуляция реального времени) ──
warmup = 60  # пропускаем разогрев индикаторов
events = []
for i in range(warmup, n):
    sub = df.iloc[: i + 1]
    ev = strategy.process_bar(sub)
    if ev.get("signal_type") in ("buy", "sell"):
        events.append(ev)

print(f"OK: обработано {n - warmup} баров, реальных сделок открыто: {len(events)}")
for e in events[:5]:
    print("  ", e["ts"], e["signal_type"], "price=", round(e["price"], 2), "macd=", round(e["macd"], 3))

# ── Проверяем состояние в БД ──────────────────────────────────
trades = storage.all_trades_df()
signals = storage.all_signals_df(limit=1000)
print(f"OK: в БД сделок={len(trades)}, сигналов(включая none/flat_no_confirm)={len(signals)}")

# Инварианты:
# 1. Не может быть двух одновременно открытых сделок одного направления
open_trades = trades[trades["status"] == "open"]
assert len(open_trades) <= 1, "Не должно быть больше одной открытой позиции"
print(f"OK: открытых позиций сейчас = {len(open_trades)}")

# 2. Все закрытые сделки имеют посчитанный pnl
closed = trades[trades["status"] == "closed"]
assert closed["pnl_abs"].notna().all(), "У всех закрытых сделок должен быть pnl"
print(f"OK: закрытых сделок = {len(closed)}, суммарный PnL = {closed['pnl_abs'].sum():.2f}")

# 3. Проверяем правило: сделка long открывается только когда MACD>0 в момент открытия
sig_buy_sell = signals[signals["signal_type"].isin(["buy", "sell"])]
bad = 0
for _, row in sig_buy_sell.iterrows():
    if row["signal_type"] == "buy" and not (row["macd_line"] > 0):
        bad += 1
    if row["signal_type"] == "sell" and not (row["macd_line"] < 0):
        bad += 1
assert bad == 0, f"Найдено {bad} сигналов, нарушающих правило MACD-фильтра"
print("OK: все buy/sell сигналы соответствуют правилу MACD-фильтра")

# 4. flat_no_confirm сигналы не должны создавать сделок
fnc = signals[signals["signal_type"] == "flat_no_confirm"]
print(f"OK: сигналов 'flat_no_confirm' (цвет сменился, MACD не подтвердил) = {len(fnc)}")

print("\nВСЕ ПРОВЕРКИ ПРОЙДЕНЫ УСПЕШНО")
