from selenium import webdriver
from selenium.webdriver.common.by import By
from sqlalchemy.orm import Session
from models import Stock

class StockListManager:
    def __init__(self, session_maker):
        self.SessionLocal = session_maker

    def update_taiwan50_list(self):
        print("🔍 啟動瀏覽器，從 CMoney 抓取 0050 成分股名單與名稱...")
        
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--disable-notifications")
        options.add_argument("start-maximized")
        driver = webdriver.Chrome(options=options)

        # 簡化抓資料的時間 用這些就好了
        taiwan50_stocks = {
            "2330": "台積電",
            "2317": "鴻海",
            "2454": "聯發科",
            "6505": "台塑化",
            "2881": "富邦金",
            "1301": "台塑",
            "2002": "中鋼",
            "2412": "中華電",
            "1101": "台泥"
        }
        # try:
        #     driver.get("https://www.cmoney.tw/etf/tw/0050/fundholding")
        #     driver.implicitly_wait(10) 
            
        #     stock_table = driver.find_element(By.XPATH, '//*[@id="__layout"]/div/div[3]/div/div[2]/main/div/div[4]/section/div[2]/div/table')
        #     stocks = stock_table.find_elements(By.TAG_NAME, "tr")

        #     for stock in stocks[1:-2]: 
        #         stock_info = stock.find_elements(By.TAG_NAME, "td")
        #         try:
        #             if len(stock_info) > 1:
        #                  code = stock_info[0].text.strip()
        #                  name = stock_info[1].text.strip()
        #                  if code and name:
        #                      taiwan50_stocks[code] = name
        #         except Exception as e:
        #             print(f"⚠️ 解析單筆資料發生錯誤，略過... ({e})")
                    
        # except Exception as e:
        #      print(f"❌ 抓取網頁失敗: {e}")
        # finally:
        #     driver.quit()

        if not taiwan50_stocks:
            print("⚠️ 未能抓取到任何名單。")
            return

        with self.SessionLocal() as session:
            try:
                # 1. 先把所有股票的 0050 標記取消
                session.query(Stock).update({Stock.is_taiwan50: False})
                
                # 2. 把抓到的名單寫進去
                for code, name in taiwan50_stocks.items():
                    stock = session.query(Stock).filter(Stock.stock_code == code).first()
                    if stock:
                         stock.is_taiwan50 = True
                         stock.name = name 
                    else:
                         new_stock = Stock(stock_code=code, name=name, is_taiwan50=True)
                         session.add(new_stock)

                # 3. 確保大盤 (^TWII) 在資料庫中
                index_stock = session.query(Stock).filter(Stock.stock_code == "^TWII").first()
                if not index_stock:
                    session.add(Stock(stock_code="^TWII", name="台灣加權指數", is_index=True))

                session.commit()
                print(f"✅ 成功更新 {len(taiwan50_stocks)} 檔 0050 成分股至資料庫")

            except Exception as e:
                session.rollback()
                print(f"❌ 資料庫更新失敗: {e}")

    def get_target_stocks(self) -> list:
        with self.SessionLocal() as session:
            stocks = session.query(Stock).filter(
                (Stock.is_taiwan50 == True) | (Stock.is_index == True)
            ).all()
            
            codes = [s.stock_code for s in stocks]
            
            # 專題要求台積電必做
            if "2330" not in codes:
                codes.append("2330")
                
            return list(set(codes))