#!/usr/bin/env python3
"""
FPL daily digest engine.

Runs on GitHub Actions (which has real internet access), pulls the full
Fantasy Premier League API, diffs it against yesterday's snapshot, and writes
a compact digest.json that a Cowork session can read and reason over.

State lives in git history: data/snapshot.json is the previous run, committed
each time. That is what makes day-over-day diffs possible across runs.
"""

import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = "https://fantasy.premierleague.com/api"
ROOT = Path(__file__).parent
DATA = ROOT / "data"
SNAPSHOT = DATA / "snapshot.json"
DIGEST = DATA / "digest.json"

POS = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
STATUS = {
    "a": "available",
    "d": "doubtful",
    "i": "injured",
    "s": "suspended",
    "u": "unavailable",
    "n": "not in squad",
}


def get(path, tries=4):
    """GET a JSON endpoint with simple backoff. Returns None on hard failure."""
    url = f"{API}/{path}"
    for attempt in range(tries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "fpl-digest/1.0 (personal use)"}
            )
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            if attempt == tries - 1:
                print(f"WARN: failed {url}: {e}", file=sys.stderr)
                return None
            time.sleep(2 ** attempt)
    return None


def money(tenths):
    return round(tenths / 10, 1)


def build_players(boot):
    """Reduce the ~700 raw elements to the fields we actually reason about."""
    teams = {t["id"]: t["short_name"] for t in boot["teams"]}
    out = {}
    for e in boot["elements"]:
        out[str(e["id"])] = {
            "name": e["web_name"],
            "team": teams.get(e["team"], "?"),
            "pos": POS.get(e["element_type"], "?"),
            "cost": money(e["now_cost"]),
            "status": e.get("status", "a"),
            "news": (e.get("news") or "").strip(),
            "chance": e.get("chance_of_playing_next_round"),
            "form": float(e.get("form") or 0),
            "pts": e.get("total_points", 0),
            "ppg": float(e.get("points_per_game") or 0),
            "mins": e.get("minutes", 0),
            "sel": float(e.get("selected_by_percent") or 0),
            "xgi": float(e.get("expected_goal_involvements") or 0),
            "xgi90": float(e.get("expected_goal_involvements_per_90") or 0),
            "ep_next": float(e.get("ep_next") or 0),
            "starts": e.get("starts", 0),
            "starts90": float(e.get("starts_per_90") or 0),
            "chance_now": e.get("chance_of_playing_this_round"),
            "pens": e.get("penalties_order"),
            "pens_text": (e.get("penalties_text") or "").strip(),
            "corners": e.get("corners_and_indirect_freekicks_order"),
            "fks": e.get("direct_freekicks_order"),
            "cost_change_event": e.get("cost_change_event", 0),
            "transfers_in_event": e.get("transfers_in_event", 0),
            "transfers_out_event": e.get("transfers_out_event", 0),
        }
    return out


def diff_players(today, prev):
    """The heart of it: what actually changed since the last run."""
    d = {
        "new_injuries": [],
        "worsened": [],
        "recovered": [],
        "price_rises": [],
        "price_falls": [],
        "form_risers": [],
        "ownership_surges": [],
    }
    if not prev:
        return d

    for pid, now in today.items():
        was = prev.get(pid)
        if not was:
            continue

        # --- availability ---
        now_ok = now["status"] == "a" and not now["news"]
        was_ok = was["status"] == "a" and not was["news"]
        entry = {
            "name": now["name"], "team": now["team"], "pos": now["pos"],
            "cost": now["cost"], "sel": now["sel"], "news": now["news"],
            "chance": now["chance"],
        }
        if was_ok and not now_ok:
            d["new_injuries"].append(entry)
        elif not was_ok and now_ok:
            d["recovered"].append(entry)
        else:
            # chance_of_playing dropped (e.g. 75% -> 25%) without full flag change
            c_now = now["chance"] if now["chance"] is not None else 100
            c_was = was["chance"] if was["chance"] is not None else 100
            if c_now < c_was:
                e2 = dict(entry)
                e2["from"], e2["to"] = c_was, c_now
                d["worsened"].append(e2)

        # --- price ---
        if now["cost"] > was["cost"]:
            d["price_rises"].append({**entry, "from": was["cost"], "to": now["cost"]})
        elif now["cost"] < was["cost"]:
            d["price_falls"].append({**entry, "from": was["cost"], "to": now["cost"]})

        # --- form / ownership momentum ---
        if now["form"] - was["form"] >= 1.0 and now["form"] >= 4.0:
            d["form_risers"].append(
                {**entry, "form_from": was["form"], "form_to": now["form"]}
            )
        if now["sel"] - was["sel"] >= 1.0:
            d["ownership_surges"].append(
                {**entry, "sel_from": was["sel"], "sel_to": now["sel"]}
            )

    # rank the noisy lists by relevance (ownership = how much it matters to managers)
    for k in ("new_injuries", "worsened", "recovered", "price_rises", "price_falls",
              "ownership_surges"):
        d[k].sort(key=lambda x: -x["sel"])
    d["form_risers"].sort(key=lambda x: -x["form_to"])
    return d


