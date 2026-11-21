Ниже — готовое ядро портфельной системы пробоя волатильности (**Volatility Breakout + ATR Risk Engine**), откалиброванное под фьючерсы **ETH, SOL, BNB на таймфрейме 2H**, и структурированное ТЗ для агента, чтобы дописать инфраструктуру и собрать проект в рабочий пайплайн.

Главная особенность для связки `ETH + SOL + BNB` — высокая корреляция. В риск-менеджер сразу заложен **портфельный контроль риска**: как только сделка по одной монете переходит в безубыток, её риск обнуляется и освобождает лимит для входа по другому активу; при одновременном сигнале приоритет получает монета с наибольшим `ADX`.

## Архитектура проекта

```text
trading_bot/
├── config.py                # [ГОТОВО] Параметры стратегии, рисков и фьючерсов
├── core/
│   └── models.py            # [ГОТОВО] Контракты данных (Signal, Position, Order, Trade)
├── indicators/
│   └── features.py          # [ГОТОВО] Векторные индикаторы без lookahead bias
├── strategy/
│   └── breakout.py          # [ГОТОВО] Stateless-генератор сигналов + логика BE/Chandelier
├── risk/
│   └── manager.py           # [ГОТОВО] ATR-сайзинг, лимиты плеча/корреляции, circuit breaker
├── backtest/
│   └── engine.py            # [ГОТОВО] Мультиактивный событийный бэктестер (USDT-M futures)
├── data/
│   └── feed.py              # [АГЕНТУ] Загрузка истории + стриминг закрытых 2H свечей (ccxt)
├── storage/
│   └── db.py                # [АГЕНТУ] SQLite/SQLAlchemy: сделки, состояние, защита от дублей
├── execution/
│   └── broker.py            # [АГЕНТУ] Интерфейс Broker: PaperBroker + Binance/Bybit Futures
├── run_backtest.py          # [АГЕНТУ] CLI для бэктеста и Walk-Forward анализа
├── run_live.py              # [АГЕНТУ] Оркестратор реального времени + Telegram-алерты
└── tests/                   # [АГЕНТУ] Unit-тесты на lookahead, SL-гэпы и идемпотентность

```

---

## Готовые модули ядра

### 1. `config.py`

```python
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass(frozen=True)
class StrategyConfig:
    symbols: tuple[str, ...] = ("ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT")
    timeframe: str = "2h"

    # Фильтр тренда и волатильности (2H: EMA200 ≈ 16.6 дней, Donchian20 ≈ 40 часов)
    ema_trend_len: int = 200
    donchian_len: int = 20
    atr_len: int = 14
    adx_len: int = 14
    adx_threshold: float = 20.0
    vol_ma_len: int = 20
    vol_mult: float = 1.15

    # Защита от входа на излёте аномальной свечи (сквиза)
    max_body_atr: float = 2.8

    # Сопровождение позиции (в единицах ATR)
    sl_atr_mult: float = 2.0          # Начальный стоп-лосс
    be_trigger_r: float = 1.5         # Перевод в безубыток при +1.5R
    be_offset_pct: float = 0.0012     # Запас на комиссии при переводе в БУ (0.12%)
    trail_atr_mult: float = 2.5       # Chandelier trailing stop
    trail_activation_r: float = 1.0   # Активация трейлинга после +1.0R


@dataclass(frozen=True)
class RiskConfig:
    risk_per_trade_pct: float = 0.0075     # 0.75% от текущего equity на сделку
    max_portfolio_risk_pct: float = 0.015  # Макс. открытый риск по всем монетам (1.5%)
    max_open_positions: int = 2            # Не более 2 одновременных позиций из 3 коррелирующих
    max_symbol_leverage: float = 1.5       # Потолок плеча на 1 монету
    max_portfolio_leverage: float = 2.5    # Суммарный потолок плеча портфеля
    min_notional_usd: float = 20.0

    # Circuit Breaker (стоп-кран)
    max_daily_dd_pct: float = 0.04         # Пауза при дневной просадке -4%
    max_consecutive_losses: int = 5        # Пауза после 5 стопов подряд
    cooldown_hours: int = 24


@dataclass(frozen=True)
class BacktestConfig:
    initial_capital: float = 10_000.0
    taker_fee_rate: float = 0.0005         # 0.05% на сторону (Binance/Bybit Taker)
    slippage_rate: float = 0.0004          # 0.04% проскальзывание на рыночных ордерах
    funding_rate_per_2h: float = 0.000025  # ~0.01% каждые 8 часов


@dataclass(frozen=True)
class AppConfig:
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)

```

