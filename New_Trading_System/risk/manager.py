from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Dict, Optional

from config import RiskConfig
from core.models import OrderRequest, Position, Signal, TradeRecord
from core.models import Direction


class RiskManager:
    def __init__(self, cfg: RiskConfig) -> None:
        self.cfg = cfg
        self.current_day: Optional[date] = None
        self.daily_start_equity: float = 0.0
        self.daily_dd_triggered_day: Optional[date] = None
        self.consecutive_losses: int = 0
        self.cooldown_until: Optional[datetime] = None

    def on_bar_start(self, ts: datetime, equity: float) -> None:
        day = ts.date()
        if self.current_day != day:
            self.current_day = day
            self.daily_start_equity = equity
        if self.daily_start_equity > 0:
            dd = (self.daily_start_equity - equity) / self.daily_start_equity
            if dd >= self.cfg.max_daily_dd_pct and self.daily_dd_triggered_day != day:
                self.daily_dd_triggered_day = day
                self._activate_cooldown(ts)

    def on_trade_closed(self, trade: TradeRecord) -> None:
        if trade.net_pnl <= 0:
            self.consecutive_losses += 1
            if self.consecutive_losses >= self.cfg.max_consecutive_losses:
                self._activate_cooldown(trade.exit_ts)
        else:
            self.consecutive_losses = 0

    def _activate_cooldown(self, ts: datetime) -> None:
        target = ts + timedelta(hours=self.cfg.cooldown_hours)
        if self.cooldown_until is None or target > self.cooldown_until:
            self.cooldown_until = target

    def is_trading_halted(self, ts: datetime) -> bool:
        return self.cooldown_until is not None and ts < self.cooldown_until

    def evaluate_signal(
        self,
        signal: Signal,
        equity: float,
        open_positions: Dict[str, Position],
        mark_prices: Dict[str, float],
        ts: datetime,
        macro_bias: Optional[str] = None,
    ) -> Optional[OrderRequest]:
        if equity <= 0 or self.is_trading_halted(ts):
            return None
        if signal.symbol in open_positions:
            return None
        if len(open_positions) >= self.cfg.max_open_positions:
            return None

        stop_dist = abs(signal.entry_price - signal.stop_loss)
        if stop_dist <= 0 or signal.entry_price <= 0:
            return None

        risk_pct = self.cfg.risk_per_trade_pct
        same_direction = sum(
            1 for p in open_positions.values()
            if p.direction == signal.direction
        )
        if same_direction:
            risk_pct *= getattr(self.cfg, "same_direction_risk_mult", 0.5)
        if self.consecutive_losses >= self.cfg.max_consecutive_losses:
            risk_pct *= getattr(self.cfg, "post_streak_risk_mult", 0.5)
        bias = (macro_bias or "").lower()
        counter_macro = (
            bias == "bearish" and signal.direction == Direction.LONG
        ) or (
            bias == "bullish" and signal.direction == Direction.SHORT
        )
        if counter_macro:
            counter_mult = getattr(self.cfg, "counter_macro_risk_mult", 0.5)
            if counter_mult <= 0:
                return None
            risk_pct *= counter_mult

        used_risk = sum(p.current_risk_usd() for p in open_positions.values())
        max_risk = equity * self.cfg.max_portfolio_risk_pct
        target_risk = min(
            equity * risk_pct,
            max(0.0, max_risk - used_risk),
        )
        if target_risk <= 0:
            return None

        qty = target_risk / stop_dist
        notional = qty * signal.entry_price
        used_notional = sum(
            p.qty * mark_prices.get(symbol, p.entry_price)
            for symbol, p in open_positions.items()
        )
        max_symbol_notional = equity * self.cfg.max_symbol_leverage
        max_port_notional = max(
            0.0,
            equity * self.cfg.max_portfolio_leverage - used_notional,
        )
        capped_notional = min(notional, max_symbol_notional, max_port_notional)
        if capped_notional < self.cfg.min_notional_usd:
            return None

        final_qty = capped_notional / signal.entry_price
        final_risk = final_qty * stop_dist
        return OrderRequest(
            symbol=signal.symbol,
            ts=ts,
            direction=signal.direction,
            qty=final_qty,
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            risk_usd=final_risk,
            notional_usd=capped_notional,
            reason=signal.reason,
        )
