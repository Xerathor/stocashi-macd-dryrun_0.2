from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from config import AppConfig
from data.feed import fetch_ohlcv_history
from indicators.features import add_indicators
from strategy.breakout import BreakoutStrategy
from macro.total3_filter import (
    fetch_synthetic_total3,
    build_daily_total3_direction,
    lock_daily_direction,
)


st.set_page_config(
    page_title="Volatility Breakout 2H",
    page_icon="chart",
    layout="wide",
)

cfg = AppConfig()

st.title("Volatility Breakout + ATR Risk Engine")
st.caption("ETH / SOL / BNB — 2H futures — closed candles")

symbol_label = st.sidebar.selectbox("Symbol", cfg.strategy.symbols)
days = st.sidebar.slider("History (days)", 180, 730, 730, 30)
bars_limit = st.sidebar.slider("Candles on chart", 100, 1000, 500, 100)
auto_refresh = st.sidebar.toggle("Refresh market data", value=False)

symbol = str(symbol_label)

@st.cache_data(ttl=300, show_spinner="Loading market history...")
def load_data(selected_symbol: str, selected_days: int) -> pd.DataFrame:
    return fetch_ohlcv_history(
        selected_symbol,
        timeframe="2h",
        since_days=selected_days,
    )

@st.cache_data(ttl=3600, show_spinner="Loading Synthetic TOTAL3...")
def load_total3(selected_days: int) -> pd.DataFrame:
    return fetch_synthetic_total3(days=selected_days, timeframe="2h")

with st.spinner("Loading candles and indicators..."):
    data = load_data(symbol, days)
    prepared = add_indicators(data, cfg.strategy)
    chart = prepared.tail(bars_limit)
    total3 = load_total3(days)
    total3_direction_1d = build_daily_total3_direction(total3)
    total3_direction = lock_daily_direction(
        total3_direction_1d,
        pd.DatetimeIndex(prepared.index),
    )

if chart.empty:
    st.error("No market data available.")
    st.stop()

strategy = BreakoutStrategy(cfg.strategy)
signals = []
for ts, bar in prepared.iterrows():
    macro_bias = str(total3_direction.loc[ts]) if ts in total3_direction.index else "neutral"
    signal = strategy.generate_signal(
        symbol,
        ts.to_pydatetime(),
        bar,
        macro_bias=macro_bias,
    )
    if signal is not None:
        signals.append(signal)

signal_df = pd.DataFrame([
    {
        "timestamp": signal.ts,
        "direction": signal.direction.value,
        "entry": signal.entry_price,
        "stop_loss": signal.stop_loss,
        "ADX": signal.adx,
        "ATR": signal.atr,
    }
    for signal in signals
])

trades_path = ROOT / "reports" / "trades.csv"
trades = pd.read_csv(trades_path) if trades_path.exists() else pd.DataFrame()
if not trades.empty:
    trades["entry_ts"] = pd.to_datetime(trades["entry_ts"], utc=True)
    trades["exit_ts"] = pd.to_datetime(trades["exit_ts"], utc=True)
    symbol_trades = trades[trades["symbol"] == symbol]
else:
    symbol_trades = pd.DataFrame()

latest = chart.iloc[-1]
latest_macro = str(total3_direction.iloc[-1]) if not total3_direction.empty else "neutral"
metric1, metric2, metric3, metric4, metric5 = st.columns(5)
metric1.metric("Close", f"{latest['close']:,.2f}")
metric2.metric("ADX", f"{latest['adx']:.2f}")
metric3.metric("ATR", f"{latest['atr']:.4f}")
metric4.metric("Signals", str(len(signal_df)))
metric5.metric("TOTAL3 day", latest_macro.upper())

fig = make_subplots(
    rows=3,
    cols=1,
    shared_xaxes=True,
    vertical_spacing=0.035,
    row_heights=[0.58, 0.22, 0.20],
    subplot_titles=("Price, EMA and Donchian channel", "ADX", "Volume"),
)

