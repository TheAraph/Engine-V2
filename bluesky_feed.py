#!/usr/bin/env python3
"""
Bluesky ingestion for the FPL bot.

Bluesky's public AppView API needs no auth, no API key and no browser. Any FPL
account that mirrors there can be read from GitHub Actions unattended, which
sidesteps the X access problem entirely for those accounts.

Only accounts with no Bluesky presence need the Chrome-on-your-Mac route.
"""

import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = "https://public.api.bsky.app/xrpc"

# handle -> why it earns its place. Keep this list short and non-redundant:
# ten accounts all posting their team is nine accounts too many.
SOURCES = {
    # --- reasoning: the part actually worth copying ---
    "the-fplwire.bsky.social":  "The FPL Wire - Lateriser, Zophar and Pras in one account",
    "bencrellin.bsky.social":   "All-time #1; fixture and chip planning",
    "fplgeneral.bsky.social":   "FPL veteran, 59th Minute podcast",
    "giannibuttice.bsky.social": "Premier League and Sky Sports FPL pundit",

    # --- team news and leaks: genuinely ahead of the API ---
    "fpl-rockstar.bsky.social": "Team leaks ahead of confirmed lineups",
    "fpltoni.bsky.social":      "Team news specialist",

    # --- data and projections ---
    "fplradar.bsky.social":     "Data scientist; stats and graphics",
    "fplreview.com":            "Projections and multi-period solver",

    # --- volume creators: lower signal, keep for sentiment ---
    "fplharry-yt.bsky.social":  "FPL Harry - 138k subs, 4x top 6k",
    "fplraptor.com":            "FPL Raptor - 170k subs",
}

# On X only - no Bluesky presence found. These need the Chrome bridge.
X_ONLY = {
    "@BigManBakar":   "former #4 overall, statistical analysis",
    "@fpl_tactician": "tactical and fixture discussion",
    "@FFScout":       "Fantasy Football Scout (subscription site)",
}

# Terms that mark a post as decision-relevant rather than banter.
SIGNAL = (
    "injur", "doubt", "fit", "return", "ruled out", "knock", "strain",
    "suspend", "ban", "red card", "press conference", "presser",
    "lineup", "line-up", "xi", "starts", "benched", "rotat", "rested",
    "price", "transfer", "captain", "chip", "wildcard", "bench boost",
    "triple captain", "free hit", "deadline",
)


def get(endpoint, params, tries=3):
    url = f"{BASE}/{endpoint}?{urllib.parse.urlencode(params)}"
    for attempt in range(tries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "fpl-digest/1.0 (personal use)"}
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            if attempt == tries - 1:
                print(f"WARN: bluesky {endpoint} for "
                      f"{params.get('actor','?')}: {e}", file=sys.stderr)
                return None
            time.sleep(1.5 ** attempt)
    return None


def post_url(handle, uri):
    """at://did/app.bsky.feed.post/RKEY -> a browsable bsky.app link."""
    rkey = uri.rsplit("/", 1)[-1] if uri else ""
    return f"https://bsky.app/profile/{handle}/post/{rkey}" if rkey else ""


def parse_feed(handle, feed, since):
    """Pull the fields we care about out of a getAuthorFeed response."""
    out = []
    for item in (feed or {}).get("feed", []):
        post = item.get("post") or {}
        rec = post.get("record") or {}

        # skip reposts - we want what this account actually said
        if item.get("reason", {}).get("$type", "").endswith("reasonRepost"):
            continue
        # skip replies - usually mid-conversation and lack context
        if rec.get("reply"):
            continue

        created = rec.get("createdAt")
        if not created:
            continue
        try:
            ts = datetime.fromisoformat(created.replace("Z", "+00:00"))
        except ValueError:
            continue
        if since and ts <= since:
            continue

        text = (rec.get("text") or "").strip()
        if not text:
            continue

        low = text.lower()
        out.append({
            "handle": handle,
            "text": text,
            "at": created,
            "likes": post.get("likeCount", 0),
            "reposts": post.get("repostCount", 0),
            "replies": post.get("replyCount", 0),
            "signal": [t for t in SIGNAL if t in low],
            "url": post_url(handle, post.get("uri", "")),
        })
    return out


def collect(hours=26, limit=30):
    """Everything the tracked accounts said in the last `hours`."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    posts, reached, missing = [], [], []

    for handle in SOURCES:
        feed = get("app.bsky.feed.getAuthorFeed",
                   {"actor": handle, "limit": limit, "filter": "posts_no_replies"})
        if feed is None:
            missing.append(handle)
            continue
        reached.append(handle)
        posts.extend(parse_feed(handle, feed, since))
        time.sleep(0.4)  # be polite to a free public API

    # Decision-relevant first, then by engagement.
    posts.sort(key=lambda p: (-len(p["signal"]), -(p["likes"] + p["reposts"] * 2)))

    return {
        "window_hours": hours,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "accounts_reached": reached,
        "accounts_failed": missing,
        "x_only_not_covered": X_ONLY,
        "post_count": len(posts),
        "high_signal": [p for p in posts if p["signal"]][:40],
        "other": [p for p in posts if not p["signal"]][:20],
    }


if __name__ == "__main__":
    data = collect()
    print(json.dumps(data, indent=2))
    print(f"\n{data['post_count']} posts from "
          f"{len(data['accounts_reached'])}/{len(SOURCES)} accounts",
          file=sys.stderr)
