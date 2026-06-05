import pandas as pd
import yfinance as yf
from sqlalchemy import text # 引入 SQL 執行套件
from models import DailyPrice

class PriceFetcher:
    def __init__(self, session_maker):
        self.SessionLocal = session_maker

    def _format_ticker(self, stock_code: str) -> str:
        if stock_code == "^TWII":
            return "^TWII"
        return f"{stock_code}.TW"

    def fetch_and_save(self, stock_code: str, start_date: str, end_date: str):
        ticker_symbol = self._format_ticker(stock_code)
        ticker = yf.Ticker(ticker_symbol)
        
        # 1. 獲取原始資料 (自動還原除權息與分割)
        df = ticker.history(start=start_date, end=end_date, auto_adjust=True)
        if df.empty:
            return 0

        # 2. 清除不完整的資料並整理欄位
        df = df.dropna(subset=['Open', 'High', 'Low', 'Close', 'Volume'])
        
        # 3. 將純 K 線資料寫入資料庫
        with self.SessionLocal() as session:
            records_count = 0
            for date_index, row in df.iterrows():
                record = DailyPrice(
                    stock_code=stock_code,
                    date=date_index.date(), 
                    open_price=float(row['Open']),
                    high_price=float(row['High']),
                    low_price=float(row['Low']),
                    close_price=float(row['Close']),
                    volume=int(row['Volume'])
                    # MA 和 BIAS 不在這邊寫入，等一下交給 SQL SP 處理
                    # RSI 和 KD 等一下交給前端動態處理
                )
                session.merge(record)
                records_count += 1
            
            session.commit()
            return records_count

    def update_prices(self, stock_list: list, start_date: str, end_date: str):
        print(f"\n📊 準備下載 {len(stock_list)} 檔標的之價格資料...")
        for stock_code in stock_list:
            print(f"下載 {stock_code}...", end=" ")
            try:
                count = self.fetch_and_save(stock_code, start_date, end_date)
                print(f"✅ 完成 ({count} 筆)")
            except Exception as e:
                print(f"❌ 錯誤: {e}")
                
        # ==========================================
        # ✨ 關鍵：所有股票資料都寫入 DB 後，計算 MA 和 BIAS
        # ==========================================
        print("\n⚙️ 正在計算技術指標 (MA, BIAS)...")
        with self.SessionLocal() as session:
            try:
                bind_name = session.get_bind().dialect.name
                if bind_name == "mssql":
                    session.execute(text("EXEC sp_CalculateTechnicalIndicators"))
                else:
                    self._calculate_indicators_in_python(session, stock_list)
                session.commit()
                print("✅ 技術指標計算完成！")
            except Exception as e:
                session.rollback()
                print(f"❌ 技術指標計算失敗: {e}")

    def _calculate_indicators_in_python(self, session, stock_list: list):
        for stock_code in stock_list:
            records = session.query(DailyPrice).filter(
                DailyPrice.stock_code == stock_code
            ).order_by(DailyPrice.date.asc()).all()

            if not records:
                continue

            df = pd.DataFrame([{
                "date": record.date,
                "close_price": record.close_price,
            } for record in records])

            for period in [5, 10, 20, 60, 120, 240]:
                df[f"ma_{period}"] = df["close_price"].rolling(period).mean()

            df["bias_10"] = ((df["close_price"] - df["ma_10"]) / df["ma_10"]) * 100
            df["bias_20"] = ((df["close_price"] - df["ma_20"]) / df["ma_20"]) * 100

            values = df.set_index("date").to_dict("index")
            for record in records:
                row = values[record.date]
                record.ma_5 = self._none_if_nan(row["ma_5"])
                record.ma_10 = self._none_if_nan(row["ma_10"])
                record.ma_20 = self._none_if_nan(row["ma_20"])
                record.ma_60 = self._none_if_nan(row["ma_60"])
                record.ma_120 = self._none_if_nan(row["ma_120"])
                record.ma_240 = self._none_if_nan(row["ma_240"])
                record.bias_10 = self._none_if_nan(row["bias_10"])
                record.bias_20 = self._none_if_nan(row["bias_20"])

    @staticmethod
    def _none_if_nan(value):
        return None if pd.isna(value) else float(value)
