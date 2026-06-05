import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

def render_backtest(df, stock_code):
    st.subheader("🛠️ 自訂條件策略回測中心")
    if 'foreign_net_buy' in df.columns:
        st.caption("此頁已整合 BB、MACD、KDJ 與三大法人條件；法人資料需先在「鴻海法人策略研究」頁籤更新。")
    
    # ==========================================
    # 1. 參數設定區
    # ==========================================
    with st.expander("⚙️ 展開設定回測參數", expanded=True):
        col_cap, col_buy, col_sell = st.columns(3)
        
        with col_cap:
            st.markdown("#### 💰 資金與部位設定")
            initial_capital = st.number_input("起始資金 (元)", min_value=10000, value=1000000, step=10000)
            
            position_mode = st.radio("資金配置模式", ["All-In (全倉投入)", "固定股數"])
            fixed_shares = 1000
            if position_mode == "固定股數":
                fixed_shares = st.number_input("每次買入股數", min_value=1, value=1000, step=1000)
            
            buy_and_hold = st.checkbox("🟢 長期投資 (首日買入後永不賣出)")
            
            st.markdown("#### 📅 選擇回測區間")
            min_date = df['date'].min().date()
            max_date = df['date'].max().date()
            
            # 智慧預設：抓取最近一年的日期
            try:
                default_start = max_date.replace(year=max_date.year - 1)
            except ValueError: # 處理閏年極端情況
                default_start = max_date.replace(year=max_date.year - 1, month=2, day=28)
            if default_start < min_date:
                default_start = min_date

            c_start, c_end = st.columns(2)
            with c_start:
                start_date = st.date_input("起始日期", value=default_start, min_value=min_date, max_value=max_date)
            with c_end:
                end_date = st.date_input("結束日期", value=max_date, min_value=min_date, max_value=max_date)

        with col_buy:
            st.markdown("#### 📈 買入條件 (多單進場)")
            buy_signals = st.multiselect(
                "選擇買入技術訊號", 
                [
                    "KD 黃金交叉",
                    "KDJ 黃金交叉",
                    "MACD 黃金交叉",
                    "BB 下緣反彈",
                    "RSI 超賣 (<30)",
                    "負乖離過大",
                    "葛蘭碧買點",
                    "均線多頭排列",
                    "外資一週內淨買超（隔日買入）",
                    "三大法人週淨買超",
                ],
                default=["KD 黃金交叉", "均線多頭排列"],
                disabled=buy_and_hold
            )
            
            num_buy_selected = len(buy_signals)
            max_buy_val = max(1, num_buy_selected) # 防呆：就算都沒選，最大值也不能小於1
            # 確保預設值不會超過目前的選項數量
            default_buy_val = min(2, max_buy_val) 
            
            buy_match_count = st.number_input(
                "上述條件符合幾項即買入？", 
                min_value=1, 
                max_value=max_buy_val, 
                value=default_buy_val,
                disabled=buy_and_hold or num_buy_selected == 0
            )
            
        with col_sell:
            st.markdown("#### 📉 賣出條件 (多單出場)")
            sell_signals = st.multiselect(
                "選擇賣出技術訊號", 
                [
                    "KD 死亡交叉",
                    "KDJ 死亡交叉",
                    "MACD 死亡交叉",
                    "BB 觸及上緣",
                    "RSI 超買 (>70)",
                    "正乖離過大",
                    "葛蘭碧賣點",
                    "均線空頭排列",
                    "外資週淨賣超",
                    "三大法人週淨賣超",
                ],
                default=["KD 死亡交叉"],
                disabled=buy_and_hold
            )
            
            num_sell_selected = len(sell_signals)
            max_sell_val = max(1, num_sell_selected)
            default_sell_val = min(1, max_sell_val)
            
            sell_match_count = st.number_input(
                "上述條件符合幾項即賣出？", 
                min_value=1, 
                max_value=max_sell_val, 
                value=default_sell_val,
                disabled=buy_and_hold or num_sell_selected == 0
            )
            
            st.markdown("---")
            enable_time_exit = st.checkbox("⏳ 啟用時間停利/停損", disabled=buy_and_hold)
            hold_days_limit = 0
            if enable_time_exit:
                hold_days_limit = st.number_input("買入後持有幾天強制賣出？", min_value=1, value=20, disabled=buy_and_hold)

    # ==========================================
    # 2. 執行回測運算引擎
    # ==========================================
    if st.button("🚀 執行歷史回測", type="primary", width="stretch"):
        
        # 防呆檢查：日期順序是否正確
        if start_date > end_date:
            st.warning("⚠️ 起始日期不能晚於結束日期！請重新選擇。")
            return
            
        # ✨ 修復：用 pd.to_datetime 強制轉型，確保時間過濾 100% 精準
        df_bt = df[(df['date'] >= pd.to_datetime(start_date)) & (df['date'] <= pd.to_datetime(end_date))].copy()
        df_bt = df_bt.sort_values('date').reset_index(drop=True)
        
        if df_bt.empty:
            st.warning("所選區間無交易資料！")
            return
            
        # 狀態變數初始化
        capital = initial_capital
        holdings = 0
        days_held = 0
        
        open_position = None
        trade_results = []
        trade_log = []
        equity_curve = []
        
        progress_bar = st.progress(0)
        total_days = len(df_bt)
        
        for i, row in df_bt.iterrows():
            current_price = row['close_price']
            current_date = row['date']
            
            current_equity = capital + (holdings * current_price)
            equity_curve.append({'date': current_date, 'equity': current_equity})
            
            # 特殊模式：長期投資 (Buy & Hold)
            if buy_and_hold:
                if i == 0:
                    shares_to_buy = int(capital // current_price) if position_mode == "All-In (全倉投入)" else fixed_shares
                    if shares_to_buy > 0 and capital >= shares_to_buy * current_price:
                        capital -= shares_to_buy * current_price
                        holdings += shares_to_buy
                        open_position = {
                            'buy_date': current_date.strftime("%Y-%m-%d"),
                            'buy_price': current_price,
                            'buy_reason': '長期投資起點',
                            'shares': shares_to_buy
                        }
                        trade_log.append({'日期': current_date.strftime("%Y-%m-%d"), '動作': '買入', '股價': current_price})
                continue 
            
            # 判斷買入條件
            matched_buy_rules = []
            if "KD 黃金交叉" in buy_signals and '黃金交叉' in str(row['signal_kd']): matched_buy_rules.append("KD金叉")
            if "KDJ 黃金交叉" in buy_signals and bool(row.get('kdj_buy', False)): matched_buy_rules.append("KDJ金叉")
            if "MACD 黃金交叉" in buy_signals and bool(row.get('macd_buy', False)): matched_buy_rules.append("MACD金叉")
            if "BB 下緣反彈" in buy_signals and bool(row.get('bb_buy', False)): matched_buy_rules.append("BB下緣反彈")
            if "RSI 超賣 (<30)" in buy_signals and '超賣' in str(row['signal_rsi']): matched_buy_rules.append("RSI超賣")
            if "負乖離過大" in buy_signals and '負乖離' in str(row['signal_bias']): matched_buy_rules.append("負乖離過大")
            if "葛蘭碧買點" in buy_signals and '買點' in str(row['signal_granville']): matched_buy_rules.append(row['signal_granville'])
            if "均線多頭排列" in buy_signals and '多頭排列' in str(row['trend_status']): matched_buy_rules.append("均線多頭")
            if "外資一週內淨買超（隔日買入）" in buy_signals and bool(row.get('foreign_week_net_buy_next_day', False)): matched_buy_rules.append("外資一週內淨買超(隔日買入)")
            if "三大法人週淨買超" in buy_signals and bool(row.get('total_recent_buy', False)): matched_buy_rules.append("三大法人週淨買超")
            
            # 判斷賣出條件
            matched_sell_rules = []
            if "KD 死亡交叉" in sell_signals and '死亡交叉' in str(row['signal_kd']): matched_sell_rules.append("KD死叉")
            if "KDJ 死亡交叉" in sell_signals and bool(row.get('kdj_sell', False)): matched_sell_rules.append("KDJ死叉")
            if "MACD 死亡交叉" in sell_signals and bool(row.get('macd_sell', False)): matched_sell_rules.append("MACD死叉")
            if "BB 觸及上緣" in sell_signals and bool(row.get('bb_sell', False)): matched_sell_rules.append("BB觸及上緣")
            if "RSI 超買 (>70)" in sell_signals and '超買' in str(row['signal_rsi']): matched_sell_rules.append("RSI超買")
            if "正乖離過大" in sell_signals and '正乖離' in str(row['signal_bias']): matched_sell_rules.append("正乖離過大")
            if "葛蘭碧賣點" in sell_signals and '賣點' in str(row['signal_granville']): matched_sell_rules.append(row['signal_granville'])
            if "均線空頭排列" in sell_signals and '空頭排列' in str(row['trend_status']): matched_sell_rules.append("均線空頭")
            if "外資週淨賣超" in sell_signals and bool(row.get('foreign_recent_sell', False)): matched_sell_rules.append("外資週淨賣超")
            if "三大法人週淨賣超" in sell_signals and bool(row.get('total_recent_sell', False)): matched_sell_rules.append("三大法人週淨賣超")
            
            # 執行買入
            if holdings == 0:
                if len(matched_buy_rules) >= buy_match_count and len(buy_signals) > 0:
                    shares_to_buy = int(capital // current_price) if position_mode == "All-In (全倉投入)" else fixed_shares
                    if shares_to_buy > 0 and capital >= shares_to_buy * current_price:
                        capital -= shares_to_buy * current_price
                        holdings += shares_to_buy
                        days_held = 0
                        
                        open_position = {
                            'buy_date': current_date.strftime("%Y-%m-%d"),
                            'buy_price': current_price,
                            'buy_reason': " + ".join(matched_buy_rules),
                            'shares': shares_to_buy
                        }
                        trade_log.append({'日期': current_date.strftime("%Y-%m-%d"), '動作': '買入', '股價': current_price})
            
            # 執行賣出
            else:
                days_held += 1
                sell_reason_str = ""
                
                if enable_time_exit and days_held >= hold_days_limit:
                    sell_reason_str = f"持滿 {hold_days_limit} 天平倉"
                elif len(matched_sell_rules) >= sell_match_count and len(sell_signals) > 0:
                    sell_reason_str = " + ".join(matched_sell_rules)
                    
                if sell_reason_str:
                    profit = (current_price - open_position['buy_price']) * holdings
                    roi = (current_price - open_position['buy_price']) / open_position['buy_price'] * 100
                    capital += holdings * current_price
                    
                    trade_results.append({
                        '買入日期': open_position['buy_date'],
                        '買入原因': open_position['buy_reason'],
                        '買入單價': open_position['buy_price'],
                        '賣出日期': current_date.strftime("%Y-%m-%d"),
                        '賣出原因': sell_reason_str,
                        '賣出單價': current_price,
                        '交易股數': holdings,
                        '報酬率(%)': roi,
                        '損益': profit
                    })
                    
                    trade_log.append({'日期': current_date.strftime("%Y-%m-%d"), '動作': '賣出', '股價': current_price})
                    holdings = 0
                    days_held = 0
                    open_position = None
            
            if i % 50 == 0: progress_bar.progress(int((i / total_days) * 100))
            
        # 回測期末強制結算
        if holdings > 0 and open_position:
            last_price = df_bt.iloc[-1]['close_price']
            profit = (last_price - open_position['buy_price']) * holdings
            roi = (last_price - open_position['buy_price']) / open_position['buy_price'] * 100
            capital += holdings * last_price
            
            equity_curve[-1]['equity'] = capital 
            
            trade_results.append({
                '買入日期': open_position['buy_date'],
                '買入原因': open_position['buy_reason'],
                '買入單價': open_position['buy_price'],
                '賣出日期': df_bt.iloc[-1]['date'].strftime("%Y-%m-%d"),
                '賣出原因': '回測結束強制平倉',
                '賣出單價': last_price,
                '交易股數': holdings,
                '報酬率(%)': roi,
                '損益': profit
            })
            
            trade_log.append({'日期': df_bt.iloc[-1]['date'].strftime("%Y-%m-%d"), '動作': '賣出', '股價': last_price})
            
        progress_bar.empty()
        
        # ==========================================
        # 3. 顯示回測績效 KPI
        # ==========================================
        final_equity = capital
        total_return_pct = ((final_equity - initial_capital) / initial_capital) * 100
        
        df_eq = pd.DataFrame(equity_curve)
        df_eq['cummax'] = df_eq['equity'].cummax()
        df_eq['drawdown'] = (df_eq['equity'] - df_eq['cummax']) / df_eq['cummax']
        max_dd = df_eq['drawdown'].min() * 100
        
        winning_trades = len([t for t in trade_results if t['損益'] > 0])
        total_closed = len(trade_results)
        win_rate = (winning_trades / total_closed * 100) if total_closed > 0 else 0
        
        st.markdown("### 🏆 回測績效報告")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("期末總資產", f"${final_equity:,.0f}", f"{total_return_pct:.2f}%")
        m2.metric("交易次數 (買賣一趟算1次)", f"{total_closed} 次")
        m3.metric("策略勝率", f"{win_rate:.1f}%")
        m4.metric("最大歷史回撤 (MDD)", f"{max_dd:.2f}%")
        
        # ==========================================
        # 4. 繪製互動式結果圖表 (K線 + 權益曲線)
        # ==========================================
        dt_all = pd.date_range(start=df_bt['date'].min(), end=df_bt['date'].max())
        dt_obs = [d.strftime("%Y-%m-%d") for d in df_bt['date']]
        dt_breaks = [d for d in dt_all.strftime("%Y-%m-%d").tolist() if d not in dt_obs]

        fig = make_subplots(
            rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.05,
            subplot_titles=(f"{stock_code} 股價與進出場點位", "資產權益曲線 (Equity Curve)")
        )

        fig.add_trace(go.Candlestick(
            x=df_bt['date'], open=df_bt['open_price'], high=df_bt['high_price'], 
            low=df_bt['low_price'], close=df_bt['close_price'], name='K線'
        ), row=1, col=1)

        buys = [t for t in trade_log if t['動作'] == '買入']
        sells = [t for t in trade_log if t['動作'] == '賣出']
        
        if buys:
            fig.add_trace(go.Scatter(
                x=[t['日期'] for t in buys], y=[t['股價']*0.95 for t in buys], 
                mode='markers+text', marker=dict(symbol='triangle-up', size=14, color='#2ecc71'), 
                name='買入訊號', text="B", textposition="bottom center"
            ), row=1, col=1)
            
        if sells:
            fig.add_trace(go.Scatter(
                x=[t['日期'] for t in sells], y=[t['股價']*1.05 for t in sells], 
                mode='markers+text', marker=dict(symbol='triangle-down', size=14, color='#e74c3c'), 
                name='賣出訊號', text="S", textposition="top center"
            ), row=1, col=1)

        fig.add_trace(go.Scatter(
            x=df_eq['date'], y=df_eq['equity'], 
            line=dict(color='#f1c40f', width=2), name='總資產', fill='tozeroy'
        ), row=2, col=1)

        fig.update_layout(
            height=700, margin=dict(l=0, r=0, t=30, b=0), hovermode='x unified',
            xaxis_rangeslider_visible=False, xaxis2_rangeslider_visible=False,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0)
        )
        fig.update_xaxes(rangebreaks=[dict(values=dt_breaks)])

        st.plotly_chart(fig, width="stretch", config={'displayModeBar': True})

        # ==========================================
        # 5. 成對交易明細清單
        # ==========================================
        st.markdown("#### 📜 詳細配對交易紀錄")
        if trade_results:
            df_res = pd.DataFrame(trade_results)
            
            st.dataframe(
                df_res.style.map(
                    lambda x: 'color: #ff4b4b;' if x > 0 else ('color: #00d26a;' if x < 0 else ''),
                    subset=['損益', '報酬率(%)']
                ).format({
                    "買入單價": "{:.2f}", 
                    "賣出單價": "{:.2f}", 
                    "損益": "{:,.0f}", 
                    "報酬率(%)": "{:.2f}%",
                    "交易股數": "{:,}"
                }),
                width="stretch", hide_index=True
            )
        else:
            st.info("此次回測期間內未觸發任何交易。")

