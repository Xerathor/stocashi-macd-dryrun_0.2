from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from config import AppConfig
from data.feed import fetch_ohlcv_history
from backtest.engine import PortfolioBacktester
from macro.total3_filter import (
    fetch_synthetic_total3,
    build_daily_total3_direction,
    lock_daily_direction,
)


def metrics_by_symbol(trades, symbols: tuple[str, ...]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for symbol in symbols:
        symbol_trades = [trade for trade in trades if trade.symbol == symbol]
        wins = [trade.net_pnl for trade in symbol_trades if trade.net_pnl > 0]
        losses = [trade.net_pnl for trade in symbol_trades if trade.net_pnl <= 0]
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        result[symbol] = {
            "trades_count": len(symbol_trades),
            "net_pnl": round(sum(trade.net_pnl for trade in symbol_trades), 2),
            "win_rate_pct": round(100 * len(wins) / len(symbol_trades), 2) if symbol_trades else 0.0,
            "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0),
        }
    return result


def print_report(name: str, result, symbol_metrics: dict) -> None:
    print(f"\n{name}")
    print(pd.Series(result.metrics).to_string())
    print("\nBy symbol:")
    print(pd.DataFrame(symbol_metrics).T.to_string())


def save_outputs(result, reports_dir: Path) -> None:
    reports_dir.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(12, 6))
    result.equity_curve.plot(ax=ax)
    ax.set_title("Portfolio Equity Curve")
    ax.set_xlabel("UTC")
    ax.set_ylabel("Equity (USDT)")
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(reports_dir / "equity_curve.png", dpi=150)
    plt.close(fig)

    rows = [
        {
            "symbol": trade.symbol,
            "direction": trade.direction.value,
            "entry_ts": trade.entry_ts,
            "exit_ts": trade.exit_ts,
            "entry_price": trade.entry_price,
            "exit_price": trade.exit_price,
            "qty": trade.qty,
            "gross_pnl": trade.gross_pnl,
            "fees": trade.fees,
            "funding": trade.funding,
            "net_pnl": trade.net_pnl,
            "r_multiple": trade.r_multiple,
            "exit_reason": trade.exit_reason,
        }
        for trade in result.trades
    ]
    pd.DataFrame(rows).to_csv(reports_dir / "trades.csv", index=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="Volatility breakout portfolio backtest")
    parser.add_argument("--days", type=int, default=730)
    args = parser.parse_args()

    cfg = AppConfig()
    data_by_symbol = {}
    for symbol in cfg.strategy.symbols:
        print(f"Loading {symbol} 2h history...")
        data_by_symbol[symbol] = fetch_ohlcv_history(
            symbol,
            timeframe="2h",
            since_days=args.days,
        )
        print(f"  {len(data_by_symbol[symbol])} bars")

    print("Building Synthetic TOTAL3 daily direction...")
    total3 = fetch_synthetic_total3(days=args.days, timeframe="2h")
    total3_direction_1d = build_daily_total3_direction(total3)
    common_timestamps = sorted(set().union(*(df.index for df in data_by_symbol.values())))
    daily_direction = lock_daily_direction(
        total3_direction_1d,
        pd.DatetimeIndex(common_timestamps),
    )
    counts = daily_direction.value_counts().to_dict()
    print(f"  TOTAL3 direction lock: {counts}")

    if not common_timestamps:
        print("No market data available.")
        return 1

    full = PortfolioBacktester(cfg).run(
        data_by_symbol,
        close_open_positions_at_end=True,
        daily_direction=daily_direction,
    )
    print_report(
        "FULL PERIOD",
        full,
        metrics_by_symbol(full.trades, cfg.strategy.symbols),
    )
    save_outputs(full, ROOT / "reports")

    split_at = int(len(common_timestamps) * 0.70)
    split_ts = common_timestamps[split_at]
    in_sample = {
        symbol: df[df.index < split_ts]
        for symbol, df in data_by_symbol.items()
    }
    out_of_sample = {
        symbol: df[df.index >= split_ts]
        for symbol, df in data_by_symbol.items()
    }
    is_result = PortfolioBacktester(cfg).run(
        in_sample,
        close_open_positions_at_end=True,
        daily_direction=daily_direction[daily_direction.index < split_ts],
    )
    print_report(
        "WALK-FORWARD IN-SAMPLE (70%)",
        is_result,
        metrics_by_symbol(is_result.trades, cfg.strategy.symbols),
    )

    oos_result = PortfolioBacktester(cfg).run(
        out_of_sample,
        close_open_positions_at_end=True,
        daily_direction=daily_direction[daily_direction.index >= split_ts],
    )
    print_report(
        "WALK-FORWARD OUT-OF-SAMPLE (30%)",
        oos_result,
        metrics_by_symbol(oos_result.trades, cfg.strategy.symbols),
    )

    from dataclasses import replace

    stress_backtest = replace(
        cfg.backtest,
        taker_fee_rate=cfg.backtest.taker_fee_rate * 1.5,
        slippage_rate=cfg.backtest.slippage_rate * 1.5,
    )
    stress_cfg = replace(cfg, backtest=stress_backtest)
    stress_result = PortfolioBacktester(stress_cfg).run(
        data_by_symbol,
        close_open_positions_at_end=True,
        daily_direction=daily_direction,
    )
    print_report(
        "FEE/SLIPPAGE STRESS (x1.5)",
        stress_result,
        metrics_by_symbol(stress_result.trades, cfg.strategy.symbols),
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
