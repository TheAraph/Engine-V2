#!/usr/bin/env python3
"""
Mini-league intelligence.

"Differential" only means something relative to the people you are actually
racing. This computes effective ownership INSIDE your invitational leagues,
then splits your squad into edges (you own, they mostly don't) and exposures
(they own, you don't).

Dormant until a gameweek has been played — the FPL API returns empty standings
and hides rival picks before the first deadline passes.

Usage: FPL_ENTRY_ID=1234567 python3 league_intel.py
Writes: data/league_intel.json
"""
import json, os, sys, time, urllib.request
from collections import Counter
from pathlib import Path

API = "https://fantasy.premierleague.com/api"
MAX_RIVALS = 60          # per league; keeps the API call count civil
POS = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}


def get(path, tries=3):
    for a in range(tries):
        try:
            req = urllib.request.Request(f"{API}/{path}",
                                         headers={"User-Agent": "fpl-digest/1.0 (personal use)"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            if a == tries - 1:
                print(f"WARN {path}: {e}", file=sys.stderr)
                return None
            time.sleep(1.5 ** a)


def main():
    entry = (os.environ.get("FPL_ENTRY_ID") or "").strip()
    if not entry:
        print("FPL_ENTRY_ID not set — nothing to do.", file=sys.stderr)
        return 1

    boot = get("bootstrap-static/")
    if not boot:
        return 1
    names = {e["id"]: (e["web_name"], POS.get(e["element_type"], "?"),
                       e["now_cost"] / 10, float(e.get("selected_by_percent") or 0))
             for e in boot["elements"]}
    finished = [e["id"] for e in boot["events"] if e.get("finished")]
    if not finished:
        out = {"status": "dormant",
               "reason": "No gameweek finished yet. Rival picks are hidden and league "
                         "standings are empty until the first deadline passes.",
               "leagues": []}
        Path("data").mkdir(exist_ok=True)
        Path("data/league_intel.json").write_text(json.dumps(out, indent=2))
        print("DORMANT - no completed gameweek yet")
        return 0
    gw = max(finished)

    me = get(f"entry/{entry}/")
    if not me:
        return 1
    my_picks = get(f"entry/{entry}/event/{gw}/picks/") or {}
    mine = {p["element"] for p in my_picks.get("picks", [])}

    # Only invitational leagues ('x'). The global/country/club ones have millions
    # of entries and tell you nothing about who you are actually racing.
    leagues = [l for l in me.get("leagues", {}).get("classic", [])
               if l.get("league_type") == "x"]

    report = []
    for lg in leagues:
        rivals, page = [], 1
        while len(rivals) < MAX_RIVALS:
            st = get(f"leagues-classic/{lg['id']}/standings/?page_standings={page}")
            if not st:
                break
            res = st.get("standings", {}).get("results", [])
            rivals.extend(r for r in res if str(r["entry"]) != entry)
            if not st.get("standings", {}).get("has_next"):
                break
            page += 1
            time.sleep(0.3)
        rivals = rivals[:MAX_RIVALS]

        counts = Counter()
        captains = Counter()
        sampled = 0
        for r in rivals:
            pk = get(f"entry/{r['entry']}/event/{gw}/picks/")
            if not pk:
                continue
            sampled += 1
            for p in pk.get("picks", []):
                counts[p["element"]] += 1
                if p.get("is_captain"):
                    captains[p["element"]] += 1
            time.sleep(0.25)
        if not sampled:
            continue

        def pct(n):
            return round(100 * n / sampled, 1)

        edges = sorted(
            [{"name": names[e][0], "pos": names[e][1], "cost": names[e][2],
              "league_own": pct(counts.get(e, 0)), "global_own": names[e][3]}
             for e in mine if e in names and pct(counts.get(e, 0)) < 30],
            key=lambda x: x["league_own"])
        exposure = sorted(
            [{"name": names[e][0], "pos": names[e][1], "cost": names[e][2],
              "league_own": pct(n), "global_own": names[e][3]}
             for e, n in counts.items() if e not in mine and pct(n) >= 50 and e in names],
            key=lambda x: -x["league_own"])
        cap = [{"name": names[e][0], "share": pct(n)} for e, n in captains.most_common(5) if e in names]

        report.append({
            "league": lg["name"], "id": lg["id"], "my_rank": lg.get("entry_rank"),
            "rivals_sampled": sampled, "gw": gw,
            "edges": edges[:12], "exposure": exposure[:12], "captains": cap,
        })

    Path("data").mkdir(exist_ok=True)
    out = {"status": "ok", "gw": gw, "entry": entry,
           "manager": f"{me.get('player_first_name','')} {me.get('player_last_name','')}".strip(),
           "leagues": report}
    Path("data/league_intel.json").write_text(json.dumps(out, indent=2))
    for L in report:
        print(f"{L['league']}: {L['rivals_sampled']} rivals | "
              f"{len(L['edges'])} edges | {len(L['exposure'])} exposures")
    return 0


if __name__ == "__main__":
    sys.exit(main())