### 2. `core/models.py`

```python
from __future__ import annotations
from dataclasses import dataclass, field
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

    def unrealized_pnl(self, mark_price: float) -> float:
        if self.direction == Direction.LONG:
            return (mark_price - self.entry_price) * self.qty
        return (self.entry_price - mark_price) * self.qty

    def current_risk_usd(self) -> float:
        """Остаточный риск в USD. Если стоп уже в БУ или в плюсе — риск 0."""
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

```

### 3. `indicators/features.py`

```python
from __future__ import annotations
import numpy as np
import pandas as pd

from config import StrategyConfig


def _wilder_rma(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def add_indicators(df: pd.DataFrame, cfg: StrategyConfig) -> pd.DataFrame:
    """
    Чистая функция расчёта индикаторов без lookahead bias.
    Ожидает df с DatetimeIndex (UTC) и колонками: open, high, low, close, volume.
    """
    out = df.copy()
    high = out["high"].astype(float)
    low = out["low"].astype(float)
    close = out["close"].astype(float)
    open_ = out["open"].astype(float)
    volume = out["volume"].astype(float)

    # 1. Глобальный тренд
    out["ema_trend"] = close.ewm(span=cfg.ema_trend_len, adjust=False, min_periods=cfg.ema_trend_len).mean()

    # 2. Канал Дончиана со сдвигом на 1 бар (пробой предыдущих N свечей)
    out["dc_high"] = high.rolling(cfg.donchian_len, min_periods=cfg.donchian_len).max().shift(1)
    out["dc_low"] = low.rolling(cfg.donchian_len, min_periods=cfg.donchian_len).min().shift(1)

    # 3. True Range и ATR (сглаживание Уайлдера)
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    out["atr"] = _wilder_rma(tr, cfg.atr_len)

    # 4. ADX (фильтр боковика)
    up_move = high - high.shift(1)
    down_move = low.shift(1) - low
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=out.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=out.index)

    atr_adx = _wilder_rma(tr, cfg.adx_len).replace(0.0, np.nan)
    plus_di = 100.0 * (_wilder_rma(plus_dm, cfg.adx_len) / atr_adx)
    minus_di = 100.0 * (_wilder_rma(minus_dm, cfg.adx_len) / atr_adx)
    di_sum = (plus_di + minus_di).replace(0.0, np.nan)
    dx = 100.0 * (plus_di - minus_di).abs() / di_sum
    out["adx"] = _wilder_rma(dx, cfg.adx_len)

    # 5. Фильтр объёма (сдвиг на 1, чтобы сама пробойная свеча не завышала базу)
    out["vol_ma"] = volume.rolling(cfg.vol_ma_len, min_periods=cfg.vol_ma_len).mean().shift(1)

    # 6. Тело свечи для фильтра перегретых импульсов
    out["body_size"] = (close - open_).abs()

    return out

```

### 4. `strategy/breakout.py`

