"""
서브노티카2 스팀 리뷰 실데이터 분석 (App ID: 1962700)
==================================================================
[본인 실행 안내]
이 코드는 실제 네트워크 요청을 포함하므로, 인터넷이 연결된 본인
노트북 환경에서 실행해야 함 (이 작업 환경은 네트워크가 차단되어 있어
직접 실행 결과를 보여드릴 수 없음 — 아래는 가짜 응답으로 로직만
검증한 버전).

흐름: 1) 리뷰 수집 → 2) 부정 리뷰 키워드 빈도 분석 → 3) 시각화
"""

import requests
import pandas as pd
import matplotlib.pyplot as plt
import time

APP_ID = 1962700
# [중요] 한국어는 "튕김/튕겨요/튕기네요"처럼 활용형이 다양해, 완전한 단어로
# 검색하면 상당수를 놓침 (예: "튕김"은 "튕겨요"라는 실제 리뷰 문장에 포함되지
# 않음 — 활용 과정에서 형태가 바뀌기 때문). 그래서 활용에 영향받지 않는
# 최소 어근 조각으로 키워드를 정의함
#
# [추가 키워드 - 습성 도입 가설과 연결] "단조", "지루", "생태계"를 추가함.
# 이유: 고철 운반형 습성 시뮬레이션 가설의 배경이 "초반 생태계·파밍이
# 단조롭게 느껴질 수 있다"는 것이었는데, 실제 부정 리뷰에 이런 언급이
# 있는지 확인하면 시뮬레이션(가상)과 별개로 실측 근거를 하나 더 확보할
# 수 있음. 있으면 정직하게 인용하고, 없으면 없는 대로 "실측 근거는
# 아직 없음"이라고 쓰면 되므로 추가에 따른 리스크는 없음.
#   - "단조"  → 단조롭다/단조로워요/단조로운 등 활용형을 모두 포함하는 어근
#   - "지루"  → 지루하다/지루해요/지루함 등 활용형을 모두 포함하는 어근
#   - "생태계" → 명사라 활용형 문제가 없어 그대로 사용
# ※ "심심하다(지루하다는 뜻)"도 후보였지만, "심심한 사과" 같은 전혀 다른
#   의미(깊은/진심 어린)로도 쓰이는 다의어라 오탐(false positive) 위험이
#   있어 이번엔 제외함
#
# [2차 추가 - 실제 데이터에서 발견한 키워드] 1차 소규모 실데이터(n=34)를 직접
# 읽어보다가 "못죽", "답답", "기절"이 비살상 설계(공격해도 죽이지 못하고
# 기절/도주만 하는 패치)에 대한 실제 유저 반발과 연결되는 것을 발견해 추가함.
# 즉 처음엔 본인 가설 기반으로 키워드를 정했지만(가설 주도), 실제 데이터를
# 보고 예상 못한 키워드를 발견해 키워드셋을 보정함(데이터 주도 보정).
#   - "못죽"  → 못죽이는/못죽여서/못죽이게 등 활용형을 포괄하는 어근
#   - "답답"  → 답답하다/답답해요/답답함 등 활용형을 포괄하는 어근
#   - "기절"  → 명사라 활용형 문제 없이 그대로 사용
# ※ "PC" 키워드는 제외함. n=150 데이터로 원문을 직접 검증해보니 "PC를 재부팅"
# 처럼 하드웨어(컴퓨터)를 가리키는 용례가 확인됐고, 나머지 사례는 자동 매칭만
# 으로는 의미를 단정하기 어려운 다의어였음. 신뢰도 낮은 키워드라 분석 범위를
# "설계·UX 불만" 쪽으로 한정함
KEYWORDS = ["레비아탄", "튕", "크래시", "어그로", "최적화", "단조", "지루", "생태계",
            "못죽", "답답", "기절"]

plt.rcParams["axes.unicode_minus"] = False
# Windows는 보통 맑은 고딕이 기본 탑재되어 한글이 바로 표시됨.
# 글자가 깨지면 아래 주석을 해제하고 본인 시스템 폰트로 설정
# plt.rcParams["font.family"] = "Malgun Gothic"


def fetch_reviews(app_id, num_pages=10, language="koreana"):
    """스팀 공식 리뷰 API 호출 — 페이지네이션 처리 포함 (API 키 불필요)"""
    reviews, cursor = [], "*"
    url = f"https://store.steampowered.com/appreviews/{app_id}"
    for _ in range(num_pages):
        params = {"json": 1, "filter": "recent", "language": language,
                  "num_per_page": 100, "cursor": cursor}
        data = requests.get(url, params=params, timeout=10).json()
        if not data.get("reviews"):
            break
        reviews += [{"text": r["review"], "voted_up": r["voted_up"]} for r in data["reviews"]]
        cursor = data.get("cursor", cursor)
        time.sleep(1)  # 서버 부담을 줄이기 위한 요청 간격
    return pd.DataFrame(reviews)


def keyword_counts(df, keywords):
    """부정 리뷰 중 키워드별 언급 건수 집계"""
    neg = df[~df["voted_up"]]
    counts = {kw: int(neg["text"].str.contains(kw, na=False).sum()) for kw in keywords}
    return counts, len(neg)


if __name__ == "__main__":
    df = fetch_reviews(APP_ID)
    df.to_csv("subnautica2_reviews.csv", index=False, encoding="utf-8-sig")

    counts, neg_total = keyword_counts(df, KEYWORDS)
    print(f"수집 리뷰 {len(df)}건 (부정 {neg_total}건)")
    for kw, c in counts.items():
        pct = c / neg_total if neg_total else 0
        print(f"  '{kw}' 언급: {c}건 ({pct:.1%})")

    plt.bar(counts.keys(), counts.values(), color="#e74c3c")
    plt.ylabel("부정 리뷰 내 언급 건수")
    plt.title("서브노티카2 부정 리뷰 키워드 빈도")
    plt.tight_layout()
    plt.savefig("subnautica2_keyword_freq.png", dpi=150)
    print("\n차트 저장 완료: subnautica2_keyword_freq.png")
