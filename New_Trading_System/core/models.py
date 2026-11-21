from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class Direction(str, Enum):
    LONG = "long"
    SHORT = "short"


@dataclass(frozen=True)
class Signal:
    symbol: str
    ts: datetime
    direction: Direction
    entry_price: float
    stop_loss: float
    atr: float
    adx: float
    reason: str


@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    ts: datetime
    direction: Direction
    qty: float
    entry_price: float
    stop_loss: float
    risk_usd: float
    notional_usd: float
    reason: str


@dataclass
class Position:
    symbol: str
    direction: Direction
    entry_ts: datetime
    entry_price: float
    qty: float
    initial_stop: float
    stop_loss: float
    initial_risk_per_unit: float
    highest_price: float
    lowest_price: float
    entry_fee: float = 0.0
    funding_paid: float = 0.0
    be_moved: bool = False
    exchange_order_id: Optional[str] = None
    exchange_sl_id: Optional[str] = None
    trailing_moved: bool = False

    def unrealized_pnl(self, mark_price: float) -> float:
        if self.direction == Direction.LONG:
            return (mark_price - self.entry_price) * self.qty
        return (self.entry_price - mark_price) * self.qty

    def current_risk_usd(self) -> float:
        if self.direction == Direction.LONG:
            dist = max(0.0, self.entry_price - self.stop_loss)
        else:
            dist = max(0.0, self.stop_loss - self.entry_price)
        return dist * self.qty

    def r_multiple(self, price: float) -> float:
        if self.initial_risk_per_unit <= 0:
            return 0.0
        if self.direction == Direction.LONG:
            return (price - self.entry_price) / self.initial_risk_per_unit
        return (self.entry_price - price) / self.initial_risk_per_unit


@dataclass(frozen=True)
class TradeRecord:
    symbol: str
    direction: Direction
    entry_ts: datetime
    exit_ts: datetime
    entry_price: float
    exit_price: float
    qty: float
    gross_pnl: float
    fees: float
    funding: float
    net_pnl: float
    r_multiple: float
    exit_reason: str