fig.add_trace(
    go.Candlestick(
        x=chart.index,
        open=chart["open"],
        high=chart["high"],
        low=chart["low"],
        close=chart["close"],
        name="OHLC",
    ),
    row=1,
    col=1,
)
fig.add_trace(
    go.Scatter(
        x=chart.index,
        y=chart["ema_trend"],
        name=f"EMA {cfg.strategy.ema_trend_len}",
        line={"color": "#F7C873", "width": 1.5},
    ),
    row=1,
    col=1,
)
fig.add_trace(
    go.Scatter(
        x=chart.index,
        y=chart["dc_high"],
        name="Donchian high",
        line={"color": "#4ECDC4", "width": 1},
    ),
    row=1,
    col=1,
)
fig.add_trace(
    go.Scatter(
        x=chart.index,
        y=chart["dc_low"],
        name="Donchian low",
        line={"color": "#FF6B6B", "width": 1},
    ),
    row=1,
    col=1,
)

if not signal_df.empty:
    visible_signals = signal_df[
        (signal_df["timestamp"] >= chart.index.min())
        & (signal_df["timestamp"] <= chart.index.max())
    ]
    long_signals = visible_signals[visible_signals["direction"] == "long"]
    short_signals = visible_signals[visible_signals["direction"] == "short"]

    fig.add_trace(
        go.Scatter(
            x=long_signals["timestamp"],
            y=long_signals["entry"],
            mode="markers",
            name="BUY signal",
            marker={"symbol": "triangle-up", "size": 12, "color": "#00E676"},
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=short_signals["timestamp"],
            y=short_signals["entry"],
            mode="markers",
            name="SELL signal",
            marker={"symbol": "triangle-down", "size": 12, "color": "#FF1744"},
        ),
        row=1,
        col=1,
    )

if not symbol_trades.empty:
    visible_trades = symbol_trades[
        (symbol_trades["entry_ts"] >= chart.index.min())
        & (symbol_trades["entry_ts"] <= chart.index.max())
    ]
    fig.add_trace(
        go.Scatter(
            x=visible_trades["entry_ts"],
            y=visible_trades["entry_price"],
            mode="markers",
            name="Backtest entries",
            marker={"symbol": "circle-open", "size": 9, "color": "#FFFFFF"},
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=visible_trades["exit_ts"],
            y=visible_trades["exit_price"],
            mode="markers",
            name="Backtest exits",
            marker={"symbol": "x", "size": 9, "color": "#B388FF"},
        ),
        row=1,
        col=1,
    )

fig.add_trace(
    go.Scatter(
        x=chart.index,
        y=chart["adx"],
        name="ADX",
        line={"color": "#42A5F5", "width": 1.5},
    ),
    row=2,
    col=1,
)
fig.add_hline(
    y=cfg.strategy.adx_threshold,
    line={"color": "#FFB300", "dash": "dot"},
    row=2,
    col=1,
)

fig.add_trace(
    go.Bar(
        x=chart.index,
        y=chart["volume"],
        name="Volume",
        marker={"color": "#607D8B"},
    ),
    row=3,
    col=1,
)
fig.update_layout(
    height=820,
    template="plotly_dark",
    xaxis_rangeslider_visible=False,
    hovermode="x unified",
    legend={"orientation": "h", "yanchor": "bottom", "y": 1.02},
)
st.plotly_chart(fig, use_container_width=True)

tab_signals, tab_trades = st.tabs(["Signals", "Backtest trades"])
with tab_signals:
    if signal_df.empty:
        st.info("No signals.")
    else:
        st.dataframe(
            signal_df.sort_values("timestamp", ascending=False).head(300),
            use_container_width=True,
            hide_index=True,
        )

with tab_trades:
    if symbol_trades.empty:
        st.info("No trades for this symbol.")
    else:
        st.dataframe(
            symbol_trades.sort_values("entry_ts", ascending=False),
            use_container_width=True,
            hide_index=True,
        )
