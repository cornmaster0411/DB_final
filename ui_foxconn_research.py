from datetime import date, timedelta

import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from db_config import get_db_session
from foxconn_strategy_compare import FoxconnBacktester, StrategySpec, prepare_strategy_specs
from institutional_fetcher import InstitutionalFetcher
from models import DailyPrice, InstitutionalTrade, Stock, TransactionRecord
from research_indicator_calculator import ResearchIndicatorCalculator


FOREIGN_WEEK_DAYS = 5


@st.cache_data(ttl=300)
def load_research_stock_options():
    with get_db_session()() as session:
        stocks = session.query(Stock).filter(
            Stock.is_index != True
        ).order_by(Stock.stock_code.asc()).all()

    return [f"{s.stock_code} {s.name}" for s in stocks if s.stock_code != "^TWII"]


@st.cache_data(ttl=300)
def load_research_price_data(stock_code):
    with get_db_session()() as session:
        records = session.query(DailyPrice).filter(
            DailyPrice.stock_code == stock_code
        ).order_by(DailyPrice.date.asc()).all()

    if not records:
        return pd.DataFrame()

    return pd.DataFrame([{
        "date": r.date,
        "open_price": r.open_price,
        "high_price": r.high_price,
        "low_price": r.low_price,
        "close_price": r.close_price,
        "volume": r.volume,
        "ma_5": r.ma_5,
        "ma_10": r.ma_10,
        "ma_20": r.ma_20,
        "ma_60": r.ma_60,
        "ma_120": r.ma_120,
        "ma_240": r.ma_240,
        "bias_10": r.bias_10,
        "bias_20": r.bias_20,
    } for r in records])


@st.cache_data(ttl=300)
def load_research_institutional_data(stock_code):
    with get_db_session()() as session:
        records = session.query(InstitutionalTrade).filter(
            InstitutionalTrade.stock_code == stock_code
        ).order_by(InstitutionalTrade.date.asc()).all()

    if not records:
        return pd.DataFrame()

    return pd.DataFrame([{
        "date": r.date,
        "foreign_net_buy": r.foreign_net_buy,
        "investment_trust_net_buy": r.investment_trust_net_buy,
        "dealer_net_buy": r.dealer_net_buy,
        "total_net_buy": r.total_net_buy,
    } for r in records])


def merge_research_data(price_df, institutional_df):
    calc = ResearchIndicatorCalculator(price_df)
    df = calc.calculate_all()
    df = ResearchIndicatorCalculator.add_research_signals(df)

    df["date"] = pd.to_datetime(df["date"])
    if institutional_df.empty:
        df["foreign_net_buy"] = 0
        df["investment_trust_net_buy"] = 0
        df["dealer_net_buy"] = 0
        df["total_net_buy"] = 0
    else:
        inst = institutional_df.copy()
        inst["date"] = pd.to_datetime(inst["date"])
        df = df.merge(inst, on="date", how="left")
        for col in ["foreign_net_buy", "investment_trust_net_buy", "dealer_net_buy", "total_net_buy"]:
            df[col] = df[col].fillna(0)

    df["foreign_recent_net_buy"] = df["foreign_net_buy"].rolling(FOREIGN_WEEK_DAYS, min_periods=1).sum()
    df["foreign_recent_buy"] = df["foreign_recent_net_buy"] > 0
    df["foreign_recent_sell"] = df["foreign_recent_net_buy"] < 0
    return df


def _matched_buy_rules(row, selected_rules):
    matched = []
    if "葛蘭碧買點" in selected_rules and bool(row.get("granville_buy", False)):
        matched.append("葛蘭碧買點")
    if "外資週淨買超" in selected_rules and bool(row.get("foreign_recent_buy", False)):
        matched.append("外資週淨買超")
    if "BB 下緣反彈" in selected_rules and bool(row.get("bb_buy", False)):
        matched.append("BB 下緣反彈")
    if "MACD 黃金交叉" in selected_rules and bool(row.get("macd_buy", False)):
        matched.append("MACD 黃金交叉")
    if "KDJ 黃金交叉" in selected_rules and bool(row.get("kdj_buy", False)):
        matched.append("KDJ 黃金交叉")
    return matched


