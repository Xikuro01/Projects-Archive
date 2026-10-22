#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
collect_lol_deaths.py — LoL 사망 이벤트 수집 (Riot Match-V5 / League-V4)
==========================================================================
[수집 설계]
  - 모집단   : 솔로랭크(queueId 420), 지정한 티어 구간(기본: 다이아 I ~ 마스터)
  - 주 표본  : 모집단에서 무작위로 뽑은 소환사의 경기 (sample_group = 'random')
                · 본인이 참여한 경기는 제외, 소환사당 최대 N경기(기본 2)
                · 같은 match_id 중복 제거
  - 검증 표본: 본인 계정의 경기 (sample_group = 'seed')
                · 분석 시 본인 행(is_seed=1)은 빼고 같이 뛴 9명만 쓰는 것을 권장
  - 기간     : 본인 마지막 솔로랭크 경기 종료 시각을 끝으로, 그 이전 --days일
                · 두 표본 모두 같은 기간으로 제한 (패치 정렬)
                · 필요하면 --patch-prefix 로 특정 패치만 허용
  - 개인정보 : puuid는 솔트 해시(12자리)로만 저장. 원본 API 응답 캐시(cache/)에는
                닉네임 등이 들어 있으므로 저장소에 올리지 말 것
                (cache/.gitignore 가 자동 생성되어 기본적으로 제외됨)

[사전 준비]
  pip install requests
  export RIOT_API_KEY="RGAPI-..."        # 키는 코드/저장소에 넣지 말 것 (개발 키는 24시간마다 만료)
  export HASH_SALT="아무 문자열"          # 선택. 없으면 실행마다 임의 솔트 사용

[실행 예]
  python collect_lol_deaths.py --seed "본인닉네임#KR1"
  python collect_lol_deaths.py --seed "본인닉네임#KR1" --random-matches 150 --patch-prefix 26.19.

[산출물] (기본 폴더 lol_data/)
  death_events.csv    : 사망 이벤트 (기존 lol_troll_detection_real.sql 과 호환되는
                        match_id, player_id, position, game_time, death_x, death_y 포함)
  matches.csv         : 경기 메타데이터 (큐, 경기 시각, 패치, 표본 그룹, 수집 시점 티어 등)
  collection_log.json : 수집 조건·건수·제외 사유·패치 분포 (README 근거 자료용)

[한계] 소환사 풀은 수집 시점의 래더 스냅샷이며, 모집단 대표성은 이 풀에 한정됨.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import secrets
import sys
import time
from collections import Counter, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import requests

SOLO_QUEUE_ID = 420
SOLO_QUEUE = "RANKED_SOLO_5x5"
MIN_DURATION_S = 300      # 이보다 짧은 경기는 다시하기/조기종료로 보고 제외
MIN_DEATHS = 10           # 기존 분석과 동일: 사망 이벤트 10건 미만 경기 제외
ROLES = {"TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"}
APEX = {"MASTER": "masterleagues", "GRANDMASTER": "grandmasterleagues",
        "CHALLENGER": "challengerleagues"}
KST = timezone(timedelta(hours=9))

DEATH_FIELDS = ["match_id", "sample_group", "player_id", "team_id", "position",
                "game_time", "death_x", "death_y", "puuid_hash", "is_seed"]
META_FIELDS = ["match_id", "sample_group", "queue_id", "game_creation_utc",
               "game_version", "game_duration_s", "seed_slot",
               "sampled_player_hash", "sampled_tier", "sampled_division",
               "sampled_lp", "n_deaths"]


