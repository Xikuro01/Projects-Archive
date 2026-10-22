# -*- coding: utf-8 -*-
"""
explore_context_effects.py — 사후 탐색 분석: '그룹(포지션·라인전)' 말고 무엇이 적진 사망 비율을 움직이는가
=======================================================================================================
※ 모든 결과는 '결과를 본 뒤 추가한 탐색적 분석'임. p값보다 효과 크기와 경기 단위 부트스트랩 구간을 본다.
  [1] 경기 시간대별 적진 사망 비율 + 라인전 경계(15분) 민감도
  [2] 분산을 설명하는 단위 비교: 그룹(포지션·라인전) vs 경기 vs 팀 vs 선수-경기 (ICC)
  [3] 경기 맥락: 경기 길이와의 관계, 진영(블루/레드) 비대칭, 팀 간 상관
  [4] (참고·한계 있음) 기준 확률별 분산비 — 추정 확률의 잡음이 분산비를 부풀려 공정한 비교가 아님
  [5] 고립 사망 vs 팀 동반 사망: 같은 팀 다른 선수가 ±W초 안에 함께 죽었는가
사용: python explore_context_effects.py --dir lol_data [--patch-prefix 16.19.]
"""
import argparse
import numpy as np
import pandas as pd
from scipy import stats
import analyze_lol_baselines as a

ap = argparse.ArgumentParser()
ap.add_argument("--dir", default=".")
ap.add_argument("--patch-prefix", default=None)
ap.add_argument("--boot", type=int, default=2000)
args = ap.parse_args()
pd.set_option("display.width", 170)
rng = np.random.default_rng(42)

class A:
    dir, group, patch_prefix = args.dir, "random", args.patch_prefix

d, ps = a.build_samples(a.load(A))
m = pd.read_csv(f"{args.dir}/matches.csv", encoding="utf-8-sig")
m = m[m.sample_group == "random"].set_index("match_id")
d["y"] = d.enemy_death
mids = d.match_id.unique()
print(f"경기 {len(mids)}개 / 사망 {len(d)}건 / 전체 적진 사망 비율 {d.y.mean():.3f}")


def wilson(k, n, z=1.96):
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return c - h, c + h


def boot_diff(df, mask_a, mask_b, B):
    """경기 단위 부트스트랩: 비율(b) - 비율(a) 의 95% 구간"""
    g = df.assign(a=mask_a.astype(int), b=mask_b.astype(int))
    g["ya"] = g.y * g.a; g["yb"] = g.y * g.b
    t = g.groupby("match_id")[["a", "b", "ya", "yb"]].sum()
    arr = t.to_numpy(float)
    est = arr[:, 3].sum() / arr[:, 1].sum() - arr[:, 2].sum() / arr[:, 0].sum()
    out = []
    for _ in range(B):
        s = arr[rng.integers(0, len(arr), len(arr))].sum(0)
        out.append(s[3] / s[1] - s[2] / s[0])
    return est, np.percentile(out, [2.5, 97.5])


# ----------------------------------------------------------------------
print("\n" + "=" * 78 + "\n[1] 경기 시간대별 적진 사망 비율\n" + "=" * 78)
edges = [0, 300, 600, 900, 1200, 1500, 1800, 10 ** 6]
labels = ["0-5분", "5-10분", "10-15분", "15-20분", "20-25분", "25-30분", "30분+"]
d["bin"] = pd.cut(d.game_time, edges, labels=labels, right=False)
t = d.groupby("bin", observed=True).y.agg(["sum", "count"])
t["rate"] = t["sum"] / t["count"]
ci = [wilson(k, n) for k, n in zip(t["sum"], t["count"])]
t["95%구간"] = [f"{lo:.3f}~{hi:.3f}" for lo, hi in ci]
print(t[["count", "rate", "95%구간"]].round(3).to_string())
rho, p = stats.spearmanr(d.game_time, d.y)
print(f"\n사망 시각과 적진 사망(0/1)의 Spearman ρ={rho:.3f} (이벤트 {len(d)}건, 참고용: 같은 경기 사망끼리 독립이 아님)")

