# engine/dry_run_engine.py
# ═══════════════════════════════════════════════════════════════
#  Фоновый поток: раз в config.POLL_SECONDS опрашивает Binance,
#  считает индикаторы и, если появилась НОВАЯ закрытая свеча,
#  прогоняет её через стратегию (strategy.process_bar).
#
#  Работает как daemon-thread внутри того же процесса, что и
#  Streamlit-приложение (см. app.py, @st.cache_resource).
# ═══════════════════════════════════════════════════════════════
from __future__ import annotations
import threading
import traceback
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

import config
from . import data_feed, strategy


class DryRunEngine:
    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._stop_flag = threading.Event()
        self._data_lock = threading.Lock()

        self._last_bar_ts = None
        self._last_df: Optional[pd.DataFrame] = None

        self.status = "stopped"
        self.last_error: Optional[str] = None
        self.last_update: Optional[datetime] = None
        self.last_event: Optional[dict] = None

    # ── управление потоком ────────────────────────────────────
    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_flag.clear()
        self._thread = threading.Thread(target=self._run_loop, name="dry-run-engine", daemon=True)
        self._thread.start()
        self.status = "running"

    def stop(self) -> None:
        self._stop_flag.set()
        self.status = "stopped"

    # ── основной цикл ─────────────────────────────────────────
    def _run_loop(self) -> None:
        while not self._stop_flag.is_set():
            try:
                df = data_feed.fetch_closed_klines()
                df = strategy.compute_indicators(df)

                with self._data_lock:
                    self._last_df = df
                    self.last_update = datetime.now(timezone.utc)
                    self.last_error = None

                last_ts = df.index[-1]

                if self._last_bar_ts is None:
                    # первый запуск после (пере)старта приложения:
                    # просто запоминаем текущий бар, чтобы не открывать
                    # сделки задним числом по уже прошедшим флипам
                    self._last_bar_ts = last_ts
                elif last_ts != self._last_bar_ts:
                    self.last_event = strategy.process_bar(df)
                    self._last_bar_ts = last_ts

            except Exception as e:
                self.last_error = f"{e}\n{traceback.format_exc()}"

            self._stop_flag.wait(config.POLL_SECONDS)

    # ── доступ к данным из UI-потока ──────────────────────────
    def snapshot(self) -> Optional[pd.DataFrame]:
        with self._data_lock:
            return self._last_df.copy() if self._last_df is not None else None


# ── синглтон на процесс ─────────────────────────────────────────
_engine_singleton: Optional[DryRunEngine] = None
_singleton_lock = threading.Lock()


def get_engine() -> DryRunEngine:
    global _engine_singleton
    with _singleton_lock:
        if _engine_singleton is None:
            _engine_singleton = DryRunEngine()
            _engine_singleton.start()
        return _engine_singleton
