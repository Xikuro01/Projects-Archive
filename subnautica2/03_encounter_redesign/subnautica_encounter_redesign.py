"""
서브노티카2: 레비아탄 조우 방식(강제 vs 확률형)이 이탈에 미치는 영향 분석
==================================================================
[프로젝트 주도자 노트 — 가설은 본인이 직접 설계함, 기존 가설1·2를 통합]

[본인의 플레이 경험 + 커뮤니티 의견을 바탕으로 한 가설 배경]
전작(서브노티카1)은 레비아탄급 생명체의 출몰/행동 반경이 특정 구역에
국한되어 있다는 인상이 강해, 유저가 해당 구역을 피해 우회하면 조우를
회피할 수 있었음. 반면 서브노티카2 얼리엑세스는 외계 유적 시설로
가는 경로 특성상 레비아탄과의 조우가 사실상 "필수"에 가깝다는 게
본인의 플레이 경험 및 커뮤니티 반응(가상 설정)에서 공통적으로 나타남.

  통합 가설) 레비아탄 조우를 "경로상 반드시 발생하는 강제 이벤트"가
  아니라 "레비아탄 행동 구역에 가까워질수록 조우 확률이 높아지는
  확률형 구조"로 재설계하면, 유저의 이탈률(스트레스)이 완화될 것이다

※ 기존에는 '어그로 범위 증가(가설1)'와 '레비아탄 대처수단 부재(가설2)'를
  서로 독립된 별개 요인으로 다뤘으나, 이번엔 "행동 반경(어그로 범위)
  설계 방식이 곧 레비아탄 조우 확률을 결정한다"는 하나의 인과 구조로
  통합함 — 즉 가설1은 원인(구역 설계), 가설2는 그 결과(조우 시 대처
  불가로 인한 스트레스)로 재배치함

[AI 협업 노트]
가설의 배경(플레이 경험, 전작 대비 인상)과 두 설계안(강제형 vs
확률형)을 어떻게 비교할지는 본인이 직접 설계함. 거리-확률 함수와
시뮬레이션 코드 구현은 Claude(AI)의 도움을 받아 작성함.

[중요 - 데이터 관련 고지]
실제 로그/텔레메트리에 접근할 수 없어, 아래 데이터는 본인의 플레이
경험과 커뮤니티 반응을 참고한 가상 설정입니다. 실측 데이터가 아니라
"이 설계 변경이 유효한 가설인지"를 검증하는 방법론 시연 목적입니다.
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

fm.fontManager.addfont("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
plt.rcParams["font.family"] = "Noto Sans CJK JP"
plt.rcParams["axes.unicode_minus"] = False
np.random.seed(42)

N = 3000

# =====================================================================
# 1. 유저별 '레비아탄 구역과의 최근접 거리' 시뮬레이션
#    (본인 주도: 무엇을 시뮬레이션할지 설계)
# =====================================================================
# 외계 유적 시설로 향하는 유저들이 이동 경로상 레비아탄 행동 구역에
# 얼마나 가깝게 지나가는지를 0(구역 정중앙 통과)~100(충분히 먼 우회로)
# 사이의 거리 점수로 표현 (가정치)
closest_distance = np.random.uniform(0, 100, N)

# =====================================================================
# 2. 두 가지 설계안 비교 (본인 주도: 강제형 vs 확률형을 어떻게 정의할지)
# =====================================================================
# (A) 현재 얼리엑세스 방식 — 경로 특성상 거리와 무관하게 사실상 강제 조우
encounter_forced = np.full(N, True)

# (B) 제안 방식 — 구역에 가까울수록 조우 확률이 높아지는 확률형 구조
#     거리 40 이상이면 조우 확률 0, 0에 가까울수록 확률 1로 선형 증가 (가정 함수)
ENCOUNTER_DECAY_RANGE = 40
encounter_prob_scaled = np.clip(1 - closest_distance / ENCOUNTER_DECAY_RANGE, 0, 1)
encounter_scaled = np.random.random(N) < encounter_prob_scaled

# =====================================================================
# 3. 조우 여부에 따른 이탈(스트레스) 확률 계산 — 두 설계에 동일 기준 적용
# =====================================================================
BASE_CHURN = 0.05                 # 조우 없을 때 기본 이탈률 (가정)
ENCOUNTER_CHURN_BOOST = 0.25      # 레비아탄 조우 시 추가되는 이탈률 (대처수단 부재 반영, 가정)

churn_prob_forced = BASE_CHURN + encounter_forced * ENCOUNTER_CHURN_BOOST
churn_prob_scaled = BASE_CHURN + encounter_scaled * ENCOUNTER_CHURN_BOOST

churned_forced = np.random.random(N) < churn_prob_forced
churned_scaled = np.random.random(N) < churn_prob_scaled

# =====================================================================
# 4. 결과 비교
# =====================================================================
result_df = pd.DataFrame({
    "설계 방식": ["현재(강제 조우)", "제안(구역 근접도 기반 확률형)"],
    "레비아탄 조우율": [encounter_forced.mean(), encounter_scaled.mean()],
    "이탈률": [churned_forced.mean(), churned_scaled.mean()],
})
print("=" * 70)
print("[설계 방식별 조우율 및 이탈률 비교]")
print("=" * 70)
print(result_df.round(3).to_string(index=False))

reduction = churned_forced.mean() - churned_scaled.mean()
print(f"\n이탈률 감소분: {reduction*100:.1f}%p")

# =====================================================================
# 5. 시각화 — (a)거리별 조우확률 함수 (b)설계별 이탈률 비교
# =====================================================================
fig, axes = plt.subplots(1, 2, figsize=(12, 5))

dist_range = np.linspace(0, 100, 200)
prob_curve = np.clip(1 - dist_range / ENCOUNTER_DECAY_RANGE, 0, 1)
axes[0].plot(dist_range, prob_curve, color="#8e44ad", label="제안(확률형)")
axes[0].axhline(1.0, color="#e74c3c", linestyle="--", label="현재(강제, 거리 무관 100%)")
axes[0].set_xlabel("레비아탄 행동 구역과의 거리")
axes[0].set_ylabel("조우 확률")
axes[0].set_title("거리에 따른 조우 확률 설계 비교")
axes[0].legend()

axes[1].bar(result_df["설계 방식"], result_df["이탈률"] * 100, color=["#e74c3c", "#2ecc71"])
axes[1].set_ylabel("이탈률 (%)")
axes[1].set_title("설계 방식별 이탈률 비교")
plt.setp(axes[1].get_xticklabels(), rotation=8, ha="right")

plt.tight_layout()
plt.savefig("/home/claude/subnautica_encounter_redesign.png", dpi=150)
print("\n[차트 저장 완료] subnautica_encounter_redesign.png")

# =====================================================================
# 6. 결론
# =====================================================================
print("\n" + "=" * 70)
print("[결론]")
print("=" * 70)
print(f"""
- 레비아탄 조우 방식을 "강제"에서 "구역 근접도 기반 확률형"으로
  바꾸면, 전체 조우율이 {encounter_forced.mean():.0%} → {encounter_scaled.mean():.0%}로 낮아지고
  이에 따라 이탈률도 {reduction*100:.1f}%p 완화될 것으로 추정됨
- 이는 어그로 범위/행동 구역 설계(기존 가설1)와 레비아탄 대처수단
  부재(기존 가설2)를 독립 요인이 아니라 "구역 설계가 조우 확률을
  결정하고, 조우가 곧 대처수단 부재로 인한 스트레스로 이어진다"는
  하나의 인과 구조로 재구성한 결과임
- 본인의 플레이 경험상 전작은 레비아탄 구역이 명확히 구획되어
  회피가 가능했다는 인상이 있었고, 이번 얼리엑세스는 경로 특성상
  회피가 어렵다는 커뮤니티 반응(가상 설정)을 반영해 설계함
- 한계: 실제 로그/텔레메트리에 접근할 수 없어 위 수치는 가상
  설정이며, 실제로는 유적 시설 경로의 지형 데이터와 실측 조우
  로그를 통해 재검증이 필요함
""")
