#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyze_lol_baselines.py — 포지션·라인전 단계별 '적진 사망' 기준선 분석 (B1 / B2 / B3)
=====================================================================================
입력 : death_events.csv, matches.csv  (collect_lol_deaths.py 산출물)
방법 : 기존 lol_troll_detection_real.sql 과 동일한 정의를 따름
        - 적진 사망 = 사망 지점이 자기 베이스보다 적 베이스에 더 가까움
        - 그룹 = 포지션 (+ 탑/미드는 15분 기준 라인전/라인전이후)
        - 분석 단위 = (match_id, player_id, group), 값 = 적진 사망 비율
        - 기준선 = 그룹별 평균/표준편차(모표준편차, SQL과 동일)

분석 항목
  B1  그룹별 '최대 도달 가능 Z'  = (1 - 평균) / 표준편차  → Z>2 규칙이 구조적으로 가능한가
  B2  플래그 방식 비교 (고정 70% / 전체 통합 기준선 Z / 그룹 기준선 Z), 그룹별 플래그 분포,
      임계값 민감도
  B3  Kruskal-Wallis(전체·신뢰표본), 가설별 Mann-Whitney U(+Holm 보정),
      라인전 전/후 대응표본 검정(Wilcoxon), 패치 민감도
  B4  건수를 반영한 이항 검정(포지션 반영 vs 무시)과 과산포 검사
  --by-patch  패치별 그룹 평균과 패치 간 순위 상관(일관성 확인)

사용 예
  python analyze_lol_baselines.py                       # random 표본 전체
  python analyze_lol_baselines.py --patch-prefix 16.19. # 특정 패치만
  python analyze_lol_baselines.py --group seed          # 본인 경기(본인 행 제외)
  python analyze_lol_baselines.py --by-patch            # 패치별 기준선 일관성