d["pos3"] = d.position.map({"TOP": "TOP/MID", "MIDDLE": "TOP/MID", "JUNGLE": "JUNGLE", "BOTTOM": "BOT/SUP", "UTILITY": "BOT/SUP"})
d["tb"] = pd.cut(d.game_time, [0, 600, 1200, 10 ** 6], labels=["<10분", "10-20분", "20분+"], right=False)
x = d.pivot_table(index="pos3", columns="tb", values="y", aggfunc=["mean", "count"], observed=True)
print("\n[포지션 묶음 × 시간대] 적진 사망 비율 / 사망 건수")
print(x.round(3).to_string())

print("\n[라인전 경계 민감도] TOP+MIDDLE 이벤트 기준 (이후 − 이전) 비율 차이, 경기 단위 부트스트랩 95% 구간")
tm = d[d.position.isin(["TOP", "MIDDLE"])]
rows = []
for cut in (600, 720, 900, 1080, 1200):
    est, (lo, hi) = boot_diff(tm, tm.game_time < cut, tm.game_time >= cut, args.boot)
    rows.append({"경계(초)": cut, "이전 비율": round(tm[tm.game_time < cut].y.mean(), 3),
                 "이후 비율": round(tm[tm.game_time >= cut].y.mean(), 3),
                 "차이": round(est, 3), "95% 구간": f"{lo:+.3f} ~ {hi:+.3f}"})
print(pd.DataFrame(rows).to_string(index=False))

# ----------------------------------------------------------------------
print("\n" + "=" * 78 + "\n[2] 분산을 설명하는 단위 비교 (ICC: 같은 묶음 안의 사망끼리 얼마나 닮았는가)\n" + "=" * 78)

def icc_from_counts(n, k):
    n, k = np.asarray(n, float), np.asarray(k, float)
    N, m_ = n.sum(), len(n)
    pbar = k.sum() / N
    ssb = (n * (k / n - pbar) ** 2).sum()
    ssw = (k - k ** 2 / n).sum()
    msb, msw = ssb / (m_ - 1), ssw / (N - m_)
    k0 = (N - (n ** 2).sum() / N) / (m_ - 1)
    return (msb - msw) / (msb + (k0 - 1) * msw)

d["team_key"] = d.match_id + "_" + d.team_id.astype(str)
d["pm_key"] = d.match_id + "_" + d.player_id.astype(str)
res = []
for name, key in (("그룹(포지션·라인전, 7개)", "group"), ("경기(match)", "match_id"),
                  ("팀-경기", "team_key"), ("선수-경기", "pm_key")):
    c = d.groupby(key).y.agg(["count", "sum"])
    est = icc_from_counts(c["count"], c["sum"])
    boots = []
    if key != "group":
        mids_arr = np.array(sorted(mids))
        by_match = {mid: g.groupby(key).y.agg(["count", "sum"]).to_numpy(float) for mid, g in d.groupby("match_id")}
        for _ in range(min(args.boot, 500)):
            pick = mids_arr[rng.integers(0, len(mids_arr), len(mids_arr))]
            arr = np.vstack([by_match[mid] for mid in pick])
            boots.append(icc_from_counts(arr[:, 0], arr[:, 1]))
        lo, hi = np.percentile(boots, [2.5, 97.5])
        res.append({"묶음 단위": name, "묶음 수": len(c), "ICC": round(est, 3), "95% 구간(경기 부트스트랩)": f"{lo:.3f} ~ {hi:.3f}"})
    else:
        res.append({"묶음 단위": name, "묶음 수": len(c), "ICC": round(est, 3), "95% 구간(경기 부트스트랩)": "-"})
