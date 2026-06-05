import streamlit as st
import pandas as pd
from datetime import timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots

def info_tooltip(text):
    return f"**{text}**"

def render_diagnostic(df_signals, stock_code):
    st.subheader("走勢圖與技術分析")
    
    ctrl_1, ctrl_2 = st.columns(2)
    with ctrl_1:
        time_range = st.radio("顯示時間範圍：", ["近 1 個月", "近 3 個月", "近半年", "近 1 年", "全部"], index=2, horizontal=True, key=f"tr_{stock_code}")
    with ctrl_2:
        # ✨ 修改選單選項文字
        sub_indicator = st.radio("下方副圖指標：", ["成交量", "KD (9日)", "RSI (5日/10日)", "BIAS (10日/20日)"], horizontal=True, key=f"si_{stock_code}")
    
    max_date = df_signals['date'].max()
    if time_range == "近 1 個月": start_date = max_date - timedelta(days=30)
    elif time_range == "近 3 個月": start_date = max_date - timedelta(days=90)
    elif time_range == "近半年": start_date = max_date - timedelta(days=180)
    elif time_range == "近 1 年": start_date = max_date - timedelta(days=365)
    else: start_date = df_signals['date'].min()

    df_plot = df_signals[df_signals['date'] >= start_date].copy()
    
    dt_all = pd.date_range(start=df_plot['date'].min(), end=df_plot['date'].max())
    dt_obs = [d.strftime("%Y-%m-%d") for d in df_plot['date']]
    dt_breaks = [d for d in dt_all.strftime("%Y-%m-%d").tolist() if d not in dt_obs]

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.75, 0.25]
    )

    # 繪製主圖 K線與均線
    fig.add_trace(go.Candlestick(x=df_plot['date'], open=df_plot['open_price'], high=df_plot['high_price'], low=df_plot['low_price'], close=df_plot['close_price'], name='K線'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['ma_5'], line=dict(color='#E377C2', width=1), name='MA5(周線)'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['ma_10'], line=dict(color='#17BECF', width=1), name='MA10(雙周)'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['ma_20'], line=dict(color='#FF7F0E', width=1.5), name='MA20(月線)'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['ma_60'], line=dict(color='#2CA02C', width=1.5), name='MA60(季線)', visible='legendonly'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['ma_120'], line=dict(color='#9467BD', width=1.5), name='MA120(半年)', visible='legendonly'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['ma_240'], line=dict(color='#8C564B', width=1.5), name='MA240(年線)', visible='legendonly'), row=1, col=1)

    # 繪製副圖
    if sub_indicator == "成交量":
        fig.add_trace(go.Bar(x=df_plot['date'], y=df_plot['volume'], name='成交量', marker_color='rgba(150, 150, 150, 0.5)'), row=2, col=1)
    elif sub_indicator == "KD (9日)":
        fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['kd_k'], line=dict(color='#3498db', width=1.2), name='K值'), row=2, col=1)
        fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['kd_d'], line=dict(color='#e67e22', width=1.2), name='D值'), row=2, col=1)
    elif sub_indicator == "RSI (5日/10日)": # ✨ 畫出 RSI_5 和 RSI_10
        fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['rsi_5'], line=dict(color='#9b59b6', width=1.5), name='RSI(5)'), row=2, col=1)
        fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['rsi_10'], line=dict(color='#3498db', width=1.5), name='RSI(10)'), row=2, col=1)
        fig.add_hline(y=70, line_dash="dot", line_color="red", row=2, col=1)
        fig.add_hline(y=30, line_dash="dot", line_color="green", row=2, col=1)
    elif sub_indicator == "BIAS (10日/20日)": # ✨ 畫出 BIAS_10 和 BIAS_20
        fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['bias_10'], line=dict(color='#e74c3c', width=1.5), name='雙周線乖離'), row=2, col=1)
        fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['bias_20'], line=dict(color='#f39c12', width=1.5), name='月線乖離'), row=2, col=1)
        fig.add_hline(y=0, line_dash="dash", line_color="white", row=2, col=1)

    fig.update_layout(
        height=650, margin=dict(l=0, r=0, t=30, b=0), hovermode='x unified', 
        xaxis_rangeslider_visible=False, xaxis2_rangeslider_visible=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        modebar_add=["v1hovermode", "toggleSpikelines"]
    )
    fig.update_xaxes(rangebreaks=[dict(values=dt_breaks)], showspikes=True, spikethickness=1, spikedash="dot", spikecolor="#aaaaaa", spikemode="across")
    fig.update_yaxes(showspikes=True, spikethickness=1, spikedash="dot", spikecolor="#aaaaaa", spikemode="across")

    st.plotly_chart(fig, width="stretch", config={'displayModeBar': True})

