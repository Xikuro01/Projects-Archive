"""
[역할 구분 명시]
이 스크립트는 '리뷰 데이터를 가져와서 DB에 적재'하는 역할만 함(Python).
실제 분석 로직(부정 리뷰 비율, 키워드 빈도 계산)은 전부 별도의
subnautica2_review_analysis.sql 파일 안에 순수 SQL로 작성됨.

[중요 - 실행 환경 고지]
이 작업 환경은 외부 네트워크가 차단되어 있어 실제 Steam 리뷰 API를
호출할 수 없음. 아래 두 함수 중:
  - fetch_reviews_from_api(): 실제 사용 시 이 함수를 쓰면 됨(본인
    노트북처럼 인터넷이 연결된 환경에서 실행)
  - generate_mock_reviews(): 이 환경에서 SQL 로직 자체의 정상 작동
    여부만 검증하기 위한 가짜 데이터 (실제 서비스 결과가 아님)
지금 이 스크립트는 후자를 사용해 DB를 생성함.
"""

import sqlite3
import requests
import time

DB_PATH = "/home/claude/subnautica2_reviews.db"
APP_ID = 1962700  # 서브노티카2 실제 Steam App ID


def fetch_reviews_from_api(app_id, num_pages=10, language="koreana"):
    """실제 사용 시 이 함수로 교체 — Steam 공식 리뷰 API(키 불필요)"""
    reviews, cursor = [], "*"
    url = f"https://store.steampowered.com/appreviews/{app_id}"
    for _ in range(num_pages):
        params = {"json": 1, "filter": "recent", "language": language,
                  "num_per_page": 100, "cursor": cursor}
        data = requests.get(url, params=params, timeout=10).json()
        if not data.get("reviews"):
            break
        for r in data["reviews"]:
            reviews.append((r["review"], int(r["voted_up"]), r["timestamp_created"]))
        cursor = data.get("cursor", cursor)
        time.sleep(1)
    return reviews


def generate_mock_reviews():
    """[테스트 전용] 이 환경에서 SQL 로직 검증을 위한 가짜 리뷰.
    실제 서비스 결과를 반영하지 않음 — 실행 환경 고지 참고."""
    samples = [
        ("정말 좋은 게임인데 레비아탄 때문에 스트레스 받아요 자꾸 튕겨요", 0),
        ("그래픽도 좋고 탐험하는 재미가 있습니다 추천!", 1),
        ("어그로 범위가 너무 넓어서 도망을 못 치겠어요", 0),
        ("최적화가 심각합니다 크래시가 너무 잦아요", 0),
        ("협동 플레이가 정말 재밌어요", 1),
        ("레비아탄 만나면 무조건 죽어요 밸런스 이상함", 0),
        ("튕김 현상 때문에 진행이 안 됩니다 환불하고 싶어요", 0),
        ("스토리도 괜찮고 사운드도 좋아요", 1),
        ("최적화 패치 좀 해주세요 렉이 심해요", 0),
        ("레비아탄 조우 강제되는 구간이 스트레스입니다", 0),
        # [추가] 습성 도입 가설과 연결되는 키워드(단조/지루/생태계) 검증용 샘플
        ("초반 생태계가 단조로워서 탐사 재미가 금방 식어요", 0),
        ("자원 파밍이 너무 지루하고 반복적입니다", 0),
    ] * 20  # 200건 규모로 확장(테스트 목적)
    return [(text, voted_up, 1700000000) for text, voted_up in samples]


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

# 실제 사용 시: rows = fetch_reviews_from_api(APP_ID)
rows = generate_mock_reviews()
cur.executemany("INSERT INTO reviews VALUES (?,?,?)", rows)
conn.commit()

count = cur.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
print(f"DB 생성 완료: {DB_PATH}")
print(f"적재된 리뷰 수: {count} (테스트용 가짜 데이터)")
conn.close()
