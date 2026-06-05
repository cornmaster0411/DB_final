import os
from urllib.parse import quote_plus
from dotenv import load_dotenv
from models import setup_database

# 載入 .env 檔案
load_dotenv()

# 用來儲存全域的 SessionLocal，避免重複建立連線引擎
_SessionLocal = None

def get_db_url() -> str:
    """從環境變數組裝並回傳資料庫連線字串"""
    db_driver = os.getenv('DB_DRIVER', 'mssql').lower()

    if db_driver == 'sqlite':
        sqlite_path = os.getenv('DB_SQLITE_PATH', 'db_final.sqlite3')
        return f"sqlite:///{sqlite_path}"

    user = os.getenv('DB_USER')
    password = os.getenv('DB_PASSWORD')
    server = os.getenv('DB_SERVER')
    db_name = os.getenv('DB_NAME')
    
    # 防呆檢查：確保 .env 都有正確填寫
    if not all([user, password, server, db_name]):
        raise ValueError("❌ 資料庫環境變數設定不完整，請檢查 .env 檔案！")

    odbc_string = (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={server};"
        f"DATABASE={db_name};"
        f"UID={user};"
        f"PWD={password};"
        "Encrypt=no;"
        "TrustServerCertificate=yes;"
    )
    db_url = f"mssql+pyodbc:///?odbc_connect={quote_plus(odbc_string)}"
    return db_url

def get_db_session():
    """取得 SQLAlchemy 的 SessionLocal (單例模式)"""
    global _SessionLocal
    
    # 如果還沒有建立過連線，就初始化一次
    if _SessionLocal is None:
        db_url = get_db_url()
        _SessionLocal = setup_database(db_url)
        
    return _SessionLocal
