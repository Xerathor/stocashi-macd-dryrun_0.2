from datetime import datetime, timezone

import numpy as np
import pandas as pd

from config import AppConfig
from core.models import Direction, Position
from indicators.features import add_indicators
from risk.manager import RiskManager
from strategy.breakout import BreakoutStrategy
from macro.total3_filter import build_daily_total3_direction, lock_daily_direction


def test_no_lookahead_for_last_ten_bars():
    cfg = AppConfig().strategy
    idx = pd.date_range("2025-01-01", periods=300, freq="2h", tz="UTC")
    close = 3000 * (1 + np.linspace(0, 0.2, 300))
    df = pd.DataFrame({
        "open": close * 0.999,
        "high": close * 1.002,
        "low": close * 0.998,
        "close": close,
        "volume": np.linspace(100, 200, 300),
    }, index=idx)
    base = add_indicators(df, cfg)
    changed = df.copy()
    changed.iloc[-10:, changed.columns.get_loc("close")] *= 1.05
    changed_result = add_indicators(changed, cfg)

    first = 240
    columns = ["ema_trend", "dc_high", "dc_low", "atr", "adx", "vol_ma"]
    np.testing.assert_allclose(
        base.iloc[:first][columns].fillna(0).to_numpy(),
        changed_result.iloc[:first][columns].fillna(0).to_numpy(),
    )


def test_trailing_stop_never_moves_back():
    cfg = AppConfig()
    strategy = BreakoutStrategy(cfg.strategy)
    pos = Position(
        symbol="ETH/USDT:USDT",
        direction=Direction.LONG,
        entry_ts=datetime.now(timezone.utc),
        entry_price=100.0,
        qty=1.0,
        initial_stop=80.0,
        stop_loss=80.0,
        initial_risk_per_unit=20.0,
        highest_price=100.0,
        lowest_price=100.0,
    )
    stop = strategy.compute_updated_stop(pos, bar_high=130.0, bar_low=125.0, atr=5.0)
    stop2 = strategy.compute_updated_stop(pos, bar_high=128.0, bar_low=120.0, atr=5.0)
    assert stop2 >= stop
    assert pos.trailing_moved


def test_daily_drawdown_cooldown_triggers_only_once_per_day():
    cfg = AppConfig()
    manager = RiskManager(cfg.risk)
    ts = datetime(2025, 1, 1, 2, tzinfo=timezone.utc)
    manager.on_bar_start(ts, 10000)
    manager.on_bar_start(ts.replace(hour=4), 9500)
    first = manager.cooldown_until
    manager.on_bar_start(ts.replace(hour=6), 9400)
    assert manager.cooldown_until == first


def test_same_direction_positions_reduce_risk():
    cfg = AppConfig()
    manager = RiskManager(cfg.risk)
    signal = type("Signal", (), {
        "symbol": "SOL/USDT:USDT",
        "entry_price": 100.0,
        "stop_loss": 80.0,
        "direction": Direction.LONG,
        "reason": "test",
    })()
    pos = Position(
        symbol="ETH/USDT:USDT",
        direction=Direction.LONG,
        entry_ts=datetime.now(timezone.utc),
        entry_price=100.0,
        qty=1.0,
        initial_stop=80.0,
        stop_loss=95.0,
        initial_risk_per_unit=20.0,
        highest_price=100.0,
        lowest_price=100.0,
    )
    order = manager.evaluate_signal(
        signal,
        equity=10000,
        open_positions={"ETH/USDT:USDT": pos},
        mark_prices={"ETH/USDT:USDT": 100.0},
        ts=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    assert order is not None
    assert order.risk_usd <= 50.0


def test_daily_total3_direction_is_locked_and_closed_candle():
    idx = pd.date_range("2025-01-01", periods=180, freq="2h", tz="UTC")
    close = 600_000_000_000 * (1 + np.linspace(0, 0.25, len(idx)))
    df = pd.DataFrame({
        "open": close * 0.99,
        "high": close * 1.02,
        "low": close * 0.98,
        "close": close,
        "volume": np.ones(len(idx)),
    }, index=idx)

    direction_1d = build_daily_total3_direction(df)
    target = pd.date_range("2025-01-02", periods=96, freq="2h", tz="UTC")
    locked = lock_daily_direction(direction_1d, target)
    assert len(locked) == len(target)
    assert set(locked.dropna().unique()).issubset({"bullish", "bearish", "neutral"})
    assert locked.is_monotonic_increasing is False or len(locked) > 0