print(pd.DataFrame(res).to_string(index=False))
print("→ ICC가 클수록 그 단위로 묶인 사망들이 서로 닮음(그 단위가 변동을 더 많이 설명). 선수-경기 ICC는 같은 선수의 사망이 묶이는 효과를 포함.")

# ----------------------------------------------------------------------
print("\n" + "=" * 78 + "\n[3] 경기 맥락\n" + "=" * 78)
pm = d.groupby("match_id").y.agg(["mean", "count"]).join(m[["game_duration_s"]])
rho, p = stats.spearmanr(pm.game_duration_s, pm["mean"])
rho2, p2 = stats.spearmanr(pm.game_duration_s, pm["count"])
print(f"경기 길이 vs 경기 평균 적진 사망 비율: Spearman ρ={rho:.2f} (p={p:.3g}, 경기 {len(pm)}개)")
print(f"경기 길이 vs 경기 내 사망 건수: Spearman ρ={rho2:.2f} (p={p2:.3g})")
q = pm.assign(구간=pd.qcut(pm.game_duration_s, 3, labels=["짧은 경기", "중간", "긴 경기"]))
print(q.groupby("구간", observed=True).agg(경기수=("mean", "size"), 평균길이_분=("game_duration_s", lambda s: round(s.mean() / 60, 1)),
                                           적진사망비율=("mean", "mean")).round(3).to_string())

side = d.groupby("team_id").y.agg(["mean", "count"])
est, (lo, hi) = boot_diff(d, d.team_id == 100, d.team_id == 200, args.boot)
print(f"\n진영별 적진 사망 비율: 블루 {side.loc[100,'mean']:.3f} / 레드 {side.loc[200,'mean']:.3f}  (레드−블루 {est:+.3f}, 95% 구간 {lo:+.3f}~{hi:+.3f})")

# 팀 간/팀 내 상관
pmk = d.groupby(["match_id", "team_id", "player_id"]).y.agg(["sum", "count"]).reset_index()
tk = pmk.groupby(["match_id", "team_id"])[["sum", "count"]].sum().rename(columns={"sum": "K", "count": "N"}).reset_index()
pmk = pmk.merge(tk, on=["match_id", "team_id"])
opp = tk.copy(); opp["team_id"] = np.where(opp.team_id == 100, 200, 100)
opp = opp.rename(columns={"K": "K_opp", "N": "N_opp"})
pmk = pmk.merge(opp, on=["match_id", "team_id"])
pmk["rate"] = pmk["sum"] / pmk["count"]
pmk["mate"] = (pmk.K - pmk["sum"]) / (pmk.N - pmk["count"])
pmk["opp"] = pmk.K_opp / pmk.N_opp
sub = pmk[pmk["count"] >= 3]
for lab, col in (("같은 팀 동료(본인 제외)", "mate"), ("상대 팀", "opp")):
    r_, p_ = stats.spearmanr(sub.rate, sub[col])
    # 경기 단위 순열: 다른 경기의 값과 섞어 우연 수준 확인
    nulls = [stats.spearmanr(sub.rate, rng.permutation(sub[col].to_numpy()))[0] for _ in range(1000)]
    print(f"선수-경기 적진 사망 비율 vs {lab} 비율: Spearman ρ={r_:+.3f} (데스 3건 이상 {len(sub)}개, 무작위 섞기 95% 범위 {np.percentile(nulls,2.5):+.3f}~{np.percentile(nulls,97.5):+.3f})")
tm_ = tk.merge(opp, on=["match_id", "team_id"])
tm_["r"] = tm_.K / tm_.N; tm_["r_opp"] = tm_.K_opp / tm_.N_opp
r_, p_ = stats.spearmanr(tm_.r, tm_.r_opp)
print(f"팀 단위(경기당 두 팀) 적진 사망 비율의 상관(내 팀 vs 상대 팀): Spearman ρ={r_:+.3f} (팀 {len(tm_)}개)")