# ----------------------------------------------------------------------
# API 클라이언트 (호출 속도 제한 + 재시도 + 응답 캐시)
# ----------------------------------------------------------------------
class RiotClient:
    def __init__(self, api_key, platform, region, cache_dir, session=None,
                 per_second=18, per_two_min=95):
        self.session = session or requests.Session()
        self.session.headers.update({"X-Riot-Token": api_key})
        self.platform, self.region = platform, region
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        (self.cache_dir / ".gitignore").write_text("*\n", encoding="utf-8")
        self.per_second, self.per_two_min = per_second, per_two_min
        self._sec, self._two = deque(), deque()
        self.calls = 0

    def _throttle(self):
        while True:
            now = time.monotonic()
            while self._sec and now - self._sec[0] >= 1.0:
                self._sec.popleft()
            while self._two and now - self._two[0] >= 120.0:
                self._two.popleft()
            wait = 0.0
            if len(self._sec) >= self.per_second:
                wait = max(wait, 1.0 - (now - self._sec[0]))
            if len(self._two) >= self.per_two_min:
                wait = max(wait, 120.0 - (now - self._two[0]))
            if wait <= 0:
                break
            time.sleep(wait + 0.01)
        t = time.monotonic()
        self._sec.append(t)
        self._two.append(t)

    def get(self, url, params=None, cache_key=None):
        path = None
        if cache_key:
            path = self.cache_dir / f"{cache_key}.json"
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        for attempt in range(6):
            self._throttle()
            self.calls += 1
            try:
                resp = self.session.get(url, params=params, timeout=20)
            except requests.RequestException:
                time.sleep(2 ** attempt)
                continue
            code = resp.status_code
            if code == 200:
                data = resp.json()
                if path is not None:
                    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                return data
            if code == 404:
                return None
            if code == 429:
                wait = int(resp.headers.get("Retry-After", "10"))
                print(f"  [429] {wait}초 대기 후 재시도")
                time.sleep(wait + 1)
                continue
            if code in (401, 403):
                sys.exit(f"[오류] HTTP {code}: API 키가 만료되었거나 잘못되었습니다 "
                         f"(개발 키는 24시간마다 만료). 키를 새로 발급해 다시 실행하세요. "
                         f"이미 받은 응답은 캐시되어 있어 이어서 진행됩니다.")
            if code >= 500:
                time.sleep(2 ** attempt)
                continue
            sys.exit(f"[오류] HTTP {code}: {url}")
        sys.exit(f"[오류] 재시도 초과: {url}")

    # --- 엔드포인트 -----------------------------------------------------
    def _plat(self, p):
        return f"https://{self.platform}.api.riotgames.com{p}"

    def _reg(self, p):
        return f"https://{self.region}.api.riotgames.com{p}"

    def puuid_by_riot_id(self, name, tag):
        d = self.get(self._reg(f"/riot/account/v1/accounts/by-riot-id/"
                               f"{quote(name, safe='')}/{quote(tag, safe='')}"))
        return d["puuid"] if d else None

    def league_entries(self, tier, division, page):
        return self.get(self._plat(f"/lol/league/v4/entries/{SOLO_QUEUE}/{tier}/{division}"),
                        params={"page": page}) or []

    def apex_entries(self, tier):
        d = self.get(self._plat(f"/lol/league/v4/{APEX[tier]}/by-queue/{SOLO_QUEUE}"))
        return (d or {}).get("entries", [])

    def entries_by_puuid(self, puuid):
        return self.get(self._plat(f"/lol/league/v4/entries/by-puuid/{puuid}")) or []

    def puuid_by_summoner_id(self, sid):
        d = self.get(self._plat(f"/lol/summoner/v4/summoners/{sid}"))
        return d.get("puuid") if d else None

    def match_ids(self, puuid, start_s=None, end_s=None, count=20):
        params = {"queue": SOLO_QUEUE_ID, "type": "ranked", "start": 0, "count": count}
        if start_s is not None:
            params["startTime"] = int(start_s)
        if end_s is not None:
            params["endTime"] = int(end_s)
        return self.get(self._reg(f"/lol/match/v5/matches/by-puuid/{puuid}/ids"),
                        params=params) or []

    def match(self, mid):
        return self.get(self._reg(f"/lol/match/v5/matches/{mid}"), cache_key=f"match_{mid}")

    def timeline(self, mid):
        return self.get(self._reg(f"/lol/match/v5/matches/{mid}/timeline"),
                        cache_key=f"timeline_{mid}")


# ----------------------------------------------------------------------
# 유틸
# ----------------------------------------------------------------------
def phash(salt, puuid):
    return hashlib.sha256(f"{salt}:{puuid}".encode("utf-8")).hexdigest()[:12]


def duration_s(info):
    d = info.get("gameDuration", 0) or 0
    return d / 1000 if d > 10000 else d      # 구버전 응답은 밀리초일 수 있음


def end_time_s(info):
    end_ms = info.get("gameEndTimestamp")
    if end_ms:
        return end_ms // 1000
    return (info["gameCreation"] + int(duration_s(info) * 1000)) // 1000


def build_pool(client, bands, max_pages):
    """티어 구간별 소환사 풀. 디비전은 전 페이지를 받아 순서 편향 없이 균등 추출."""
    pool, sizes = [], {}
    for band in bands:
        tier, _, div = band.partition(":")
        tier, div = tier.strip().upper(), (div.strip().upper() or "I")
        entries = []
        if tier in APEX:
            entries = client.apex_entries(tier)
            div = "I"
        else:
            for page in range(1, max_pages + 1):
                chunk = client.league_entries(tier, div, page)
                if not chunk:
                    break
                entries.extend(chunk)
        entries = [e for e in entries if not e.get("inactive")]
        sizes[band] = len(entries)
        print(f"  풀 [{band}] {len(entries)}명")
        pool += [{"entry": e, "tier": tier, "division": div} for e in entries]
    return pool, sizes


# ----------------------------------------------------------------------
# 수집기
# ----------------------------------------------------------------------
class Collector:
    def __init__(self, client, args, salt, seed_puuid, seed_info, death_w, meta_w, files):
        self.client, self.args, self.salt = client, args, salt
        self.seed_puuid, self.seed_info = seed_puuid, seed_info
        self.death_w, self.meta_w, self.files = death_w, meta_w, files
        self.skip = Counter()
        self.accepted = {"seed": [], "random": []}
        self.patches = {"seed": Counter(), "random": Counter()}
        self.per_player = Counter()
        self.seen = set()             # 이미 검토한 match_id (수락/제외 모두, 중복 방지)
        self.dup_encounters = 0       # 이미 검토한 경기를 다시 만난 횟수
        self.forbidden = set()        # 주 표본에서 제외할 match_id (본인 경기)
        self.forbidden_hit = set()    # 위 목록과 실제로 겹친 경기

    # 경기 단위 검증 — 통과하면 None, 아니면 제외 사유
    def validate(self, mj, group):
        info = mj["info"]
        if info.get("queueId") != SOLO_QUEUE_ID:
            return "wrong_queue"
        if duration_s(info) < MIN_DURATION_S:
            return "remake_or_short"
        ps = info["participants"]
        if len(ps) != 10:
            return "not_10_players"
        pre = self.args.patch_prefix
        if pre and not str(info.get("gameVersion", "")).startswith(pre):
            return "other_patch"
        if group == "random" and any(p["puuid"] == self.seed_puuid for p in ps):
            return "contains_seed"
        for team in (100, 200):
            if {p.get("teamPosition") for p in ps if p["teamId"] == team} != ROLES:
                return "bad_positions"
        if not all((p["participantId"] <= 5) == (p["teamId"] == 100) for p in ps):
            return "slot_team_mismatch"
        return None

    def build_rows(self, mj, tj, group, sampled):
        info = mj["info"]
        parts = {p["participantId"]: p for p in info["participants"]}
        seed_slot = next((pid for pid, p in parts.items() if p["puuid"] == self.seed_puuid), None)
        rows = []
        for frame in tj.get("info", {}).get("frames", []):
            for ev in frame.get("events", []):
                if ev.get("type") != "CHAMPION_KILL":
                    continue
                pid, pos = ev.get("victimId"), ev.get("position") or {}
                if pid not in parts or "x" not in pos or "y" not in pos:
                    continue
                p = parts[pid]
                rows.append({
                    "match_id": mj["metadata"]["matchId"], "sample_group": group,
                    "player_id": pid, "team_id": p["teamId"], "position": p["teamPosition"],
                    "game_time": round(ev["timestamp"] / 1000, 1),
                    "death_x": pos["x"], "death_y": pos["y"],
                    "puuid_hash": phash(self.salt, p["puuid"]),
                    "is_seed": int(pid == seed_slot),
                })
        if len(rows) < MIN_DEATHS:
            return None, None
        created = datetime.fromtimestamp(info["gameCreation"] / 1000, tz=timezone.utc)
        meta = {
            "match_id": mj["metadata"]["matchId"], "sample_group": group,
            "queue_id": info["queueId"], "game_creation_utc": created.isoformat(),
            "game_version": info.get("gameVersion", ""),
            "game_duration_s": int(duration_s(info)),
            "seed_slot": seed_slot if seed_slot is not None else "",
            "sampled_player_hash": sampled["hash"], "sampled_tier": sampled["tier"],
            "sampled_division": sampled["division"], "sampled_lp": sampled["lp"],
            "n_deaths": len(rows),
        }
        return meta, rows

    def try_add(self, mid, group, sampled):
        if group == "random" and mid in self.forbidden:
            self.forbidden_hit.add(mid)
            return False
        if mid in self.seen:
            self.dup_encounters += 1
            return False
        self.seen.add(mid)
        mj = self.client.match(mid)
        if not mj:
            self.skip["match_not_found"] += 1
            return False
        reason = self.validate(mj, group)
        if reason:
            self.skip[reason] += 1
            return False
        tj = self.client.timeline(mid)
        if not tj:
            self.skip["timeline_not_found"] += 1
            return False
        meta, rows = self.build_rows(mj, tj, group, sampled)
        if meta is None:
            self.skip["few_deaths"] += 1
            return False
        self.meta_w.writerow(meta)
        self.death_w.writerows(rows)
        for f in self.files:
            f.flush()
        self.accepted[group].append(mid)
        self.patches[group][meta["game_version"].rsplit(".", 2)[0]] += 1
        print(f"  [{group}] {len(self.accepted[group]):>3} 경기 수집: {mid} "
              f"(사망 {meta['n_deaths']}건, 패치 {meta['game_version']})")
        return True

    def resolve_puuid(self, entry):
        if entry.get("puuid"):
            return entry["puuid"]
        if entry.get("summonerId"):
            return self.client.puuid_by_summoner_id(entry["summonerId"])
        return None


# ----------------------------------------------------------------------
# 메인 흐름
# ----------------------------------------------------------------------
def parse_args(argv=None):
    p = argparse.ArgumentParser(description="LoL 사망 이벤트 수집 (주 표본: 무작위, 검증 표본: 본인 계정)")
    p.add_argument("--seed", default=os.environ.get("SEED_RIOT_ID"),
                   help='본인 Riot ID "이름#태그" (또는 환경변수 SEED_RIOT_ID)')
    p.add_argument("--platform", default="kr", help="플랫폼 라우팅 (기본 kr)")
    p.add_argument("--region", default="asia", help="지역 라우팅 (기본 asia)")
    p.add_argument("--bands", default="DIAMOND:I,MASTER",
                   help='모집단 구간, 쉼표 구분 (예: "DIAMOND:I,DIAMOND:II,MASTER")')
    p.add_argument("--days", type=int, default=14, help="본인 마지막 경기 기준 소급 기간(일)")
    p.add_argument("--seed-matches", type=int, default=30, help="검증 표본(본인) 목표 경기 수")
    p.add_argument("--random-matches", type=int, default=100, help="주 표본(무작위) 목표 경기 수")
    p.add_argument("--max-per-player", type=int, default=2, help="무작위 소환사당 최대 경기 수")
    p.add_argument("--patch-prefix", default=None, help='허용할 gameVersion 접두어 (예: "26.19.")')
    p.add_argument("--max-pages", type=int, default=60, help="디비전별 리그 페이지 상한")
    p.add_argument("--max-players", type=int, default=3000, help="검토할 소환사 수 상한")
    p.add_argument("--rng-seed", type=int, default=42, help="무작위 추출 시드 (로그에 기록)")
    p.add_argument("--out", default="lol_data", help="출력 폴더")
    p.add_argument("--per-second", type=int, default=18)
    p.add_argument("--per-two-min", type=int, default=95)
    return p.parse_args(argv)


def run(args, session=None, api_key=None):
    api_key = api_key or os.environ.get("RIOT_API_KEY")
    if not api_key:
        sys.exit("[오류] 환경변수 RIOT_API_KEY 가 없습니다.")
    if not args.seed or "#" not in args.seed:
        sys.exit('[오류] --seed "이름#태그" 형식으로 본인 Riot ID를 지정하세요.')
    name, _, tag = args.seed.rpartition("#")
    salt = os.environ.get("HASH_SALT") or secrets.token_hex(8)
    random.seed(args.rng_seed)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    client = RiotClient(api_key, args.platform, args.region, out / "cache",
                        session=session, per_second=args.per_second,
                        per_two_min=args.per_two_min)
    started = datetime.now(timezone.utc)

    # 1) 본인 계정 확인 + 수집 시점 티어
    print("[1/5] 본인 계정 확인")
    seed_puuid = client.puuid_by_riot_id(name, tag)
    if not seed_puuid:
        sys.exit("[오류] Riot ID를 찾지 못했습니다. 이름#태그와 --region 을 확인하세요.")
    seed_tier = {"tier": "", "division": "", "lp": ""}
    for e in client.entries_by_puuid(seed_puuid):
        if e.get("queueType") == SOLO_QUEUE:
            seed_tier = {"tier": e.get("tier", ""), "division": e.get("rank", ""),
                         "lp": e.get("leaguePoints", "")}
    print(f"  수집 시점 티어: {seed_tier['tier']} {seed_tier['division']} {seed_tier['lp']}LP")

    # 2) 기간 확정: 본인 마지막 솔로랭크 경기 종료 시각 기준
    print("[2/5] 수집 기간 확정")
    latest = client.match_ids(seed_puuid, count=1)
    if not latest:
        sys.exit("[오류] 본인의 솔로랭크 경기를 찾지 못했습니다.")
    latest_match = client.match(latest[0])
    end_s = end_time_s(latest_match["info"]) + 60
    start_s = end_s - args.days * 86400
    fmt = lambda s: (datetime.fromtimestamp(s, tz=timezone.utc).isoformat(timespec="minutes")
                     + " / " + datetime.fromtimestamp(s, tz=KST).strftime("%m-%d %H:%M KST"))
    print(f"  기간: {fmt(start_s)}  ~  {fmt(end_s)}")

    death_f = open(out / "death_events.csv", "w", newline="", encoding="utf-8-sig")
    meta_f = open(out / "matches.csv", "w", newline="", encoding="utf-8-sig")
    death_w = csv.DictWriter(death_f, fieldnames=DEATH_FIELDS)
    meta_w = csv.DictWriter(meta_f, fieldnames=META_FIELDS)
    death_w.writeheader()
    meta_w.writeheader()
    col = Collector(client, args, salt, seed_puuid, seed_tier, death_w, meta_w, [death_f, meta_f])
    pool_sizes, examined = {}, 0
    try:
        # 3) 검증 표본(본인)
        print(f"[3/5] 검증 표본(본인) 수집 — 목표 {args.seed_matches}경기")
        seed_ids = client.match_ids(seed_puuid, start_s, end_s, count=100)
        col.forbidden = set(seed_ids)
        seed_sampled = {"hash": phash(salt, seed_puuid), **seed_tier}
        for mid in seed_ids:
            if len(col.accepted["seed"]) >= args.seed_matches:
                break
            col.try_add(mid, "seed", seed_sampled)

        # 4) 주 표본(무작위)
        print(f"[4/5] 소환사 풀 구성 — 구간 {args.bands}")
        bands = [b for b in args.bands.split(",") if b.strip()]
        pool, pool_sizes = build_pool(client, bands, args.max_pages)
        random.shuffle(pool)
        print(f"[5/5] 주 표본(무작위) 수집 — 목표 {args.random_matches}경기, "
              f"소환사당 최대 {args.max_per_player}경기")
        for item in pool:
            if len(col.accepted["random"]) >= args.random_matches or examined >= args.max_players:
                break
            puuid = col.resolve_puuid(item["entry"])
            if not puuid or puuid == seed_puuid:
                continue
            examined += 1
            ids = client.match_ids(puuid, start_s, end_s, count=20)
            random.shuffle(ids)
            sampled = {"hash": phash(salt, puuid), "tier": item["tier"],
                       "division": item["division"], "lp": item["entry"].get("leaguePoints", "")}
            took = 0
            for mid in ids:
                if took >= args.max_per_player or len(col.accepted["random"]) >= args.random_matches:
                    break
                if col.try_add(mid, "random", sampled):
                    took += 1
                    col.per_player[sampled["hash"]] += 1
    finally:
        death_f.close()
        meta_f.close()

    # 요약 + 로그
    ended = datetime.now(timezone.utc)
    log = {
        "started_utc": started.isoformat(), "ended_utc": ended.isoformat(),
        "params": {k: v for k, v in vars(args).items() if k != "seed"},
        "window_utc": [datetime.fromtimestamp(start_s, tz=timezone.utc).isoformat(),
                       datetime.fromtimestamp(end_s, tz=timezone.utc).isoformat()],
        "seed_tier_at_collection": seed_tier,
        "pool_sizes": pool_sizes, "players_examined": examined,
        "accepted": {g: len(v) for g, v in col.accepted.items()},
        "patch_distribution": {g: dict(c) for g, c in col.patches.items()},
        "skip_reasons": {**dict(col.skip), "in_seed_set": len(col.forbidden_hit)},
        "duplicate_encounters": col.dup_encounters,
        "max_matches_per_sampled_player": max(col.per_player.values(), default=0),
        "api_calls": client.calls, "hash_salt_provided": bool(os.environ.get("HASH_SALT")),
    }
    (out / "collection_log.json").write_text(
        json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 60)
    print(f"수집 완료: 주 표본 {len(col.accepted['random'])}경기 / 검증 표본 {len(col.accepted['seed'])}경기"
          f"  (API 호출 {client.calls}회)")
    print(f"패치 분포: {log['patch_distribution']}")
    print(f"제외 사유(경기 수 기준): {log['skip_reasons']}  / 이미 검토한 경기 재조우 {col.dup_encounters}회")
    if len(col.accepted["random"]) < args.random_matches:
        print("※ 주 표본이 목표보다 적습니다 — --days 를 늘리거나 --bands 를 넓혀 보세요.")
    if len({p for c in col.patches.values() for p in c}) > 1:
        print("※ 두 개 이상의 패치가 섞여 있습니다 — 분석 전에 --patch-prefix 로 맞출지 결정하세요.")
    print(f"저장 위치: {out.resolve()}")
    return log


if __name__ == "__main__":
    run(parse_args())
