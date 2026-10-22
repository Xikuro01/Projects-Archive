"""
[역할 구분 유지] 이 스크립트는 실제 수집된 리뷰 CSV를 DB에 적재하는
역할만 함(Python). setup_subnautica2_db.py의 generate_mock_reviews()를
대체하는 "실제 사용" 버전 — 분석 로직(subnautica2_review_analysis.sql)은
전혀 건드리지 않고 그대로 재사용함.

입력 CSV: subnautica2_reviews_2026-08-31.csv
  컬럼: review_id, voted_up(True/False), review_text, playtime_forever_hrs,
        playtime_at_review_hrs, votes_up, created_at_dt
"""

import sqlite3
import pandas as pd

DB_PATH = "/home/claude/subnautica2_reviews.db"
CSV_PATH = "/mnt/user-data/uploads/subnautica2_reviews_150_2026-08-31.csv"

# encoding='utf-8-sig'로 읽어야 헤더 앞 BOM 문자가 컬럼명에 섞이지 않음
df = pd.read_csv(CSV_PATH, encoding="utf-8-sig")

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()
cur.execute("DROP TABLE IF EXISTS reviews")
cur.execute("""
    CREATE TABLE reviews (
        review_text TEXT,
        voted_up INTEGER,
        timestamp_created INTEGER
    )
""")

timestamp = pd.to_datetime(df["created_at_dt"]).astype("int64") // 10**9
rows = list(zip(df["review_text"], df["voted_up"].astype(int), timestamp))
cur.executemany("INSERT INTO reviews VALUES (?,?,?)", rows)
conn.commit()

count = cur.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
neg_count = cur.execute("SELECT COUNT(*) FROM reviews WHERE voted_up=0").fetchone()[0]
print(f"DB 적재 완료: {DB_PATH}")
print(f"적재된 리뷰 수: {count}건 (실제 데이터, 부정 리뷰 {neg_count}건)")
conn.close()
