from datetime import datetime, timedelta
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import func

from db_config import get_db_session
from institutional_fetcher import InstitutionalFetcher
from models import DailyPrice, Stock
from stock_list_manager import StockListManager
from price_fetcher import PriceFetcher

class SchedulerManager:
    def __init__(self):
        # 取得統一的資料庫連線
        self.SessionLocal = get_db_session()
        self.list_manager = StockListManager(self.SessionLocal)
        self.price_fetcher = PriceFetcher(self.SessionLocal)
        self.institutional_fetcher = InstitutionalFetcher(self.SessionLocal)
        
        self.scheduler = BlockingScheduler(timezone="Asia/Taipei")

    def run_manual_update(self):
        """
        【單次手動更新
        執行完整的名單爬取與歷史資料(2010年至今)更新
        """
        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🌟 開始執行【全量資料更新】任務...")
        
        self.list_manager.update_taiwan50_list()
        target_stocks = self.list_manager.get_target_stocks()
        
        start_date = "2010-01-01"
        end_date = datetime.now().strftime("%Y-%m-%d")
        
        self.price_fetcher.update_prices(target_stocks, start_date, end_date)
        print("✅ 【全量資料更新】任務完成！")

    def run_institutional_update(self):
        """補齊資料庫內所有股票的三大法人資料，前端回測只讀 DB。"""
        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🏦 開始補齊【三大法人資料】...")

        with self.SessionLocal() as session:
            stocks = session.query(Stock.stock_code).filter(Stock.is_index != True).all()
            stock_codes = [row.stock_code for row in stocks]

            range_rows = session.query(
                DailyPrice.stock_code,
                func.min(DailyPrice.date),
                func.max(DailyPrice.date),
            ).filter(
                DailyPrice.stock_code.in_(stock_codes)
            ).group_by(DailyPrice.stock_code).all()
            ranges = {stock_code: (start_date, end_date) for stock_code, start_date, end_date in range_rows}

        for stock_code in stock_codes:
            date_range = ranges.get(stock_code)
            if not date_range:
                print(f"略過 {stock_code}: 尚無價格資料")
                continue

            start_date, end_date = date_range
            print(f"補齊 {stock_code} 法人資料: {start_date} ~ {end_date}")
            count = self.institutional_fetcher.fetch_and_save(
                stock_code,
                start_date.strftime("%Y-%m-%d"),
                end_date.strftime("%Y-%m-%d"),
            )
            print(f"✅ {stock_code} 新增 {count} 筆法人資料")

        print("✅ 【三大法人資料】補齊完成！")

    def job_monthly_full_update(self):
        """[每月任務] 每個月初重新整理一次"""
        # 直接呼叫寫好的全量更新邏輯，避免程式碼重複
        self.run_manual_update() 

    def job_daily_price_update(self):
        """[每日任務] 僅抓取最近幾天的收盤價來補齊資料"""
        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 📈 開始執行【每日收盤更新】任務...")
        
        target_stocks = self.list_manager.get_target_stocks()
        
        # 往前推 100 天確保補齊週末或假日缺口
        start_date = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d")
        end_date = datetime.now().strftime("%Y-%m-%d")
        
        self.price_fetcher.update_prices(target_stocks, start_date, end_date)
        print("✅ 【每日收盤更新】任務完成！")

    def start(self):
        """設定時間並啟動排程"""
        self.scheduler.add_job(
            self.job_monthly_full_update, 
            trigger=CronTrigger(day='1', hour='16', minute='0')
        )
        
        self.scheduler.add_job(
            self.job_daily_price_update, 
            trigger=CronTrigger(day_of_week='mon-fri', hour='15', minute='0')
        )
        
        print("🕒 排程管理員已啟動 (按 Ctrl+C 停止)...")
        print("\n🚀 初次啟動排程，強制先執行一次全量初始化...")
        self.run_manual_update()
        
        # 進入無窮迴圈，開始背景監聽
        self.scheduler.start()

if __name__ == "__main__":
    manager = SchedulerManager()
    manager.start()
