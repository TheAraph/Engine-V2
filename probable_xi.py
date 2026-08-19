#!/usr/bin/env python3
"""
Probable XIs for all 20 clubs, inferred from FPL's own data.

IMPORTANT: these are INFERRED, not reported lineups. The model blends last
season's starts with price rank inside each club and position — price is how
FPL itself encodes expected role, which is the only signal a summer signing
with no Premier League history has. Anyone with zero starts is marked UNPROVEN
so the guesswork is visible rather than hidden.

Also surfaces penalty, free-kick and corner order, which the API publishes
officially — that is fact, not inference.

Reads data/snapshot.json (needs the enriched fields), writes data/probable_xi.html
"""
import json, html
from pathlib import Path
from collections import defaultdict

esc = lambda s: html.escape(str(s))
SNAP = Path("data/snapshot.json")
players = json.loads(SNAP.read_text())["players"]
FORM = {"GKP": 1, "DEF": 4, "MID": 4, "FWD": 2}   # 4-4-2 shape for the projected XI

teams = defaultdict(list)
for pid, p in players.items():
    if p.get("status") in ("u", "n"):        # left the club / not registered
        continue
    teams[p["team"]].append({**p, "id": pid})

def rank_club(squad):
    """Score each player's likelihood of starting, within his own club."""
    for pos in ("GKP", "DEF", "MID", "FWD"):
        grp = [p for p in squad if p["pos"] == pos]
        if not grp:
            continue
        costs = sorted({p["cost"] for p in grp})
        for p in grp:
            # price percentile within club+position: how FPL rates his expected role
            price_pct = (costs.index(p["cost"]) + 1) / len(costs)
            starts_pct = min(p.get("starts", 0) / 34, 1.0)
            p["unproven"] = p.get("starts", 0) == 0
            p["score"] = 0.5 * starts_pct + 0.5 * price_pct
            if p["status"] != "a" or p["news"]:
                p["score"] *= 0.35          # flagged players drop but do not vanish
    return squad

def badge(p):
    bits = []
    if p.get("pens") == 1:      bits.append('<span class="sp pen">PEN 1</span>')
    elif p.get("pens"):         bits.append(f'<span class="sp">PEN {p["pens"]}</span>')
    if p.get("fks") == 1:       bits.append('<span class="sp">FK 1</span>')
    if p.get("corners") == 1:   bits.append('<span class="sp">COR 1</span>')
    if p.get("unproven"):       bits.append('<span class="sp unp">UNPROVEN</span>')
    if p["news"]:               bits.append(f'<span class="sp out">{esc(p["news"][:26])}</span>')
    return "".join(bits)

cards = ""
for team in sorted(teams):
    squad = rank_club(teams[team])
    xi, bench = [], []
    for pos, n in FORM.items():
        grp = sorted([p for p in squad if p["pos"] == pos], key=lambda p: -p["score"])
        xi += grp[:n]
        bench += grp[n:n + 2]
    rows = ""
    for p in xi:
        rows += (f'<tr><td class="pos">{esc(p["pos"])}</td><td class="pn">{esc(p["name"])}</td>'
                 f'<td class="num">£{p["cost"]:.1f}</td>'
                 f'<td class="num">{p.get("starts",0)}</td>'
                 f'<td class="num">{p["sel"]:.1f}%</td><td>{badge(p)}</td></tr>')
    alts = ", ".join(f'{esc(p["name"])} ({p.get("starts",0)})'
                     for p in sorted(bench, key=lambda p: -p["score"])[:5])
    flagged = [p for p in squad if p["news"]]
    warn = (f'<div class="warn">{len(flagged)} flagged: '
            + ", ".join(esc(p["name"]) for p in flagged[:5]) + "</div>") if flagged else ""
    cards += (f'<section><h2>{esc(team)}</h2>{warn}<table><thead><tr><th></th><th>Player</th>'
              f'<th class="num">Price</th><th class="num">Starts</th><th class="num">Owned</th>'
              f'<th>Notes</th></tr></thead><tbody>{rows}</tbody></table>'
              f'<div class="alts"><strong>Next in line:</strong> {alts}</div></section>')

