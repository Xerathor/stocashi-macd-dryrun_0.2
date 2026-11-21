```python
import pandas as pd
import numpy as np

df = pd.read_csv('trades.csv')
df['entry_ts'] = pd.to_datetime(df['entry_ts'])
df['exit_ts'] = pd.to_datetime(df['exit_ts'])
df['bars_2h'] = (df['exit_ts'] - df['entry_ts']).dt.total_seconds() / 7200.0
df['entry_notional'] = df['entry_price'] * df['qty']
df['exit_notional'] = df['exit_price'] * df['qty']

# 1. Verify Fees formula: 0.05% per side
df['calc_fees'] = (df['entry_notional'] + df['exit_notional']) * 0.0005
print("Max diff fees (0.05% per side):", (df['fees'] - df['calc_fees']).abs().max())

# 2. Verify Funding formula: 0.0025% per 2H candle
df['calc_fund_entry'] = df['entry_notional'] * 0.000025 * df['bars_2h']
df['calc_fund_exit'] = df['exit_notional'] * 0.000025 * df['bars_2h']
print("Max diff funding (vs entry_notional * bars_2h * 0.0025%):", (df['funding'] - df['calc_fund_entry']).abs().max())
print("Median ratio funding / (entry_notional * bars_2h * 0.0025%):", (df['funding'] / df['calc_fund_entry']).median())
print("Min/Max ratio:", (df['funding'] / df['calc_fund_entry']).min(), (df['funding'] / df['calc_fund_entry']).max())
print("Zero funding count:", (df['funding'] == 0).sum(), "bars_2h for those:", df[df['funding']==0]['bars_2h'].value_counts().to_dict())

# 3. Inspect exit_reason vs r_multiple distribution
print("\n=== EXIT REASON vs R_MULTIPLE ===")
for reason, g in df.groupby('exit_reason'):
    print(f"\n{reason} (n={len(g)}):")
    print("  min R:", g['r_multiple'].min(), "max R:", g['r_multiple'].max(), "median R:", g['r_multiple'].median())
    print("  R > 0:", (g['r_multiple'] > 0).sum(), "| -0.95 < R <= 0:", ((g['r_multiple'] > -0.95) & (g['r_multiple'] <= 0)).sum(), "| R <= -0.95:", (g['r_multiple'] <= -0.95).sum())

print("\ninitial_sl with R > -0.95 (stop moved BEFORE exit but tagged initial_sl!):")
moved_isl = df[(df['exit_reason'] == 'initial_sl') & (df['r_multiple'] > -0.95)]
print(f"Count: {len(moved_isl)} / {(df['exit_reason'] == 'initial_sl').sum()}")
print(moved_isl[['symbol', 'direction', 'bars_2h', 'r_multiple', 'gross_pnl', 'net_pnl']].sort_values('r_multiple').to_string())

print("\ntrailing_or_be_stop with lowest R:")
print(df[df['exit_reason'] == 'trailing_or_be_stop'].sort_values('r_multiple').head(10)[['symbol', 'direction', 'bars_2h', 'r_multiple', 'gross_pnl', 'net_pnl']].to_string())


```

```text
Max diff fees (0.05% per side): 1.7763568394002505e-15
Max diff funding (vs entry_notional * bars_2h * 0.0025%): 0.26048781478873795
Median ratio funding / (entry_notional * bars_2h * 0.0025%): 0.8979663371696526
Min/Max ratio: 0.0 1.0560639409529458
Zero funding count: 5 bars_2h for those: {1.0: 5}

=== EXIT REASON vs R_MULTIPLE ===

initial_sl (n=124):
  min R: -1.0496292290325793 max R: 0.5833238939644614 median R: -1.0127912567343038
  R > 0: 11 | -0.95 < R <= 0: 19 | R <= -0.95: 94

trailing_or_be_stop (n=75):
  min R: 0.0228127475222737 max R: 6.209398146604799 median R: 1.3464914867327864
  R > 0: 75 | -0.95 < R <= 0: 0 | R <= -0.95: 0

initial_sl with R > -0.95 (stop moved BEFORE exit but tagged initial_sl!):
Count: 30 / 124
            symbol direction  bars_2h  r_multiple  gross_pnl    net_pnl
65   SOL/USDT:USDT      long      7.0   -0.356003 -28.046176 -30.561799
133  ETH/USDT:USDT      long      3.0   -0.328012 -28.304343 -30.834620
21   ETH/USDT:USDT     short      7.0   -0.290566 -23.956947 -25.692885
75   SOL/USDT:USDT      long      6.0   -0.253255 -20.018635 -22.519540
28   BNB/USDT:USDT      long     11.0   -0.242905 -20.216305 -24.081036
106  BNB/USDT:USDT     short      9.0   -0.240614 -20.122722 -22.469738
36   SOL/USDT:USDT      long     12.0   -0.236325 -19.426932 -21.995746
63   ETH/USDT:USDT      long      7.0   -0.235558 -18.871392 -21.876742
38   BNB/USDT:USDT      long     11.0   -0.221054 -18.343510 -25.852963
97   ETH/USDT:USDT      long      6.0   -0.220127 -18.401719 -22.924028
32   BNB/USDT:USDT     short      3.0   -0.210807 -17.392601 -21.509711
17   BNB/USDT:USDT      long      9.0   -0.206727 -16.572188 -19.054614
27   SOL/USDT:USDT     short     16.0   -0.133986 -11.101356 -14.499470
68   SOL/USDT:USDT     short      6.0   -0.131744 -10.245018 -13.039021
192  SOL/USDT:USDT     short     12.0   -0.123041 -10.535370 -13.976930
182  SOL/USDT:USDT      long     10.0   -0.090732  -7.886071 -11.490348
136  SOL/USDT:USDT      long     11.0   -0.045433  -3.854238  -7.502286
181  ETH/USDT:USDT      long     10.0   -0.005671  -0.502301  -4.840685
22   BNB/USDT:USDT     short      7.0   -0.000167  -0.013761  -2.859067
198  ETH/USDT:USDT     short      7.0    0.028614   2.511356   0.092548
13   BNB/USDT:USDT     short      2.0    0.031925   2.525649  -2.164019
71   ETH/USDT:USDT      long      9.0    0.040479   3.189017  -0.626185
30   ETH/USDT:USDT     short     25.0    0.143421  11.764568   7.366929
26   BNB/USDT:USDT      long      8.0    0.163368  13.609610   9.149790
76   ETH/USDT:USDT      long     20.0    0.179639  14.309255  10.692859
139  SOL/USDT:USDT     short     15.0    0.277200  23.614875  19.497043
48   SOL/USDT:USDT     short     24.0    0.367811  29.873972  26.362476
70   BNB/USDT:USDT     short     23.0    0.375970  29.152047  25.228842
5    SOL/USDT:USDT      long     24.0    0.382028  29.229361  25.268270
0    ETH/USDT:USDT      long     35.0    0.583324  44.193617  40.601436

trailing_or_be_stop with lowest R:
            symbol direction  bars_2h  r_multiple  gross_pnl    net_pnl
25   BNB/USDT:USDT     short      5.0    0.022813   1.892023  -0.706848
58   SOL/USDT:USDT      long     12.0    0.134362  10.567429   6.606504
101  BNB/USDT:USDT     short      9.0    0.172694  14.602389  12.187577
93   ETH/USDT:USDT     short      2.0    0.330832  27.454679  25.250198
8    ETH/USDT:USDT     short     15.0    0.367048  28.203563  24.973731
6    ETH/USDT:USDT      long     43.0    0.380592  29.465289  22.253544
89   ETH/USDT:USDT      long     16.0    0.408800  32.823253  28.249486
161  SOL/USDT:USDT      long      8.0    0.426096  35.586698  31.738269
118  BNB/USDT:USDT      long     24.0    0.449489  35.783984  26.244346
124  ETH/USDT:USDT     short      4.0    0.462880  37.214682  32.146154


```