def _matched_sell_rules(row, selected_rules):
    matched = []
    if "葛蘭碧賣點" in selected_rules and bool(row.get("granville_sell", False)):
        matched.append("葛蘭碧賣點")
    if "外資週淨賣超" in selected_rules and bool(row.get("foreign_recent_sell", False)):
        matched.append("外資週淨賣超")
    if "BB 觸及上緣" in selected_rules and bool(row.get("bb_sell", False)):
        matched.append("BB 觸及上緣")
    if "MACD 死亡交叉" in selected_rules and bool(row.get("macd_sell", False)):
        matched.append("MACD 死亡交叉")
    if "KDJ 死亡交叉" in selected_rules and bool(row.get("kdj_sell", False)):
        matched.append("KDJ 死亡交叉")
    return matched


def build_custom_strategy(buy_rules, buy_match_count, sell_rules, sell_match_count):
    return StrategySpec(
        name="自訂條件策略",
        buy_signal=lambda row: len(_matched_buy_rules(row, buy_rules)) >= buy_match_count,
        sell_signal=lambda row: len(_matched_sell_rules(row, sell_rules)) >= sell_match_count,
    )


@st.cache_data(ttl=300)
def load_portfolio_positions():
    with get_db_session()() as session:
        trades = session.query(TransactionRecord).order_by(TransactionRecord.trade_date.asc()).all()
        latest_prices = {
            record.stock_code: record.close_price
            for record in session.query(DailyPrice).order_by(DailyPrice.date.asc()).all()
        }

    inventory = {}
    for trade in trades:
        code = str(trade.stock_code).strip()
        trade_type = str(trade.trade_type).strip()
        qty = int(trade.quantity)
        price = float(trade.price)
        if code not in inventory:
            inventory[code] = {"shares": 0, "cost": 0.0}

        if trade_type == "買入":
            inventory[code]["shares"] += qty
            inventory[code]["cost"] += qty * price
        elif trade_type == "賣出" and inventory[code]["shares"] > 0:
            avg_cost = inventory[code]["cost"] / inventory[code]["shares"]
            sell_qty = min(qty, inventory[code]["shares"])
            inventory[code]["shares"] -= sell_qty
            inventory[code]["cost"] -= sell_qty * avg_cost

    rows = []
    for code, item in inventory.items():
        if item["shares"] <= 0:
            continue
        latest_price = latest_prices.get(code, item["cost"] / item["shares"])
        value = item["shares"] * latest_price
        pnl = value - item["cost"]
        rows.append({
            "股票代號": code,
            "持有股數": item["shares"],
            "持有成本": item["cost"],
            "最新市值": value,
            "未實現損益": pnl,
            "報酬率(%)": pnl / item["cost"] * 100 if item["cost"] else 0,
        })

    return pd.DataFrame(rows)


@st.cache_data(ttl=300)
def load_close_price_matrix(stock_codes, lookback_days=252):
    if not stock_codes:
        return pd.DataFrame()

    with get_db_session()() as session:
        rows = session.query(DailyPrice).filter(
            DailyPrice.stock_code.in_(stock_codes)
        ).order_by(DailyPrice.date.asc()).all()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame([{
        "date": row.date,
        "stock_code": row.stock_code,
        "close_price": row.close_price,
    } for row in rows])
    matrix = df.pivot(index="date", columns="stock_code", values="close_price").dropna(how="all")
    return matrix.tail(lookback_days).ffill().dropna(axis=1)


def make_advice(df, stock_code, label, holding_row=None):
    latest = df.iloc[-1]
    buy_reasons = _matched_buy_rules(latest, ["葛蘭碧買點", "外資週淨買超", "BB 下緣反彈", "MACD 黃金交叉", "KDJ 黃金交叉"])
    sell_reasons = _matched_sell_rules(latest, ["葛蘭碧賣點", "外資週淨賣超", "BB 觸及上緣", "MACD 死亡交叉", "KDJ 死亡交叉"])

    if holding_row is not None and sell_reasons:
        action = "賣出/減碼觀察"
        reason = " + ".join(sell_reasons)
    elif holding_row is not None and buy_reasons:
        action = "續抱偏多"
        reason = " + ".join(buy_reasons)
    elif holding_row is None and buy_reasons:
        action = "買進觀察"
        reason = " + ".join(buy_reasons)
    else:
        action = "觀望"
        reason = "訊號不足"

    pnl_text = ""
    if holding_row is not None:
        pnl_text = f"；未實現損益 {holding_row['未實現損益']:,.0f} 元（{holding_row['報酬率(%)']:.2f}%）"

    return {
        "股票": label,
        "建議": action,
        "原因": reason,
        "補充": f"收盤價 {latest['close_price']:.2f}{pnl_text}",
    }


