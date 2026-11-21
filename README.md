---
title: Stocashi Macd Eth Dryrun
emoji: 📈
colorFrom: blue
colorTo: green
sdk: docker
app_port: 8501
tags:
  - streamlit
pinned: false
---

# Stocashi + MACD — ETHUSDT H1 Dry Run

Автоматическая dry-run (бумажная) торговая система на связке двух индикаторов:

- **Stocashi** — Stochastic RSI + Heikin-Ashi свечи (точный порт `Stocashi_Gem_0.1.mq5`)
- **MACD** — классический (12/26/9), используется как фильтр по нулевой линии

## Логика сигналов

Позиция **закрывается** всегда при смене цвета свечи Stocashi.
Позиция в новом направлении **открывается только если её подтверждает MACD**:

| Событие | Условие | Действие |
|---|---|---|
| Stocashi: красный → зелёный | MACD > 0 | **BUY** — открыть LONG |
| Stocashi: зелёный → красный | MACD < 0 | **SELL** — открыть SHORT |
| Цвет сменился, MACD не подтвердил | — | остаёмся вне рынка до следующей смены цвета |

Данные — ETHUSDT, таймфрейм H1, публичный REST Binance (без API-ключей).

## Архитектура

Space использует **Docker SDK** (нативный SDK `streamlit` в форме создания Space
сейчас deprecated на Hugging Face — актуальный способ деплоя Streamlit-приложений
это Docker SDK + свой `Dockerfile`, что уже настроено в этом проекте).

```
Dockerfile                 # описывает контейнер для HF Spaces (Docker SDK)
app.py                     # Streamlit UI: график + таблицы сигналов/сделок
config.py                  # все параметры (символ, таймфрейм, индикаторы, БД)
indicators/
  stocashi.py               # индикатор Stocashi (как в исходном .py)
  macd.py                    # индикатор MACD
engine/
  data_feed.py               # получение свечей с Binance (klines REST API)
  strategy.py                 # правила BUY/SELL + управление позицией
  storage.py                   # SQLite / Neon Postgres (SQLAlchemy)
  dry_run_engine.py             # фоновый Thread: опрос биржи раз в POLL_SECONDS
```

Фоновый поток (`engine/dry_run_engine.py`) стартует один раз на процесс
(через `st.cache_resource`) и работает внутри того же веб-приложения —
отдельный сервис не нужен.

## Переменные окружения (Space secrets / variables)

| Переменная | По умолчанию | Описание |
|---|---|---|
| `SYMBOL` | `ETHUSDT` | Торговая пара Binance |
| `INTERVAL` | `1h` | Таймфрейм свечей |
| `POLL_SECONDS` | `60` | Как часто фоновый поток опрашивает биржу |
| `HISTORY_LIMIT` | `500` | Сколько свечей истории подгружать при старте |
| `START_BALANCE` | `10000` | Условный баланс для расчёта размера позиции |
| `POSITION_PCT` | `1.0` | Доля баланса на одну сделку (1.0 = 100%) |
| `DATABASE_URL` | *(не задана → SQLite)* | Строка подключения Neon/Postgres, например `postgresql://user:pass@host/db?sslmode=require` |

### Подключение Neon (опционально)

По умолчанию сигналы и сделки пишутся в локальный SQLite-файл
(`data/stocashi_dryrun.db`) — он живёт только внутри контейнера Space
и может сброситься при пересборке/перезапуске Space.

Чтобы данные сохранялись постоянно — заведи бесплатную базу на
[neon.tech](https://neon.tech), скопируй connection string и добавь его
в Space как **Secret** с именем `DATABASE_URL`. Код менять не нужно —
`engine/storage.py` через SQLAlchemy сам переключится на Postgres.

## Локальный запуск

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Важные оговорки

- Это **dry run** (бумажная торговля) — реальные ордера никуда не отправляются.
- Расчёт PnL условный: фиксированная доля виртуального баланса на сделку,
  без учёта комиссий, проскальзывания и ограничений биржи.
- Сигналы считаются только по **закрытым** H1-свечам — текущая формирующаяся
  свеча в расчёт не берётся, чтобы индикаторы не «перерисовывались».
- Публичный REST Binance иногда даёт гео-ограничения по IP; код пробует
  запасной хост `data-api.binance.vision` (market-data-only домен).