```python
import pandas as pd
import numpy as np

df = pd.read_csv('trades.csv')
df['entry_ts'] = pd.to_datetime(df['entry_ts'])
df['exit_ts'] = pd.to_datetime(df['exit_ts'])
df['bars_2h'] = (df['exit_ts'] - df['entry_ts']).dt.total_seconds() / 7200.0
df['entry_notional'] = df['entry_price'] * df['qty']
df['exit_notional'] = df['exit_price'] * df['qty']

# 1. Check funding vs (bars_2h - 1)
df['calc_fund_minus1'] = df['entry_notional'] * 0.000025 * (df['bars_2h'] - 1)
nz_bars = df[df['bars_2h'] > 1]
print("Funding / (entry_notional * (bars_2h - 1) * 0.0025%) median/min/max:",
      (nz_bars['funding'] / nz_bars['calc_fund_minus1']).median(),
      (nz_bars['funding'] / nz_bars['calc_fund_minus1']).min(),
      (nz_bars['funding'] / nz_bars['calc_fund_minus1']).max())
# Check if funding is based on bar-by-bar mark-to-market notional (close * qty) for bars_2h - 1 bars!

# 2. Check notional caps and actual risk %
df_s = df.sort_values('exit_ts').reset_index(drop=True)
df_s['equity_before'] = 10000.0 + df_s['net_pnl'].cumsum().shift(1).fillna(0)
df_s['notional_x_eq'] = df_s['entry_notional'] / df_s['equity_before']
print("\nNotional / Equity stats:")
print(df_s['notional_x_eq'].describe())
print("Trades near 1.5x cap (>1.45x):", (df_s['notional_x_eq'] > 1.45).sum())

# 3. Check trade #25 (BE stop) price move %
t25 = df.loc[25]
move_pct_25 = (t25['entry_price'] - t25['exit_price']) / t25['entry_price'] * 100
print(f"\nTrade #25 (BNB short trailing_or_be_stop): price move = {move_pct_25:.4f}% (0.12% BE - 0.04% slip = 0.08%)")

# 4. Check initial_sl R distribution detail
isl = df[df['exit_reason'] == 'initial_sl']
print("\ninitial_sl R buckets:")
bins = [-2, -0.95, -0.5, -0.25, 0, 0.25, 1.0]
print(pd.cut(isl['r_multiple'], bins=bins).value_counts().sort_index())

# 5. Check consecutive losses & circuit breaker pauses!
df_s['is_loss'] = df_s['net_pnl'] <= 0
df_s['loss_streak'] = 0
streak = 0
for i in range(len(df_s)):
    if df_s.loc[i, 'is_loss']:
        streak += 1
    else:
        streak = 0
    df_s.loc[i, 'loss_streak'] = streak

print("\n=== STREAKS >= 5 CONSECUTIVE LOSSES ===")
streaks5 = df_s[df_s['loss_streak'] >= 5]
print(f"Rows with loss_streak >= 5: {len(streaks5)}")
# For each row where streak == 5, check gap to next entry_ts
for idx in df_s[df_s['loss_streak'] >= 5].index:
    exit_t = df_s.loc[idx, 'exit_ts']
    # find next trade entered AFTER exit_t
    later = df[df['entry_ts'] > exit_t].sort_values('entry_ts')
    if len(later) > 0:
        next_entry = later.iloc[0]['entry_ts']
        gap_h = (next_entry - exit_t).total_seconds() / 3600.0
    else:
        gap_h = np.nan
    print(f"  idx={idx}, streak={df_s.loc[idx, 'loss_streak']}, exit={exit_t}, next_entry_gap={gap_h:.1f}h")

# 6. Check net R vs gross R
df_s['implied_risk_usd'] = np.where(df_s['r_multiple'].abs() > 0.01, df_s['gross_pnl'] / df_s['r_multiple'], np.nan)
df_s['net_r'] = df_s['net_pnl'] / df_s['implied_risk_usd']
print(f"\nMean Gross R (reported): {df_s['r_multiple'].mean():.4f}R (sum={df_s['r_multiple'].sum():.2f}R)")
print(f"Mean Net R   (actual):   {df_s['net_r'].mean():.4f}R (sum={df_s['net_r'].sum():.2f}R)")
print(f"Difference (cost drag in R): {(df_s['r_multiple'].mean() - df_s['net_r'].mean()):.4f}R per trade")

# 7. Check stop distance % across symbols
df['stop_dist_pct'] = (df['gross_pnl'] / df['r_multiple']) / df['entry_notional'] * 100
print("\nImplied initial stop distance % by symbol (median, min, max):")
print(df.groupby('symbol')['stop_dist_pct'].agg(['median', 'min', 'max', 'mean']).round(2))

# 8. Check how many trades are killed by trailing between +1.0R and +1.5R (those 30 trades!)
print(f"\n30 trades where Chandelier moved stop (tagged initial_sl, R > -0.95):")
print(f"  Net PnL sum: ${moved_isl_sum := df[(df['exit_reason']=='initial_sl') & (df['r_multiple']>-0.95)]['net_pnl'].sum():.2f}")
print(f"  Avg R: {df[(df['exit_reason']=='initial_sl') & (df['r_multiple']>-0.95)]['r_multiple'].mean():.3f}R")
print(f"  Negative net PnL count: {(df[(df['exit_reason']=='initial_sl') & (df['r_multiple']>-0.95)]['net_pnl'] <= 0).sum()} / 30")


```

```text
Funding / (entry_notional * (bars_2h - 1) * 0.0025%) median/min/max: 0.9975490107107061 0.9173423922221302 1.1097167928551894

Notional / Equity stats:
count    199.000000
mean       0.300372
std        0.126635
min        0.078945
25%        0.211178
50%        0.277424
75%        0.361358
max        0.960767
Name: notional_x_eq, dtype: float64
Trades near 1.5x cap (>1.45x): 0

Trade #25 (BNB short trailing_or_be_stop): price move = 0.0800% (0.12% BE - 0.04% slip = 0.08%)

initial_sl R buckets:
r_multiple
(-2.0, -0.95]    94
(-0.95, -0.5]     0
(-0.5, -0.25]     4
(-0.25, 0.0]     15
(0.0, 0.25]       6
(0.25, 1.0]       5
Name: count, dtype: int64

=== STREAKS >= 5 CONSECUTIVE LOSSES ===
Rows with loss_streak >= 5: 27
  idx=45, streak=5, exit=2025-05-18 18:00:00+00:00, next_entry_gap=80.0h
  idx=46, streak=6, exit=2025-05-23 10:00:00+00:00, next_entry_gap=174.0h
  idx=47, streak=7, exit=2025-05-23 10:00:00+00:00, next_entry_gap=174.0h
  idx=53, streak=5, exit=2025-06-12 10:00:00+00:00, next_entry_gap=226.0h
  idx=67, streak=5, exit=2025-07-28 18:00:00+00:00, next_entry_gap=40.0h
  idx=68, streak=6, exit=2025-07-30 22:00:00+00:00, next_entry_gap=26.0h
  idx=99, streak=5, exit=2025-10-31 18:00:00+00:00, next_entry_gap=58.0h
  idx=108, streak=5, exit=2025-12-02 10:00:00+00:00, next_entry_gap=36.0h
  idx=109, streak=6, exit=2025-12-02 12:00:00+00:00, next_entry_gap=34.0h
  idx=110, streak=7, exit=2025-12-04 18:00:00+00:00, next_entry_gap=254.0h
  idx=111, streak=8, exit=2025-12-15 14:00:00+00:00, next_entry_gap=2.0h
  idx=112, streak=9, exit=2025-12-17 14:00:00+00:00, next_entry_gap=2.0h
  idx=113, streak=10, exit=2025-12-18 12:00:00+00:00, next_entry_gap=254.0h
  idx=114, streak=11, exit=2025-12-29 08:00:00+00:00, next_entry_gap=96.0h
  idx=144, streak=5, exit=2026-04-16 12:00:00+00:00, next_entry_gap=24.0h
  idx=145, streak=6, exit=2026-04-18 10:00:00+00:00, next_entry_gap=272.0h
  idx=146, streak=7, exit=2026-05-01 12:00:00+00:00, next_entry_gap=62.0h
  idx=147, streak=8, exit=2026-05-04 10:00:00+00:00, next_entry_gap=40.0h
  idx=148, streak=9, exit=2026-05-06 12:00:00+00:00, next_entry_gap=144.0h
  idx=168, streak=5, exit=2026-07-27 12:00:00+00:00, next_entry_gap=24.0h
  idx=169, streak=6, exit=2026-07-27 14:00:00+00:00, next_entry_gap=22.0h
  idx=170, streak=7, exit=2026-07-28 14:00:00+00:00, next_entry_gap=288.0h
  idx=171, streak=8, exit=2026-08-09 22:00:00+00:00, next_entry_gap=230.0h
  idx=184, streak=5, exit=2026-10-05 04:00:00+00:00, next_entry_gap=54.0h
  idx=191, streak=5, exit=2026-10-24 22:00:00+00:00, next_entry_gap=398.0h
  idx=192, streak=6, exit=2026-11-11 12:00:00+00:00, next_entry_gap=22.0h
  idx=193, streak=7, exit=2026-11-11 14:00:00+00:00, next_entry_gap=20.0h

Mean Gross R (reported): 0.1614R (sum=32.13R)
Mean Net R   (actual):   0.1130R (sum=22.26R)
Difference (cost drag in R): 0.0485R per trade

Implied initial stop distance % by symbol (median, min, max):
               median   min   max  mean
symbol                                 
BNB/USDT:USDT    2.13  0.80  6.77  2.37
ETH/USDT:USDT    2.74  1.24  6.87  2.97
SOL/USDT:USDT    3.20  1.42  9.62  3.45

30 trades where Chandelier moved stop (tagged initial_sl, R > -0.95):


```

