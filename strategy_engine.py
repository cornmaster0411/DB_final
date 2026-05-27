import pandas as pd
import numpy as np

class StrategyEngine:
    """
    綜合量化策略引擎：
    依照 MD -> RSI -> KD -> BIAS -> 葛蘭必 的順序計算所有訊號。
    使用矩陣運算，一次性處理所有歷史資料。
    """
    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
        if 'date' in self.df.columns:
            self.df = self.df.set_index('date')
        self.df = self.df.sort_index()

    def generate_all_signals(self, ma_period=10, rsi_period=5, kd_period=9, bias_threshold=10.0):
        """一次性計算並標記所有的技術訊號"""
        self._calc_md_trend()                               # 1. MD (均線多空趨勢)
        self._calc_rsi_signals(rsi_period)                  # 2. RSI 訊號
        self._calc_kd_signals()                             # 3. KD 訊號
        self._calc_bias_signals(ma_period, bias_threshold)  # 4. BIAS 乖離率
        self._calc_granville(ma_period, bias_threshold)     # 5. 葛蘭必八大法則
        
        return self.df

    def _calc_md_trend(self):
        """【1. MD 均線趨勢】引入 MA5, MA10, MA20 三線邏輯判斷"""
        if 'ma_5' not in self.df.columns or 'ma_10' not in self.df.columns or 'ma_20' not in self.df.columns:
            self.df['trend_status'] = '資料不足'
            return

        c = self.df['close_price']
        ma5 = self.df['ma_5']
        ma10 = self.df['ma_10']
        ma20 = self.df['ma_20']
        
        conditions = [
            (c > ma5) & (ma5 > ma10) & (ma10 > ma20), # 多頭排列 (強勢)
            (c < ma20) & (ma20 < ma10) & (ma10 < ma5), # 空頭排列 (弱勢)
            (c > ma20) & (ma20 < ma10),                # 突破均線 (反彈轉強)
            (c < ma20) & (ma20 > ma10)                 # 跌破均線 (漲多拉回)
        ]
        choices = [
            '多頭排列 (強勢)',
            '空頭排列 (弱勢)',
            '突破均線 (反彈轉強)',
            '跌破均線 (漲多拉回)'
        ]
        self.df['trend_status'] = np.select(conditions, choices, default='中繼盤整')

    def _calc_rsi_signals(self, period, overbought=70, oversold=30):
        """【2. RSI 訊號】判斷超買與超賣"""
        rsi_col = f'rsi_{period}'
        self.df['signal_rsi'] = '無'
        if rsi_col in self.df.columns:
            rsi = self.df[rsi_col]
            self.df.loc[rsi <= oversold, 'signal_rsi'] = '🔴 超賣區 (可能有跌深反彈機會)'
            self.df.loc[rsi >= overbought, 'signal_rsi'] = '🟢 超買區 (注意過熱拉回風險)'

    def _calc_kd_signals(self):
        """【3. KD 訊號】判斷黃金交叉與死亡交叉"""
        self.df['signal_kd'] = '無'
        if 'kd_k' in self.df.columns and 'kd_d' in self.df.columns:
            k, d = self.df['kd_k'], self.df['kd_d']
            prev_k, prev_d = k.shift(1), d.shift(1)
            
            # 黃金交叉 (K由下往上穿過D)
            self.df.loc[(prev_k < prev_d) & (k > d), 'signal_kd'] = '🔴 KD黃金交叉 (偏多)'
            # 死亡交叉 (K由上往下跌破D)
            self.df.loc[(prev_k > prev_d) & (k < d), 'signal_kd'] = '🟢 KD死亡交叉 (偏空)'

    def _calc_bias_signals(self, ma_period, threshold):
        """【4. BIAS 乖離率】判斷偏離均線程度"""
        bias_col = f'bias_{ma_period}'
        self.df['signal_bias'] = '無'
        if bias_col in self.df.columns:
            bias = self.df[bias_col]
            self.df.loc[bias > threshold, 'signal_bias'] = f'🟢 正乖離過大 (>{threshold}%)'
            self.df.loc[bias < -threshold, 'signal_bias'] = f'🔴 負乖離過大 (<-{threshold}%)'

    def _calc_granville(self, ma_period, bias_threshold):
        """【5. 葛蘭必八大法則】完整實作四買四賣"""
        self.df['signal_granville'] = '無'
        ma_col = f'ma_{ma_period}'
        bias_col = f'bias_{ma_period}'
        
        if ma_col not in self.df.columns or bias_col not in self.df.columns:
            return

        c = self.df['close_price']
        o = self.df['open_price']
        h = self.df['high_price']
        l = self.df['low_price']
        ma = self.df[ma_col]
        bias = self.df[bias_col]

        prev_c = c.shift(1)
        prev_ma = ma.shift(1)

        ma_slope = ma - prev_ma
        ma_is_rising = ma_slope > 0
        ma_is_falling = ma_slope < 0
        ma_is_flat = ma_slope.abs() < (ma * 0.001)

        cross_up = (prev_c < prev_ma) & (c > ma)
        cross_down = (prev_c > prev_ma) & (c < ma)

        buy1 = cross_up & (ma_is_flat | ma_is_rising)
        buy2 = cross_up & ma_is_rising
        buy3 = ma_is_rising & (l <= ma * 1.015) & (l >= ma) & (c > o)
        buy4 = ma_is_falling & (bias <= -bias_threshold)

        sell1 = cross_down & (ma_is_flat | ma_is_falling)
        sell2 = cross_down & ma_is_falling
        sell3 = ma_is_falling & (h >= ma * 0.985) & (h <= ma) & (c < o)
        sell4 = ma_is_rising & (bias >= bias_threshold)

        self.df.loc[buy1, 'signal_granville'] = '🔴 買點1: 突破均線 (均線走平/轉強)'
        self.df.loc[buy2, 'signal_granville'] = '🔴 買點2: 假跌破站回 (均線上升)'
        self.df.loc[buy3, 'signal_granville'] = '🔴 買點3: 回測支撐不破 (趨勢延續)'
        self.df.loc[buy4, 'signal_granville'] = '🔴 買點4: 負乖離過大 (搶跌深反彈)'
        
        self.df.loc[sell1, 'signal_granville'] = '🟢 賣點1: 跌破均線 (均線走平/轉弱)'
        self.df.loc[sell2, 'signal_granville'] = '🟢 賣點2: 假突破跌回 (均線下降)'
        self.df.loc[sell3, 'signal_granville'] = '🟢 賣點3: 反彈遇壓回落 (弱勢延續)'
        self.df.loc[sell4, 'signal_granville'] = '🟢 賣點4: 正乖離過大 (漲多獲利了結)'