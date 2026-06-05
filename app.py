import streamlit as st
import pandas as pd
from db_config import get_db_session
from models import Stock, DailyPrice, InstitutionalTrade
from indicator_calculator import IndicatorCalculator
from strategy_engine import StrategyEngine
from research_indicator_calculator import ResearchIndicatorCalculator

# 引入我們剛剛拆分出去的模組
from ui_diagnostic import render_diagnostic, render_diagnosis_panel
from ui_backtest import render_backtest
from ui_portfolio import render_portfolio
from ui_strategy_research import render_daily_advice_page, render_strategy_research

# 網頁基本設定
st.set_page_config(page_title="0050 智能量化分析系統", layout="wide")

@st.cache_data(ttl=300)
def load_stock_list():
    with get_db_session()() as session:
        price_codes = [
            row[0]
            for row in session.query(DailyPrice.stock_code)
            .distinct()
            .order_by(DailyPrice.stock_code.asc())
            .all()
        ]
        stock_names = {
            stock.stock_code: stock.name
            for stock in session.query(Stock).filter(Stock.stock_code.in_(price_codes)).all()
        }
        return [f"{code} {stock_names.get(code, code)}" for code in price_codes]

@st.cache_data(ttl=300)
def load_stock_data(stock_code):
    with get_db_session()() as session:
        records = session.query(DailyPrice).filter(
            DailyPrice.stock_code == stock_code
        ).order_by(DailyPrice.date.desc()).all()
        
        if not records: return pd.DataFrame()
        
        df = pd.DataFrame([{
            'date': r.date, 'open_price': r.open_price, 'high_price': r.high_price, 
            'low_price': r.low_price, 'close_price': r.close_price, 'volume': r.volume,
            'ma_5': r.ma_5, 'ma_10': r.ma_10, 'ma_20': r.ma_20, 
            'ma_60': r.ma_60, 'ma_120': r.ma_120, 'ma_240': r.ma_240, 
            'bias_10': r.bias_10, 'bias_20': r.bias_20
        } for r in records]).iloc[::-1]
        return df

@st.cache_data(ttl=300)
def load_institutional_data(stock_code):
    with get_db_session()() as session:
        records = session.query(InstitutionalTrade).filter(
            InstitutionalTrade.stock_code == stock_code
        ).order_by(InstitutionalTrade.date.asc()).all()

        if not records:
            return pd.DataFrame()

        return pd.DataFrame([{
            'date': r.date,
            'foreign_net_buy': r.foreign_net_buy,
            'investment_trust_net_buy': r.investment_trust_net_buy,
            'dealer_net_buy': r.dealer_net_buy,
            'total_net_buy': r.total_net_buy,
        } for r in records])

def enrich_backtest_data(df_signals, stock_code, institutional_window=5):
    research_df = ResearchIndicatorCalculator(df_signals).calculate_all()
    research_df = ResearchIndicatorCalculator.add_research_signals(research_df)
    research_df['date'] = pd.to_datetime(research_df['date'])

    institutional_df = load_institutional_data(stock_code)
    if institutional_df.empty:
        for col in ['foreign_net_buy', 'investment_trust_net_buy', 'dealer_net_buy', 'total_net_buy']:
            research_df[col] = 0
    else:
        institutional_df['date'] = pd.to_datetime(institutional_df['date'])
        research_df = research_df.merge(institutional_df, on='date', how='left')
        for col in ['foreign_net_buy', 'investment_trust_net_buy', 'dealer_net_buy', 'total_net_buy']:
            research_df[col] = research_df[col].fillna(0)

    research_df['foreign_recent_net_buy'] = research_df['foreign_net_buy'].rolling(institutional_window, min_periods=1).sum()
    research_df['total_recent_net_buy'] = research_df['total_net_buy'].rolling(institutional_window, min_periods=1).sum()
    research_df['foreign_recent_buy'] = research_df['foreign_recent_net_buy'] > 0
    research_df['foreign_recent_sell'] = research_df['foreign_recent_net_buy'] < 0
    research_df['total_recent_buy'] = research_df['total_recent_net_buy'] > 0
    research_df['total_recent_sell'] = research_df['total_recent_net_buy'] < 0
    research_df['foreign_week_net_buy_next_day'] = research_df['foreign_recent_buy'].shift(1, fill_value=False).astype(bool)
    return research_df

with st.sidebar:
    st.header("⚙️ 系統控制")
    if st.button("🔄 強制刷新最新資料"):
        st.cache_data.clear()
        st.success("快取已清除！畫面已更新。")

st.title("📈 智能量化分析系統")

# ================= 頁籤切換路由 =================
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 個股即時診斷看板", "⚙️ 泛用型策略回測", "💰 個人投資帳戶", "🔬 泛用型策略回測1", "🕣 每日投資建議"])

with tab1:
    stock_options = load_stock_list()
    selected_option = st.selectbox("請選擇要分析的標的：", stock_options)
    stock_code = selected_option.split(" ")[0]

    df = load_stock_data(stock_code)

    if not df.empty:
        calc = IndicatorCalculator(df)
        df_with_indicators = calc.calculate_all()
        df_with_indicators = df_with_indicators.reset_index()

        engine = StrategyEngine(df_with_indicators)
        df_signals = engine.generate_all_signals(ma_period=20, rsi_period=10, kd_period=9, bias_threshold=10)
        df_signals = df_signals.reset_index()
        df_signals['date'] = pd.to_datetime(df_signals['date'])
        df_signals = enrich_backtest_data(df_signals, stock_code)
        
        available_dates = df_signals['date'].dt.date.tolist()
        default_date = available_dates[-1]

        col_left, col_right = st.columns([2.5, 1]) 
        with col_left:
            render_diagnostic(df_signals, stock_code)
        with col_right:
            render_diagnosis_panel(df_signals, available_dates, default_date)
    else:
        st.warning("查無資料，請先執行 main.py 更新資料庫。")

with tab2:
    if not df.empty:
        render_backtest(df_signals, stock_code)

with tab3:
    render_portfolio()

with tab4:
    render_strategy_research()

with tab5:
    render_daily_advice_page()