HTML = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Probable XIs</title><style>
*{{box-sizing:border-box}}
:root{{--s:#fcfcfb;--p:#f9f9f7;--i:#0b0b0b;--i2:#52514e;--m:#898781;--g:#e1e0d9;
--r:rgba(11,11,11,.10);--a:#2a78d6;color-scheme:light}}
@media(prefers-color-scheme:dark){{:root{{--s:#1a1a19;--p:#0d0d0d;--i:#fff;--i2:#c3c2b7;
--g:#2c2c2a;--r:rgba(255,255,255,.10);--a:#3987e5;color-scheme:dark}}}}
body{{margin:0;background:var(--p);color:var(--i);font:15px/1.5 system-ui,-apple-system,sans-serif}}
.w{{max-width:1240px;margin:0 auto;padding:26px 20px 70px}}
h1{{font-size:25px;margin:0 0 6px;letter-spacing:-.02em}}
.lede{{color:var(--i2);font-size:14px;margin:0 0 8px;max-width:70ch}}
.caveat{{background:var(--s);border:1px solid var(--r);border-left:3px solid var(--a);
border-radius:10px;padding:13px 15px;font-size:13.5px;color:var(--i2);margin:0 0 22px;max-width:80ch}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(370px,1fr));gap:16px}}
section{{background:var(--s);border:1px solid var(--r);border-radius:13px;padding:16px}}
h2{{font-size:13px;margin:0 0 11px;letter-spacing:.07em;text-transform:uppercase;color:var(--m);font-weight:700}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{text-align:left;font-size:10px;color:var(--m);text-transform:uppercase;letter-spacing:.06em;padding:4px 5px;font-weight:600}}
td{{padding:5px;border-top:1px solid var(--g)}}
.num{{font-variant-numeric:tabular-nums;text-align:right;white-space:nowrap}}
.pos{{color:var(--m);font-size:10.5px;font-weight:700;width:30px}}
.pn{{font-weight:600;white-space:nowrap}}
.sp{{display:inline-block;font-size:9.5px;font-weight:700;letter-spacing:.04em;padding:1px 5px;
border-radius:4px;background:var(--p);border:1px solid var(--r);color:var(--i2);margin-right:3px}}
.sp.pen{{background:#0ca30c;color:#fff;border-color:transparent}}
.sp.unp{{background:#fab219;color:#0b0b0b;border-color:transparent}}
.sp.out{{background:#d03b3b;color:#fff;border-color:transparent}}
.alts{{margin-top:9px;font-size:12px;color:var(--i2)}}
.warn{{font-size:12px;color:#d03b3b;margin-bottom:8px}}
footer{{color:var(--m);font-size:12px;text-align:center;margin-top:28px}}
</style></head><body><div class="w">
<h1>Probable XIs — all 20 clubs</h1>
<p class="lede">A most-likely eleven per club, plus who's next in line, penalty and set-piece order,
and every flagged player.</p>
<div class="caveat"><strong>These are inferred, not reported.</strong> The model blends last season's
starts with each player's price rank inside his own club and position — price is how FPL itself encodes
expected role, and it's the only signal a summer signing has. Players with zero starts are tagged
<span class="sp unp">UNPROVEN</span> so the guesswork stays visible. <strong>Penalty, free-kick and corner
order are official API data</strong>, not inference. For actual reported lineups, open Chrome and ask for
a sweep of the eleven expert accounts.</div>
<div class="grid">{cards}</div>
<footer>Built from the official FPL API · inferred XIs, official set-piece order</footer>
</div></body></html>"""

Path("data").mkdir(exist_ok=True)
Path("data/probable_xi.html").write_text(HTML)
print(f"probable_xi.html written: {len(teams)} clubs, {len(HTML)} bytes")
