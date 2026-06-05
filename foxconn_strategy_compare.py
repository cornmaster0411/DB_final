from dataclasses import dataclass
from typing import Callable

import pandas as pd


SignalFunc = Callable[[pd.Series], bool]


@dataclass
class StrategySpec:
    name: str
    buy_signal: SignalFunc
    sell_signal: SignalFunc


def prepare_strategy_specs() -> list[StrategySpec]:
    return [
        StrategySpec(
            name="純葛蘭碧",
            buy_signal=lambda row: bool(row.get("granville_buy", False)),
            sell_signal=lambda row: bool(row.get("granville_sell", False)),
        ),
        StrategySpec(
            name="葛蘭碧 + 外資週淨買超",
            buy_signal=lambda row: bool(row.get("granville_buy", False))
            and bool(row.get("foreign_recent_buy", False)),
            sell_signal=lambda row: bool(row.get("granville_sell", False)),
        ),
        StrategySpec(
            name="葛蘭碧 + BB",
            buy_signal=lambda row: bool(row.get("granville_buy", False)) and bool(row.get("bb_buy", False)),
            sell_signal=lambda row: bool(row.get("granville_sell", False)) or bool(row.get("bb_sell", False)),
        ),
        StrategySpec(
            name="葛蘭碧 + MACD",
            buy_signal=lambda row: bool(row.get("granville_buy", False)) and bool(row.get("macd_buy", False)),
            sell_signal=lambda row: bool(row.get("granville_sell", False)) or bool(row.get("macd_sell", False)),
        ),
        StrategySpec(
            name="葛蘭碧 + KDJ",
            buy_signal=lambda row: bool(row.get("granville_buy", False)) and bool(row.get("kdj_buy", False)),
            sell_signal=lambda row: bool(row.get("granville_sell", False)) or bool(row.get("kdj_sell", False)),
        ),
    ]