def simulate_optimal_portfolio(price_matrix, weight_sum_limit, simulations=1500):
    returns = price_matrix.pct_change().dropna()
    if returns.empty or len(returns.columns) < 2:
        return pd.DataFrame(), None

    mean_returns = returns.mean() * 252
    covariance = returns.cov() * 252
    rng = np.random.default_rng(42)
    rows = []

    for _ in range(simulations):
        random_values = pd.Series(rng.random(len(returns.columns)), index=returns.columns)
        random_values = random_values / random_values.sum()
        total_weight = rng.uniform(0, weight_sum_limit)
        weights = random_values * total_weight

        expected_return = float(weights @ mean_returns)
        volatility = float((weights.T @ covariance @ weights) ** 0.5)
        sharpe = expected_return / volatility if volatility > 0 else 0
        rows.append({
            "預期年化報酬(%)": expected_return * 100,
            "年化波動(%)": volatility * 100,
            "Sharpe": sharpe,
            "權重總和": weights.sum(),
            **{f"{code} 權重": weight for code, weight in weights.items()},
        })

    result = pd.DataFrame(rows)
    best = result.loc[result["Sharpe"].idxmax()] if not result.empty else None
    return result, best


def render_daily_advice_and_portfolio(stock_options, selected_stock_code):
    st.markdown("### 每日投資建議與最適投資組合")
    advice_col, portfolio_col = st.columns([1, 1])

    option_map = {option.split(" ")[0]: option for option in stock_options}
    positions = load_portfolio_positions()
    holding_codes = positions["股票代號"].tolist() if not positions.empty else []

    with advice_col:
        st.markdown("#### 08:30 / 13:50 投資建議")
        watch_defaults = [selected_stock_code] if selected_stock_code in option_map else []
        watch_labels = st.multiselect(
            "觀察股票",
            stock_options,
            default=[option_map[code] for code in watch_defaults],
            key="daily_advice_watchlist",
        )
        watch_codes = [label.split(" ")[0] for label in watch_labels]
        target_codes = list(dict.fromkeys(holding_codes + watch_codes))

        report_time = st.radio(
            "建議時段",
            ["08:30 盤前建議", "13:50 盤中建議"],
            horizontal=True,
            key="daily_advice_time",
        )

        if not target_codes:
            st.info("目前沒有持股，也尚未選擇觀察股票。")
        else:
            advice_rows = []
            for code in target_codes:
                price_df = load_research_price_data(code)
                inst_df = load_research_institutional_data(code)
                if price_df.empty:
                    continue

                research_df = merge_research_data(price_df, inst_df)
                holding_row = None
                if not positions.empty and code in holding_codes:
                    holding_row = positions[positions["股票代號"] == code].iloc[0]
                advice_rows.append(make_advice(research_df, code, option_map.get(code, code), holding_row))

            if advice_rows:
                st.caption(f"{report_time}：依最新資料產生。若盤中即時價未更新，會使用資料庫最新收盤價。")
                st.dataframe(pd.DataFrame(advice_rows), width="stretch", hide_index=True)
            else:
                st.info("觀察清單目前沒有可用價格資料。")

        if not positions.empty:
            st.markdown("#### 目前持股損益")
            st.dataframe(
                positions[["股票代號", "持有股數", "最新市值", "未實現損益", "報酬率(%)"]].style.format({
                    "持有股數": "{:,}",
                    "最新市值": "{:,.0f}",
                    "未實現損益": "{:,.0f}",
                    "報酬率(%)": "{:.2f}",
                }),
                width="stretch",
                hide_index=True,
            )

    with portfolio_col:
        st.markdown("#### 隨機權重最適投資組合")
        candidate_codes = list(dict.fromkeys(holding_codes + watch_codes))
        selected_labels = st.multiselect(
            "納入最佳化股票",
            stock_options,
            default=[option_map[code] for code in candidate_codes if code in option_map],
            key="optimizer_symbols",
        )
        optimizer_codes = [label.split(" ")[0] for label in selected_labels]
        weight_sum_limit = st.slider("權重總和上限", min_value=0.0, max_value=2.0, value=1.0, step=0.1)
        simulation_count = st.slider("隨機投資組合數量", min_value=300, max_value=3000, value=1500, step=300)

        price_matrix = load_close_price_matrix(optimizer_codes)
        portfolios, best = simulate_optimal_portfolio(price_matrix, weight_sum_limit, simulation_count)
        if portfolios.empty or best is None:
            st.info("請至少選擇兩檔有足夠價格資料的股票。")
            return

        fig = px.scatter(
            portfolios,
            x="年化波動(%)",
            y="預期年化報酬(%)",
            color="Sharpe",
            color_continuous_scale="Viridis",
            title="隨機投資組合風險 / 報酬分布",
        )
        fig.add_trace(go.Scatter(
            x=[best["年化波動(%)"]],
            y=[best["預期年化報酬(%)"]],
            mode="markers+text",
            text=["最佳 Sharpe"],
            textposition="top center",
            marker=dict(size=14, color="red", symbol="star"),
            name="最佳 Sharpe",
        ))
        fig.update_layout(height=420, margin=dict(l=0, r=0, t=50, b=0))
        st.plotly_chart(fig, width="stretch")

        weight_cols = [col for col in portfolios.columns if col.endswith(" 權重")]
        best_weights = best[weight_cols].rename(lambda value: value.replace(" 權重", ""))
        best_weights = best_weights[best_weights > 0.001].sort_values(ascending=False)
        st.markdown("#### 最適權重")
        st.dataframe(
            best_weights.rename("權重").reset_index().rename(columns={"index": "股票代號"}).style.format({"權重": "{:.2%}"}),
            width="stretch",
            hide_index=True,
        )