```python
import pandas as pd
import numpy as np

df = pd.read_csv('trades.csv')
df['entry_ts'] = pd.to_datetime(df['entry_ts'])
df['exit_ts'] = pd.to_datetime(df['exit_ts'])
df['bars_2h'] = (df['exit_ts'] - df['entry_ts']).dt.total_seconds() / 7200.0
df['entry_notional'] = df['entry_price'] * df['qty']
df['exit_notional'] = df['exit_price'] * df['qty']

# 1. Check funding vs (bars_2h - 1)
df['calc_fund_minus1'] = df['entry_notional'] * 0.000025 * (df['bars_2h'] - 1)
nz_bars = df[df['bars_2h'] > 1]
print("Funding / (entry_notional * (bars_2h - 1) * 0.0025%) median/min/max:",
      round((nz_bars['funding'] / nz_bars['calc_fund_minus1']).median(), 4),
      round((nz_bars['funding'] / nz_bars['calc_fund_minus1']).min(), 4),
      round((nz_bars['funding'] / nz_bars['calc_fund_minus1']).max(), 4))

# 2. Check notional caps and actual risk %
df_s = df.sort_values('exit_ts').reset_index(drop=True)
df_s['equity_before'] = 10000.0 + df_s['net_pnl'].cumsum().shift(1).fillna(0)
df_s['notional_x_eq'] = df_s['entry_notional'] / df_s['equity_before']
print("\nNotional / Equity stats:")
print(df_s['notional_x_eq'].describe().round(3))
print("Trades near 1.5x cap (>1.45x):", (df_s['notional_x_eq'] > 1.45).sum())

# 3. Check trade #25 (BE stop) price move %
t25 = df.loc[25]
move_pct_25 = (t25['entry_price'] - t25['exit_price']) / t25['entry_price'] * 100
print(f"\nTrade #25 (BNB short trailing_or_be_stop): price move = {move_pct_25:.4f}% (0.12% BE - 0.04% slip = 0.08%)")

# 4. Check initial_sl R distribution detail
isl = df[df['exit_reason'] == 'initial_sl']
print("\ninitial_sl R buckets:")
bins = [-2, -0.95, -0.5, -0.25, 0, 0.25, 1.0]
print(pd.cut(isl['r_multiple'], bins=bins).value_counts().sort_index())

# 5. Check consecutive losses & circuit breaker pauses!
df_s['is_loss'] = df_s['net_pnl'] <= 0
df_s['loss_streak'] = 0
streak = 0
for i in range(len(df_s)):
    if df_s.loc[i, 'is_loss']:
        streak += 1
    else:
        streak = 0
    df_s.loc[i, 'loss_streak'] = streak

print("\n=== STREAKS >= 5 CONSECUTIVE LOSSES ===")
for idx in df_s[df_s['loss_streak'] >= 5].index:
    exit_t = df_s.loc[idx, 'exit_ts']
    later = df[df['entry_ts'] > exit_t].sort_values('entry_ts')
    gap_h = (later.iloc[0]['entry_ts'] - exit_t).total_seconds() / 3600.0 if len(later) > 0 else np.nan
    print(f"  idx={idx}, streak={df_s.loc[idx, 'loss_streak']}, exit={exit_t}, next_entry_gap={gap_h:.1f}h")

# 6. Check net R vs gross R
df_s['implied_risk_usd'] = np.where(df_s['r_multiple'].abs() > 0.01, df_s['gross_pnl'] / df_s['r_multiple'], np.nan)
df_s['net_r'] = df_s['net_pnl'] / df_s['implied_risk_usd']
print(f"\nMean Gross R (reported): {df_s['r_multiple'].mean():.4f}R (sum={df_s['r_multiple'].sum():.2f}R)")
print(f"Mean Net R   (actual):   {df_s['net_r'].mean():.4f}R (sum={df_s['net_r'].sum():.2f}R)")
print(f"Difference (cost drag in R): {(df_s['r_multiple'].mean() - df_s['net_r'].mean()):.4f}R per trade")

# 7. Check stop distance % across symbols
df['stop_dist_pct'] = (df['gross_pnl'] / df['r_multiple']) / df['entry_notional'] * 100
print("\nImplied initial stop distance % by symbol:")
print(df.groupby('symbol')['stop_dist_pct'].agg(['median', 'min', 'max', 'mean']).round(2))

# 8. Check those 30 trades where Chandelier moved stop (tagged initial_sl, R > -0.95)
moved_isl = df[(df['exit_reason'] == 'initial_sl') & (df['r_multiple'] > -0.95)]
print(f"\n30 trades where Chandelier moved stop (tagged initial_sl, R > -0.95):")
print(f"  Net PnL sum: ${moved_isl['net_pnl'].sum():.2f}")
print(f"  Avg R: {moved_isl['r_multiple'].mean():.3f}R")
print(f"  Negative net PnL count: {(moved_isl['net_pnl'] <= 0).sum()} / {len(moved_isl)}")
print(f"  Positive net PnL count: {(moved_isl['net_pnl'] > 0).sum()} / {len(moved_isl)}")
print(f"  Exact initial SL hits (R <= -0.95): count={(isl['r_multiple'] <= -0.95).sum()}, Net PnL=${isl[isl['r_multiple'] <= -0.95]['net_pnl'].sum():.2f}")


```

