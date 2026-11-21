# engine/storage.py
# ═══════════════════════════════════════════════════════════════
#  Хранилище сигналов и dry-run сделок.
#  По умолчанию — локальный SQLite (data/stocashi_dryrun.db).
#  Если задана переменная окружения DATABASE_URL (например, строка
#  подключения Neon Postgres) — используется она, без изменений кода.
# ═══════════════════════════════════════════════════════════════
from __future__ import annotations
import os
import threading
from typing import Optional

import pandas as pd
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker

import config

Base = declarative_base()
_write_lock = threading.Lock()


class SignalRow(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime(timezone=True), index=True)
    symbol = Column(String(20))
    interval = Column(String(10))
    stocashi_color = Column(String(10))
    stocashi_ha_close = Column(Float, nullable=True)
    macd_line = Column(Float, nullable=True)
    signal_type = Column(String(20))   # buy / sell / flat_no_confirm / none
    note = Column(Text, default="")


class TradeRow(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    direction = Column(String(5))       # long / short
    entry_time = Column(DateTime(timezone=True))
    entry_price = Column(Float)
    exit_time = Column(DateTime(timezone=True), nullable=True)
    exit_price = Column(Float, nullable=True)
    qty = Column(Float)
    pnl_abs = Column(Float, nullable=True)
    pnl_pct = Column(Float, nullable=True)
    status = Column(String(10), default="open")   # open / closed
    close_reason = Column(String(50), default="")


def _make_engine():
    url = config.DATABASE_URL
    if url.startswith("sqlite"):
        os.makedirs("data", exist_ok=True)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, pool_pre_ping=True, future=True, connect_args=connect_args)


_engine = _make_engine()
Base.metadata.create_all(_engine)
SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, future=True)


def get_session():
    return SessionLocal()


# ── Сигналы ──────────────────────────────────────────────────
def log_signal(**kwargs) -> None:
    with _write_lock:
        with get_session() as s:
            s.add(SignalRow(**kwargs))
            s.commit()


def all_signals_df(limit: int = 300) -> pd.DataFrame:
    with get_session() as s:
        rows = s.query(SignalRow).order_by(SignalRow.ts.desc()).limit(limit).all()
        data = [
            dict(
                ts=r.ts, symbol=r.symbol, interval=r.interval,
                stocashi_color=r.stocashi_color,
                stocashi_ha_close=r.stocashi_ha_close,
                macd_line=r.macd_line, signal_type=r.signal_type, note=r.note,
            )
            for r in rows
        ]
    return pd.DataFrame(data)


# ── Сделки ───────────────────────────────────────────────────
def open_trade(direction: str, entry_time, entry_price: float, qty: float) -> TradeRow:
    with _write_lock:
        with get_session() as s:
            t = TradeRow(
                direction=direction, entry_time=entry_time,
                entry_price=entry_price, qty=qty, status="open",
            )
            s.add(t)
            s.commit()
            s.refresh(t)
            return t


def close_open_trade(direction: str, exit_time, exit_price: float,
                      reason: str = "") -> Optional[TradeRow]:
    with _write_lock:
        with get_session() as s:
            t = (
                s.query(TradeRow)
                .filter(TradeRow.direction == direction, TradeRow.status == "open")
                .order_by(TradeRow.entry_time.desc())
                .first()
            )
            if t is None:
                return None
            t.exit_time = exit_time
            t.exit_price = exit_price
            t.status = "closed"
            t.close_reason = reason
            if direction == "long":
                t.pnl_abs = (exit_price - t.entry_price) * t.qty
                t.pnl_pct = (exit_price / t.entry_price - 1.0) * 100.0
            else:  # short
                t.pnl_abs = (t.entry_price - exit_price) * t.qty
                t.pnl_pct = (t.entry_price / exit_price - 1.0) * 100.0
            s.commit()
            s.refresh(t)
            return t


def get_open_trade() -> Optional[TradeRow]:
    with get_session() as s:
        return (
            s.query(TradeRow)
            .filter(TradeRow.status == "open")
            .order_by(TradeRow.entry_time.desc())
            .first()
        )


def all_trades_df() -> pd.DataFrame:
    with get_session() as s:
        rows = s.query(TradeRow).order_by(TradeRow.entry_time.desc()).all()
        data = [
            dict(
                id=r.id, direction=r.direction,
                entry_time=r.entry_time, entry_price=r.entry_price,
                exit_time=r.exit_time, exit_price=r.exit_price,
                qty=r.qty, pnl_abs=r.pnl_abs, pnl_pct=r.pnl_pct,
                status=r.status, close_reason=r.close_reason,
            )
            for r in rows
        ]
    return pd.DataFrame(data)
