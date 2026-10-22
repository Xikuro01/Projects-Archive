# -*- coding: utf-8 -*-
"""
make_figures.py — README용 그림 생성 (analyze_lol_baselines.py 의 함수를 재사용)
  lol_baseline_by_group.png : (좌) 그룹별 평균 적진 사망 비율 ± 95% 구간(전체 100경기) + 패치별 점
                              (우) 그룹별 최대 도달 가능 Z vs 임계값(2.0)
사용: python make_figures.py --dir lol_data
"""
import argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import analyze_lol_baselines as a

ap = argparse.ArgumentParser()
ap.add_argument("--dir", default=".")
args0 = ap.parse_args()
for path in ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",):
    try:
        fm.fontManager.addfont(path); plt.rcParams["font.family"] = "Noto Sans CJK JP"
    except Exception:
        plt.rcParams["font.family"] = "Malgun Gothic"   # 로컬(Windows)용
plt.rcParams["axes.unicode_minus"] = False

class A:  # load()가 쓰는 인자
    dir, group = args0.dir, "random"
    patch_prefix = None

def stats_for(prefix):
    A.patch_prefix = prefix
    d, ps = a.build_samples(a.load(A))
    b = a.baseline(ps)
    return b

b_all = stats_for(None); b19 = stats_for("16.19."); b20 = stats_for("16.20.")
order = list(b_all.sort_values("mean").index)
x = np.arange(len(order))
se = (b_all["std"] / np.sqrt(b_all["n"])).reindex(order)

fig, ax = plt.subplots(1, 2, figsize=(13, 4.8))
ax[0].errorbar(x, b_all["mean"].reindex(order), yerr=1.96 * se, fmt="o", color="#2c3e50", capsize=4,
               label="전체 100경기 (평균 ± 95% 구간)")
ax[0].scatter(x - 0.12, b19["mean"].reindex(order), marker="s", color="#2980b9", s=28, label="16.19만 (74경기)")
ax[0].scatter(x + 0.12, b20["mean"].reindex(order), marker="^", color="#e67e22", s=32, label="16.20만 (26경기)")
ax[0].set_xticks(x); ax[0].set_xticklabels(order, rotation=25, ha="right")
ax[0].set_ylabel("평균 적진 사망 비율"); ax[0].set_ylim(0.2, 0.62)
ax[0].set_title("그룹별 기준선 — 구간이 서로 크게 겹침"); ax[0].legend(fontsize=8, loc="upper left")

zs = b_all["max_z"].reindex(order)
ax[1].bar(x, zs, color=["#c0392b" if v > 2 else "#95a5a6" for v in zs])
ax[1].axhline(2.0, color="#c0392b", ls="--"); ax[1].text(len(x) - 0.5, 2.03, "Z 임계값 2.0", ha="right", color="#c0392b", fontsize=9)
ax[1].set_xticks(x); ax[1].set_xticklabels(order, rotation=25, ha="right")
ax[1].set_ylabel("최대 도달 가능 Z = (1 − 평균) / 표준편차"); ax[1].set_ylim(0, 2.5)
ax[1].set_title("Z>2 규칙: 임계값을 넘는 그룹은 1개뿐")
plt.tight_layout(); plt.savefig("lol_baseline_by_group.png", dpi=150)
print("saved lol_baseline_by_group.png")