```text
Funding / (entry_notional * (bars_2h - 1) * 0.0025%) median/min/max: 0.9975 0.9173 1.1097

Notional / Equity stats:
count    199.000
mean       0.300
std        0.127
min        0.079
25%        0.211
50%        0.277
75%        0.361
max        0.961
Name: notional_x_eq, dtype: float64
Trades near 1.5x cap (>1.45x): 0

Trade #25 (BNB short trailing_or_be_stop): price move = 0.0800% (0.12% BE - 0.04% slip = 0.08%)

initial_sl R buckets:
r_multiple
(-2.0, -0.95]    94
(-0.95, -0.5]     0
(-0.5, -0.25]     4
(-0.25, 0.0]     15
(0.0, 0.25]       6
(0.25, 1.0]       5
Name: count, dtype: int64

=== STREAKS >= 5 CONSECUTIVE LOSSES ===
  idx=45, streak=5, exit=2025-05-18 18:00:00+00:00, next_entry_gap=80.0h
  idx=46, streak=6, exit=2025-05-23 10:00:00+00:00, next_entry_gap=174.0h
  idx=47, streak=7, exit=2025-05-23 10:00:00+00:00, next_entry_gap=174.0h
  idx=53, streak=5, exit=2025-06-12 10:00:00+00:00, next_entry_gap=226.0h
  idx=67, streak=5, exit=2025-07-28 18:00:00+00:00, next_entry_gap=40.0h
  idx=68, streak=6, exit=2025-07-30 22:00:00+00:00, next_entry_gap=26.0h
  idx=99, streak=5, exit=2025-10-31 18:00:00+00:00, next_entry_gap=58.0h
  idx=108, streak=5, exit=2025-12-02 10:00:00+00:00, next_entry_gap=36.0h
  idx=109, streak=6, exit=2025-12-02 12:00:00+00:00, next_entry_gap=34.0h
  idx=110, streak=7, exit=2025-12-04 18:00:00+00:00, next_entry_gap=254.0h
  idx=111, streak=8, exit=2025-12-15 14:00:00+00:00, next_entry_gap=2.0h
  idx=112, streak=9, exit=2025-12-17 14:00:00+00:00, next_entry_gap=2.0h
  idx=113, streak=10, exit=2025-12-18 12:00:00+00:00, next_entry_gap=254.0h
  idx=114, streak=11, exit=2025-12-29 08:00:00+00:00, next_entry_gap=96.0h
  idx=144, streak=5, exit=2026-04-16 12:00:00+00:00, next_entry_gap=24.0h
  idx=145, streak=6, exit=2026-04-18 10:00:00+00:00, next_entry_gap=272.0h
  idx=146, streak=7, exit=2026-05-01 12:00:00+00:00, next_entry_gap=62.0h
  idx=147, streak=8, exit=2026-05-04 10:00:00+00:00, next_entry_gap=40.0h
  idx=148, streak=9, exit=2026-05-06 12:00:00+00:00, next_entry_gap=144.0h
  idx=168, streak=5, exit=2026-07-27 12:00:00+00:00, next_entry_gap=24.0h
  idx=169, streak=6, exit=2026-07-27 14:00:00+00:00, next_entry_gap=22.0h
  idx=170, streak=7, exit=2026-07-28 14:00:00+00:00, next_entry_gap=288.0h
  idx=171, streak=8, exit=2026-08-09 22:00:00+00:00, next_entry_gap=230.0h
  idx=184, streak=5, exit=2026-10-05 04:00:00+00:00, next_entry_gap=54.0h
  idx=191, streak=5, exit=2026-10-24 22:00:00+00:00, next_entry_gap=398.0h
  idx=192, streak=6, exit=2026-11-11 12:00:00+00:00, next_entry_gap=22.0h
  idx=193, streak=7, exit=2026-11-11 14:00:00+00:00, next_entry_gap=20.0h

Mean Gross R (reported): 0.1614R (sum=32.13R)
Mean Net R   (actual):   0.1130R (sum=22.26R)
Difference (cost drag in R): 0.0485R per trade

Implied initial stop distance % by symbol:
               median   min   max  mean
symbol                                 
BNB/USDT:USDT    2.13  0.80  6.77  2.37
ETH/USDT:USDT    2.74  1.24  6.87  2.97
SOL/USDT:USDT    3.20  1.42  9.62  3.45

30 trades where Chandelier moved stop (tagged initial_sl, R > -0.95):
  Net PnL sum: $-196.11
  Avg R: -0.033R
  Negative net PnL count: 21 / 30
  Positive net PnL count: 9 / 30
  Exact initial SL hits (R <= -0.95): count=94, Net PnL=$-8268.68


```

```python
import pandas as pd
import numpy as np

df = pd.read_csv('trades.csv')
df['entry_ts'] = pd.to_datetime(df['entry_ts'])
df['exit_ts'] = pd.to_datetime(df['exit_ts'])
df_s = df.sort_values('exit_ts').reset_index(drop=True)

print("=== INSPECT 11-LOSS STREAK (idx 104..116) ===")
print(df_s.loc[103:116, ['symbol', 'direction', 'entry_ts', 'exit_ts', 'gross_pnl', 'net_pnl', 'r_multiple', 'exit_reason']].to_string())

# Check funding paid by longs vs shorts
print("\n=== FUNDING BY DIRECTION ===")
print(df.groupby('direction')['funding'].agg(['count', 'sum', 'mean']).round(2))
short_fund = df[df['direction'] == 'short']['funding'].sum()
print(f"If shorts RECEIVED funding instead of paying it: +${2*short_fund:.2f} swing (new Net PnL = ${df['net_pnl'].sum() + 2*short_fund:.2f})")

# Check if circuit breaker counts gross_pnl <= 0 vs net_pnl <= 0
df_s['gross_loss'] = df_s['gross_pnl'] <= 0
g_streak = 0
max_g_streak = 0
for v in df_s['gross_loss']:
    g_streak = g_streak + 1 if v else 0
    max_g_streak = max(max_g_streak, g_streak)
print(f"Max consecutive GROSS losses: {max_g_streak}")

# Check exact BE trades (where price move is ~0.08% = 0.12% - 0.04% slip)
df['price_move_pct'] = np.where(
    df['direction'] == 'long',
    (df['exit_price'] - df['entry_price']) / df['entry_price'] * 100,
    (df['entry_price'] - df['exit_price']) / df['entry_price'] * 100
)
be_hits = df[(df['price_move_pct'] > 0.05) & (df['price_move_pct'] < 0.12)]
print(f"\nTrades exiting near exact BE (+0.08% move): {len(be_hits)}")
if len(be_hits):
    print(be_hits[['symbol', 'direction', 'price_move_pct', 'gross_pnl', 'net_pnl', 'r_multiple', 'exit_reason']].to_string())


```

```text
=== INSPECT 11-LOSS STREAK (idx 104..116) ===
            symbol direction                  entry_ts                   exit_ts  gross_pnl    net_pnl  r_multiple          exit_reason
103  SOL/USDT:USDT     short 2025-11-13 16:00:00+00:00 2025-11-15 16:00:00+00:00  49.416886  46.535836    0.584384  trailing_or_be_stop
104  SOL/USDT:USDT     short 2025-11-16 16:00:00+00:00 2025-11-17 06:00:00+00:00 -85.829498 -88.223377   -1.009999           initial_sl
105  ETH/USDT:USDT     short 2025-11-19 18:00:00+00:00 2025-11-19 22:00:00+00:00 -85.004328 -86.929895   -1.009116           initial_sl
106  BNB/USDT:USDT     short 2025-11-21 06:00:00+00:00 2025-11-22 00:00:00+00:00 -20.122722 -22.469738   -0.240614           initial_sl
107  ETH/USDT:USDT     short 2025-11-21 06:00:00+00:00 2025-11-24 04:00:00+00:00 -83.283054 -86.080080   -1.007540           initial_sl
108  BNB/USDT:USDT     short 2025-12-01 12:00:00+00:00 2025-12-02 10:00:00+00:00 -84.616669 -88.646591   -1.015686           initial_sl
109  SOL/USDT:USDT     short 2025-12-01 14:00:00+00:00 2025-12-02 12:00:00+00:00 -82.994372 -86.132880   -1.012464           initial_sl
110  ETH/USDT:USDT      long 2025-12-03 22:00:00+00:00 2025-12-04 18:00:00+00:00 -82.792818 -85.968540   -1.012446           initial_sl
111  ETH/USDT:USDT      long 2025-12-15 08:00:00+00:00 2025-12-15 14:00:00+00:00 -82.889048 -86.577025   -1.017035           initial_sl
112  ETH/USDT:USDT     short 2025-12-15 16:00:00+00:00 2025-12-17 14:00:00+00:00 -81.441978 -85.318299   -1.012701           initial_sl
113  ETH/USDT:USDT     short 2025-12-17 16:00:00+00:00 2025-12-18 12:00:00+00:00 -80.577764 -83.302401   -1.011411           initial_sl
114  BNB/USDT:USDT      long 2025-12-29 02:00:00+00:00 2025-12-29 08:00:00+00:00 -83.080320 -89.529624   -1.030275           initial_sl
115  ETH/USDT:USDT      long 2026-01-02 08:00:00+00:00 2026-01-03 06:00:00+00:00  56.052112  49.199664    0.703555  trailing_or_be_stop
116  BNB/USDT:USDT      long 2026-01-02 16:00:00+00:00 2026-01-03 06:00:00+00:00 -82.750654 -88.926263   -1.026453           initial_sl

=== FUNDING BY DIRECTION ===
           count    sum  mean
direction                    
long         107  95.73  0.89
short         92  77.66  0.84
If shorts RECEIVED funding instead of paying it: +$155.32 swing (new Net PnL = $1745.18)
Max consecutive GROSS losses: 11

Trades exiting near exact BE (+0.08% move): 4
            symbol direction  price_move_pct  gross_pnl   net_pnl  r_multiple          exit_reason
13   BNB/USDT:USDT     short        0.055175   2.525649 -2.164019    0.031925           initial_sl
25   BNB/USDT:USDT     short        0.080048   1.892023 -0.706848    0.022813  trailing_or_be_stop
71   ETH/USDT:USDT      long        0.100604   3.189017 -0.626185    0.040479           initial_sl
198  ETH/USDT:USDT     short        0.119063   2.511356  0.092548    0.028614           initial_sl


```

Сверка правил из `SIGNALS_AND_RISK.md` с фактическими сделками в `trades.csv` вскрыла **4 математических/логических бага в риск-движке и бэктестере** и **3 структурные причины**, почему стратегия теряет деньги на лонгах и на `BNB`.

---

## 1. Баги в механике выходов и учёта (подтверждены цифрами)

