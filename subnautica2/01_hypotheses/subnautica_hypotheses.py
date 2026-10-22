"""
서브노티카2 얼리엑세스 이탈 구간 가설 검증 (간결 버전)
==================================================================
[프로젝트 주도자 노트 — 가설은 본인이 직접 설계함]
얼리엑세스 진행 중 커뮤니티 반응과 직접 플레이 경험을 바탕으로,
이탈이 발생할 수 있는 지점을 아래 3가지 가설로 세움:

  가설1) 전작 대비 적대생명체의 추적 범위와 어그로 유지 거리가
         늘어나, 조우 빈도가 늘어난 유저일수록 이탈 확률이 높다
  가설2) 레비아탄급 생명체를 확실히 상대할 대처 수단이 없어,
         레비아탄급을 조우한 유저는 그 직후 이탈 확률이 높다
  가설3) 특정 심해 구간에서 하드웨어 사양이 못 받쳐줘 튕김(크래시)이
         발생하고, 이를 겪은 유저는 이탈 확률이 높다

[AI 협업 노트]
위 3개 가설과 어떤 지표로 검증할지에 대한 설계는 본인이 직접 함.
이를 검증하는 통계 코드와 시각화 구현은 Claude(AI)의 도움을 받아
작성함. 실제 텔레메트리 데이터가 없는 현재 단계이므로, 아래 수치는
가설 검증 "방법론"을 시연하기 위한 가정치이며 실측 데이터가 아님.
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

fm.fontManager.addfont("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
plt.rcParams["font.family"] = "Noto Sans CJK JP"
plt.rcParams["axes.unicode_minus"] = False
np.random.seed(42)


# =====================================================================
# 1. (임시) 가상 유저 로그 생성 — 실제 사용 시 텔레메트리 로그로 교체
#    (AI 협업 구간: 데이터 구조 설계 및 코드 구현)
# =====================================================================
def generate_mock_player_log(n=3000):
    df = pd.DataFrame({
        # 가설1 관련 변수: 늘어난 어그로 범위/거리로 잦은 조우를 겪었는지
        "high_aggro_encounter": np.random.choice([True, False], n, p=[0.4, 0.6]),
        # 가설2 관련 변수: 대처 수단 없이 레비아탄급을 조우했는지
        "leviathan_no_counter": np.random.choice([True, False], n, p=[0.15, 0.85]),
        # 가설3 관련 변수: 특정 심해 구간에서 하드웨어 병목(튕김)을 겪었는지
        "deep_zone_crash": np.random.choice([True, False], n, p=[0.1, 0.9]),
    })
    # 각 요인이 이탈 확률에 더해지는 영향력(가정치) — 세 요인은 독립적으로 작용한다고 가정
    base_churn = 0.05
    churn_prob = (
        base_churn
        + df["high_aggro_encounter"] * 0.10
        + df["leviathan_no_counter"] * 0.20
        + df["deep_zone_crash"] * 0.25
    ).clip(upper=0.95)
    df["churned"] = np.random.random(n) < churn_prob
    return df


df = generate_mock_player_log()

# =====================================================================
# 2. 가설별 이탈률 비교 (요인 있음 vs 없음)
#    (본인 주도 구간: 어떤 두 그룹을 비교해야 가설이 검증되는지 설계)
# =====================================================================
hypotheses = {
    "가설1: 어그로 범위 증가": "high_aggro_encounter",
    "가설2: 레비아탄 대처수단 부재": "leviathan_no_counter",
    "가설3: 심해구간 하드웨어 병목": "deep_zone_crash",
}

results = []
for label, col in hypotheses.items():
    with_factor = df[df[col]]["churned"].mean()
    without_factor = df[~df[col]]["churned"].mean()
    results.append({
        "가설": label,
        "요인 있음 이탈률": with_factor,
        "요인 없음 이탈률": without_factor,
        "차이(%p)": (with_factor - without_factor) * 100,
    })

result_df = pd.DataFrame(results)
print("=" * 70)
print("[가설별 이탈률 비교]")
print("=" * 70)
print(result_df.round(3).to_string(index=False))

# =====================================================================
# 3. 시각화
# =====================================================================
fig, ax = plt.subplots(figsize=(9, 5))
x = np.arange(len(result_df))
width = 0.35
ax.bar(x - width / 2, result_df["요인 있음 이탈률"] * 100, width, label="요인 있음", color="#e74c3c")
ax.bar(x + width / 2, result_df["요인 없음 이탈률"] * 100, width, label="요인 없음", color="#3498db")
ax.set_xticks(x)
ax.set_xticklabels(result_df["가설"], rotation=10, ha="right")
ax.set_ylabel("이탈률 (%)")
ax.set_title("가설별 이탈률 비교 (요인 있음 vs 없음)")
ax.legend()
plt.tight_layout()
plt.savefig("/home/claude/subnautica_hypotheses.png", dpi=150)
print("\n[차트 저장 완료] subnautica_hypotheses.png")

# =====================================================================
# 4. 결론
# =====================================================================
biggest = result_df.loc[result_df["차이(%p)"].idxmax()]
print("\n" + "=" * 70)
print("[결론]")
print("=" * 70)
print(f"""
- 3개 가설 중 '{biggest['가설']}'의 이탈률 차이가 가장 커,
  가장 우선적으로 검증/대응이 필요한 요인으로 추정됨
- 세 가설 모두 본인이 얼리엑세스 커뮤니티 반응 및 직접 플레이
  경험을 바탕으로 설정했으며, 위 수치는 이를 검증하는 방법론을
  보여주기 위한 가정치임
- 한계: 위 비교는 상관관계이며 인과관계를 증명하지 않음
  (예: 원래 게임 인내심이 낮은 유저가 세 요인을 모두 자주 겪을
  가능성 등 교란변수가 있을 수 있음)
- 실제 텔레메트리 로그 확보 시, generate_mock_player_log() 함수만
  실제 로그 로딩 함수로 교체하면 이후 분석 로직은 그대로 재사용 가능
""")
