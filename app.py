# app.py
# ═══════════════════════════════════════════════════════════════
#  Stocashi + MACD — ETHUSDT H1 Dry Run
#  Streamlit-приложение для Hugging Face Spaces.
#
#  • Фоновый Thread (engine/dry_run_engine.py) опрашивает Binance,
#    считает индикаторы и ведёт dry-run сделки — работает внутри
#    того же процесса, что и этот UI.
#  • Данные (сигналы, сделки) хранятся через engine/storage.py
#    (SQLite по умолчанию, либо Neon Postgres через DATABASE_URL).
# ═══════════════════════════════════════════════════════════════
from __future__ import annotations
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from streamlit_autorefresh import st_autorefresh

import config
from engine import storage
from engine.dry_run_engine import DryRunEngine

st.set_page_config(page_title="Stocashi + MACD — ETH Dry Run", layout="wide", page_icon="📈")


@st.cache_resource(show_spinner=False)
def _get_engine() -> DryRunEngine:
    eng = DryRunEngine()
    eng.start()
    return eng


engine = _get_engine()

# Лёгкое автообновление UI, НЕ блокирующее поток (в отличие от time.sleep+rerun).
st_autorefresh(interval=config.UI_REFRESH_SECONDS * 1000, key="ui_autorefresh")

# ── Шапка / статус ────────────────────────────────────────────
st.title("📈 Stocashi + MACD — ETHUSDT H1 (Dry Run)")

open_trade = storage.get_open_trade()
position_label = open_trade.direction.upper() if open_trade else "FLAT"

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Символ", config.SYMBOL)
c2.metric("Таймфрейм", config.INTERVAL)
c3.metric("Позиция", position_label)
c4.metric("Опрос биржи", f"{config.POLL_SECONDS} с")
c5.metric("Баланс (условный)", f"${config.START_BALANCE:,.0f}")

if engine.last_error:
    st.error(f"⚠️ Ошибка в фоновом движке (будет повторная попытка):\n\n{engine.last_error}")

if engine.last_update:
    st.caption(
        f"Последнее обновление данных: {engine.last_update:%Y-%m-%d %H:%M:%S} UTC "
        f"· UI обновляется каждые {config.UI_REFRESH_SECONDS} с"
    )

df = engine.snapshot()

if df is None or df.empty:
    st.info("⏳ Загружаю первые данные с Binance… страница обновится автоматически.")
    st.stop()

# ── График: цена / Stocashi / MACD ────────────────────────────
plot_df = df.tail(200)  # последние ~200 баров для читаемости

fig = make_subplots(
    rows=3, cols=1, shared_xaxes=True,
    row_heights=[0.5, 0.27, 0.23],
    vertical_spacing=0.03,
    subplot_titles=(f"{config.SYMBOL} — цена", "Stocashi (RSI-Stoch, Heikin-Ashi)", "MACD"),
)

fig.add_trace(
    go.Candlestick(
        x=plot_df.index, open=plot_df["open"], high=plot_df["high"],
        low=plot_df["low"], close=plot_df["close"], name=config.SYMBOL,
        increasing=dict(line=dict(color="#26a69a")),
        decreasing=dict(line=dict(color="#ef5350")),
    ),
    row=1, col=1,
)

if "stocashi_ha_open" in plot_df.columns:
    fig.add_trace(
        go.Candlestick(
            x=plot_df.index,
            open=plot_df["stocashi_ha_open"], high=plot_df["stocashi_ha_high"],
            low=plot_df["stocashi_ha_low"], close=plot_df["stocashi_ha_close"],
            name="Stocashi",
            increasing=dict(line=dict(color="#00e676", width=1), fillcolor="#00e676"),
            decreasing=dict(line=dict(color="#ff1744", width=1), fillcolor="#ff1744"),
            showlegend=True,
        ),
        row=2, col=1,
    )
    for lvl, color in [(50, "#ff4444"), (40, "#ff4444"), (0, "#9e9e9e"), (-40, "#00e676"), (-50, "#00e676")]:
        fig.add_hline(y=lvl, line=dict(color=color, width=1, dash="dot"), row=2, col=1)

if "macd_line" in plot_df.columns:
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df["macd_line"], name="MACD",
                              line=dict(color="#42a5f5", width=1.5)), row=3, col=1)
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df["macd_signal"], name="Signal",
                              line=dict(color="#ffb300", width=1.5)), row=3, col=1)
    hist_colors = ["#26a69a" if v >= 0 else "#ef5350" for v in plot_df["macd_hist"].fillna(0)]
    fig.add_trace(go.Bar(x=plot_df.index, y=plot_df["macd_hist"], name="Hist",
                          marker_color=hist_colors), row=3, col=1)
    fig.add_hline(y=0, line=dict(color="#9e9e9e", width=1, dash="dot"), row=3, col=1)

fig.update_layout(
    height=850,
    xaxis_rangeslider_visible=False,
    xaxis2_rangeslider_visible=False,
    xaxis3_rangeslider_visible=False,
    template="plotly_dark",
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
    margin=dict(l=40, r=20, t=40, b=20),
)
st.plotly_chart(fig, use_container_width=True)

# ── Таблицы: сигналы и сделки ─────────────────────────────────
tab_signals, tab_trades = st.tabs(["📋 Сигналы", "💰 Сделки (dry run)"])

with tab_signals:
    sig_df = storage.all_signals_df(limit=300)
    if sig_df.empty:
        st.info("Сигналов пока нет — ждём первого флипа цвета Stocashi.")
    else:
        st.dataframe(sig_df, use_container_width=True, hide_index=True)

with tab_trades:
    trades_df = storage.all_trades_df()
    if trades_df.empty:
        st.info("Сделок пока нет.")
    else:
        st.dataframe(trades_df, use_container_width=True, hide_index=True)

        closed = trades_df[trades_df["status"] == "closed"]
        if not closed.empty:
            total_pnl = closed["pnl_abs"].sum()
            win_rate = (closed["pnl_abs"] > 0).mean() * 100
            avg_pnl_pct = closed["pnl_pct"].mean()

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Закрытых сделок", len(closed))
            m2.metric("Суммарный PnL", f"${total_pnl:,.2f}")
            m3.metric("Win rate", f"{win_rate:.1f}%")
            m4.metric("Средний PnL/сделку", f"{avg_pnl_pct:.2f}%")

# ── Сайдбар: параметры системы ────────────────────────────────
with st.sidebar:
    st.header("⚙️ Параметры")
    st.write(f"**Индикатор Stocashi**")
    st.json(config.INDICATOR_PARAMS["stocashi"])
    st.write(f"**Индикатор MACD**")
    st.json(config.INDICATOR_PARAMS["macd"])

    st.divider()
    st.write("**Правила сигналов**")
    st.markdown(
        """
- Позиция **закрывается** всегда при смене цвета Stocashi.
- **BUY** (открыть LONG): Stocashi стал зелёным **и** MACD > 0
- **SELL** (открыть SHORT): Stocashi стал красным **и** MACD < 0
- Если цвет сменился, а MACD не подтвердил — остаёмся вне рынка
  до следующей смены цвета.
        """
    )

    st.divider()
    db_kind = "Neon / внешний Postgres" if not config.DATABASE_URL.startswith("sqlite") else "SQLite (локально)"
    st.write(f"**Хранилище:** {db_kind}")

    if st.button("🔄 Обновить сейчас"):
        st.rerun()
