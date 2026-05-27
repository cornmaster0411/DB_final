-- 如果已經有這個 SP，就先刪除
IF OBJECT_ID('sp_CalculateTechnicalIndicators', 'P') IS NOT NULL
    DROP PROCEDURE sp_CalculateTechnicalIndicators;
GO

CREATE PROCEDURE sp_CalculateTechnicalIndicators
    @StockCode VARCHAR(10) = NULL -- 可以傳入特定股票代號，如果 NULL 就全算
AS
BEGIN
    SET NOCOUNT ON;

    -- 為了計算方便，我們先把需要的資料寫入一個暫存表 #TempStockData
    SELECT 
        stock_code, 
        date, 
        close_price
    INTO #TempStockData
    FROM daily_prices
    WHERE (@StockCode IS NULL OR stock_code = @StockCode);

    -- ==========================================
    -- 第一階段：計算 MA (移動平均) 與 Row Number
    -- 【修正重點】: Window Function (包含 ROW_NUMBER) 只能寫在 SELECT 裡面，不能寫在 UPDATE SET 裡面。
    -- 所以我們在這裡把 rn (第幾天) 一起算出來。
    -- ==========================================
    WITH MACalc AS (
        SELECT 
            stock_code, 
            date,
            ROW_NUMBER() OVER (PARTITION BY stock_code ORDER BY date) AS rn,
            AVG(close_price) OVER (PARTITION BY stock_code ORDER BY date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) AS ma_5,
            AVG(close_price) OVER (PARTITION BY stock_code ORDER BY date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW) AS ma_10,
            AVG(close_price) OVER (PARTITION BY stock_code ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS ma_20,
            AVG(close_price) OVER (PARTITION BY stock_code ORDER BY date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS ma_60,
            AVG(close_price) OVER (PARTITION BY stock_code ORDER BY date ROWS BETWEEN 119 PRECEDING AND CURRENT ROW) AS ma_120,
            AVG(close_price) OVER (PARTITION BY stock_code ORDER BY date ROWS BETWEEN 239 PRECEDING AND CURRENT ROW) AS ma_240
        FROM #TempStockData
    )
    -- 將計算出來的 MA 更新回主表
    UPDATE d
    SET 
        d.ma_5   = CASE WHEN m.rn >= 5   THEN m.ma_5   ELSE NULL END,
        d.ma_10  = CASE WHEN m.rn >= 10  THEN m.ma_10  ELSE NULL END,
        d.ma_20  = CASE WHEN m.rn >= 20  THEN m.ma_20  ELSE NULL END,
        d.ma_60  = CASE WHEN m.rn >= 60  THEN m.ma_60  ELSE NULL END,
        d.ma_120 = CASE WHEN m.rn >= 120 THEN m.ma_120 ELSE NULL END,
        d.ma_240 = CASE WHEN m.rn >= 240 THEN m.ma_240 ELSE NULL END
    FROM daily_prices d
    INNER JOIN MACalc m ON d.stock_code = m.stock_code AND d.date = m.date;

    -- ==========================================
    -- 第二階段：計算 BIAS (乖離率)
    -- ==========================================
    UPDATE daily_prices
    SET bias_10 = CASE WHEN ma_10 IS NOT NULL AND ma_10 <> 0 THEN ((close_price - ma_10) / ma_10) * 100 ELSE NULL END,
        bias_20 = CASE WHEN ma_20 IS NOT NULL AND ma_20 <> 0 THEN ((close_price - ma_20) / ma_20) * 100 ELSE NULL END
    WHERE (@StockCode IS NULL OR stock_code = @StockCode);

    DROP TABLE #TempStockData;
END;
GO