```python
from __future__ import annotations
from datetime import datetime
from typing import Optional
import pandas as pd

from config import StrategyConfig
from core.models import Direction, Position, Signal


class BreakoutStrategy:
    """Stateless-ядро стратегии: одинаково используется в бэктесте и в проде."""

    def __init__(self, cfg: StrategyConfig) -> None:
        self.cfg = cfg

    def generate_signal(self, symbol: str, ts: datetime, bar: pd.Series) -> Optional[Signal]:
        required = ("close", "volume", "ema_trend", "dc_high", "dc_low", "atr", "adx", "vol_ma", "body_size")
        if any(pd.isna(bar.get(col)) for col in required):
            return None

        close = float(bar["close"])
        atr = float(bar["atr"])
        adx = float(bar["adx"])
        ema = float(bar["ema_trend"])
        dc_high = float(bar["dc_high"])
        dc_low = float(bar["dc_low"])
        vol = float(bar["volume"])
        vol_ma = float(bar["vol_ma"])
        body = float(bar["body_size"])

        if atr <= 0 or close <= 0 or vol_ma <= 0:
            return None

        # Фильтр боковика, объёма и перегретой свечи
        if adx < self.cfg.adx_threshold:
            return None
        if vol < vol_ma * self.cfg.vol_mult:
            return None
        if body > atr * self.cfg.max_body_atr:
            return None

        # Пробой вверх по тренду
        if close > ema and close > dc_high:
            stop_loss = close - atr * self.cfg.sl_atr_mult
            return Signal(
                symbol=symbol,
                ts=ts,
                direction=Direction.LONG,
                entry_price=close,
                stop_loss=stop_loss,
                atr=atr,
                adx=adx,
                reason="donchian_breakout_long",
            )

        # Пробой вниз по тренду
        if close < ema and close < dc_low:
            stop_loss = close + atr * self.cfg.sl_atr_mult
            return Signal(
                symbol=symbol,
                ts=ts,
                direction=Direction.SHORT,
                entry_price=close,
                stop_loss=stop_loss,
                atr=atr,
                adx=adx,
                reason="donchian_breakout_short",
            )

        return None

    def compute_updated_stop(self, pos: Position, bar_high: float, bar_low: float, atr: float) -> float:
        """
        Вызывается ПОСЛЕ проверки срабатывания текущего стопа на закрытой свече.
        Возвращает новый уровень стопа (двигается строго в сторону прибыли).
        """
        if pd.isna(atr) or atr <= 0:
            return pos.stop_loss

        new_stop = pos.stop_loss

        if pos.direction == Direction.LONG:
            pos.highest_price = max(pos.highest_price, bar_high)
            max_r = pos.r_multiple(pos.highest_price)

            if not pos.be_moved and max_r >= self.cfg.be_trigger_r:
                be_level = pos.entry_price * (1.0 + self.cfg.be_offset_pct)
                new_stop = max(new_stop, be_level)
                pos.be_moved = True

            if max_r >= self.cfg.trail_activation_r:
                chandelier = pos.highest_price - atr * self.cfg.trail_atr_mult
                new_stop = max(new_stop, chandelier)

        else:
            pos.lowest_price = min(pos.lowest_price, bar_low)
            max_r = pos.r_multiple(pos.lowest_price)

            if not pos.be_moved and max_r >= self.cfg.be_trigger_r:
                be_level = pos.entry_price * (1.0 - self.cfg.be_offset_pct)
                new_stop = min(new_stop, be_level)
                pos.be_moved = True

            if max_r >= self.cfg.trail_activation_r:
                chandelier = pos.lowest_price + atr * self.cfg.trail_atr_mult
                new_stop = min(new_stop, chandelier)

        return new_stop

```

### 5. `risk/manager.py`

