# Сигналы и риск-движок Streamlit-системы

Актуальная конфигурация: `ADX threshold = 25`, `rising ADX`, таймфрейм `2H`, портфель `ETH/SOL/BNB`, дневной фильтр Synthetic TOTAL3.

## Дневной фильтр Synthetic TOTAL3

Фильтр построен по принципу из `synthetic_total_monitor_v2.html`:

- 18 альт-монет из корзины TOTAL3;
- рыночная капитализация каждого актива = рыночная цена × резервная circulating supply;
- Synthetic TOTAL3 = сумма капитализаций альтов;
- `EMA20` и `EMA50` по дневной свече;
- `SuperTrend(10, 3)` по дневной свече.

Направление фиксируется только по уже закрытой дневной свече. На следующий UTC-день применяется одно значение:

```text
BULLISH:
close > EMA20
EMA20 > EMA50
SuperTrend direction = 1

BEARISH:
close < EMA20
EMA20 < EMA50
SuperTrend direction = -1

Иначе: NEUTRAL
```

При `BULLISH` система открывает только LONG. При `BEARISH` — только SHORT. При `NEUTRAL` новые позиции не открываются.

## Расчёт индикаторов

Формула EMA тренда:

```text
EMA_trend = EMA(close, 200)
```

Пробойный канал Donchian строится только по прошлым свечам:

```text
DC_high = max(high, window=20).shift(1)
DC_low  = min(low, window=20).shift(1)
```

ATR:

```text
TR = max(high-low, abs(high-prev_close), abs(low-prev_close))
ATR = Wilder RMA(TR, 14)
```

ADX рассчитывается по Wilder RMA для +DM/-DM и +DI/-DI с периодом 14.

Средний объём:

```text
Volume_MA = mean(volume, window=20).shift(1)
```

Тело свечи:

```text
Body = abs(close-open)
```

Расчёт индикаторов находится в `indicators/features.py`.

## Правила входа

Сигнал создаётся только при одновременном выполнении условий.

Общие фильтры:

```text
ATR > 0
close > 0
Volume_MA > 0
ADX >= 30
volume >= Volume_MA * 1.15
Body <= ATR * 2.8
```

Вход в LONG:

```text
close > EMA_trend
close > DC_high

Initial stop = close - ATR * 2.0
```

Вход в SHORT:

```text
close < EMA_trend
close < DC_low

Initial stop = close + ATR * 2.0
```

Одновременно срабатывающие сигналы сортируются по убывающему ADX. Максимум две позиции из трёх активов.

Формирование сигнала находится в `strategy/breakout.py`.

## Размер позиции и риск

Для каждого нового входа:

```text
Stop distance = abs(entry_price - stop_loss)
Target risk = equity * 0.75%
Portfolio risk limit = equity * 1.5%
Used risk = sum(current_risk_usd of open positions)
Available risk = max(0, Portfolio risk limit - Used risk)
Risk budget = min(Target risk, Available risk)

Quantity = Risk budget / Stop distance
Notional = Quantity * Entry price
```

После расчёта применяется три ограничения:

```text
Max notional per symbol = equity * 1.5
Max portfolio notional = equity * 2.5 - used portfolio notional
Min notional = 20 USDT
Final quantity = capped_notional / entry_price
```

Остаточный риск позиции:

```text
LONG:  max(0, entry_price - stop_loss) * quantity
SHORT: max(0, stop_loss - entry_price) * quantity
```

После перевода стопа в безубыток или выше прибыльного уровня остаточный риск считается равным нулю.

Риск-движок находится в `risk/manager.py`.

## Правила выхода и сопровождения

Позиция проверяется на пробитие стопа по свечному low/high:

```text
LONG stop hit: low <= stop_loss
SHORT stop hit: high >= stop_loss
```

Код рассчитывает консервативный fill:

```text
LONG exit fill = min(bar_open, stop_loss) * (1 - slippage)
SHORT exit fill = max(bar_open, stop_loss) * (1 + slippage)
```

Позиция переводится в безубыток при достижении `+1.5R`:

```text
R = profit distance / initial_risk_per_unit

LONG BE = entry_price * (1 + 0.0012)
SHORT BE = entry_price * (1 - 0.0012)
```

Chandelier trailing stop активируется с `+1.0R`:

```text
LONG stop = highest_price - ATR * 2.5
SHORT stop = lowest_price + ATR * 2.5
```

Новый стоп никогда не откатывается назад:

```text
LONG:  stop_new = max(stop_old, stop_candidate)
SHORT: stop_new = min(stop_old, stop_candidate)
```

Причины закрытия:

- `initial_sl` — сработал начальный стоп;
- `trailing_or_be_stop` — сработал BE/trailing stop.

## Circuit breaker

Дневная просадка:

```text
Daily DD = (daily_start_equity - current_equity) / daily_start_equity
Pause = 24 hours when Daily DD >= 4%
```

Серия убытков:

```text
Pause = 24 hours after 5 consecutive losing trades
```

При pause все новые входы блокируются.

## Расчёт PnL

```text
LONG gross PnL  = (exit_price-entry_price) * quantity
SHORT gross PnL = (entry_price-exit_price) * quantity

Net PnL = gross PnL - entry_fee - exit_fee - funding
R multiple = (exit_price-entry_price)/initial_risk_per_unit   # LONG
R multiple = (entry_price-exit_price)/initial_risk_per_unit   # SHORT
```

Бэктестовые параметры:

```text
Initial capital = 10,000 USDT
Taker fee = 0.05% per side
Slippage = 0.04%
Funding = 0.0025% per 2H candle
```