def fixture_outlook(boot, fixtures, next_gw, horizon=5):
    """Average fixture difficulty per team over the next `horizon` gameweeks."""
    teams = {t["id"]: t["short_name"] for t in boot["teams"]}
    window = range(next_gw, next_gw + horizon)
    out = {}
    for f in fixtures or []:
        gw = f.get("event")
        if gw not in window:
            continue
        for side, opp_side, diff_key in (
            ("team_h", "team_a", "team_h_difficulty"),
            ("team_a", "team_h", "team_a_difficulty"),
        ):
            t = teams.get(f[side])
            if not t:
                continue
            rec = out.setdefault(t, {"fixtures": [], "total": 0})
            rec["fixtures"].append({
                "gw": gw,
                "opp": teams.get(f[opp_side], "?"),
                "home": side == "team_h",
                "fdr": f.get(diff_key, 3),
            })
            rec["total"] += f.get(diff_key, 3)
    for t, rec in out.items():
        n = len(rec["fixtures"]) or 1
        rec["avg_fdr"] = round(rec["total"] / n, 2)
        rec["games"] = len(rec["fixtures"])
        rec["fixtures"].sort(key=lambda x: x["gw"])
        del rec["total"]
    return dict(sorted(out.items(), key=lambda kv: kv[1]["avg_fdr"]))


def my_squad(entry_id, players, last_gw):
    """Your actual picks. Public endpoint, but only after a deadline has passed."""
    if not entry_id:
        return None
    meta = get(f"entry/{entry_id}/")
    if not meta:
        return None
    squad = {
        "name": meta.get("name"),
        "manager": f"{meta.get('player_first_name','')} {meta.get('player_last_name','')}".strip(),
        "overall_rank": meta.get("summary_overall_rank"),
        "total_points": meta.get("summary_overall_points"),
        "bank": money(meta.get("last_deadline_bank") or 0),
        "value": money(meta.get("last_deadline_value") or 0),
        "picks": [],
    }
    if last_gw:
        picks = get(f"entry/{entry_id}/event/{last_gw}/picks/")
        if picks:
            for p in picks.get("picks", []):
                pl = players.get(str(p["element"]))
                if not pl:
                    continue
                squad["picks"].append({
                    **{k: pl[k] for k in
                       ("name", "team", "pos", "cost", "status", "news",
                        "chance", "form", "sel", "ep_next")},
                    "slot": p["position"],
                    "captain": p.get("is_captain", False),
                    "vice": p.get("is_vice_captain", False),
                    "starting": p["position"] <= 11,
                })
            squad["chips_used"] = picks.get("active_chip")
    return squad


def main():
    DATA.mkdir(exist_ok=True)
    entry_id = os.environ.get("FPL_ENTRY_ID", "").strip()

    boot = get("bootstrap-static/")
    if not boot:
        print("FATAL: could not reach the FPL API", file=sys.stderr)
        return 1
    fixtures = get("fixtures/")

    events = boot["events"]
    nxt = next((e for e in events if e.get("is_next")), None)
    cur = next((e for e in events if e.get("is_current")), None)
    next_gw = nxt["id"] if nxt else (cur["id"] + 1 if cur else 1)

    players = build_players(boot)
    prev = {}
    if SNAPSHOT.exists():
        try:
            prev = json.loads(SNAPSHOT.read_text()).get("players", {})
        except Exception as e:
            print(f"WARN: unreadable snapshot, treating as first run: {e}", file=sys.stderr)

    changes = diff_players(players, prev)

    # Everyone currently unavailable, most-owned first - the standing worry list.
    flagged = sorted(
        [
            {"name": p["name"], "team": p["team"], "pos": p["pos"], "cost": p["cost"],
             "sel": p["sel"], "news": p["news"], "chance": p["chance"],
             "status": STATUS.get(p["status"], p["status"])}
            for p in players.values()
            if p["status"] != "a" or p["news"]
        ],
        key=lambda x: -x["sel"],
    )

    in_form = sorted(
        [
            {"name": p["name"], "team": p["team"], "pos": p["pos"], "cost": p["cost"],
             "form": p["form"], "sel": p["sel"], "xgi90": p["xgi90"], "ep_next": p["ep_next"]}
            for p in players.values()
            if p["form"] >= 4.0 and p["mins"] >= 90 and p["status"] == "a"
        ],
        key=lambda x: -x["form"],
    )[:30]

    digest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "next_gw": next_gw,
        "deadline": nxt["deadline_time"] if nxt else None,
        "is_first_run": not bool(prev),
        "totals": {"players": len(players), "flagged": len(flagged),
                   "managers": boot.get("total_players")},
        "changes": changes,
        "flagged": flagged,
        "in_form": in_form,
        "fixtures": fixture_outlook(boot, fixtures, next_gw),
        "squad": my_squad(entry_id, players, cur["id"] if cur else None),
    }

    # No community layer here by design. Bluesky was checked and abandoned:
    # of the 11 tracked FPL accounts only FPL General still posts there, so the
    # layer implied breadth it did not have. The real expert reading happens in
    # an interactive session via the browser pane, which cannot run on a
    # schedule (the desktop bridge does not attach to cloud scheduled runs).
    digest["community"] = {
        "status": "not_collected",
        "reason": "Expert reading requires a logged-in browser, which scheduled "
                  "cloud runs cannot reach. Run an interactive sweep instead.",
        "post_count": 0,
    }

    DIGEST.write_text(json.dumps(digest, indent=2))
    SNAPSHOT.write_text(json.dumps(
        {"captured_at": digest["generated_at"], "players": players}, indent=2))

    c = changes
    print(f"GW{next_gw} | deadline {digest['deadline']}")
    print(f"{len(players)} players, {len(flagged)} flagged")
    print(f"new injuries {len(c['new_injuries'])} | worsened {len(c['worsened'])} | "
          f"recovered {len(c['recovered'])} | rises {len(c['price_rises'])} | "
          f"falls {len(c['price_falls'])}")
    print("community: not collected (needs an interactive browser)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