class FoxconnBacktester:
    """Batch backtester for the Foxconn research page.

    Signals are observed at day close and executed at the next trading day's open
    to avoid same-bar lookahead.
    """

    def __init__(
        self,
        df: pd.DataFrame,
        initial_capital: float = 1_000_000,
        fee_rate: float = 0.001425,
        tax_rate: float = 0.003,
    ):
        self.df = df.copy().sort_values("date").reset_index(drop=True)
        self.initial_capital = float(initial_capital)
        self.fee_rate = fee_rate
        self.tax_rate = tax_rate

    def run_all(self, strategies: list[StrategySpec]) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, pd.DataFrame]]:
        summaries = []
        curves = []
        trades_by_strategy = {}

        hold_summary, hold_curve, hold_trades = self._run_buy_and_hold()
        summaries.append(hold_summary)
        curves.append(hold_curve)
        trades_by_strategy["Buy & Hold"] = hold_trades

        for strategy in strategies:
            summary, curve, trades = self.run_strategy(strategy)
            summaries.append(summary)
            curves.append(curve)
            trades_by_strategy[strategy.name] = trades

        return pd.DataFrame(summaries), pd.concat(curves, ignore_index=True), trades_by_strategy

    def _run_buy_and_hold(self):
        data = self.df.dropna(subset=["open_price", "close_price"]).reset_index(drop=True)
        if len(data) < 2:
            return self._empty_summary("Buy & Hold"), pd.DataFrame(), pd.DataFrame()

        buy_row = data.iloc[0]
        sell_row = data.iloc[-1]
        buy_price = float(buy_row["open_price"])
        shares = int(self.initial_capital // (buy_price * (1 + self.fee_rate)))
        capital = self.initial_capital - shares * buy_price * (1 + self.fee_rate)
        curve = []
        for _, row in data.iterrows():
            equity = capital + shares * float(row["close_price"])
            curve.append({"date": row["date"], "strategy": "Buy & Hold", "equity": equity})

        sell_price = float(sell_row["close_price"])
        final_equity = capital + shares * sell_price * (1 - self.fee_rate - self.tax_rate)
        trade = pd.DataFrame([{
            "買入日期": buy_row["date"],
            "買入價": buy_price,
            "賣出日期": sell_row["date"],
            "賣出價": sell_price,
            "股數": shares,
            "報酬率(%)": (sell_price - buy_price) / buy_price * 100,
            "損益": final_equity - self.initial_capital,
            "買入原因": "期初買入",
            "賣出原因": "期末結算",
        }])
        return self._summary("Buy & Hold", final_equity, pd.DataFrame(curve), trade), pd.DataFrame(curve), trade

    def run_strategy(self, strategy: StrategySpec):
        capital = self.initial_capital
        shares = 0
        open_position = None
        trades = []
        curve = []

        data = self.df.dropna(subset=["open_price", "close_price"]).reset_index(drop=True)
        for i in range(len(data) - 1):
            signal_row = data.iloc[i]
            exec_row = data.iloc[i + 1]
            mark_price = float(signal_row["close_price"])
            curve.append({
                "date": signal_row["date"],
                "strategy": strategy.name,
                "equity": capital + shares * mark_price,
            })

            if shares == 0 and strategy.buy_signal(signal_row):
                exec_price = float(exec_row["open_price"])
                shares_to_buy = int(capital // (exec_price * (1 + self.fee_rate)))
                if shares_to_buy > 0:
                    cost = shares_to_buy * exec_price * (1 + self.fee_rate)
                    capital -= cost
                    shares = shares_to_buy
                    open_position = {
                        "buy_date": exec_row["date"],
                        "buy_price": exec_price,
                        "shares": shares_to_buy,
                        "buy_reason": self._reason_for_buy(signal_row),
                    }
            elif shares > 0 and strategy.sell_signal(signal_row):
                exec_price = float(exec_row["open_price"])
                capital += shares * exec_price * (1 - self.fee_rate - self.tax_rate)
                trades.append(self._close_trade(open_position, exec_row, exec_price, shares, signal_row))
                shares = 0
                open_position = None

        if len(data) > 0:
            last = data.iloc[-1]
            if shares > 0 and open_position:
                sell_price = float(last["close_price"])
                capital += shares * sell_price * (1 - self.fee_rate - self.tax_rate)
                trades.append(self._close_trade(open_position, last, sell_price, shares, last, "期末結算"))
                shares = 0
                open_position = None
            curve.append({"date": last["date"], "strategy": strategy.name, "equity": capital})

        curve_df = pd.DataFrame(curve)
        trades_df = pd.DataFrame(trades)
        return self._summary(strategy.name, capital, curve_df, trades_df), curve_df, trades_df

    def _close_trade(self, open_position, sell_row, sell_price, shares, signal_row, sell_reason=None):
        buy_price = open_position["buy_price"]
        return {
            "買入日期": open_position["buy_date"],
            "買入價": buy_price,
            "賣出日期": sell_row["date"],
            "賣出價": sell_price,
            "股數": shares,
            "報酬率(%)": (sell_price - buy_price) / buy_price * 100,
            "損益": (sell_price - buy_price) * shares,
            "買入原因": open_position["buy_reason"],
            "賣出原因": sell_reason or self._reason_for_sell(signal_row),
        }

    def _summary(self, name, final_equity, curve_df, trades_df):
        total_return = (final_equity - self.initial_capital) / self.initial_capital * 100
        max_drawdown = 0.0
        if not curve_df.empty:
            cummax = curve_df["equity"].cummax()
            drawdown = (curve_df["equity"] - cummax) / cummax
            max_drawdown = float(drawdown.min() * 100)

        trade_count = len(trades_df)
        win_rate = 0.0
        if trade_count > 0 and "損益" in trades_df:
            win_rate = float((trades_df["損益"] > 0).mean() * 100)

        return {
            "策略": name,
            "期末資產": round(final_equity, 0),
            "總報酬率(%)": round(total_return, 2),
            "最大回撤(%)": round(max_drawdown, 2),
            "交易次數": trade_count,
            "勝率(%)": round(win_rate, 1),
        }

    def _empty_summary(self, name):
        return {
            "策略": name,
            "期末資產": self.initial_capital,
            "總報酬率(%)": 0.0,
            "最大回撤(%)": 0.0,
            "交易次數": 0,
            "勝率(%)": 0.0,
        }

    @staticmethod
    def _reason_for_buy(row):
        reasons = []
        if row.get("granville_buy", False):
            reasons.append(f"葛蘭碧{row.get('granville_rule', '')}".strip())
        if row.get("foreign_recent_buy", False):
            reasons.append("外資週淨買超")
        if row.get("bb_buy", False):
            reasons.append("BB 反彈")
        if row.get("macd_buy", False):
            reasons.append("MACD 金叉")
        if row.get("kdj_buy", False):
            reasons.append("KDJ 金叉")
        return " + ".join(reasons) or "買入訊號"

    @staticmethod
    def _reason_for_sell(row):
        reasons = []
        if row.get("granville_sell", False):
            reasons.append(f"葛蘭碧{row.get('granville_rule', '')}".strip())
        if row.get("bb_sell", False):
            reasons.append("BB 上緣")
        if row.get("macd_sell", False):
            reasons.append("MACD 死叉")
        if row.get("kdj_sell", False):
            reasons.append("KDJ 死叉")
        return " + ".join(reasons) or "賣出訊號"

