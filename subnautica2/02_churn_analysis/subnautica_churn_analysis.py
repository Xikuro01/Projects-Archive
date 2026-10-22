"""
서브노티카2: 적대생명체 조우 패턴이 유저 이탈에 미치는 영향 분석 (기초 버전)
==================================================================
[기존 접근과의 차이]
- 기존: "어그로 범위가 넓은 것 같으니 낮추자" (직관/기획자 감)
- 재설계: "레비아탄급 생명체 조우 후 이탈률이 통계적으로 유의하게
  높은가?"를 검증 가능한 가설로 바꿔서 확인

[방법론]
- 카이제곱 검정(Chi-square test): 두 개 이상의 범주형 그룹 간
  비율 차이가 우연에 의한 것인지, 통계적으로 유의한 차이인지 확인하는
  가장 기본적인 통계 검정. "조우 유형별로 이탈률이 다른가?"라는
  질문에 정확히 맞는 방법이라 선택함

[중요 - 데이터 관련 고지]
서브노티카2는 공개 API나 공개 로그가 없어, 실제 접근 가능한 데이터가
존재하지 않는 주제입니다. 아래 데이터는 전면 가상 시뮬레이션이며,
실측 데이터가 아니라 "이런 데이터가 있다면 어떤 방법론으로 검증할
것인가"를 보여주는 방법론 시연 목적임을 명확히 합니다.
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from scipy.stats import chi2_contingency

fm.fontManager.addfont("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
plt.rcParams["font.family"] = "Noto Sans CJK JP"
plt.rcParams["axes.unicode_minus"] = False

np.random.seed(42)


# =====================================================================
# 1. (임시) 가상 세션 로그 생성 — 실제 사용 시 실제 게임 로그로 교체
# =====================================================================
def generate_mock_session_data(n_players=3000):
    encounter_types = ["없음", "일반 생명체", "레비아탄급"]
    # 조우 유형별 '조우 직후 이탈' 확률 (가정치 — 방법론 시연용)
    churn_prob = {"없음": 0.05, "일반 생명체": 0.12, "레비아탄급": 0.28}

    rows = []
    for _ in range(n_players):
        encounter = np.random.choice(encounter_types, p=[0.5, 0.35, 0.15])
        churned = np.random.random() < churn_prob[encounter]
        rows.append({"encounter_type": encounter, "churned_after": churned})
    return pd.DataFrame(rows)


df = generate_mock_session_data()

# =====================================================================
# 2. 조우 유형별 이탈률 집계
# =====================================================================
summary = df.groupby("encounter_type")["churned_after"].agg(["mean", "count"]).reset_index()
summary.columns = ["조우 유형", "이탈률", "표본 수"]
summary = summary.sort_values("이탈률", ascending=False)

print("=" * 60)
print("[1] 조우 유형별 이탈률")
print("=" * 60)
print(summary.to_string(index=False))

# =====================================================================
# 3. 카이제곱 검정 — 이 차이가 통계적으로 유의한가?
# =====================================================================
contingency = pd.crosstab(df["encounter_type"], df["churned_after"])
chi2, p_value, dof, expected = chi2_contingency(contingency)

print("\n" + "=" * 60)
print("[2] 카이제곱 검정 결과")
print("=" * 60)
print(f"카이제곱 통계량: {chi2:.2f}")
print(f"p-value: {p_value:.6f}")
print(f"판정: {'통계적으로 유의한 차이 있음 (p < 0.05)' if p_value < 0.05 else '유의한 차이 없음'}")

# =====================================================================
# 4. 시각화
# =====================================================================
fig, ax = plt.subplots(figsize=(7, 5))
ax.bar(summary["조우 유형"], summary["이탈률"] * 100, color=["#95a5a6", "#f39c12", "#e74c3c"])
ax.set_ylabel("조우 직후 이탈률 (%)")
ax.set_title("적대생명체 조우 유형별 이탈률 비교")
plt.tight_layout()
plt.savefig("/home/claude/subnautica_churn_analysis.png", dpi=150)
print("\n[차트 저장 완료] subnautica_churn_analysis.png")

# =====================================================================
# 5. 결론
# =====================================================================
print("\n" + "=" * 60)
print("[결론]")
print("=" * 60)
print(f"""
- 레비아탄급 생명체 조우 후 이탈률이 다른 조우 유형 대비 뚜렷하게 높고,
  카이제곱 검정 결과 p-value {p_value:.4f}로 통계적으로 유의함
- 이는 "레비아탄급 조우가 유저 이탈과 관련 있다"는 가설을 뒷받침함
- 다만 이 데이터는 실제 로그가 아닌 가상 시뮬레이션이므로,
  실제 개발사 내부 로그(또는 커뮤니티 설문)로 재검증이 반드시 필요함
- 검증된다면, 단순 "어그로 범위 하향"보다 "조우 직후 생존 가능성을
  높이는 대응 아이템 제공"이 이탈 방지에 더 직접적인 처방일 수 있음
""")