# ----------------------------------------------------------------------
print("\n" + "=" * 78 + "\n[4] 과산포(분산비)를 줄이는 기준 확률 — 각 표본의 '본인 사망'은 제외하고 계산\n" + "=" * 78)
rel = ps[ps.n_deaths >= 4].copy()
ev = d.copy()
tot_K, tot_N = ev.y.sum(), len(ev)
gK = ev.groupby("group").y.sum(); gN = ev.groupby("group").y.size()
mK = ev.groupby("match_id").y.sum(); mN = ev.groupby("match_id").y.size()
tK = ev.groupby("team_key").y.sum(); tN = ev.groupby("team_key").y.size()
pK = ev.groupby("pm_key").y.sum(); pN = ev.groupby("pm_key").y.size()
rel["match_id_"] = rel.match_id
rel["pm_key"] = rel.match_id + "_" + rel.player_id.astype(str)
tmap = ev.drop_duplicates("pm_key").set_index("pm_key").team_key
rel["team_key"] = rel.pm_key.map(tmap)
own_K, own_N = rel.k_enemy.to_numpy(float), rel.n_deaths.to_numpy(float)
pm_K, pm_N = rel.pm_key.map(pK).to_numpy(float), rel.pm_key.map(pN).to_numpy(float)

def disp(p):
    p = np.clip(p, 0.02, 0.98)
    chi = ((own_K - own_N * p) ** 2 / (own_N * p * (1 - p))).sum()
    return chi / len(rel)

sources = {
    "전체 단일 확률": (tot_K - own_K) / (tot_N - own_N),
    "그룹(포지션·라인전) 확률": (rel.group.map(gK).to_numpy(float) - own_K) / (rel.group.map(gN).to_numpy(float) - own_N),
    "경기 확률 (같은 경기 다른 선수 사망)": (rel.match_id.map(mK).to_numpy(float) - pm_K) / (rel.match_id.map(mN).to_numpy(float) - pm_N),
    "같은 팀 동료 확률 (본인 제외)": (rel.team_key.map(tK).to_numpy(float) - pm_K) / (rel.team_key.map(tN).to_numpy(float) - pm_N),
}
opp_key = rel.team_key.str.replace("_100", "_X").str.replace("_200", "_100").str.replace("_X", "_200")
sources["상대 팀 확률 (상대 팀 사망)"] = (opp_key.map(tK).to_numpy(float)) / (opp_key.map(tN).to_numpy(float))
rows = [{"기준 확률": k, "분산비(χ²/n)": round(disp(v), 2)} for k, v in sources.items() if not np.isnan(v).any()]
print(f"신뢰 표본 {len(rel)}개. 분산비 1에 가까울수록 '우연(이항)'만으로 설명되는 변동에 가까움")
print(pd.DataFrame(rows).to_string(index=False))
print("※ 주의: 팀·경기 단위 확률은 사망 수가 적어 추정 잡음이 크고, 잡음 자체가 분산비를 부풀림. 분산비가 커졌다고 해서 맥락이 설명력이 없다는 뜻이 아님(공정한 비교 아님). 맥락 효과는 [3]의 상관과 [5]로 판단.")

# ----------------------------------------------------------------------
print("\n" + "=" * 78 + "\n[5] 고립 사망 vs 팀 동반 사망 (같은 팀 다른 선수가 ±W초 안에 함께 죽었는가)\n" + "=" * 78)

def mark_grouped(df, W):
    df = df.sort_values(["match_id", "team_id", "game_time"]).copy()
    flag = np.zeros(len(df), dtype=bool)
    pos = 0
    for _, g in df.groupby(["match_id", "team_id"], sort=False):
        t, pid = g.game_time.to_numpy(), g.player_id.to_numpy()
        for i in range(len(g)):
            flag[pos + i] = bool(((np.abs(t - t[i]) <= W) & (pid != pid[i])).any())
        pos += len(g)
    df["grouped"] = flag
    return df

