"""
서브노티카 2 Steam 리뷰 — 제출 전 재점검 스크립트 (2026-10-23)
==================================================================
README의 수치를 "고유 리뷰 기준"으로 다시 확인하기 위한 스크립트.
기존 SQL 파이프라인(subnautica2_review_analysis.sql)을 대체하지 않으며,
아래 네 가지를 같은 CSV에서 독립적으로 재확인함.

  1) 리뷰 언어(문자) 구성과 분모 — 한국어 키워드를 적용해도 되는 표본인가
  2) 키워드별 건수와, 키워드 간 중복을 제거한 '고유 리뷰' 수
  3) 키워드 1개 이상에 걸린 부정 리뷰 비율 (키워드셋의 커버리지)
  4) 1차(n=34) 표본과 2차(n=150) 표본의 관계, 중복 여부

실행: python3 verify_keyword_overlap.py <150건 CSV> [<34건 CSV>]
"""
import sys
import math
import re
import pandas as pd

CSV_MAIN = sys.argv[1] if len(sys.argv) > 1 else "subnautica2_reviews_150_2026-08-31.csv"
CSV_FIRST = sys.argv[2] if len(sys.argv) > 2 else None

# SQL 파일과 동일한 키워드(어근) 정의
KEYWORDS = ["레비아탄", "튕", "크래시", "어그로", "최적화", "단조", "지루",
            "생태계", "못죽", "답답", "기절"]
UX_GROUP = ["못죽", "답답", "기절"]  # 기존 README의 '합산 9~10%' 대상


def wilson(k, n, z=1.96):
    """이항 비율의 Wilson 95% 신뢰구간 (소표본에서 정규근사보다 안정적)"""
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return (center - half, center + half)


def fmt_ci(k, n):
    lo, hi = wilson(k, n)
    return f"{k}/{n} = {100*k/n:.1f}%  (Wilson 95% CI {100*lo:.1f}% ~ {100*hi:.1f}%)"


df = pd.read_csv(CSV_MAIN, encoding="utf-8-sig")
df["when"] = pd.to_datetime(df["created_at_dt"])
text = df["review_text"].fillna("")

print("=" * 70)
print("[0] 표본 개요")
print("=" * 70)
neg = df[~df["voted_up"]].copy()
pos = df[df["voted_up"]]
print(f"전체 {len(df)}건 / 긍정 {len(pos)}건 / 부정 {len(neg)}건 (표본 내 긍정 비율 {100*len(pos)/len(df):.1f}%)")
print(f"작성일 범위: {df['when'].min().date()} ~ {df['when'].max().date()}")
print(f"review_id 중복 {df['review_id'].duplicated().sum()}건 / 본문 완전 중복 {text.duplicated().sum()}건 / 빈 본문 {(text.str.strip() == '').sum()}건")
print(f"작성 시점 플레이타임(시간): 중앙값 {df['playtime_at_review_hrs'].median():.1f}, "
      f"최소 {df['playtime_at_review_hrs'].min():.1f}, 최대 {df['playtime_at_review_hrs'].max():.1f}")

print("\n" + "=" * 70)
print("[1] 리뷰 언어 구성 — 한국어 키워드 적용 가능 여부")
print("=" * 70)
print("※ CSV에 언어 컬럼이 없어 '한글 포함 여부'로 판별함 (수집 시 language=koreana 필터 사용)")
df["has_hangul"] = text.str.contains(r"[가-힣]")
neg["has_hangul"] = neg["review_text"].fillna("").str.contains(r"[가-힣]")
print(f"한글 포함: 전체 {int(df['has_hangul'].sum())}/{len(df)}건, 부정 {int(neg['has_hangul'].sum())}/{len(neg)}건")
print("한글 없는 리뷰(키워드 매칭 불가 대상) — 본문 앞 60자:")
for _, r in df[~df["has_hangul"]].iterrows():
    tag = "부정" if not r["voted_up"] else "긍정"
    body = r["review_text"].replace("\r", " ").replace("\n", " ")[:60]
    print(f"  [{tag}] {body!r}")

print("\n" + "=" * 70)
print("[2] 키워드별 건수 (부정 리뷰 기준) 및 중복 제거")
print("=" * 70)
for k in KEYWORDS:
    neg[k] = neg["review_text"].fillna("").str.contains(k)
counts = {k: int(neg[k].sum()) for k in KEYWORDS}
n_neg = len(neg)
n_neg_ko = int(neg["has_hangul"].sum())
for k, c in sorted(counts.items(), key=lambda x: -x[1]):
    print(f"  {k:<6} {c}건  ({100*c/n_neg:.1f}% of 부정 {n_neg}건 / {100*c/n_neg_ko:.1f}% of 한글 부정 {n_neg_ko}건)")

neg["ux_hits"] = neg[UX_GROUP].sum(axis=1)
sum_dup = int(neg[UX_GROUP].sum().sum())
uniq = int((neg["ux_hits"] > 0).sum())
print(f"\n'못죽·답답·기절' 키워드 건수 단순 합산: {sum_dup}건 ({100*sum_dup/n_neg:.1f}%)  ← 중복 포함")
print(f"'못죽·답답·기절' 고유 리뷰 수           : {uniq}건 → {fmt_ci(uniq, n_neg)}")
print(f"  (한글 부정 {n_neg_ko}건 분모: {100*uniq/n_neg_ko:.1f}%)")
print(f"  2개 이상 키워드가 겹친 리뷰: {int((neg['ux_hits'] > 1).sum())}건 (그중 3개 모두 포함 {int((neg['ux_hits'] == 3).sum())}건)")
print(f"'못죽'만 따로: {fmt_ci(counts['못죽'], n_neg)}")
print(f"'최적화'(원문 대조 전): {fmt_ci(counts['최적화'], n_neg)}")

print("\n" + "=" * 70)
print("[3] 키워드셋 커버리지 — 부정 리뷰 중 키워드 1개 이상 포함")
print("=" * 70)
any_hit = neg[KEYWORDS].any(axis=1)
print(f"  {int(any_hit.sum())}/{n_neg}건 ({100*any_hit.mean():.1f}%) — 나머지 {n_neg-int(any_hit.sum())}건은 이 11개 키워드 밖의 불만/내용")
print("\n긍정 리뷰에서의 키워드 건수(참고: 키워드 자체가 부정 신호는 아님)")
print("  " + ", ".join(f"{k} {int(pos['review_text'].fillna('').str.contains(k).sum())}" for k in KEYWORDS))

print("\n" + "=" * 70)
print("[4] 표본 관계 — 1차(n=34)와 2차(n=150)")
print("=" * 70)
if CSV_FIRST:
    d1 = pd.read_csv(CSV_FIRST, encoding="utf-8-sig")
    overlap = len(set(d1["review_id"]) & set(df["review_id"]))
    print(f"1차 {len(d1)}건 중 2차에 포함된 review_id: {overlap}건 → "
          f"{'1차는 2차의 부분집합(독립 표본 아님)' if overlap == len(d1) else '일부만 겹침'}")
    print(f"1차 부정 {int((~d1['voted_up']).sum())}건 / 2차 부정 {len(neg)}건")
else:
    print("(1차 CSV 경로를 두 번째 인자로 넘기면 비교함)")