| Проблема | Что написано в спецификации | Что реально произошло в `trades.csv` | Как исправить |
| --- | --- | --- | --- |
| **Конфликт Chandelier (`+1.0R`) и BE (`+1.5R`)** | Initial SL = `2.0 × ATR` (`1R`). Chandelier (`2.5 × ATR`) стартует с `+1.0R`, а BE (`+0.12%`) — только с `+1.5R` | На `+1.0R` Chandelier ставит стоп на `-0.25R`, к `+1.25R` проходит точку входа, а к `+1.5R` уже стоит на `+0.25R`. Правило BE почти **мёртвый код** — сработало ровно **1 раз из 199** (сделка #25) | Поменять порядок: либо BE раньше трейлинга (`BE` на `+1.0R..+1.2R`, Chandelier с `+1.5R..+2.0R`), либо убрать BE совсем |
| **Неверная маркировка `exit_reason**` | `initial_sl` — сработал начальный стоп; `trailing_or_be_stop` — BE/трейлинг | **30 из 124 сделок** с тегом `initial_sl` закрылись от `-0.36R` до `+0.58R` (9 — в чистый плюс, между `-0.95R` и `-0.36R` ровно **0 сделок**). Трейлинг их поджал, но тег меняется только после `+1.5R` | Менять `exit_reason` при любом сдвиге стопа (`abs(stop_loss - initial_stop) > eps`), а не по флагу BE |
| **Убыточный безубыток (`0.12%`)** | `BE = entry × (1 ± 0.0012)` при комиссии `0.05%` на сторону + `0.04%` проскальзывание + фандинг | `0.12% − 0.04% (slip) = +0.08%`, что **меньше `0.10%` комиссий**. Сделка #25 закрылась ровно в `+0.0800%` по цене, но в чистый минус (`−$0.71`) | Поднять буфер BE минимум до **`0.0018`–`0.0020**` (`0.18%–0.20%`) с учётом комиссий, проскальзывания и фандинга |
| **Завышенный `R multiple**` | `(exit − entry) / initial_risk_per_unit` (валовый, без издержек) | Репортируемый `Mean Gross R = +0.161R` (`+32.13R`), реальный `Mean Net R = +0.113R` (`+22.26R`). Издержки съедают **`0.049R` на каждую сделку** (30% от ожидания) | Считать `net_r = net_pnl / initial_risk_usd` (или хранить оба поля: `gross_r` и `net_r`) |
| **Односторонний фандинг** | `0.0025%` за каждую 2H-свечу (`~0.01%` за 8ч) | Списывается в минус за `(bars − 1)` свечей **и по лонгам (`$95.73`), и по шортам (`$77.66`)** | Подтянуть исторический funding rate Binance; даже при фиксированной ставке +0.01%/8ч шорты его *получают* (эффект `+$155.32`, итог стал бы `~$1,745`) |

Отдельно стоит обратить внимание на **эти 30 сделок**, которые Chandelier поджал между `+1.0R` и `+1.5R` (помечены как `initial_sl` с `R > −0.95`): все 30 уже успели сходить в плюс `>= +1.0R`, но из-за раннего включения Chandelier (`2.5 × ATR`) на `+1.0R` 21 из них закрылась в убыток, а суммарный результат группы составил **`−$196.11`**.

Также проверь логику **Circuit Breaker** (`5 consecutive losing trades` → пауза 24ч): в ноябре–декабре 2025 прошла серия из **11 убытков подряд** (сделки #104–#114). После 5-го убытка (#108) пауза сработала и счётчик, судя по данным, **сбросился в 0** — поэтому после 8-го (#111) и 9-го (#112) убытков новые позиции открывались уже через **2 часа**. Если цель — пережидать неблагоприятную фазу рынка, пауза должна срабатывать повторно при продолжении серии (или по снижению краткосрочного `winrate`), а не обнуляться после первого срабатывания.

---

## 2. Что в риск-движке сделано правильно (менять не нужно)

* **Нет lookahead bias в расчёте индикаторов:** `DC_high`, `DC_low` и `Volume_MA` корректно сдвинуты через `.shift(1)`, а `ATR` и `ADX` считаются по Уайлдеру (RMA).
* **Честный консервативный `exit fill`:** формула `min(bar_open, stop_loss) * (1 - slippage)` реалистично моделирует гэпы на стопах (фактические стопы ложатся в `-1.01R..-1.05R`).
* **Лимиты notional не искажают размер позиции:** максимальный notional за 2 года составил `0.96×` от эквити (средний `0.30×`), поэтому порог `1.5×` на инструмент и `2.5×` на портфель ни разу не обрезал расчётный риск `0.75%`.



---

## 3. Почему стратегия буксует по `LONG` и `BNB` — и что тестировать дальше

1. **Пробой на `ADX >= 30` — вход в уже зрелый тренд:**
В связке с 20-свечным каналом Дончиана (40 часов) высокий порог `ADX >= 30` часто срабатывает ближе к кульминации импульса, а не в его начале. Для пробойных систем обычно устойчивее работает более низкий порог **`ADX >= 20–25`** в паре с условием **роста** (`ADX > ADX.shift(1)` — тренд *ускоряется*, а не выдыхается).


2. **`EMA(200)` на 2H слишком короткая для макро-фильтра:**
200 свечей по 2 часа — это всего **16.6 дней**. Любой 2–3-недельный отскок на медвежьем рынке выводит цену выше `EMA 200` и запускает серию убыточных лонгов (107 лонгов → `Winrate 32.7%`, `Net PnL −$412`). Добавление старшего фильтра (`BTC 1D > EMA 200` или наш синтетический `TOTAL3 > SuperTrend / EMA`) как раз решает проблему переторговки против глобального тренда.


3. **Почему `BNB` тянет портфель вниз (`PF 0.82`, `−$533`):**
По `trades.csv` медианная дистанция начального стопа (`2 × ATR`) у `BNB` составляет всего **`2.13%`** (против `2.74%` у `ETH` и `3.20%` у `SOL`). Из-за узкой волатильности фиксированные издержки (`0.10%` комиссии + `0.08%` двойное проскальзывание + фандинг) отъедают у `BNB` ~**`0.08R`–`0.09R**` с каждого входа, плюс сам инструмент чаще пилит канал Дончиана.
4. **Двойной коррелированный риск в одну сторону:**
Сейчас `Target risk = 0.75%` и `Portfolio risk limit = 1.5%` позволяют открыть 2 синхронных входа в одном направлении (это происходит в **63.3%** сделок). В реальности `ETH` и `SOL` ходят синхронно — при ложном пробое портфель ловит сразу `−1.5%` (как на сделках #3–#4, #108–#109, #190–#191). Простое правило: для второй открытой позиции в *ту же* сторону снижать риск до `0.35%–0.40%` (суммарно `~1.1%` на одно направление вместо `1.5%`), а полный `0.75%` оставлять только при разнонаправленных позициях или после переноса первой в BE.







Код `breakout.py` и `manager.py` на 100% подтвердил все аномалии из `trades.csv` — все 4 бага оказались прямо в этих двух файлах.

### 1. Разбор найденных ошибок в коде

* **Почему 30 выходов по трейлингу записались как `initial_sl` (`breakout.py`):** в `compute_updated_stop` флаг `pos.be_moved = True` ставится **только** при `max_r >= be_trigger_r` (`1.5R`), а `chandelier` включается раньше — с `trail_activation_r` (`1.0R`) и никак не помечает сдвиг стопа. Если цена доходит до `1.0R–1.45R` (ниже `1.5R`), Chandelier подтягивает стоп вверх (а при сжатии ATR — даже в плюс до `+0.58R`), но `pos.be_moved` остаётся `False`, и движок маркирует закрытие как `initial_sl`. К тому же на `1.5R` Chandelier (`+0.5×ATR`) почти всегда уже выше уровня `BE (+0.12%)`, из-за чего правило BE превратилось в мёртвый код.


* **Опасный порядок проверки стопа (проверь в движке симуляции):** `compute_updated_stop` принимает `bar_high` и `bar_low` и мутирует `pos.stop_loss` прямо на месте. Если в цикле бэктеста `compute_updated_stop` вызывается **до** проверки пробоя стопа на той же свече, возникает внутрибарный lookahead bias (цена якобы сначала сходила к `high`, подтянула стоп, и только потом ударила в `low`). Проверка пробоя `stop_loss` всегда должна идти строго **перед** обновлением стопа.


* **Бесконечное продление паузы при дневной просадке (`manager.py`):** в `on_bar_start` условие `if dd >= self.cfg.max_daily_dd_pct: self._activate_cooldown(ts)` срабатывает на **каждой** 2H-свече до полуночи UTC, пока эквити ниже `-4%`, каждый раз сдвигая `cooldown_until` ещё на +24 часа вперёд (фактическая пауза растягивается почти до 46 часов вместо 24).


* **Обнуление счётчика убытков внутри серии (`manager.py`):** в `on_trade_closed` при достижении `5` убытков подряд выполняется `self.consecutive_losses = 0`. Из-за этого после 5-го стопа система забывает о просадке, и на 6–9 убытках подряд (как в ноябре–декабре 2025) снова открывает позиции через 2 часа на полный риск.


* **Коррелированный двойной риск (`manager.py`):** `evaluate_signal` проверяет только суммарный `used_risk` (1.5%), не отличая хеджированные позиции от двух синхронных сделок в одну сторону (например, `ETH` + `SOL` оба в лонг), из-за чего 63% сделок несут двойной направленный риск на один рыночный импульс.



---

### 2. Исправленный `strategy/breakout.py`

Обратно совместим с текущими `StrategyConfig` и `Position` (новые поля читаются через `getattr` с безопасными дефолтами).

* Добавлены опциональные фильтры **ускорения тренда** (`adx > prev_adx` через колонку `adx_prev`, если она есть) и **макро-режима** (`macro_bias`: `"bullish"` / `"bearish"` от `TOTAL3` или `BTC 1D`).
* Устранён конфликт BE и Chandelier (при рекомендуемых настройках `be_trigger_r <= trail_activation_r` стоп сначала фиксируется в чистый безубыток, а затем передаётся трейлингу).
* Если у `Position` есть поле `trailing_moved`, оно корректно выставляется при любом сдвиге стопа.

```python
from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd

from config import StrategyConfig
from core.models import Direction, Position, Signal


class BreakoutStrategy:
    def __init__(self, cfg: StrategyConfig) -> None:
        self.cfg = cfg

    def generate_signal(
        self,
        symbol: str,
        ts: datetime,
        bar: pd.Series,
        macro_bias: Optional[str] = None,
    ) -> Optional[Signal]:
        required = (
            "close", "volume", "ema_trend", "dc_high", "dc_low",
            "atr", "adx", "vol_ma", "body_size",
        )
        if any(pd.isna(bar.get(col)) for col in required):
            return None

        close = float(bar["close"])
        atr = float(bar["atr"])
        adx = float(bar["adx"])
        ema = float(bar["ema_trend"])
        dc_high = float(bar["dc_high"])
        dc_low = float(bar["dc_low"])
        volume = float(bar["volume"])
        vol_ma = float(bar["vol_ma"])
        body = float(bar["body_size"])

        if atr <= 0 or close <= 0 or vol_ma <= 0:
            return None
        if adx < self.cfg.adx_threshold:
            return None

        # Опциональный фильтр ускорения тренда (отсекает входы в затухающий импульс)
        if getattr(self.cfg, "require_rising_adx", False):
            adx_prev = bar.get("adx_prev")
            if adx_prev is not None and not pd.isna(adx_prev):
                if adx <= float(adx_prev):
                    return None

        if volume < vol_ma * self.cfg.vol_mult:
            return None
        if body > atr * self.cfg.max_body_atr:
            return None

        # Опциональный строгий макро-фильтр (например, от TOTAL3 / BTC 1D)
        strict_macro = getattr(self.cfg, "strict_macro_filter", False)
        bias = (macro_bias or "").lower()

        if close > ema and close > dc_high:
            if strict_macro and bias == "bearish":
                return None
            return Signal(
                symbol=symbol,
                ts=ts,
                direction=Direction.LONG,
                entry_price=close,
                stop_loss=close - atr * self.cfg.sl_atr_mult,
                atr=atr,
                adx=adx,
                reason="donchian_breakout_long",
            )

        if close < ema and close < dc_low:
            if strict_macro and bias == "bullish":
                return None
            return Signal(
                symbol=symbol,
                ts=ts,
                direction=Direction.SHORT,
                entry_price=close,
                stop_loss=close + atr * self.cfg.sl_atr_mult,
                atr=atr,
                adx=adx,
                reason="donchian_breakout_short",
            )
        return None

    def compute_updated_stop(
        self,
        pos: Position,
        bar_high: float,
        bar_low: float,
        atr: float,
    ) -> float:
        """
        ВАЖНО: вызывать строго ПОСЛЕ проверки пробоя pos.stop_loss на текущей свече,
        чтобы исключить внутрибарный lookahead bias.
        """
        if pd.isna(atr) or atr <= 0:
            return pos.stop_loss

        prev_stop = pos.stop_loss
        # Минимум 0.18% покрывает 0.10% комиссий + 0.04% slippage выхода + фандинг
        be_offset = max(self.cfg.be_offset_pct, getattr(self.cfg, "min_be_offset_pct", 0.0018))

        if pos.direction == Direction.LONG:
            pos.highest_price = max(pos.highest_price, bar_high)
            max_r = pos.r_multiple(pos.highest_price)

            if not pos.be_moved and max_r >= self.cfg.be_trigger_r:
                be_stop = pos.entry_price * (1.0 + be_offset)
                if be_stop > pos.stop_loss:
                    pos.stop_loss = be_stop
                pos.be_moved = True

            if max_r >= self.cfg.trail_activation_r:
                chandelier = pos.highest_price - atr * self.cfg.trail_atr_mult
                if chandelier > pos.stop_loss:
                    pos.stop_loss = chandelier
                    if hasattr(pos, "trailing_moved"):
                        pos.trailing_moved = True
        else:
            pos.lowest_price = min(pos.lowest_price, bar_low)
            max_r = pos.r_multiple(pos.lowest_price)

            if not pos.be_moved and max_r >= self.cfg.be_trigger_r:
                be_stop = pos.entry_price * (1.0 - be_offset)
                if be_stop < pos.stop_loss:
                    pos.stop_loss = be_stop
                pos.be_moved = True

            if max_r >= self.cfg.trail_activation_r:
                chandelier = pos.lowest_price + atr * self.cfg.trail_atr_mult
                if chandelier < pos.stop_loss:
                    pos.stop_loss = chandelier
                    if hasattr(pos, "trailing_moved"):
                        pos.trailing_moved = True

        # Подстраховка для обратной совместимости: если старый движок определяет
        # exit_reason только по pos.be_moved, помечаем флаг, когда стоп вышел в профитную зону
        if pos.stop_loss != prev_stop and not pos.be_moved:
            in_profit_zone = (
                pos.stop_loss >= pos.entry_price
                if pos.direction == Direction.LONG
                else pos.stop_loss <= pos.entry_price
            )
            if in_profit_zone:
                pos.be_moved = True

        return pos.stop_loss

```

---

### 3. Исправленный `risk/manager.py`

* **Фикс дневной паузы:** срабатывает строго 1 раз за календарный день (`daily_dd_triggered_day`), не продлевая блок до 46 часов.
* **Фикс серии убытков:** счётчик `consecutive_losses` сбрасывается **только прибыльной сделкой**; если серия продолжается после выхода из 24ч паузы, включается повторный cooldown и автоматическое снижение риска вдвое (`post_streak_risk_mult = 0.5`) до первого профита.
* **Контроль корреляции:** если уже открыта позиция в ту же сторону по другой монете, риск второй сделки автоматически режется вдвое (`same_direction_risk_mult = 0.5`), снижая пиковую просадку на синхронных выносах.
* **Поддержка `macro_bias`:** при входе против макро-тренда (`TOTAL3`/`BTC 1D`) риск снижается через `counter_macro_risk_mult` (по умолчанию `0.5`).

```python
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Dict, Optional

from config import RiskConfig
from core.models import Direction, OrderRequest, Position, Signal, TradeRecord


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

        if (
            self.daily_start_equity > 0
            and self.daily_dd_triggered_day != day
        ):
            dd = (self.daily_start_equity - equity) / self.daily_start_equity
            if dd >= self.cfg.max_daily_dd_pct:
                self.daily_dd_triggered_day = day
                self._activate_cooldown(ts)

    def on_trade_closed(self, trade: TradeRecord) -> None:
        if trade.net_pnl <= 0:
            self.consecutive_losses += 1
            # Не обнуляем серию до первой прибыльной сделки:
            # 5-й и каждый последующий убыток снова ставят паузу
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

        # 1. Демпфер коррелированного риска в одну сторону (ETH + SOL одновременно)
        same_dir_open = sum(
            1 for p in open_positions.values()
            if p.direction == signal.direction and p.current_risk_usd() > 0
        )
        if same_dir_open > 0:
            same_dir_mult = getattr(self.cfg, "same_direction_risk_mult", 0.5)
            risk_pct *= same_dir_mult

        # 2. Защитное снижение риска после выхода из серии убытков до первого профита
        if self.consecutive_losses >= self.cfg.max_consecutive_losses:
            post_streak_mult = getattr(self.cfg, "post_streak_risk_mult", 0.5)
            risk_pct *= post_streak_mult

        # 3. Мягкий макро-фильтр (вход против режима TOTAL3 / BTC 1D с половинным риском)
        bias = (macro_bias or "").lower()
        is_counter_macro = (
            (bias == "bearish" and signal.direction == Direction.LONG)
            or (bias == "bullish" and signal.direction == Direction.SHORT)
        )
        if is_counter_macro:
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

```

---

### 4. Три точечные правки в `config.py`, `indicators/features.py` и движке бэктеста

Чтобы изменения заработали на полную силу, поправь 3 места в смежных файлах:

1. **Параметры в `config.py` (разводим BE и Chandelier + чистый BE):**
```python
# Было: be_trigger_r=1.5, be_offset_pct=0.0012, trail_activation_r=1.0
be_trigger_r: float = 1.15         # Сначала фиксируем безубыток
be_offset_pct: float = 0.0020      # +0.20% покрывает 0.10% fee + 0.04% slip + funding
trail_activation_r: float = 1.50   # Chandelier подключается после BE
adx_threshold: float = 25.0        # Тестировать 22..25 с require_rising_adx=True
require_rising_adx: bool = True

```


2. **В `indicators/features.py` (1 строка для ускорения ADX):**
```python
df["adx_prev"] = df["adx"].shift(1)

```


3. **В цикле бэктеста (честные `exit_reason`, `r_multiple` и знак фандинга):**
```python
# exit_reason: сравнивать фактический стоп с начальным, а не только pos.be_moved
stop_moved = pos.be_moved or abs(pos.stop_loss - pos.initial_stop_loss) > 1e-9
exit_reason = "trailing_or_be_stop" if stop_moved else "initial_sl"

# r_multiple: считать чистый Net R (с учётом комиссий, проскальзывания и фандинга)
initial_risk_usd = abs(pos.entry_price - pos.initial_stop_loss) * pos.qty
r_multiple = net_pnl / initial_risk_usd if initial_risk_usd > 0 else 0.0

```


И в расчёте фандинга: при положительной базовой ставке `+0.0025% / 2H` лонг платит (`+cost`), а шорт **получает** (`-cost`), либо лучше подтянуть реальную историю `/fapi/v1/fundingRate` с Binance.















При этом в engine.py нашлись 6 конкретных недоработок, включая причину расхождения в ~$260 между trades.csv и equity_curve.png:

Сломанный exit_reason (строка 95): в Position уже хранится initial_stop=order.stop_loss, но при закрытии проверяется только pos.be_moved — из-за этого 30 выходов по Chandelier-трейлингу записались как initial_sl.

Валовый r_multiple (строка 94): pos.r_multiple(exit_price) не учитывает комиссии и фандинг, завышая среднее ожидание в R на +0.049R на сделку.

Односторонний фандинг (строки 102–104): cash -= funding списывает ставку в минус и на лонгах, и на шортах (на фьючерсах при положительной ставке шорт фандинг получает), плюс нет поддержки исторической колонки funding_rate.

«Зависшие» позиции в конце бэктеста: открытые на последнем баре сделки не закрываются и не выводятся в metrics. Из-за этого equity_curve.png показал ~$11,850 (с учётом нереализованного плюса), а сумма сделок в trades.csv — $11,589.85.

Утечка стейта RiskManager между запусками: self.risk создаётся один раз в __init__ — при повторном вызове run() (например, в Walk-Forward или грид-поиске) туда протекут старые consecutive_losses и cooldown_until.

Жёсткий np.sqrt(4380) в Sharpe (строка 172): ломается при смене таймфрейма с 2H и искажается плоскими участками без открытых позиций; корректнее считать Sharpe по дневной ресемплированной доходности (np.sqrt(365)).   
equity_curve.png
Ещё 1

Исправленный backtest/engine.py (с каузальным макро-фильтром)
Сохранены все старые ключи в metrics и сигнатура run(data_by_symbol) — Streamlit-интерфейс заработает без правок. Дополнительно добавлены:

Метод build_daily_macro_bias() — строит макро-режим ("bullish" / "bearish") по закрытой дневке (BTC или синтетического TOTAL3) со сдвигом .shift(1), полностью исключая подглядывание в будущее.

Пост-учёт entry_fee и проскальзывания в эквити до оценки 2-го сигнала на том же баре.

Опция close_open_positions_at_end=True для точного совпадения sum(net_pnl) с финальной точкой эквити.

Python
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


def build_daily_macro_bias(
    benchmark_df: pd.DataFrame,
    target_index: pd.DatetimeIndex,
    ema_period: int = 50,
) -> pd.Series:
    """
    Каузальный дневной макро-фильтр (например, по BTC или синтетическому TOTAL3).
    Сигнал берётся строго по ЗАКРЫТОЙ предыдущей дневной свече (.shift(1)),
    что полностью исключает lookahead bias на внутридневных барах.
    """
    if benchmark_df is None or benchmark_df.empty:
        return pd.Series(index=target_index, dtype="object")

    daily_close = benchmark_df.sort_index()["close"].resample("1D").last().dropna()
    daily_ema = daily_close.ewm(span=ema_period, adjust=False, min_periods=ema_period).mean()

    raw_bias = pd.Series(
        np.where(
            daily_ema.isna(),
            None,
            np.where(daily_close > daily_ema, "bullish", "bearish"),
        ),
        index=daily_close.index,
        dtype="object",
    )
    # Сдвиг на 1 завершённый день -> весь день T используется закрытие дня T-1
    causal_daily = raw_bias.shift(1)
    return causal_daily.reindex(target_index, method="ffill")


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
    ) -> BacktestResult:
        # Изолируем состояние RiskManager на каждый прогон (защита для Walk-Forward / грид-поиска)
        self.risk = RiskManager(self.cfg.risk)

        prepared = {
            symbol: add_indicators(df.sort_index(), self.cfg.strategy)
            for symbol, df in data_by_symbol.items()
        }
        all_timestamps = pd.DatetimeIndex(
            sorted(set().union(*(df.index for df in prepared.values())))
        )

        # Каузальный макро-фильтр (если передан benchmark вроде BTC или синтетического TOTAL3)
        macro_bias_series = (
            build_daily_macro_bias(macro_df, all_timestamps, ema_period=macro_ema_days)
            if macro_df is not None
            else None
        )

        cash = float(self.cfg.backtest.initial_capital)
        positions: Dict[str, Position] = {}
        trades: List[TradeRecord] = []
        equity_points: List[Tuple[pd.Timestamp, float]] = []
        last_close: Dict[str, float] = {}

        fee_rate = self.cfg.backtest.taker_fee_rate
        slip = self.cfg.backtest.slippage_rate
        default_funding_rate = self.cfg.backtest.funding_rate_per_2h
        directional_funding = getattr(self.cfg.backtest, "directional_funding", True)

        def calc_equity() -> float:
            return cash + sum(
                p.unrealized_pnl(last_close.get(sym, p.entry_price))
                for sym, p in positions.items()
            )

        for ts in all_timestamps:
            ts_dt = ts.to_pydatetime()
            closed_this_bar: set[str] = set()

            for symbol, df in prepared.items():
                if ts in df.index:
                    last_close[symbol] = float(df.loc[ts, "close"])

            # 1. СНАЧАЛА проверка стопов по текущему бару (без lookahead)
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
                    trade = self._finalize_trade(
                        pos=pos,
                        exit_ts=ts_dt,
                        exit_price=exit_price,
                        fee_rate=fee_rate,
                        reason_override=None,
                    )
                    cash += trade.gross_pnl - (pos.qty * exit_price * fee_rate)
                    trades.append(trade)
                    self.risk.on_trade_closed(trade)
                    del positions[symbol]
                    closed_this_bar.add(symbol)
                    continue

                # Направленный фандинг: при ставке > 0 лонг платит (+), шорт получает (-)
                bar_funding_rate = (
                    float(bar["funding_rate"])
                    if "funding_rate" in bar and not pd.isna(bar["funding_rate"])
                    else default_funding_rate
                )
                if directional_funding:
                    funding_sign = 1.0 if pos.direction == Direction.LONG else -1.0
                else:
                    funding_sign = 1.0  # режим стресс-теста (фандинг всегда расход)

                funding = funding_sign * pos.qty * bar_close * bar_funding_rate
                cash -= funding
                pos.funding_paid += funding

                # Обновление BE / Chandelier строго ПОСЛЕ проверки стопа на этом баре
                pos.stop_loss = self.strategy.compute_updated_stop(
                    pos,
                    bar_high=bar_high,
                    bar_low=bar_low,
                    atr=float(bar["atr"]),
                )

            pre_entry_equity = calc_equity()
            if pre_entry_equity <= 0:
                equity_points.append((ts, pre_entry_equity))
                break

            self.risk.on_bar_start(ts_dt, pre_entry_equity)

            # 2. ПОИСК И ИСПОЛНЕНИЕ НОВЫХ СИГНАЛОВ ПО ЗАКРЫТИЮ БАРА
            macro_bias: Optional[str] = None
            if macro_bias_series is not None:
                val = macro_bias_series.loc[ts]
                if isinstance(val, str):
                    macro_bias = val

            candidates = []
            for symbol, df in prepared.items():
                if symbol in positions or symbol in closed_this_bar or ts not in df.index:
                    continue
                signal = self.strategy.generate_signal(
                    symbol, ts_dt, df.loc[ts], macro_bias=macro_bias
                )
                if signal is not None:
                    candidates.append(signal)
            candidates.sort(key=lambda s: s.adx, reverse=True)

            for signal in candidates:
                current_equity = calc_equity()
                order = self.risk.evaluate_signal(
                    signal,
                    current_equity,
                    positions,
                    last_close,
                    ts_dt,
                    macro_bias=macro_bias,
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

            # Фиксируем эквити в конце бара уже с учётом комиссий и проскальзывания новых входов
            equity_points.append((ts, calc_equity()))

        # Опциональное принудительное закрытие открытых позиций на последнем баре
        if close_open_positions_at_end and positions and len(all_timestamps) > 0:
            last_ts_dt = all_timestamps[-1].to_pydatetime()
            for symbol in list(positions.keys()):
                pos = positions[symbol]
                mark = last_close.get(symbol, pos.entry_price)
                exit_price = (
                    mark * (1.0 - slip)
                    if pos.direction == Direction.LONG
                    else mark * (1.0 + slip)
                )
                trade = self._finalize_trade(
                    pos=pos,
                    exit_ts=last_ts_dt,
                    exit_price=exit_price,
                    fee_rate=fee_rate,
                    reason_override="end_of_backtest",
                )
                cash += trade.gross_pnl - (pos.qty * exit_price * fee_rate)
                trades.append(trade)
                del positions[symbol]
            equity_points[-1] = (all_timestamps[-1], cash)

        unrealized_end = sum(
            pos.unrealized_pnl(last_close.get(sym, pos.entry_price))
            for sym, pos in positions.items()
        )

        equity_series = pd.Series(
            [value for _, value in equity_points],
            index=pd.DatetimeIndex([timestamp for timestamp, _ in equity_points]),
            name="equity",
        )
        return BacktestResult(
            trades=trades,
            equity_curve=equity_series,
            metrics=self._compute_metrics(
                trades=trades,
                equity=equity_series,
                open_positions_count=len(positions),
                unrealized_pnl=unrealized_end,
            ),
        )

    @staticmethod
    def _finalize_trade(
        pos: Position,
        exit_ts,
        exit_price: float,
        fee_rate: float,
        reason_override: Optional[str],
    ) -> TradeRecord:
        gross_pnl = (
            (exit_price - pos.entry_price) * pos.qty
            if pos.direction == Direction.LONG
            else (pos.entry_price - exit_price) * pos.qty
        )
        exit_fee = pos.qty * exit_price * fee_rate
        total_fees = pos.entry_fee + exit_fee
        net_pnl = gross_pnl - total_fees - pos.funding_paid

        # Честный Net R (учитывает комиссии, проскальзывание и фандинг)
        initial_risk_usd = pos.initial_risk_per_unit * pos.qty
        net_r = net_pnl / initial_risk_usd if initial_risk_usd > 0 else 0.0

        # Точная причина выхода: любой сдвиг стопа от initial_stop считается trailing/BE
        stop_moved = pos.be_moved or abs(pos.stop_loss - pos.initial_stop) > 1e-9
        exit_reason = reason_override or (
            "trailing_or_be_stop" if stop_moved else "initial_sl"
        )

        return TradeRecord(
            symbol=pos.symbol,
            direction=pos.direction,
            entry_ts=pos.entry_ts,
            exit_ts=exit_ts,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            qty=pos.qty,
            gross_pnl=gross_pnl,
            fees=total_fees,
            funding=pos.funding_paid,
            net_pnl=net_pnl,
            r_multiple=net_r,
            exit_reason=exit_reason,
        )

    def _compute_metrics(
        self,
        trades: List[TradeRecord],
        equity: pd.Series,
        open_positions_count: int = 0,
        unrealized_pnl: float = 0.0,
    ) -> Dict[str, float]:
        if equity.empty:
            return {}
        start_capital = float(self.cfg.backtest.initial_capital)
        final_equity = float(equity.iloc[-1])
        total_return = final_equity / start_capital - 1.0

        running_max = equity.cummax()
        drawdown = (equity - running_max) / running_max
        max_drawdown = float(drawdown.min())

        # Дневной Sharpe (устойчив к смене таймфрейма и пропускам баров)
        daily_equity = equity.resample("1D").last().dropna()
        daily_returns = daily_equity.pct_change().dropna()
        sharpe = (
            float((daily_returns.mean() / daily_returns.std()) * np.sqrt(365))
            if len(daily_returns) > 1 and daily_returns.std() > 0
            else 0.0
        )

        span_days = max(1.0, (equity.index[-1] - equity.index[0]).total_seconds() / 86400.0)
        cagr = (final_equity / start_capital) ** (365.25 / span_days) - 1.0 if final_equity > 0 else -1.0
        calmar = cagr / abs(max_drawdown) if max_drawdown < 0 else 0.0

        wins = [t.net_pnl for t in trades if t.net_pnl > 0]
        losses = [t.net_pnl for t in trades if t.net_pnl <= 0]
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
        win_rate = len(wins) / len(trades) if trades else 0.0
        avg_r = float(np.mean([t.r_multiple for t in trades])) if trades else 0.0

        return {
            "final_equity": round(final_equity, 2),
            "total_return_pct": round(total_return * 100, 2),
            "cagr_pct": round(cagr * 100, 2),
            "max_drawdown_pct": round(max_drawdown * 100, 2),
            "calmar_ratio": round(calmar, 2),
            "sharpe_ratio": round(sharpe, 2),
            "trades_count": len(trades),
            "win_rate_pct": round(win_rate * 100, 2),
            "profit_factor": round(profit_factor, 2),
            "avg_r_multiple": round(avg_r, 3),
            "realized_net_pnl": round(sum(t.net_pnl for t in trades), 2),
            "total_fees": round(sum(t.fees for t in trades), 2),
            "total_funding": round(sum(t.funding for t in trades), 2),
            "open_positions_count": open_positions_count,
            "unrealized_pnl": round(unrealized_pnl, 2),
        }
Как сразу проверить эффект макро-фильтра в раннере / Streamlit
В месте вызова бэктестера просто передай дневной бенчмарк (например, уже загруженный BTC/USDT:USDT или средневзвешенную корзину ETH + SOL + BNB) и сравните 3 прогона:

Python
# Вариант А: базовый (без макро-фильтра, но с починенными багами)
res_base = backtester.run(data_by_symbol, close_open_positions_at_end=True)

# Вариант Б: с каузальным макро-фильтром по BTC 1D EMA 50 (или 100)
res_macro = backtester.run(
    data_by_symbol,
    macro_df=btc_2h_df,
    macro_ema_days=50,
    close_open_positions_at_end=True,
)



Если после прогона скинешь новый trades.csv (или метрики сравнения базового прогона, варианта без BNB и варианта с macro_df) — сразу сделаем объективное сравнение «до / после» по просадке, PF, Calmar и стагнации.