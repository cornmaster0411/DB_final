import numpy as np
import pandas as pd


class ResearchIndicatorCalculator:
    """Indicators used by the generic strategy comparison page."""

    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
        if "date" in self.df.columns:
            self.df = self.df.set_index("date")
        self.df = self.df.sort_index()

    def calculate_all(self) -> pd.DataFrame:
        self._calculate_moving_averages()
        self._calculate_bias()
        self._calculate_bb()
        self._calculate_macd()
        self._calculate_kdj()
        return self.df.reset_index()

    def _calculate_moving_averages(self):
        close = self.df["close_price"]
        for period in [5, 10, 20, 60, 120, 240]:
            col = f"ma_{period}"
            if col not in self.df.columns or self.df[col].isna().all():
                self.df[col] = close.rolling(period).mean()

    def _calculate_bias(self):
        close = self.df["close_price"]
        for period in [10, 20]:
            ma_col = f"ma_{period}"
            bias_col = f"bias_{period}"
            if ma_col in self.df.columns:
                self.df[bias_col] = ((close - self.df[ma_col]) / self.df[ma_col]) * 100

    def _calculate_bb(self, period: int = 20, width: float = 2.0):
        close = self.df["close_price"]
        middle = close.rolling(period).mean()
        std = close.rolling(period).std()
        self.df["bb_middle"] = middle
        self.df["bb_upper"] = middle + width * std
        self.df["bb_lower"] = middle - width * std
        self.df["bb_buy"] = (close.shift(1) < self.df["bb_lower"].shift(1)) & (close > self.df["bb_lower"])
        self.df["bb_sell"] = close >= self.df["bb_upper"]

    def _calculate_macd(self, fast: int = 12, slow: int = 26, signal: int = 9):
        close = self.df["close_price"]
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        self.df["macd"] = ema_fast - ema_slow
        self.df["macd_signal"] = self.df["macd"].ewm(span=signal, adjust=False).mean()
        self.df["macd_hist"] = self.df["macd"] - self.df["macd_signal"]
        self.df["macd_buy"] = (
            (self.df["macd"].shift(1) <= self.df["macd_signal"].shift(1))
            & (self.df["macd"] > self.df["macd_signal"])
        )
        self.df["macd_sell"] = (
            (self.df["macd"].shift(1) >= self.df["macd_signal"].shift(1))
            & (self.df["macd"] < self.df["macd_signal"])
        )

    def _calculate_kdj(self, period: int = 9):
        low_min = self.df["low_price"].rolling(window=period).min()
        high_max = self.df["high_price"].rolling(window=period).max()
        rsv = 100 * (self.df["close_price"] - low_min) / (high_max - low_min + 1e-8)
        self.df["kdj_k"] = rsv.ewm(com=2, adjust=False).mean()
        self.df["kdj_d"] = self.df["kdj_k"].ewm(com=2, adjust=False).mean()
        self.df["kdj_j"] = 3 * self.df["kdj_k"] - 2 * self.df["kdj_d"]
        self.df["kdj_buy"] = (
            (self.df["kdj_k"].shift(1) <= self.df["kdj_d"].shift(1))
            & (self.df["kdj_k"] > self.df["kdj_d"])
            & (self.df["kdj_j"] < 100)
        )
        self.df["kdj_sell"] = (
            (self.df["kdj_k"].shift(1) >= self.df["kdj_d"].shift(1))
            & (self.df["kdj_k"] < self.df["kdj_d"])
        )

    @staticmethod
    def add_research_signals(df: pd.DataFrame, ma_period: int = 20, bias_threshold: float = 10.0):
        work = df.copy().sort_values("date").reset_index(drop=True)
        close = work["close_price"]
        open_price = work["open_price"]
        high = work["high_price"]
        low = work["low_price"]
        ma = work[f"ma_{ma_period}"]
        bias = work[f"bias_{ma_period}"]

        prev_close = close.shift(1)
        prev_ma = ma.shift(1)
        ma_slope = ma - prev_ma
        ma_rising = ma_slope > 0
        ma_falling = ma_slope < 0
        ma_flat = ma_slope.abs() < (ma * 0.001)

        cross_up = (prev_close < prev_ma) & (close > ma)
        cross_down = (prev_close > prev_ma) & (close < ma)

        buy1 = cross_up & (ma_flat | ma_rising)
        buy2 = cross_up & ma_rising
        buy3 = ma_rising & (low <= ma * 1.015) & (low >= ma) & (close > open_price)
        buy4 = ma_falling & (bias <= -bias_threshold)
        sell1 = cross_down & (ma_flat | ma_falling)
        sell2 = cross_down & ma_falling
        sell3 = ma_falling & (high >= ma * 0.985) & (high <= ma) & (close < open_price)
        sell4 = ma_rising & (bias >= bias_threshold)

        work["granville_buy"] = buy1 | buy2 | buy3 | buy4
        work["granville_sell"] = sell1 | sell2 | sell3 | sell4
        work["granville_rule"] = np.select(
            [buy1, buy2, buy3, buy4, sell1, sell2, sell3, sell4],
            ["買點1", "買點2", "買點3", "買點4", "賣點1", "賣點2", "賣點3", "賣點4"],
            default="",
        )
        return work
