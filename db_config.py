import os
from dotenv import load_dotenv
from models import setup_database

# 載入 .env 檔案
load_dotenv()

# 用來儲存全域的 SessionLocal，避免重複建立連線引擎
_SessionLocal = None

def get_db_url() -> str:
    """從環境變數組裝並回傳 MS SQL 資料庫連線字串"""
    user = os.getenv('DB_USER')
    password = os.getenv('DB_PASSWORD')
    server = os.getenv('DB_SERVER')
    db_name = os.getenv('DB_NAME')
    
    # 防呆檢查：確保 .env 都有正確填寫
    if not all([user, password, server, db_name]):
        raise ValueError("❌ 資料庫環境變數設定不完整，請檢查 .env 檔案！")

    db_url = (
        f"mssql+pyodbc://{user}:{password}@{server}/{db_name}"
        "?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
    )
    return db_url

def get_db_session():
    """取得 SQLAlchemy 的 SessionLocal (單例模式)"""
    global _SessionLocal
    
    # 如果還沒有建立過連線，就初始化一次
    if _SessionLocal is None:
        db_url = get_db_url()
        _SessionLocal = setup_database(db_url)
        
    return _SessionLocal