```python
from __future__ import annotations
from datetime import date, datetime, timedelta
from typing import Dict, Optional

from config import RiskConfig
from core.models import OrderRequest, Position, Signal, TradeRecord


class RiskManager:
    """Портфельный риск-менеджер: сайзинг от ATR, лимиты плеча и circuit breaker."""

    def __init__(self, cfg: RiskConfig) -> None:
        self.cfg = cfg
        self.current_day: Optional[date] = None
        self.daily_start_equity: float = 0.0
        self.consecutive_losses: int = 0
        self.cooldown_until: Optional[datetime] = None

    def on_bar_start(self, ts: datetime, equity: float) -> None:
        day = ts.date()
        if self.current_day != day:
            self.current_day = day
            self.daily_start_equity = equity

        if self.daily_start_equity > 0:
            daily_dd = (self.daily_start_equity - equity) / self.daily_start_equity
            if daily_dd >= self.cfg.max_daily_dd_pct:
                self._activate_cooldown(ts)

    def on_trade_closed(self, trade: TradeRecord) -> None:
        if trade.net_pnl < 0:
            self.consecutive_losses += 1
            if self.consecutive_losses >= self.cfg.max_consecutive_losses:
                self._activate_cooldown(trade.exit_ts)
                self.consecutive_losses = 0
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

        # 1. Проверка свободного портфельного бюджета риска
        used_risk_usd = sum(p.current_risk_usd() for p in open_positions.values())
        max_port_risk_usd = equity * self.cfg.max_portfolio_risk_pct
        avail_risk_usd = max(0.0, max_port_risk_usd - used_risk_usd)
        target_risk_usd = min(equity * self.cfg.risk_per_trade_pct, avail_risk_usd)

        if target_risk_usd <= 0:
            return None

        qty = target_risk_usd / stop_dist
        notional = qty * signal.entry_price

        # 2. Ограничение плеча на инструмент и на весь портфель
        used_notional = sum(
            p.qty * mark_prices.get(sym, p.entry_price)
            for sym, p in open_positions.items()
        )
        max_sym_notional = equity * self.cfg.max_symbol_leverage
        max_port_notional = max(0.0, equity * self.cfg.max_portfolio_leverage - used_notional)
        capped_notional = min(notional, max_sym_notional, max_port_notional)

        if capped_notional < self.cfg.min_notional_usd:
            return None

        final_qty = capped_notional / signal.entry_price
        final_risk_usd = final_qty * stop_dist

        return OrderRequest(
            symbol=signal.symbol,
            ts=ts,
            direction=signal.direction,
            qty=final_qty,
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            risk_usd=final_risk_usd,
            notional_usd=capped_notional,
            reason=signal.reason,
        )

```

### 6. `backtest/engine.py`

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Tuple
import numpy as np
import pandas as pd

from config import AppConfig
from core.models import Direction, Position, Signal, TradeRecord
from indicators.features import add_indicators
from risk.manager import RiskManager
from strategy.breakout import BreakoutStrategy


@dataclass
class BacktestResult:
    trades: List[TradeRecord]
    equity_curve: pd.Series
    metrics: Dict[str, float]