rows = []
for W in (20, 30, 45, 60):
    dg = mark_grouped(d, W)
    est, (lo, hi) = boot_diff(dg, dg.grouped, ~dg.grouped, args.boot)   # (고립 - 동반)
    rows.append({"W(초)": W, "고립 사망 비중": round((~dg.grouped).mean(), 3),
                 "적진 사망 비율(동반)": round(dg[dg.grouped].y.mean(), 3),
                 "적진 사망 비율(고립)": round(dg[~dg.grouped].y.mean(), 3),
                 "차이(고립−동반)": round(est, 3), "95% 구간(경기 부트스트랩)": f"{lo:+.3f} ~ {hi:+.3f}"})
print(pd.DataFrame(rows).to_string(index=False))

dg = mark_grouped(d, 30)
print("\n[W=30초] 포지션 묶음별 적진 사망 비율 — 동반 사망 / 고립 사망")
x = dg.assign(유형=np.where(dg.grouped, "동반", "고립")).pivot_table(index="pos3", columns="유형", values="y", aggfunc=["mean", "count"])
print(x.round(3).to_string())

# 고정 70% 기준으로 플래그된 표본을 '동반/고립'으로 분해
dg["y_grp"] = (dg.y.astype(bool) & dg.grouped).astype(int)
dg["y_iso"] = (dg.y.astype(bool) & ~dg.grouped).astype(int)
cnt = dg.groupby(["match_id", "player_id", "group"])[["y", "y_grp", "y_iso"]].sum().reset_index()
cnt = cnt.merge(ps[["match_id", "player_id", "group", "n_deaths", "rate"]], on=["match_id", "player_id", "group"])
rel2 = cnt[cnt.n_deaths >= 4].copy()
fx = rel2[rel2.rate >= 0.70]
print(f"\n[고정 70% 기준 플래그 {len(fx)}건 분해 (신뢰 표본 {len(rel2)}개 중)]")
print(f"  플래그 표본의 적진 사망 {int(fx.y.sum())}건 중 팀 동반 사망 {int(fx.y_grp.sum())}건 ({fx.y_grp.sum() / fx.y.sum():.1%}), 고립 사망 {int(fx.y_iso.sum())}건")
share = (fx.y_grp / fx.y)
print(f"  표본별 '동반 비중' 중앙값 {share.median():.2f} / 동반 비중 50% 이상인 표본 {(share >= 0.5).sum()}건 / 100%인 표본 {(share == 1).sum()}건")
for thr in (0.7, 0.5):
    n_iso = int(((rel2.y_iso / rel2.n_deaths) >= thr).sum())
    print(f"  고립 적진 사망만 세면(분모=전체 데스) 비율 ≥{thr:.0%}인 표본: {n_iso}건 (원래 고정 기준 ≥{thr:.0%}: {int((rel2.rate >= thr).sum())}건)")
zf = rel2.merge(ps[["match_id", "player_id", "group"]].assign(k=1), on=["match_id", "player_id", "group"])
zflag = a.zscores(ps, a.baseline(ps))[0]
zflag = zflag[(zflag.n_deaths >= 4) & (zflag.z_group > 2)][["match_id", "player_id", "group", "n_deaths", "k_enemy"]]
zdet = zflag.merge(cnt, on=["match_id", "player_id", "group"])
print("\n[그룹 Z>2로 플래그된 표본의 동반/고립 분해]")
print(zdet[["group", "n_deaths_x", "k_enemy", "y_grp", "y_iso"]].rename(columns={"n_deaths_x": "데스", "k_enemy": "적진", "y_grp": "동반", "y_iso": "고립"}).to_string(index=False))
print("※ 동반 사망 = 같은 팀 다른 선수가 ±30초 안에 함께 사망(팀 교전·푸시·수비). 고립 사망 = 혼자 죽은 경우.")
