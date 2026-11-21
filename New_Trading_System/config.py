from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StrategyConfig:
    symbols: tuple[str, ...] = ("ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT")
    timeframe: str = "2h"
    ema_trend_len: int = 200
    donchian_len: int = 20
    atr_len: int = 14
    adx_len: int = 14
    adx_threshold: float = 25.0
    require_rising_adx: bool = True
    vol_ma_len: int = 20
    vol_mult: float = 1.15
    max_body_atr: float = 2.8
    sl_atr_mult: float = 2.0
    be_trigger_r: float = 1.15
    be_offset_pct: float = 0.0020
    min_be_offset_pct: float = 0.0018
    trail_atr_mult: float = 2.5
    trail_activation_r: float = 1.50
    strict_macro_filter: bool = True


@dataclass(frozen=True)
class RiskConfig:
    risk_per_trade_pct: float = 0.0075
    max_portfolio_risk_pct: float = 0.015
    max_open_positions: int = 2
    max_symbol_leverage: float = 1.5
    max_portfolio_leverage: float = 2.5
    min_notional_usd: float = 20.0
    max_daily_dd_pct: float = 0.04
    max_consecutive_losses: int = 5
    cooldown_hours: int = 24
    same_direction_risk_mult: float = 0.5
    post_streak_risk_mult: float = 0.5
    counter_macro_risk_mult: float = 0.5


@dataclass(frozen=True)
class BacktestConfig:
    initial_capital: float = 10_000.0
    taker_fee_rate: float = 0.0005
    slippage_rate: float = 0.0004
    funding_rate_per_2h: float = 0.000025
    directional_funding: bool = True


@dataclass(frozen=True)
class AppConfig:
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