class PortfolioBacktester:
    """Событийный мультиактивный бэктестер для USDT-M фьючерсов."""

    def __init__(self, cfg: AppConfig) -> None:
        self.cfg = cfg
        self.strategy = BreakoutStrategy(cfg.strategy)
        self.risk = RiskManager(cfg.risk)

    def run(self, data_by_symbol: Dict[str, pd.DataFrame]) -> BacktestResult:
        prepared = {
            sym: add_indicators(df.sort_index(), self.cfg.strategy)
            for sym, df in data_by_symbol.items()
        }

        all_timestamps = sorted(set().union(*(df.index for df in prepared.values())))
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

            # Обновляем известные цены закрытия
            for sym, df in prepared.items():
                if ts in df.index:
                    last_close[sym] = float(df.loc[ts, "close"])

            # 1. Проверка стопов и списание фандинга по открытым позициям
            for sym in list(positions.keys()):
                df = prepared[sym]
                if ts not in df.index:
                    continue

                bar = df.loc[ts]
                pos = positions[sym]
                bar_open = float(bar["open"])
                bar_high = float(bar["high"])
                bar_low = float(bar["low"])
                bar_close = float(bar["close"])

                # Сначала проверка внутрисвечного пробития стопа (консервативный порядок)
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
                    gross = (
                        (exit_price - pos.entry_price) * pos.qty
                        if pos.direction == Direction.LONG
                        else (pos.entry_price - exit_price) * pos.qty
                    )
                    exit_fee = pos.qty * exit_price * fee_rate
                    cash += gross - exit_fee
                    net_pnl = gross - pos.entry_fee - exit_fee - pos.funding_paid

                    trade = TradeRecord(
                        symbol=sym,
                        direction=pos.direction,
                        entry_ts=pos.entry_ts,
                        exit_ts=ts_dt,
                        entry_price=pos.entry_price,
                        exit_price=exit_price,
                        qty=pos.qty,
                        gross_pnl=gross,
                        fees=pos.entry_fee + exit_fee,
                        funding=pos.funding_paid,
                        net_pnl=net_pnl,
                        r_multiple=pos.r_multiple(exit_price),
                        exit_reason="trailing_or_be_stop" if pos.be_moved else "initial_sl",
                    )
                    trades.append(trade)
                    self.risk.on_trade_closed(trade)
                    del positions[sym]
                    closed_this_bar.add(sym)
                    continue

                # Позиция выжила: учитываем фандинг и подтягиваем стоп на следующий бар
                funding = pos.qty * bar_close * funding_rate
                cash -= funding
                pos.funding_paid += funding
                pos.stop_loss = self.strategy.compute_updated_stop(
                    pos, bar_high=bar_high, bar_low=bar_low, atr=float(bar["atr"])
                )

            # 2. Mark-to-market equity и проверка дневного circuit breaker
            equity = cash + sum(
                p.unrealized_pnl(last_close.get(s, p.entry_price))
                for s, p in positions.items()
            )
            equity_points.append((ts, equity))
            if equity <= 0:
                break

            self.risk.on_bar_start(ts_dt, equity)

            # 3. Сбор новых сигналов по свободным инструментам
            candidates: List[Signal] = []
            for sym, df in prepared.items():
                if sym in positions or sym in closed_this_bar or ts not in df.index:
                    continue
                sig = self.strategy.generate_signal(sym, ts_dt, df.loc[ts])
                if sig is not None:
                    candidates.append(sig)

            # При одновременном сигнале приоритет монете с самым сильным трендом (ADX)
            candidates.sort(key=lambda s: s.adx, reverse=True)

            for sig in candidates:
                order = self.risk.evaluate_signal(sig, equity, positions, last_close, ts_dt)
                if order is None:
                    continue

                fill_price = (
                    order.entry_price * (1.0 + slip)
                    if order.direction == Direction.LONG
                    else order.entry_price * (1.0 - slip)
                )
                entry_fee = order.qty * fill_price * fee_rate
                cash -= entry_fee

                positions[sig.symbol] = Position(
                    symbol=sig.symbol,
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

        eq_series = pd.Series(
            [v for _, v in equity_points],
            index=pd.DatetimeIndex([t for t, _ in equity_points]),
            name="equity",
        )
        return BacktestResult(
            trades=trades,
            equity_curve=eq_series,
            metrics=self._compute_metrics(trades, eq_series),
        )

    def _compute_metrics(self, trades: List[TradeRecord], eq: pd.Series) -> Dict[str, float]:
        if eq.empty:
            return {}
        start_cap = self.cfg.backtest.initial_capital
        total_return = (eq.iloc[-1] / start_cap) - 1.0

        running_max = eq.cummax()
        dd = (eq - running_max) / running_max
        max_dd = float(dd.min())

        # Аннуализация для 2H свечей (12 баров/день * 365 = 4380 баров/год)
        returns = eq.pct_change().dropna()
        sharpe = (
            float((returns.mean() / returns.std()) * np.sqrt(4380))
            if len(returns) > 1 and returns.std() > 0
            else 0.0
        )

        wins = [t.net_pnl for t in trades if t.net_pnl > 0]
        losses = [t.net_pnl for t in trades if t.net_pnl <= 0]
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")
        win_rate = (len(wins) / len(trades)) if trades else 0.0
        avg_r = float(np.mean([t.r_multiple for t in trades])) if trades else 0.0

        return {
            "final_equity": round(float(eq.iloc[-1]), 2),
            "total_return_pct": round(total_return * 100, 2),
            "max_drawdown_pct": round(max_dd * 100, 2),
            "sharpe_ratio": round(sharpe, 2),
            "trades_count": len(trades),
            "win_rate_pct": round(win_rate * 100, 2),
            "profit_factor": round(profit_factor, 2),
            "avg_r_multiple": round(avg_r, 3),
        }

```

---

## Инструкция для передачи кодинг-агенту (скопируй как ТЗ)

Ниже — готовый промпт-спецификация. Сохрани модули выше в репозиторий и передай агенту этот блок:

> **Контекст и ограничения:**
> В репозитории уже реализовано ядро торговой системы (`config.py`, `core/models.py`, `indicators/features.py`, `strategy/breakout.py`, `risk/manager.py`, `backtest/engine.py`) под фьючерсы `ETH/USDT:USDT`, `SOL/USDT:USDT`, `BNB/USDT:USDT` на таймфрейме `2h`.
> **Запрещено** менять торговую логику и контракты в `core/models.py`, `strategy/breakout.py` и `risk/manager.py`, если не найден явный баг. Все новые модули должны строго использовать эти типы и классы.
> **Задача — дописать 5 модулей и покрыть систему тестами:**
> **1. `data/feed.py` (Загрузчик и кэш рыночных данных на `ccxt`)**
> * Использовать `ccxt` (Binance USDM или Bybit Linear, выбор через `.env`).
> * Реализовать `fetch_ohlcv_history(symbol, timeframe="2h", since_days=730) -> pd.DataFrame` с пагинацией, rate-limit handling и сохранением кэша в `data/cache/{symbol}_2h.parquet` (инкрементальное дозаполнение только недостающих баров).
> * Реализовать `fetch_latest_closed_bars(symbol, timeframe="2h", limit=300) -> pd.DataFrame`: **строго отбрасывать последнюю незакрытую свечу** (проверять `bar_open_ts + 2h <= utc_now()`).
> * Индекс DataFrame всегда `pd.DatetimeIndex` в UTC без дубликатов и с проверкой на пропуски свечей (логировать warning при гэпах).
> 
> 
> **2. `storage/db.py` (Персистентность на SQLite)**
> * Таблицы: `positions` (активные позиции), `trades` (история закрытых сделок), `processed_bars` (`symbol`, `ts` — UNIQUE для идемпотентности), `risk_state` (`current_day`, `daily_start_equity`, `consecutive_losses`, `cooldown_until`).
> * При перезапуске бота `RiskManager` и словарь `open_positions` должны полностью восстанавливаться из SQLite без потери состояния стопов и счётчика убытков.
> 
> 
> **3. `execution/broker.py` (Абстракция исполнения)**
> * Базовый ABC-класс `BaseBroker` с методами: `get_equity() -> float`, `get_open_positions() -> dict`, `open_market_with_sl(order: OrderRequest) -> Position`, `update_stop_loss(pos: Position, new_stop: float) -> str`, `sync_positions_from_exchange()`.
> * Реализация `PaperBroker` (локальная симуляция с сохранением в SQLite, для прогона в реальном времени без биржевых ключей).
> * Реализация `CcxtFuturesBroker`:
> * Настройка `isolated` или `cross` маржи и плеча (`3x` технический потолок на бирже) при старте.
> * Округление `qty` и `stop_loss` через `exchange.amount_to_precision` / `price_to_precision`.
> * **Критично:** стоп-лосс выставляется на стороне биржи (`STOP_MARKET` с `reduceOnly=True`). При обновлении трейлинга — сначала ставить новый SL, затем отменять старый (или использовать атомарный edit, если биржа поддерживает), чтобы позиция никогда не оставалась без защиты.
> * Поддержка `testnet=True` по умолчанию.
> 
> 
> 
> 
> **4. `run_backtest.py` (Валидация стратегии)**
> * Загружает 2 года данных по `ETH`, `SOL`, `BNB` (2H) через `data/feed.py`.
> * Запускает `PortfolioBacktester` на полном периоде + делает **Walk-Forward сплит** (70% In-Sample / 30% Out-of-Sample) + **стресс-тест комиссий** (x1.5 `taker_fee_rate` и x1.5 `slippage_rate`).
> * Выводит таблицу метрик в консоль (общие + отдельно по каждой монете), сохраняет `reports/equity_curve.png` и `reports/trades.csv`.
> 
> 
> **5. `run_live.py` (Цикл реального времени)**
> * Запускается по расписанию сразу после закрытия каждой 2H свечи (UTC 00:00:05, 02:00:05, ..., 22:00:05) через `APScheduler` или цикл с точным расчётом `sleep` до следующей границы 2H + 5 секунд буфера.
> * Алгоритм тика:
> 1. `broker.sync_positions_from_exchange()` — обнаружить, если биржевой SL уже сработал внутри свечи; зафиксировать `TradeRecord` в SQLite и вызвать `risk.on_trade_closed()`.
> 2. Загрузить закрытые свечи (`limit=300`) по всем 3 монетам, пропустить уже обработанные `ts` через `processed_bars`.
> 3. Посчитать `add_indicators`. Для оставшихся открытых позиций пересчитать стоп через `strategy.compute_updated_stop()` и, если стоп сдвинулся, обновить его на бирже через `broker.update_stop_loss()`.
> 4. Вызвать `risk.on_bar_start(ts, equity)`, собрать сигналы через `strategy.generate_signal()`, отсортировать по `adx` убыванию, прогнать через `risk.evaluate_signal()` и исполнить через `broker.open_market_with_sl()`.
> 5. Отправить краткое уведомление в Telegram при открытии/закрытии сделки, срабатывании circuit breaker или необработанном исключении.
> 
> 
> * Добавить `Dockerfile`, `requirements.txt` и `.env.example`.
> 
> 
> **6. `tests/` (Обязательные unit-тесты на `pytest`)**
> * `test_no_lookahead`: добавление/изменение последних 10 свечей не должно менять значения индикаторов и сигналов на более ранних барах.
> * `test_sl_gap_and_trailing`: проверка, что при гэпе ниже стопа позиция закрывается по `open` (а не по `stop_loss`), и что трейлинг-стоп никогда не откатывается назад.
> * `test_portfolio_risk_caps`: проверка, что при 3 одновременных сигналах открываются максимум 2 позиции, а при переходе 1-й в безубыток её риск обнуляется.
> * `test_idempotency`: повторный прогон `run_live` на том же таймстемпе не создаёт дублей ордеров.
> 
> 
> **Порядок выполнения:**
> 1. Создай зависимости (`requirements.txt`) и реализуй `data/feed.py` + `run_backtest.py`.
> 2. Прогони реальный бэктест на 2 годах истории `ETH/SOL/BNB 2H` и покажи отчёт с метриками (полный период, OOS и стресс-тест комиссий).
> 3. Только после успешной проверки бэктеста переходи к `storage/db.py`, `execution/broker.py`, `run_live.py` и тестам.
> 
> 

---

После того как агент выполнит шаги 1–2 и выдаст результаты первого бэктеста (метрики, просадку и статистику по каждой из трёх монет), приноси цифры сюда — разберём, стоит ли корректировать `donchian_len`, `adx_threshold` или множители ATR перед выходом на тестнет.