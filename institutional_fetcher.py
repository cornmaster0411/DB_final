from datetime import datetime, timedelta
import time
from typing import Any

import requests

from models import InstitutionalTrade


class InstitutionalFetcher:
    """Fetch and persist TWSE institutional investor T86 daily data."""

    TWSE_T86_URL = "https://www.twse.com.tw/rwd/zh/fund/T86"

    def __init__(self, session_maker):
        self.SessionLocal = session_maker
        self.http = requests.Session()
        self.http.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/125.0 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": "https://www.twse.com.tw/zh/trading/foreign/t86.html",
        })

    @staticmethod
    def _parse_int(value: Any) -> int:
        if value is None:
            return 0
        text = str(value).replace(",", "").replace("+", "").strip()
        if text in {"", "--", "X"}:
            return 0
        return int(float(text))

    @staticmethod
    def _date_range(start_date: str, end_date: str):
        current = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
        while current <= end:
            yield current
            current += timedelta(days=1)

    def fetch_one_day(self, stock_code: str, trade_date) -> dict | None:
        params = {
            "date": trade_date.strftime("%Y%m%d"),
            "selectType": "ALLBUT0999",
            "response": "json",
        }
        payload = self._get_json(params)
        if payload is None:
            return None

        if payload.get("stat") != "OK":
            return None

        fields = payload.get("fields", [])
        rows = payload.get("data", [])
        if not fields or not rows:
            return None

        field_index = {name: idx for idx, name in enumerate(fields)}
        code_idx = field_index.get("證券代號")
        if code_idx is None:
            return None

        target_row = next((row for row in rows if str(row[code_idx]).strip() == stock_code), None)
        if target_row is None:
            return None

        def value_for(*possible_names: str) -> int:
            for name in possible_names:
                idx = field_index.get(name)
                if idx is not None and idx < len(target_row):
                    return self._parse_int(target_row[idx])
            return 0

        foreign = value_for(
            "外陸資買賣超股數(不含外資自營商)",
            "外資及陸資買賣超股數",
        )
        trust = value_for("投信買賣超股數")
        dealer = value_for(
            "自營商買賣超股數",
            "自營商買賣超股數(自行買賣)",
        )
        total = value_for("三大法人買賣超股數")
        if total == 0:
            total = foreign + trust + dealer

        return {
            "stock_code": stock_code,
            "date": trade_date,
            "foreign_net_buy": foreign,
            "investment_trust_net_buy": trust,
            "dealer_net_buy": dealer,
            "total_net_buy": total,
        }

    def _get_json(self, params: dict) -> dict | None:
        for attempt in range(3):
            response = self.http.get(self.TWSE_T86_URL, params=params, timeout=20)
            if response.status_code in {429, 500, 502, 503, 504}:
                time.sleep(1.5 + attempt)
                continue

            response.raise_for_status()
            text = response.text.strip()
            if not text or text[0] not in "[{":
                time.sleep(1.5 + attempt)
                continue

            try:
                return response.json()
            except ValueError:
                time.sleep(1.5 + attempt)

        return None

    def fetch_and_save(self, stock_code: str, start_date: str, end_date: str) -> int:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
        with self.SessionLocal() as session:
            existing_dates = {
                row.date for row in session.query(InstitutionalTrade.date).filter(
                    InstitutionalTrade.stock_code == stock_code,
                    InstitutionalTrade.date >= start_dt,
                    InstitutionalTrade.date <= end_dt,
                ).all()
            }

        rows_to_save = []
        skipped_count = len(existing_dates)
        missing_count = 0
        for trade_date in self._date_range(start_date, end_date):
            if trade_date in existing_dates:
                continue

            missing_count += 1
            try:
                data = self.fetch_one_day(stock_code, trade_date)
            except Exception as exc:
                print(f"法人資料 {stock_code} {trade_date} 抓取失敗: {exc}")
                continue

            if data:
                rows_to_save.append(data)
            else:
                skipped_count += 1

            time.sleep(0.25)

        saved_count = 0
        batch_size = 50
        with self.SessionLocal() as session:
            for start in range(0, len(rows_to_save), batch_size):
                batch = rows_to_save[start:start + batch_size]
                with session.no_autoflush:
                    for data in batch:
                        session.merge(InstitutionalTrade(**data))
                        saved_count += 1
                session.commit()

        if skipped_count:
            print(f"法人資料 {stock_code} 已有 {skipped_count} 天，直接略過不重抓")
        no_data_count = missing_count - len(rows_to_save)
        if no_data_count:
            print(f"法人資料 {stock_code} 另有 {no_data_count} 天為休市、無資料或 TWSE 暫時無回應")
        return saved_count
