from __future__ import annotations
import pandas as pd


class BaseIndicator:
    """Минимальный интерфейс индикатора: принимает OHLCV DataFrame,
    возвращает его же с добавленными колонками."""

    name: str = "base"

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        raise NotImplementedError
