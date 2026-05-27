# 期末專題: 股票分析

##  啟動步驟 
1. 設定一下 `.env`檔案的DB密碼隨便打就好
 
2.
    ```bash
    docker compose up -d
    ```
3. 連線到 `http://localhost:8080/`建立DB(`.env`裡面的名稱) 然後把`indicator.sql`複製進去執行
4. 
    ```bash
    pip install -r requirements.txt
    ```
5. 
    啟動之後等他抓完資料會需要幾分鐘
    ```bash
    python -u main.py
    ```
6. 把服務跑起來
    ```bash
    streamlit run app.py
    ```
這樣應該就能看到畫面了
![alt text](images/index_page.png)
