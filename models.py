from sqlalchemy import NVARCHAR, Column, Integer, String, Date, Float, BigInteger, Boolean, create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()

# 第一張表：儲存股票基本資料
class Stock(Base):
    __tablename__ = 'stocks'
    
    # 股票代號只有英數字，維持一般 String(VARCHAR) 即可
    stock_code = Column(String(10), primary_key=True, comment="股票代號")
    # 名稱包含中文，明確指定使用 NVARCHAR 確保編碼正確
    name = Column(NVARCHAR(50), nullable=False, comment="股票名稱")
    
    is_taiwan50 = Column(Boolean, default=False, comment="是否為0050成分股")
    is_index = Column(Boolean, default=False, comment="是否為大盤指數")

# 第二張表：儲存每天的價格紀錄
class DailyPrice(Base):
    __tablename__ = 'daily_prices'
    
    # --- 基礎資料 ---
    stock_code = Column(String(10), primary_key=True, comment="股票代號")
    date = Column(Date, primary_key=True, comment="交易日期")
    
    open_price = Column(Float, comment="開盤價")
    high_price = Column(Float, comment="最高價")
    low_price = Column(Float, comment="最低價")
    close_price = Column(Float, comment="收盤價(已還原)")
    volume = Column(BigInteger, comment="成交股數")
    
    # --- 新增技術指標欄位 ---
    # MA 均線
    ma_5 = Column(Float, comment="5日均線")
    ma_10 = Column(Float, comment="10日均線")
    ma_20 = Column(Float, comment="20日均線")
    ma_60 = Column(Float, comment="60日均線")
    ma_120 = Column(Float, comment="120日均線(半年線)")
    ma_240 = Column(Float, comment="240日均線(年線)")
    
    # 乖離率 Bias
    bias_10 = Column(Float, comment="10日乖離率")
    bias_20 = Column(Float, comment="20日乖離率")


# 第三張表：三大法人每日買賣超
class InstitutionalTrade(Base):
    """三大法人買賣超資料，來源為 TWSE T86 日報。"""
    __tablename__ = 'institutional_trades'

    stock_code = Column(String(10), primary_key=True, comment="股票代號")
    date = Column(Date, primary_key=True, comment="交易日期")

    foreign_net_buy = Column(BigInteger, comment="外資及陸資買賣超股數")
    investment_trust_net_buy = Column(BigInteger, comment="投信買賣超股數")
    dealer_net_buy = Column(BigInteger, comment="自營商買賣超股數")
    total_net_buy = Column(BigInteger, comment="三大法人買賣超股數合計")


# 第四張表：個人交易紀錄表
class TransactionRecord(Base):
    """個人交易紀錄表"""
    __tablename__ = 'transaction_records'

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(10), nullable=False) # 股票代號
    trade_date = Column(Date, nullable=False)       # 交易日期
    trade_type = Column(NVARCHAR(50), nullable=False) # '買入' 或 '賣出'
    quantity = Column(Integer, nullable=False)      # 交易股數 (買入為正，賣出也可存正數，由系統判斷)
    price = Column(Float, nullable=False)           # 成交單價
    fee = Column(Float, default=0.0)                # 手續費
    tax = Column(Float, default=0.0)                # 交易稅 (通常賣出才收)
    notes = Column(NVARCHAR(50), nullable=True)      # 備註 (例如：分割調整、質押註記)

def setup_database(db_url: str):
    """初始化資料庫與自動建表"""
    connect_args = {}
    if db_url.startswith("sqlite"):
        connect_args = {"timeout": 30, "check_same_thread": False}

    engine = create_engine(db_url, echo=False, connect_args=connect_args)

    if db_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def set_sqlite_pragmas(dbapi_connection, _):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()

    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal
