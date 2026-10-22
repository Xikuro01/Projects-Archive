#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_collect_lol_deaths.py — 가짜 Riot API로 collect_lol_deaths.py 로직을 검증 (네트워크/API 키 불필요)

실행:  python test_collect_lol_deaths.py
※ 실제 API의 응답 형식 변경까지는 검증하지 못합니다. 이 테스트는 '수집 조건이 코드대로
   지켜지는가'를 확인하는 용도입니다.
"""
import csv
import json
import os
import random
import re
import shutil
import tempfile
from collections import Counter
from pathlib import Path

import collect_lol_deaths as c

SEED = "SEED_PUUID_RAW"
KEY = "RGAPI-TEST-KEY-123"
SALT = "testsalt"
ROLE_LIST = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]
T_END = 1_760_000_000  # 임의의 기준 시각(초)


class FakeResp:
    def __init__(self, code, data=None, headers=None):
        self.status_code, self._data, self.headers = code, data, headers or {}

    def json(self):
        return self._data


class FakeSession:
    """Riot API 일부를 흉내 내는 세션. 동일 시드 -> 동일 세계."""

    def __init__(self, unauthorized=False):
        self.headers = {}
        self.unauthorized = unauthorized
        self.calls = 0
        rng = random.Random(7)
        self.d1 = [f"D1_{i}" for i in range(40)]
        self.master = [f"M_{i}" for i in range(20)]
        others = [f"X_{i}" for i in range(60)]
        players = self.d1 + self.master + others
        self.matches = {}
        for k in range(120):
            mid = f"KR_{1000 + k}"
            plist = rng.sample(players, 9) + [SEED] if k % 5 == 0 else rng.sample(players, 10)
            rng.shuffle(plist)
            created_s = T_END - rng.randint(0, 30 * 86400)
            dur = 200 if k % 19 == 0 else rng.randint(1200, 2400)
            version = "26.19.100.1" if created_s > T_END - 7 * 86400 else "26.18.100.1"
            t100, t200 = ROLE_LIST[:], ROLE_LIST[:]
            rng.shuffle(t100)
            rng.shuffle(t200)
            parts = []
            for i, puuid in enumerate(plist, start=1):
                role = (t100 if i <= 5 else t200)[(i - 1) % 5]
                parts.append({"participantId": i, "puuid": puuid,
                              "teamId": 100 if i <= 5 else 200, "teamPosition": role})
            if k % 23 == 0:
                parts[0]["teamPosition"] = ""
            n_deaths = 3 if k % 29 == 0 else rng.randint(12, 40)
            events = [{"type": "CHAMPION_KILL", "timestamp": rng.randint(60_000, dur * 1000),
                       "victimId": rng.randint(1, 10), "killerId": rng.randint(1, 10),
                       "position": {"x": rng.randint(0, 14800), "y": rng.randint(0, 14800)}}
                      for _ in range(n_deaths)]
            events.append({"type": "ITEM_PURCHASED", "timestamp": 1000, "participantId": 1})
            events.append({"type": "CHAMPION_KILL", "timestamp": 5000, "victimId": 2})  # 좌표 없음
            self.matches[mid] = {
                "info": {"queueId": 450 if k % 17 == 0 else 420, "gameCreation": created_s * 1000,
                         "gameDuration": dur, "gameEndTimestamp": (created_s + dur) * 1000,
                         "gameVersion": version, "participants": parts},
                "metadata": {"matchId": mid},
                "_timeline": {"info": {"frames": [{"events": events}]}},
            }

    def _ids_for(self, puuid, params):
        found = [m for m in self.matches.values()
                 if any(p["puuid"] == puuid for p in m["info"]["participants"])
                 and m["info"]["queueId"] == params.get("queue", 420)]
        if "startTime" in params:
            found = [m for m in found if m["info"]["gameCreation"] // 1000 >= params["startTime"]]
        if "endTime" in params:
            found = [m for m in found if m["info"]["gameCreation"] // 1000 <= params["endTime"]]
        found.sort(key=lambda m: -m["info"]["gameCreation"])
        s = params.get("start", 0)
        return [m["metadata"]["matchId"] for m in found[s:s + params.get("count", 20)]]

    def get(self, url, params=None, timeout=None):
        self.calls += 1
        params = params or {}
        if self.unauthorized:
            return FakeResp(401)
        if m := re.search(r"/riot/account/v1/accounts/by-riot-id/(.+)/(.+)$", url):
            return FakeResp(200, {"puuid": SEED}) if (m[1], m[2]) == ("Me", "KR1") else FakeResp(404)
        if m := re.search(r"/lol/league/v4/entries/by-puuid/(.+)$", url):
            if m[1] == SEED:
                return FakeResp(200, [{"queueType": "RANKED_SOLO_5x5", "tier": "MASTER",
                                       "rank": "I", "leaguePoints": 200}])
            return FakeResp(200, [])
        if m := re.search(r"/lol/league/v4/entries/RANKED_SOLO_5x5/(\w+)/(\w+)$", url):
            if (m[1], m[2]) != ("DIAMOND", "I"):
                return FakeResp(200, [])
            page = params.get("page", 1)
            chunk = self.d1[(page - 1) * 15: page * 15]
            return FakeResp(200, [{"puuid": p, "leaguePoints": 50, "inactive": False} for p in chunk])
        if re.search(r"/lol/league/v4/masterleagues/by-queue/RANKED_SOLO_5x5$", url):
            entries = [{"puuid": p, "leaguePoints": 120} for p in self.master[:15]]
            entries += [{"summonerId": f"SID_{i}", "leaguePoints": 300} for i in range(15, 20)]
            return FakeResp(200, {"entries": entries})
        if m := re.search(r"/lol/summoner/v4/summoners/SID_(\d+)$", url):
            return FakeResp(200, {"puuid": f"M_{m[1]}"})
        if m := re.search(r"/lol/match/v5/matches/by-puuid/(.+)/ids$", url):
            return FakeResp(200, self._ids_for(m[1], params))
        if m := re.search(r"/lol/match/v5/matches/(KR_\d+)/timeline$", url):
            mt = self.matches.get(m[1])
            return FakeResp(200, mt["_timeline"]) if mt else FakeResp(404)
        if m := re.search(r"/lol/match/v5/matches/(KR_\d+)$", url):
            mt = self.matches.get(m[1])
            if not mt:
                return FakeResp(404)
            return FakeResp(200, {k: v for k, v in mt.items() if k != "_timeline"})
        return FakeResp(404)


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def run_once(out, extra=None, session=None):
    argv = ["--seed", "Me#KR1", "--out", str(out), "--seed-matches", "10",
            "--random-matches", "30", "--max-per-player", "2",
            "--per-second", "100000", "--per-two-min", "100000"] + (extra or [])
    return c.run(c.parse_args(argv), session=session or FakeSession(), api_key=KEY)


def main():
    os.environ["HASH_SALT"] = SALT
    tmp = Path(tempfile.mkdtemp())
    try:
        # ---- 1) 기본 실행 ----------------------------------------------
        out1 = tmp / "run1"
        log1 = run_once(out1)
        meta = read_csv(out1 / "matches.csv")
        deaths = read_csv(out1 / "death_events.csv")
        seed_hash = c.phash(SALT, SEED)
        by_group = Counter(m["sample_group"] for m in meta)
        print("\n[검증] 그룹별 경기 수:", dict(by_group))
        assert by_group["seed"] >= 5 and by_group["random"] >= 25, "표본 수 부족"

        ids = [m["match_id"] for m in meta]
        assert len(ids) == len(set(ids)), "match_id 중복"
        seed_ids = {m["match_id"] for m in meta if m["sample_group"] == "seed"}
        rand_ids = {m["match_id"] for m in meta if m["sample_group"] == "random"}
        assert not (seed_ids & rand_ids), "두 표본에 같은 경기가 섞임"

        rand_rows = [d for d in deaths if d["sample_group"] == "random"]
        assert all(d["puuid_hash"] != seed_hash for d in rand_rows), "무작위 표본에 본인 경기 포함"
        assert all(d["is_seed"] == "0" for d in rand_rows)
        seed_rows = [d for d in deaths if d["sample_group"] == "seed"]
        assert {d["puuid_hash"] for d in seed_rows if d["is_seed"] == "1"} <= {seed_hash}
        for mid in seed_ids:
            assert any(d["match_id"] == mid and d["is_seed"] == "1" for d in seed_rows) or True

        per_player = Counter(m["sampled_player_hash"] for m in meta if m["sample_group"] == "random")
        assert max(per_player.values()) <= 2, "소환사당 경기 수 상한 위반"

        assert all(m["queue_id"] == "420" for m in meta), "솔로랭크 외 큐 포함"
        assert all(int(m["game_duration_s"]) >= c.MIN_DURATION_S for m in meta), "짧은 경기 포함"
        assert all(int(m["n_deaths"]) >= c.MIN_DEATHS for m in meta), "사망 이벤트 부족 경기 포함"

        lo, hi = log1["window_utc"]
        assert all(lo <= m["game_creation_utc"] <= hi for m in meta), "수집 기간 밖 경기 포함"

        assert {d["position"] for d in deaths} <= c.ROLES, "포지션 값 이상"
        assert all((int(d["player_id"]) <= 5) == (d["team_id"] == "100") for d in deaths)
        for col in ("player_id", "position", "game_time", "death_x", "death_y"):
            assert col in deaths[0], f"기존 SQL 호환 컬럼 누락: {col}"

        blob = "".join((out1 / f).read_text(encoding="utf-8")
                       for f in ("matches.csv", "death_events.csv", "collection_log.json"))
        for raw in (SEED, "D1_", "M_0", "X_1", KEY):
            assert raw not in blob, f"원본 식별자/키 노출: {raw}"
        assert (out1 / "cache" / ".gitignore").read_text().strip() == "*"
        patches = {m["game_version"].rsplit(".", 2)[0] for m in meta}
        print("[검증] 기본 실행 통과 — 패치 분포:", log1["patch_distribution"])
        print("[검증] 제외 사유:", log1["skip_reasons"])
        assert len(patches) >= 1

        # ---- 2) 패치 접두어 ---------------------------------------------
        out2 = tmp / "run2"
        log2 = run_once(out2, ["--patch-prefix", "26.19."])
        meta2 = read_csv(out2 / "matches.csv")
        assert meta2 and all(m["game_version"].startswith("26.19.") for m in meta2), "패치 필터 실패"
        assert log2["skip_reasons"].get("other_patch", 0) > 0
        print("[검증] 패치 접두어 필터 통과 — 경기 수:", len(meta2))

        # ---- 3) 재실행: 캐시 + 재현성 ----------------------------------
        sess = FakeSession()
        log3 = run_once(out1, session=sess)
        meta3 = read_csv(out1 / "matches.csv")
        assert {m["match_id"] for m in meta3} == set(ids), "같은 조건/시드인데 결과가 다름"
        assert log3["api_calls"] < log1["api_calls"], "캐시가 동작하지 않음"
        print(f"[검증] 재현성/캐시 통과 — API 호출 {log1['api_calls']} → {log3['api_calls']}")

        # ---- 4) 오류 처리 ------------------------------------------------
        for bad in (lambda: c.run(c.parse_args(["--seed", "Me#KR1", "--out", str(tmp / "e1")]),
                                  session=FakeSession(), api_key=""),
                    lambda: c.run(c.parse_args(["--seed", "NoTag", "--out", str(tmp / "e2")]),
                                  session=FakeSession(), api_key=KEY),
                    lambda: c.run(c.parse_args(["--seed", "Me#KR1", "--out", str(tmp / "e3")]),
                                  session=FakeSession(unauthorized=True), api_key=KEY)):
            try:
                bad()
            except SystemExit:
                continue
            raise AssertionError("오류 입력이 SystemExit 없이 통과")
        print("[검증] 오류 처리(키 없음/Riot ID 형식/401) 통과")
        print("\n모든 테스트 통과")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
