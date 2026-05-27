import pandas as pd
import numpy as np

class IndicatorCalculator:
    """
    專注於計算遞迴指標 (RSI, KD) 的計算引擎。
    MA 和 BIAS 已經由資料庫 SP 算好了，所以這裡直接跳過它們。
    預期的輸入 DataFrame 必須包含： 'date', 'high_price', 'low_price', 'close_price'
    """
    
    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
        if 'date' in self.df.columns:
            self.df = self.df.set_index('date')
        self.df = self.df.sort_index()

    def calculate_all(self) -> pd.DataFrame:
        """只計算 RSI 和 KD"""
        self._calculate_rsi()
        self._calculate_kd()
        return self.df

    def _calculate_rsi(self):
        """計算 RSI (5日, 10日) - 使用 EMA 平滑"""
        periods = [5, 10]
        delta = self.df['close_price'].diff()
        gain = delta.clip(lower=0)
        loss = -1 * delta.clip(upper=0)
        
        for period in periods:
            avg_gain = gain.ewm(com=(period - 1), min_periods=period).mean()
            avg_loss = loss.ewm(com=(period - 1), min_periods=period).mean()
            rs = avg_gain / (avg_loss + 1e-8)
            self.df[f'rsi_{period}'] = 100 - (100 / (1 + rs))

    def _calculate_kd(self, period: int = 9):
        """計算 KD 指標 (9日 RSV) - 使用 EMA 平滑"""
        low_min = self.df['low_price'].rolling(window=period).min()
        high_max = self.df['high_price'].rolling(window=period).max()
        
        rsv = 100 * (self.df['close_price'] - low_min) / (high_max - low_min + 1e-8)
        
        self.df['kd_k'] = rsv.ewm(com=2, adjust=False).mean() 
        self.df['kd_d'] = self.df['kd_k'].ewm(com=2, adjust=False).mean()