def render_diagnosis_panel(df_signals, available_dates, default_date):
    st.subheader("🎯 歷史診斷時光機")
    
    if 'analysis_date' not in st.session_state:
        st.session_state['analysis_date'] = default_date

    selected_date = st.date_input(
        "選擇要分析的日期：", 
        value=st.session_state['analysis_date'], 
        min_value=available_dates[0], 
        max_value=default_date
    )
    
    if selected_date != st.session_state['analysis_date']:
        st.session_state['analysis_date'] = selected_date
        st.rerun()
    
    target_data = df_signals[df_signals['date'].dt.date <= st.session_state['analysis_date']]
    if not target_data.empty:
        current = target_data.iloc[-1]
        
        st.write(f"📅 **分析日期：{current['date'].strftime('%Y-%m-%d')}**")
        st.metric("收盤價", f"{current['close_price']:g}")
        st.markdown("---")
        
        st.markdown(info_tooltip("1. MD (均線多空)"), help="判斷長期趨勢方向。\n\n多頭排列：收盤價 > MA5 > MA10 > MA20\n空頭排列：收盤價 < MA20 < MA10 < MA5\n中繼盤整：均線糾結或方向不一致")
        ts = current['trend_status']
        if '多頭' in ts: 
            st.error(f"🔴 {ts}")
        elif '空頭' in ts: 
            st.success(f"🟢 {ts}")
        elif '突破' in ts or '跌破' in ts: 
            st.warning(f"🟡 {ts}")
        else: 
            st.info(f"⚪ {ts}")
        
        st.markdown(info_tooltip("2. RSI (相對強弱)"), help="判斷短期是否過熱或超跌 (預設 5 日)。\n\n大於 70 為超買區 (偏空)，小於 30 為超賣區 (偏多)。")
        if current['signal_rsi'] != '無': st.warning(current['signal_rsi'])
        else: st.write(f"⚪ 中性區間 (RSI: {current['rsi_5']:.1f})")
            
        st.markdown(info_tooltip("3. KD (隨機指標)"), help="捕捉短期轉折點 (預設 9 日)。\n\n黃金交叉 (K由下穿過D) 偏多。\n死亡交叉 (K由上跌破D) 偏空。")
        if current['signal_kd'] != '無': st.warning(current['signal_kd'])
        else: st.write(f"⚪ 無交叉訊號 (K: {current['kd_k']:.1f}, D: {current['kd_d']:.1f})")
            
        st.markdown(info_tooltip("4. BIAS (乖離率)"), help="判斷股價是否偏離月線太遠 (預設門檻 10%)。\n\n正乖離過大：隨時可能獲利了結拉回。\n負乖離過大：可能出現跌深反彈。")
        if current['signal_bias'] != '無': st.warning(current['signal_bias'])
        else: st.write(f"⚪ 乖離正常 (MA10 乖離: {current['bias_10']:.2f}%)")

        st.markdown(info_tooltip("5. 葛蘭碧法則 (八大買賣點)"), help="利用均線方向與股價突破/跌破的關係，判斷絕佳的進出場時機。")
        if current['signal_granville'] != '無': 
            if '買點' in current['signal_granville']:
                st.error(current['signal_granville']) 
            else:
                st.success(current['signal_granville']) 
        else: 
            st.write("⚪ 當日無觸發葛蘭碧買賣點")
    else:
        st.warning("所選日期之前無交易資料。")