"""
import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

BLUE = (1962.0, 2038.0)     # 블루 베이스 근사 좌표 (기존 SQL과 동일)
RED = (12831.0, 12848.0)    # 레드 베이스 근사 좌표
LANE_CUT = 900              # 라인전 구분 시점(초)
MIN_DEATHS = 4              # '신뢰 표본' 기준 (기존과 동일)
ABS_THRESHOLD = 0.70        # 고정 기준 예시값 (기존 5절과 동일)
Z_THRESHOLD = 2.0

ORDER = ["BOTTOM", "TOP-라인전", "UTILITY", "JUNGLE", "MIDDLE-라인전",
         "TOP-라인전이후", "MIDDLE-라인전이후"]


def load(args):
    d = pd.read_csv(Path(args.dir) / "death_events.csv", encoding="utf-8-sig")
    m = pd.read_csv(Path(args.dir) / "matches.csv", encoding="utf-8-sig")
    d = d[d.sample_group == args.group]
    if args.group == "seed":
        d = d[d.is_seed == 0]                      # 본인 행 제외
    if args.patch_prefix:
        keep = set(m[m.game_version.astype(str).str.startswith(args.patch_prefix)].match_id)
        d = d[d.match_id.isin(keep)]
    # 사망 이벤트 10건 미만 경기 제외 (기존 valid_matches 규칙)
    ok = d.groupby("match_id").size()
    d = d[d.match_id.isin(ok[ok >= 10].index)]
    return d.copy()


def build_samples(d):
    blue = d.team_id == 100
    own = np.where(blue.values[:, None], np.array(BLUE), np.array(RED))
    enemy = np.where(blue.values[:, None], np.array(RED), np.array(BLUE))
    xy = d[["death_x", "death_y"]].to_numpy(dtype=float)
    d = d.assign(
        enemy_death=(np.linalg.norm(xy - enemy, axis=1) < np.linalg.norm(xy - own, axis=1)).astype(int))
    lane = np.where(d.game_time < LANE_CUT, "-라인전", "-라인전이후")
    d["group"] = np.where(d.position.isin(["TOP", "MIDDLE"]), d.position + lane, d.position)
    ps = (d.groupby(["match_id", "player_id", "group"])
            .agg(rate=("enemy_death", "mean"), n_deaths=("enemy_death", "size"),
                 k_enemy=("enemy_death", "sum"))
            .reset_index())
    return d, ps


def baseline(ps):
    g = ps.groupby("group")["rate"]
    b = pd.DataFrame({"n": g.size(), "mean": g.mean(),
                      "std": np.sqrt((ps.assign(r2=ps.rate ** 2).groupby("group").r2.mean()) - g.mean() ** 2)})
    b["max_z"] = (1 - b["mean"]) / b["std"].replace(0, 0.01)
    b["can_flag_z>2"] = np.where(b.max_z > Z_THRESHOLD, "가능(100%일 때만)", "불가능")
    return b.reindex([x for x in ORDER if x in b.index])


def zscores(ps, b):
    std = b["std"].replace(0, 0.01)
    ps = ps.assign(z_group=(ps.rate - ps.group.map(b["mean"])) / ps.group.map(std))
    pm, pstd = ps.rate.mean(), math.sqrt(max((ps.rate ** 2).mean() - ps.rate.mean() ** 2, 1e-12))
    ps["z_pooled"] = (ps.rate - pm) / pstd
    return ps, pm, pstd


def holm(pvals):
    order = np.argsort(pvals)
    m, adj, running = len(pvals), np.empty(len(pvals)), 0.0
    for rank, idx in enumerate(order):
        running = max(running, (m - rank) * pvals[idx])
        adj[idx] = min(1.0, running)
    return adj


def section(title):
    print("\n" + "=" * 78 + f"\n{title}\n" + "=" * 78)


def by_patch(args):
    m = pd.read_csv(Path(args.dir) / "matches.csv", encoding="utf-8-sig")
    m = m[m.sample_group == args.group]
    m["patch"] = m.game_version.astype(str).str.rsplit(".", n=2).str[0]
    tables = {}
    for patch, sub in m.groupby("patch"):
        class A:  # load()가 쓰는 인자만 흉내
            dir, group, patch_prefix = args.dir, args.group, patch + "."
        d, ps = build_samples(load(A))
        b = baseline(ps)
        tables[patch] = b["mean"]
        print(f"[패치 {patch}] 경기 {d.match_id.nunique()}개 / 사망 {len(d)}건 / 분석 표본 {len(ps)}개")
    out = pd.DataFrame(tables).reindex(ORDER)
    section("[패치별 그룹 평균 적진 사망 비율]")
    print(out.round(3).to_string())
    if out.shape[1] >= 2:
        cols = list(out.columns)
        for i in range(len(cols)):
            for j in range(i + 1, len(cols)):
                rho, p = stats.spearmanr(out[cols[i]], out[cols[j]])
                print(f"\n순위 상관(Spearman) {cols[i]} vs {cols[j]}: rho={rho:.2f} (그룹 7개 기준, p={p:.3f})")
        print("→ 표본이 작은 패치(경기 수 적음)에서는 평균 자체가 크게 흔들리므로 참고용")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=".", help="death_events.csv / matches.csv 가 있는 폴더")
    ap.add_argument("--group", default="random", choices=["random", "seed"])
    ap.add_argument("--patch-prefix", default=None)
    ap.add_argument("--by-patch", action="store_true", help="패치별 그룹 평균과 순위 상관 출력 후 종료")
    args = ap.parse_args()
    pd.set_option("display.width", 160)
    if args.by_patch:
        by_patch(args)
        return

    d, ps = build_samples(load(args))
    b = baseline(ps)
    ps, pm, pstd = zscores(ps, b)
    rel = ps[ps.n_deaths >= MIN_DEATHS]

    section(f"[0] 데이터 요약 (group={args.group}, patch={args.patch_prefix or '전체'})")
    print(f"경기 {d.match_id.nunique()}개 / 사망 이벤트 {len(d)}건 / 분석 표본(경기·선수·그룹) {len(ps)}개 "
          f"/ 신뢰 표본(데스 {MIN_DEATHS}건 이상) {len(rel)}개")
    print(f"전체 적진 사망 비율(이벤트 기준): {d.enemy_death.mean():.3f}")

    section("[1] 그룹별 기준선 + B1: 최대 도달 가능 Z")
    print(b.round(3).to_string())
    print(f"\n전체 통합 기준선: 평균 {pm:.3f}, 표준편차 {pstd:.3f}, 최대 Z {(1 - pm) / pstd:.2f}")
    print("→ '최대 Z'가 2 이하인 그룹은 Z>2 규칙으로 어떤 값이 나와도 플래그될 수 없음")

    section("[2] B2: 플래그 방식 비교 (신뢰 표본 기준)")
    methods = {
        f"고정 기준 (적진 사망 {ABS_THRESHOLD:.0%} 이상)": rel.rate >= ABS_THRESHOLD,
        "전체 통합 기준선 Z>2": rel.z_pooled > Z_THRESHOLD,
        "그룹 기준선 Z>2": rel.z_group > Z_THRESHOLD,
    }
    out = pd.DataFrame({k: v.groupby(rel.group).sum() for k, v in methods.items()}).reindex(
        [x for x in ORDER if x in rel.group.unique()]).fillna(0).astype(int)
    out.loc["합계"] = out.sum()
    out.insert(0, "신뢰표본수", rel.groupby("group").size().reindex(out.index[:-1]).tolist() + [len(rel)])
    print(out.to_string())
    fixed = methods[f"고정 기준 (적진 사망 {ABS_THRESHOLD:.0%} 이상)"]
    nf = int(fixed.sum())
    if nf:
        print(f"\n고정 기준 플래그 {nf}건 중 그룹 Z≤2: {int((rel[fixed].z_group <= 2).sum())}건, "
              f"통합 Z≤2: {int((rel[fixed].z_pooled <= 2).sum())}건")
        print("→ 위 두 수치는 '최대 Z' 때문에 그룹별로 구조적으로 정해지는 부분이 큼 (B1 표 참고)")
    flagged = rel[methods["그룹 기준선 Z>2"] | methods["전체 통합 기준선 Z>2"]]
    if len(flagged):
        print("\n[Z 방식으로 플래그된 표본 상세]")
        print(flagged[["match_id", "player_id", "group", "n_deaths", "k_enemy", "rate", "z_group", "z_pooled"]]
              .round(2).to_string(index=False))

    print("\n[임계값 민감도 — 신뢰 표본 중 플래그 건수]")
    rows = []
    for z in (1.0, 1.5, 1.8, 2.0):
        rows.append({"Z 임계값": z, "그룹 기준선": int((rel.z_group > z).sum()),
                     "통합 기준선": int((rel.z_pooled > z).sum())})
    print(pd.DataFrame(rows).to_string(index=False))
    print("\n[고정 비율 민감도 — 신뢰 표본 중 플래그 건수]")
    print(pd.DataFrame([{"적진 사망 비율 ≥": t, "플래그": int((rel.rate >= t).sum())}
                        for t in (0.5, 0.6, 0.7, 0.8, 1.0)]).to_string(index=False))

    section("[3] B3: 통계 검정")
    for label, data in (("전체 표본", ps), (f"신뢰 표본(데스 {MIN_DEATHS}건 이상)", rel)):
        groups = [g.rate.values for _, g in data.groupby("group")]
        h, p = stats.kruskal(*groups)
        print(f"Kruskal-Wallis [{label}, n={len(data)}]: H={h:.3f}, p={p:.4f}")

    print("\n가설별 개별 검정 (Mann-Whitney U, 단측) — 앞 4개는 기존 README 가설, 뒤 2개는 2절 가설 중 미검정이던 항목")
    tests = [("BOTTOM", "TOP-라인전이후", "less", "BOTTOM < TOP-라인전이후"),
             ("BOTTOM", "MIDDLE-라인전이후", "less", "BOTTOM < MIDDLE-라인전이후"),
             ("TOP-라인전", "TOP-라인전이후", "less", "TOP 라인전 < 라인전이후 (독립 가정 — 참고용)"),
             ("MIDDLE-라인전", "MIDDLE-라인전이후", "less", "MIDDLE 라인전 < 라인전이후 (독립 가정 — 참고용)"),
             ("JUNGLE", "BOTTOM", "greater", "JUNGLE > BOTTOM"),
             ("UTILITY", "BOTTOM", "greater", "UTILITY > BOTTOM")]
    res = []
    for a, c, alt, desc in tests:
        ga, gc = ps[ps.group == a].rate, ps[ps.group == c].rate
        u, p = stats.mannwhitneyu(ga, gc, alternative=alt)
        res.append({"가설": desc, "n_a": len(ga), "n_c": len(gc),
                    "평균_a": round(ga.mean(), 3), "평균_c": round(gc.mean(), 3), "p": p})
    r = pd.DataFrame(res)
    r["Holm 보정 p(6개)"] = holm(r.p.values)
    r["p"] = r.p.round(4)
    r["Holm 보정 p(6개)"] = r["Holm 보정 p(6개)"].round(4)
    print(r.to_string(index=False))

    print("\n라인전 전/후 대응표본 검정 (같은 경기·선수가 두 단계 모두 사망 기록이 있는 경우, Wilcoxon 단측)")
    for pos in ("TOP", "MIDDLE"):
        a = ps[ps.group == f"{pos}-라인전"].set_index(["match_id", "player_id"]).rate
        c = ps[ps.group == f"{pos}-라인전이후"].set_index(["match_id", "player_id"]).rate
        both = a.index.intersection(c.index)
        if len(both) < 6:
            print(f"- {pos}: 짝 {len(both)}쌍 — 검정하기엔 부족")
            continue
        diff = a.loc[both].values - c.loc[both].values
        if np.allclose(diff, 0):
            print(f"- {pos}: 짝 {len(both)}쌍, 차이 전부 0")
            continue
        w, p = stats.wilcoxon(a.loc[both].values, c.loc[both].values, alternative="less")
        print(f"- {pos}: 짝 {len(both)}쌍, 라인전 평균 {a.loc[both].mean():.3f} vs 이후 평균 {c.loc[both].mean():.3f}, p={p:.4f}")

    section("[4] B4: 건수를 반영한 이항 검정(단측)과 과산포 검사 — 신뢰 표본 기준")
    grp_p = ps.groupby("group").k_enemy.sum() / ps.groupby("group").n_deaths.sum()
    pool_p = ps.k_enemy.sum() / ps.n_deaths.sum()
    r4 = rel.copy()
    r4["p_group"] = r4.group.map(grp_p)
    r4["pv_group"] = stats.binom.sf(r4.k_enemy - 1, r4.n_deaths, r4.p_group)
    r4["pv_pool"] = stats.binom.sf(r4.k_enemy - 1, r4.n_deaths, pool_p)
    print("그룹별 이벤트 기준 적진 사망 확률:", grp_p.reindex(ORDER).round(3).to_dict(), "| 전체:", round(pool_p, 3))
    rows4 = []
    for alpha in (0.05, 0.01):
        g, p = set(r4[r4.pv_group < alpha].index), set(r4[r4.pv_pool < alpha].index)
        rows4.append({"alpha": alpha, "우연 기대 건수": round(alpha * len(r4), 1),
                      "그룹 확률 기준 플래그": len(g), "통합 확률 기준 플래그": len(p),
                      "그룹만": len(g - p), "통합만": len(p - g), "공통": len(g & p)})
    print(pd.DataFrame(rows4).to_string(index=False))
    exp = r4.n_deaths * r4.p_group
    chi = ((r4.k_enemy - exp) ** 2 / (r4.n_deaths * r4.p_group * (1 - r4.p_group))).sum()
    dof = len(r4) - r4.group.nunique()
    print(f"\n과산포 검사: Pearson chi2={chi:.1f}, 자유도≈{dof}, 분산비={chi / dof:.2f}, p={stats.chi2.sf(chi, dof):.4g}")
    print("※ 이항 검정은 같은 선수의 사망을 서로 독립으로 가정함(같은 교전의 사망은 독립이 아님) → 참고용")


if __name__ == "__main__":
    main()
