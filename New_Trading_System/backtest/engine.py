from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from config import AppConfig
from core.models import Direction, Position, TradeRecord
from indicators.features import add_indicators
from risk.manager import RiskManager
from strategy.breakout import BreakoutStrategy


@dataclass
class BacktestResult:
    trades: List[TradeRecord]
    equity_curve: pd.Series
    metrics: Dict[str, float]


class PortfolioBacktester:
    def __init__(self, cfg: AppConfig) -> None:
        self.cfg = cfg
        self.strategy = BreakoutStrategy(cfg.strategy)
        self.risk = RiskManager(cfg.risk)

    def run(
        self,
        data_by_symbol: Dict[str, pd.DataFrame],
        macro_df: Optional[pd.DataFrame] = None,
        macro_ema_days: int = 50,
        close_open_positions_at_end: bool = False,
        daily_direction: Optional[pd.Series] = None,
    ) -> BacktestResult:
        self.risk = RiskManager(self.cfg.risk)
        prepared = {
            symbol: add_indicators(df.sort_index(), self.cfg.strategy)
            for symbol, df in data_by_symbol.items()
        }
        all_timestamps = sorted(set().union(*(df.index for df in prepared.values())))
        macro_bias = None
        if daily_direction is not None and not daily_direction.empty:
            daily_index = pd.DatetimeIndex(all_timestamps)
            macro_bias = daily_direction.reindex(daily_index, method="ffill").fillna("neutral")
        elif macro_df is not None and not macro_df.empty:
            daily = macro_df.sort_index()["close"].resample("1D").last().dropna()
            ema = daily.ewm(span=macro_ema_days, adjust=False, min_periods=macro_ema_days).mean()
            raw = pd.Series(
                ["bullish" if c > e else "bearish" for c, e in zip(daily, ema)],
                index=daily.index,
            )
            macro_bias = raw.shift(1).reindex(pd.DatetimeIndex(all_timestamps), method="ffill")

        cash = self.cfg.backtest.initial_capital
        positions: Dict[str, Position] = {}
        trades: List[TradeRecord] = []
        equity_points: List[Tuple[pd.Timestamp, float]] = []
        last_close: Dict[str, float] = {}

        fee_rate = self.cfg.backtest.taker_fee_rate
        slip = self.cfg.backtest.slippage_rate
        funding_rate = self.cfg.backtest.funding_rate_per_2h

        for ts in all_timestamps:
            ts_dt = ts.to_pydatetime()
            closed_this_bar: set[str] = set()

            for symbol, df in prepared.items():
                if ts in df.index:
                    last_close[symbol] = float(df.loc[ts, "close"])

            for symbol in list(positions.keys()):
                df = prepared[symbol]
                if ts not in df.index:
                    continue

                bar = df.loc[ts]
                pos = positions[symbol]
                bar_open = float(bar["open"])
                bar_high = float(bar["high"])
                bar_low = float(bar["low"])
                bar_close = float(bar["close"])

                stopped = False
                exit_price = 0.0
                if pos.direction == Direction.LONG and bar_low <= pos.stop_loss:
                    stopped = True
                    raw_fill = min(bar_open, pos.stop_loss)
                    exit_price = raw_fill * (1.0 - slip)
                elif pos.direction == Direction.SHORT and bar_high >= pos.stop_loss:
                    stopped = True
                    raw_fill = max(bar_open, pos.stop_loss)
                    exit_price = raw_fill * (1.0 + slip)

                if stopped:
                    gross_pnl = (
                        (exit_price - pos.entry_price) * pos.qty
                        if pos.direction == Direction.LONG
                        else (pos.entry_price - exit_price) * pos.qty
                    )
                    exit_fee = pos.qty * exit_price * fee_rate
                    cash += gross_pnl - exit_fee
                    net_pnl = gross_pnl - pos.entry_fee - exit_fee - pos.funding_paid
                    stop_moved = pos.trailing_moved or pos.be_moved or abs(pos.stop_loss - pos.initial_stop) > 1e-9
                    initial_risk_usd = pos.initial_risk_per_unit * pos.qty
                    trade = TradeRecord(
                        symbol=symbol,
                        direction=pos.direction,
                        entry_ts=pos.entry_ts,
                        exit_ts=ts_dt,
                        entry_price=pos.entry_price,
                        exit_price=exit_price,
                        qty=pos.qty,
                        gross_pnl=gross_pnl,
                        fees=pos.entry_fee + exit_fee,
                        funding=pos.funding_paid,
                        net_pnl=net_pnl,
                        r_multiple=net_pnl / initial_risk_usd if initial_risk_usd > 0 else 0.0,
                        exit_reason="trailing_or_be_stop" if stop_moved else "initial_sl",
                    )
                    trades.append(trade)
                    self.risk.on_trade_closed(trade)
                    del positions[symbol]
                    closed_this_bar.add(symbol)
                    continue

                raw_funding = (
                    float(bar["funding_rate"])
                    if "funding_rate" in bar and not pd.isna(bar["funding_rate"])
                    else funding_rate
                )
                funding_sign = (
                    1.0 if pos.direction == Direction.LONG else -1.0
                ) if getattr(self.cfg.backtest, "directional_funding", True) else 1.0
                funding = funding_sign * pos.qty * bar_close * raw_funding
                cash -= funding
                pos.funding_paid += funding
                pos.stop_loss = self.strategy.compute_updated_stop(
                    pos,
                    bar_high=bar_high,
                    bar_low=bar_low,
                    atr=float(bar["atr"]),
                )

            equity = cash + sum(
                pos.unrealized_pnl(last_close.get(symbol, pos.entry_price))
                for symbol, pos in positions.items()
            )
            equity_points.append((ts, equity))
            if equity <= 0:
                break

            self.risk.on_bar_start(ts_dt, equity)

            candidates = []
            for symbol, df in prepared.items():
                if symbol in positions or symbol in closed_this_bar or ts not in df.index:
                    continue
                current_macro = (
                    str(macro_bias.loc[ts])
                    if macro_bias is not None and ts in macro_bias.index
                    else None
                )
                signal = self.strategy.generate_signal(
                    symbol,
                    ts_dt,
                    df.loc[ts],
                    macro_bias=current_macro,
                )
                if signal is not None:
                    candidates.append(signal)
            candidates.sort(key=lambda signal: signal.adx, reverse=True)

            for signal in candidates:
                order = self.risk.evaluate_signal(
                    signal,
                    equity,
                    positions,
                    last_close,
                    ts_dt,
                    macro_bias=(
                        str(macro_bias.loc[ts])
                        if macro_bias is not None and ts in macro_bias.index
                        else None
                    ),
                )
                if order is None:
                    continue

                fill_price = (
                    order.entry_price * (1.0 + slip)
                    if order.direction == Direction.LONG
                    else order.entry_price * (1.0 - slip)
                )
                entry_fee = order.qty * fill_price * fee_rate
                cash -= entry_fee
                positions[signal.symbol] = Position(
                    symbol=signal.symbol,
                    direction=order.direction,
                    entry_ts=ts_dt,
                    entry_price=fill_price,
                    qty=order.qty,
                    initial_stop=order.stop_loss,
                    stop_loss=order.stop_loss,
                    initial_risk_per_unit=abs(fill_price - order.stop_loss),
                    highest_price=fill_price,
                    lowest_price=fill_price,
                    entry_fee=entry_fee,
                )

        if close_open_positions_at_end and positions and equity_points:
            last_ts = equity_points[-1][0]
            for symbol in list(positions.keys()):
                pos = positions[symbol]
                mark = last_close.get(symbol, pos.entry_price)
                exit_price = (
                    mark * (1.0 - slip)
                    if pos.direction == Direction.LONG
                    else mark * (1.0 + slip)
                )
                gross_pnl = (
                    (exit_price - pos.entry_price) * pos.qty
                    if pos.direction == Direction.LONG
                    else (pos.entry_price - exit_price) * pos.qty
                )
                exit_fee = pos.qty * exit_price * fee_rate
                net_pnl = gross_pnl - pos.entry_fee - exit_fee - pos.funding_paid
                initial_risk_usd = pos.initial_risk_per_unit * pos.qty
                trades.append(TradeRecord(
                    symbol=symbol,
                    direction=pos.direction,
                    entry_ts=pos.entry_ts,
                    exit_ts=last_ts.to_pydatetime(),
                    entry_price=pos.entry_price,
                    exit_price=exit_price,
                    qty=pos.qty,
                    gross_pnl=gross_pnl,
                    fees=pos.entry_fee + exit_fee,
                    funding=pos.funding_paid,
                    net_pnl=net_pnl,
                    r_multiple=net_pnl / initial_risk_usd if initial_risk_usd > 0 else 0.0,
                    exit_reason="end_of_backtest",
                ))
                cash += gross_pnl - exit_fee
                del positions[symbol]
            equity_points[-1] = (last_ts, cash)

        equity_series = pd.Series(
            [value for _, value in equity_points],
            index=pd.DatetimeIndex([timestamp for timestamp, _ in equity_points]),
            name="equity",
        )
        return BacktestResult(
            trades=trades,
            equity_curve=equity_series,
            metrics=self._compute_metrics(trades, equity_series),
        )

    def _compute_metrics(
        self,
        trades: List[TradeRecord],
        equity: pd.Series,
    ) -> Dict[str, float]:
        if equity.empty:
            return {}
        start_capital = self.cfg.backtest.initial_capital
        total_return = equity.iloc[-1] / start_capital - 1.0

        running_max = equity.cummax()
        drawdown = (equity - running_max) / running_max
        max_drawdown = float(drawdown.min())

        daily_equity = equity.resample("1D").last().dropna()
        returns = daily_equity.pct_change().dropna()
        sharpe = (
            float((returns.mean() / returns.std()) * np.sqrt(365))
            if len(returns) > 1 and returns.std() > 0
            else 0.0
        )

        wins = [trade.net_pnl for trade in trades if trade.net_pnl > 0]
        losses = [trade.net_pnl for trade in trades if trade.net_pnl <= 0]
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
        win_rate = len(wins) / len(trades) if trades else 0.0
        avg_r = float(np.mean([trade.r_multiple for trade in trades])) if trades else 0.0

        return {
            "final_equity": round(float(equity.iloc[-1]), 2),
            "total_return_pct": round(total_return * 100, 2),
            "max_drawdown_pct": round(max_drawdown * 100, 2),
            "sharpe_ratio": round(sharpe, 2),
            "trades_count": len(trades),
            "win_rate_pct": round(win_rate * 100, 2),
            "profit_factor": round(profit_factor, 2),
            "avg_r_multiple": round(avg_r, 3),
        }