def render_daily_advice_page():
    st.subheader("每日投資建議")
    stock_options = load_research_stock_options()
    if not stock_options:
        st.warning("目前沒有股票清單，請先執行 python main.py update。")
        return

    default_code = stock_options[0].split(" ")[0]
    render_daily_advice_and_portfolio(stock_options, default_code)


def render_foxconn_research():
    st.subheader("泛用型策略回測1")

    stock_options = load_research_stock_options()
    if not stock_options:
        st.warning("目前沒有股票清單，請先執行 python main.py update。")
        return

    default_index = next((i for i, option in enumerate(stock_options) if option.startswith("2317 ")), 0)

    buy_rule_options = ["葛蘭碧買點", "外資週淨買超", "BB 下緣反彈", "MACD 黃金交叉", "KDJ 黃金交叉"]
    sell_rule_options = ["葛蘭碧賣點", "外資週淨賣超", "BB 觸及上緣", "MACD 死亡交叉", "KDJ 死亡交叉"]

    with st.expander("⚙️ 展開設定回測參數", expanded=True):
        col_cap, col_buy, col_sell = st.columns(3)

        with col_cap:
            st.markdown("#### 💰 資金與標的設定")
            selected_option = st.selectbox("選擇分析標的", stock_options, index=default_index, key="research_stock")
            stock_code = selected_option.split(" ")[0]
            stock_name = selected_option.replace(stock_code, "", 1).strip()

            initial_capital = st.number_input(
                "起始資金 (元)",
                min_value=10000,
                value=1000000,
                step=10000,
                key="research_initial_capital",
            )

            st.markdown("#### 📅 選擇回測區間")
            price_preview = load_research_price_data(stock_code)
            if price_preview.empty:
                st.warning(f"目前沒有 {stock_code} 價格資料，請先執行 python main.py update。")
                return

            price_preview["date"] = pd.to_datetime(price_preview["date"])
            min_date = price_preview["date"].min().date()
            max_date = price_preview["date"].max().date()
            default_start = max(min_date, max_date - timedelta(days=365 * 3))

            c_start, c_end = st.columns(2)
            with c_start:
                start_date = st.date_input(
                    "回測起始日",
                    value=default_start,
                    min_value=min_date,
                    max_value=max_date,
                    key="research_start_date",
                )
            with c_end:
                end_date = st.date_input(
                    "回測結束日",
                    value=max_date,
                    min_value=min_date,
                    max_value=max_date,
                    key="research_end_date",
                )

        with col_buy:
            st.markdown("#### 📈 買入條件 (策略比較)")
            buy_rules = st.multiselect(
                "選擇買入技術訊號",
                buy_rule_options,
                default=["葛蘭碧買點", "外資週淨買超"],
                key="research_buy_signals",
            )
            buy_match_count = st.number_input(
                "上述條件符合幾項即買入？",
                min_value=1,
                max_value=max(1, len(buy_rules)),
                value=min(2, max(1, len(buy_rules))),
                key="research_buy_match_count",
            )
            st.text_input(
                "外資條件",
                value="外資週淨買超（近 5 個交易日合計 > 0）",
                disabled=True,
                key="research_foreign_rule",
            )

        with col_sell:
            st.markdown("#### 📉 賣出條件 (策略比較)")
            sell_rules = st.multiselect(
                "選擇賣出技術訊號",
                sell_rule_options,
                default=["葛蘭碧賣點"],
                key="research_sell_signals",
            )
            sell_match_count = st.number_input(
                "上述條件符合幾項即賣出？",
                min_value=1,
                max_value=max(1, len(sell_rules)),
                value=1,
                key="research_sell_match_count",
            )
            fee_rate = st.number_input(
                "手續費率",
                min_value=0.0,
                value=0.001425,
                step=0.0001,
                format="%.6f",
                key="research_fee_rate",
            )
            tax_rate = st.number_input(
                "證交稅率",
                min_value=0.0,
                value=0.003,
                step=0.0001,
                format="%.6f",
                key="research_tax_rate",
            )

        st.markdown("---")
        f1, f2, f3 = st.columns([1, 1, 2])
        with f1:
            fetch_start = st.date_input("法人資料起始日", value=date.today() - timedelta(days=365), key="research_fetch_start")
        with f2:
            fetch_end = st.date_input("法人資料結束日", value=date.today(), key="research_fetch_end")
        with f3:
            st.write("")
            st.write("")
            if st.button(f"更新 {stock_code} {stock_name} 三大法人資料", width="stretch", key="research_fetch_button"):
                fetcher = InstitutionalFetcher(get_db_session())
                count = fetcher.fetch_and_save(
                    stock_code,
                    fetch_start.strftime("%Y-%m-%d"),
                    fetch_end.strftime("%Y-%m-%d"),
                )
                st.cache_data.clear()
                st.success(f"已寫入 {count} 筆法人資料")

    price_df = load_research_price_data(stock_code)
    inst_df = load_research_institutional_data(stock_code)

    if price_df.empty:
        st.warning(f"目前沒有 {stock_code} 價格資料，請先執行 python main.py update。")
        return

    df = merge_research_data(price_df, inst_df)

    if start_date > end_date:
        st.warning("回測起始日不能晚於結束日。")
        return

    df_bt = df[(df["date"] >= pd.to_datetime(start_date)) & (df["date"] <= pd.to_datetime(end_date))].copy()
    if df_bt.empty:
        st.warning("此區間沒有資料。")
        return

    backtester = FoxconnBacktester(
        df_bt,
        initial_capital=initial_capital,
        fee_rate=fee_rate,
        tax_rate=tax_rate,
    )
    strategies = prepare_strategy_specs()
    if buy_rules and sell_rules:
        strategies.append(build_custom_strategy(buy_rules, buy_match_count, sell_rules, sell_match_count))
    summary_df, curve_df, trades_by_strategy = backtester.run_all(strategies)

    st.markdown(f"### {stock_code} {stock_name} 策略績效比較")
    st.dataframe(
        summary_df.style.format({
            "期末資產": "{:,.0f}",
            "總報酬率(%)": "{:.2f}",
            "最大回撤(%)": "{:.2f}",
            "勝率(%)": "{:.1f}",
        }),
        use_container_width=True,
        hide_index=True,
    )

    if not curve_df.empty:
        fig = px.line(
            curve_df,
            x="date",
            y="equity",
            color="strategy",
            title="多策略權益曲線比較",
        )
        fig.update_layout(height=520, margin=dict(l=0, r=0, t=50, b=0), hovermode="x unified")
        st.plotly_chart(fig, width="stretch")

    st.markdown("### 法人資料概況")
    inst_count = len(inst_df)
    latest_inst_date = inst_df["date"].max() if inst_count else "尚無資料"
    m1, m2, m3 = st.columns(3)
    m1.metric("法人資料筆數", f"{inst_count:,}")
    m2.metric("最新法人日期", str(latest_inst_date))
    m3.metric("外資週淨買超", f"{df_bt.iloc[-1]['foreign_recent_net_buy']:,.0f} 股")

    st.markdown("### 交易明細")
    strategy_name = st.selectbox("選擇策略", list(trades_by_strategy.keys()))
    trades = trades_by_strategy[strategy_name]
    if trades.empty:
        st.info("此策略在回測區間內沒有完成交易。")
    else:
        st.dataframe(
            trades.style.format({
                "買入價": "{:.2f}",
                "賣出價": "{:.2f}",
                "股數": "{:,}",
                "報酬率(%)": "{:.2f}",
                "損益": "{:,.0f}",
            }),
            use_container_width=True,
            hide_index=True,
        )
