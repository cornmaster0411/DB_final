import streamlit as st
import pandas as pd
import plotly.express as px
from db_config import get_db_session
from models import TransactionRecord, DailyPrice, Stock

def render_portfolio():
    # 隱藏預設的頁籤標題，因為我們要在這邊做自己的大標題
    st.markdown("## 💰 個人投資帳戶與庫存管理")
    
    # ==========================================
    # 1. 取得資料庫中的股票清單 (供下拉選單使用)
    # ==========================================
    with get_db_session()() as session:
        stocks = session.query(Stock).filter(
            (Stock.is_taiwan50 == True) | (Stock.is_index == True)
        ).all()
        stock_options = [f"{s.stock_code} {s.name}" for s in stocks]
        
    default_stock_idx = 0
    for i, s in enumerate(stock_options):
        if s.startswith("0050"):
            default_stock_idx = i
            break

    # ==========================================
    # 2. 獲取所有交易紀錄與計算庫存
    # ==========================================
    with get_db_session()() as session:
        trades = session.query(TransactionRecord).order_by(TransactionRecord.trade_date).all()
    
    inventory = {}
    for t in trades:
        code = str(t.stock_code)
        ttype = str(t.trade_type)
        
        if code not in inventory:
            inventory[code] = {'總股數': 0, '總成本': 0.0}
        
        qty = int(t.quantity)
        price = float(t.price)
        
        # 處理 0050 於 2025 年的股票分割 (根據你的歷史修正紀錄[cite: 1])
        if code == '0050' and t.trade_date.year < 2025:
            qty = qty * 2
            
        if ttype == '買入':
            inventory[code]['總股數'] += qty
            inventory[code]['總成本'] += qty * price
        elif ttype == '賣出':
            if inventory[code]['總股數'] > 0:
                avg_cost = inventory[code]['總成本'] / inventory[code]['總股數']
                inventory[code]['總股數'] -= qty
                inventory[code]['總成本'] -= qty * avg_cost
    
    # 過濾掉已經賣光的部位
    active_inv = {k: v for k, v in inventory.items() if v['總股數'] > 0}
    
    # ==========================================
    # 3. 上半部：庫存資產總覽 (全寬版面)
    # ==========================================
    st.markdown("### 📦 庫存資產總覽")
    if not active_inv:
        st.info("目前手上無庫存部位。請於下方新增買入交易來開始建立你的投資組合！")
    else:
        df_inv = pd.DataFrame.from_dict(active_inv, orient='index').reset_index()
        df_inv.rename(columns={'index': '股票代號'}, inplace=True)
        df_inv['持有均價'] = (df_inv['總成本'] / df_inv['總股數']).round(2)
        
        # 抓取最新市價
        latest_prices = {}
        with get_db_session()() as session:
            for code in df_inv['股票代號']:
                latest_record = session.query(DailyPrice).filter_by(stock_code=code).order_by(DailyPrice.date.desc()).first()
                latest_prices[code] = latest_record.close_price if latest_record else df_inv.loc[df_inv['股票代號']==code, '持有均價'].values[0]
        
        df_inv['最新市價'] = df_inv['股票代號'].map(latest_prices)
        df_inv['現值'] = df_inv['總股數'] * df_inv['最新市價']
        df_inv['未實現損益'] = (df_inv['現值'] - df_inv['總成本']).round(2)
        df_inv['報酬率(%)'] = ((df_inv['未實現損益'] / df_inv['總成本']) * 100).round(2)
        
        # 建立上方三大數字指標 (Metrics)
        total_cost = df_inv['總成本'].sum()
        total_value = df_inv['現值'].sum()
        total_pnl = df_inv['未實現損益'].sum()
        total_roi = (total_pnl / total_cost * 100) if total_cost > 0 else 0
        
        m1, m2, m3 = st.columns(3)
        m1.metric("總投入成本", f"${total_cost:,.0f}")
        m2.metric("目前總市值", f"${total_value:,.0f}")
        m3.metric("總未實現損益", f"${total_pnl:,.0f}", f"{total_roi:.2f}%")
        
        st.markdown("<br>", unsafe_allow_html=True) # 增加一些留白
        
        # 顯示資料表與圓餅圖
        col_tbl, col_pie = st.columns([2, 1.2])
        with col_tbl:
            st.dataframe(
                df_inv[['股票代號', '總股數', '持有均價', '最新市價', '現值', '未實現損益', '報酬率(%)']], 
                width='stretch', hide_index=True
            )
        with col_pie:
            # 甜甜圈圓餅圖 (hole=0.4) 更有質感
            fig = px.pie(df_inv, values='現值', names='股票代號', hole=0.4)
            fig.update_traces(textposition='inside', textinfo='percent+label')
            fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=250)
            st.plotly_chart(fig, width="stretch")

    st.divider() # 分隔線

    # ==========================================
    # 4. 下半部：操作區 (新增/編輯 與 歷史明細)
    # ==========================================
    col_add, col_history = st.columns([1, 1.5])
    
    with col_add:
        st.markdown("#### 📝 新增交易")
        with st.form("add_transaction_form"):
            t_date = st.date_input("交易日期")
            t_type = st.selectbox("交易類別", ["買入", "賣出"])
            t_stock_full = st.selectbox("股票標的", stock_options, index=default_stock_idx)
            
            c1, c2 = st.columns(2)
            with c1:
                t_price = st.number_input("成交單價", min_value=0.0, format="%.2f")
            with c2:
                t_qty = st.number_input("交易股數", min_value=1, step=1000, value=1000)
            
            t_notes = st.text_input("備註 (選填)")
            submitted = st.form_submit_button("送出紀錄", type="primary")
            
            if submitted:
                t_stock = t_stock_full.split(" ")[0] 
                with get_db_session()() as session:
                    new_trade = TransactionRecord(
                        stock_code=t_stock,
                        trade_date=t_date,
                        trade_type=t_type.strip(),
                        quantity=t_qty,
                        price=t_price,
                        notes=t_notes.strip() if t_notes else ""
                    )
                    session.add(new_trade)
                    session.commit()
                    st.success("✅ 交易新增成功！")
                    st.rerun()

        st.markdown("#### ⚙️ 編輯或刪除歷史紀錄")
        if trades:
            with st.expander("點此展開管理工具"):
                trade_options = {
                    f"{t.trade_date} | {str(t.stock_code).strip()} {str(t.trade_type).strip()} {t.quantity}股 @ {t.price}": t.id 
                    for t in reversed(trades) # 讓最新的交易排在最上面
                }
                selected_trade_label = st.selectbox("選擇要修改的紀錄", list(trade_options.keys()))
                
                if selected_trade_label:
                    selected_id = trade_options[selected_trade_label]
                    with get_db_session()() as session:
                        record_to_edit = session.query(TransactionRecord).get(selected_id)
                        
                        if record_to_edit:
                            with st.form(key=f"edit_form_{selected_id}"):
                                e_date = st.date_input("日期", value=record_to_edit.trade_date)
                                
                                current_type = str(record_to_edit.trade_type).strip()
                                e_type = st.selectbox("類別", ["買入", "賣出"], index=0 if current_type == "買入" else 1)
                                
                                current_code = str(record_to_edit.stock_code).strip()
                                try:
                                    e_stock_index = next(i for i, v in enumerate(stock_options) if v.startswith(current_code))
                                except StopIteration:
                                    e_stock_index = 0
                                    
                                e_stock_full = st.selectbox("標的", stock_options, index=e_stock_index)
                                
                                c1, c2 = st.columns(2)
                                with c1:
                                    e_price = st.number_input("單價", min_value=0.0, value=float(record_to_edit.price), format="%.2f")
                                with c2:
                                    e_qty = st.number_input("股數", min_value=1, step=1000, value=int(record_to_edit.quantity))
                                
                                e_notes = st.text_input("備註", value=record_to_edit.notes if record_to_edit.notes else "")
                                
                                col_upd, col_del = st.columns(2)
                                with col_upd:
                                    btn_update = st.form_submit_button("💾 儲存修改", type="primary")
                                with col_del:
                                    btn_delete = st.form_submit_button("🗑️ 刪除此筆")
                                    
                            if btn_update:
                                record_to_edit.trade_date = e_date
                                record_to_edit.trade_type = e_type
                                record_to_edit.stock_code = e_stock_full.split(" ")[0]
                                record_to_edit.price = e_price
                                record_to_edit.quantity = e_qty
                                record_to_edit.notes = e_notes
                                session.commit()
                                st.success("✅ 紀錄已成功更新！")
                                st.rerun()
                            if btn_delete:
                                session.delete(record_to_edit)
                                session.commit()
                                st.warning("🗑️ 紀錄已徹底刪除！")
                                st.rerun()
        else:
            st.info("尚無紀錄可編輯。")

    with col_history:
        st.markdown("#### 🔍 各股歷史交易明細")
        if trades:
            all_traded_stocks = sorted(list(set([str(t.stock_code).strip() for t in trades])))
            selected_detail_stock = st.selectbox("篩選查看的股票標的", ["全部"] + all_traded_stocks)
            
            details = []
            for t in reversed(trades): # 由新到舊
                code = str(t.stock_code).strip()
                if selected_detail_stock == "全部" or code == selected_detail_stock:
                    details.append({
                        '交易日期': t.trade_date,
                        '股票': code,
                        '類別': str(t.trade_type).strip(),
                        '股數': t.quantity,
                        '單價': t.price,
                        '總額': t.quantity * t.price,
                        '備註': t.notes
                    })
            
            df_trades = pd.DataFrame(details)
            # 設定高度讓它可以滾動，版面不會過長
            st.dataframe(df_trades, width='stretch', hide_index=True, height=500)
        else:
            st.info("尚無任何交易紀錄。")