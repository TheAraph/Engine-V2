# FPL Bot — data engine

Pulls the full Fantasy Premier League API twice a day, diffs it against the
previous run, and commits a compact `data/digest.json`. A Claude Cowork session
reads that digest each morning, layers on community/press reading, and publishes
the dashboard.

Git history is the state store — that is what makes "what changed since
yesterday" possible across runs that share no memory.

## Setup

1. Create a **private** repo and push these files.
2. Settings → Secrets and variables → Actions → **Variables** → New variable:
   - Name: `FPL_ENTRY_ID`
   - Value: your FPL team ID (the number in the URL when you view your points page:
     `fantasy.premierleague.com/entry/<THIS NUMBER>/event/1`)
3. Settings → Actions → General → Workflow permissions → **Read and write**.
4. Actions tab → *FPL digest* → **Run workflow** to seed the first snapshot.

The first run produces an empty `changes` block (nothing to diff against) and
sets `is_first_run: true`. The second run onward is where the value starts.

## What lands in digest.json

| Key | Contents |
|---|---|
| `changes.new_injuries` | Players who became unavailable since the last run, most-owned first |
| `changes.worsened` | Chance-of-playing downgrades (e.g. 75% → 25%) |
| `changes.recovered` | Players cleared to play again |
| `changes.price_rises` / `price_falls` | Overnight price movement |
| `changes.form_risers` | Form up ≥1.0 and now ≥4.0 |
| `changes.ownership_surges` | Ownership up ≥1 percentage point — what the crowd is doing |
| `flagged` | Everyone currently unavailable or carrying news |
| `in_form` | Top 30 by form, available, ≥90 minutes played |
| `fixtures` | Next 5 GWs per team, sorted by average difficulty (easiest first) |
| `squad` | Your XI and bench with live status, rank, bank and team value |
| `community` | Last 26h of posts from tracked Bluesky FPL accounts, decision-relevant ones ranked first |

## The community layer

`bluesky_feed.py` reads tracked FPL accounts through Bluesky's **public API** —
no auth, no API key, no browser, no cost. That is why it can run unattended in
Actions alongside the data pull.

Posts are filtered (no reposts, no replies, no empties), scored against a set of
decision-relevant terms (injury, presser, lineup, price, chip, deadline...) and
ranked signal-first, then by engagement. Edit `SOURCES` in that file to change
who is tracked.

`X_ONLY` lists accounts with no Bluesky presence. Those need the Chrome-on-your-Mac
route and are not covered by this workflow.

If Bluesky is unreachable the digest still completes — the FPL API data is the
part that must always land.

## Timing notes

- Cron is **UTC**. At the October DST change Malta shifts UTC+2 → UTC+1, so both
  cron lines need shifting by an hour to keep the same local time.
- GitHub can delay scheduled runs during peak load; the 06:30 slot has headroom
  before the morning brief.
- Scheduled workflows are disabled after 60 days of repo inactivity. The daily
  commit keeps the repo active, so this only bites if the bot is already broken.

## Running it locally

    FPL_ENTRY_ID=1234567 python3 fpl_digest.py
