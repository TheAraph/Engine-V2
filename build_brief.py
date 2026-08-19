#!/usr/bin/env python3
"""
Daily FPL brief - API layer only.

Runs in a cloud scheduled session with NO browser access, so it never depends
on Chrome. Reads the digest the GitHub Action committed, renders the dashboard,
and prints an ALERTS block the calling session turns into a push notification.

Usage:  python3 build_brief.py [ENTRY_ID] > /dev/null
Writes: dashboard.html   in the current directory
"""
import json, html, sys, urllib.request
from datetime import datetime, timezone

RAW = "https://raw.githubusercontent.com/TheAraph/Engine-V2/main/data"
esc = lambda s: html.escape(str(s))

def fetch(name):
    with urllib.request.urlopen(f"{RAW}/{name}", timeout=45) as r:
        return json.loads(r.read().decode())

d = fetch("digest.json")
P = fetch("snapshot.json")["players"]
FX = d["fixtures"]
FDRC = {1:"#0ca30c",2:"#0ca30c",3:"#fab219",4:"#ec835a",5:"#d03b3b"}

dl = datetime.fromisoformat(d["deadline"].replace("Z","+00:00")) if d.get("deadline") else None
hrs = (dl - datetime.now(timezone.utc)).total_seconds()/3600 if dl else 999

# ---------- alerts: what actually needs the user's attention ----------
alerts, ch = [], d["changes"]
squad = d.get("squad") or {}
own = {p["name"] for p in squad.get("picks", [])}
for p in ch["new_injuries"]:
    mine = p["name"] in own
    if mine or p["sel"] >= 10:
        alerts.append(("YOUR SQUAD" if mine else "Widely owned",
                       f'{p["name"]} ({p["team"]}) flagged: {p["news"]}'))
for p in ch["worsened"]:
    if p["name"] in own or p["sel"] >= 15:
        alerts.append(("Downgrade", f'{p["name"]} {p["from"]}% -> {p["to"]}%'))
for p in ch["price_falls"][:4]:
    if p["name"] in own:
        alerts.append(("Price fall", f'{p["name"]} to £{p["to"]}m'))
if 0 < hrs <= 30:
    alerts.append(("Deadline", f"GW{d['next_gw']} in {hrs:.0f}h — open Chrome and say “sweep” "
                                "if you want the expert layer refreshed"))

def rows(items, cols):
    return "".join("<tr>" + "".join(f'<td class="{c}">{v}</td>' for c, v in zip(cols, it)) + "</tr>"
                   for it in items)

def chg(key, extra=None):
    out = []
    for p in ch[key][:8]:
        tail = extra(p) if extra else esc(p.get("news",""))
        out.append((esc(p["name"]), esc(p["team"]), f'£{p["cost"]:.1f}', f'{p["sel"]:.1f}%', tail))
    return rows(out, ["pn","dim","num","num","dim sm"]) or '<tr><td colspan="5" class="dim">Nothing today.</td></tr>'

ticker = ""
for t, v in FX.items():
    cells = ""
    for f in v["fixtures"][:5]:
        cells += (f'<td class="fx" style="--c:{FDRC.get(f["fdr"],"#fab219")}" '
                  f'title="GW{f["gw"]} vs {esc(f["opp"])}{"" if f["home"] else " (a)"} — difficulty {f["fdr"]}">'
                  f'<span class="opp">{esc(f["opp"])}</span><span class="fdrn">{f["fdr"]}</span></td>')
    cells += '<td class="fx blank"></td>' * (5 - len(v["fixtures"][:5]))
    ticker += f'<tr><th>{esc(t)}</th><td class="num">{v["avg_fdr"]:.2f}</td>{cells}</tr>'

flag = rows([(esc(p["name"]), esc(p["team"]), f'£{p["cost"]:.1f}', f'{p["sel"]:.1f}%',
             ("OUT" if p["chance"] == 0 else ("?" if p["chance"] is None else f'{p["chance"]}%')),
             esc(p["news"])) for p in d["flagged"][:12]],
            ["pn","dim","num","num","pill","dim sm"])

alert_html = "".join(
    f'<div class="al"><span class="k">{esc(k)}</span><span>{esc(v)}</span></div>' for k, v in alerts
) or '<div class="dim">Nothing needs your attention today.</div>'

HTML = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>FPL Brief — GW{d['next_gw']}</title><style>
*{{box-sizing:border-box}}
:root{{--s:#fcfcfb;--p:#f9f9f7;--i:#0b0b0b;--i2:#52514e;--m:#898781;--g:#e1e0d9;
--r:rgba(11,11,11,.10);--a:#2a78d6;color-scheme:light}}
@media(prefers-color-scheme:dark){{:root{{--s:#1a1a19;--p:#0d0d0d;--i:#fff;--i2:#c3c2b7;
--g:#2c2c2a;--r:rgba(255,255,255,.10);--a:#3987e5;color-scheme:dark}}}}
body{{margin:0;background:var(--p);color:var(--i);font:15px/1.55 system-ui,-apple-system,sans-serif}}
.w{{max-width:1000px;margin:0 auto;padding:26px 20px 70px}}
h1{{font-size:25px;margin:0 0 4px;letter-spacing:-.02em}}
h2{{font-size:14px;margin:0 0 13px;letter-spacing:.06em;text-transform:uppercase;color:var(--m);font-weight:600}}
.sub{{color:var(--i2);margin:0 0 22px;font-size:14px}}
section{{background:var(--s);border:1px solid var(--r);border-radius:14px;padding:19px;margin-bottom:17px}}
table{{width:100%;border-collapse:collapse;font-size:13.5px}}
th{{text-align:left;font-size:11px;color:var(--m);text-transform:uppercase;letter-spacing:.06em;padding:6px 8px;font-weight:600}}
td{{padding:7px 8px;border-top:1px solid var(--g)}}
.num{{font-variant-numeric:tabular-nums;text-align:right;white-space:nowrap}}
.dim{{color:var(--i2)}} .pn{{font-weight:600;white-space:nowrap}} .sm{{font-size:12.5px}}
.al{{display:flex;gap:11px;align-items:baseline;padding:9px 0;border-top:1px solid var(--g);font-size:14px}}
.al:first-child{{border-top:0}}
.k{{font-size:10px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;background:var(--a);
color:#fff;padding:2px 7px;border-radius:4px;white-space:nowrap}}
.pill{{font-weight:650;font-size:11.5px}}
.fx{{padding:4px;text-align:center;width:64px}}
.fx .opp{{display:block;font-size:11px;font-weight:600;color:#fff;background:var(--c);border-radius:6px 6px 0 0;padding:3px 2px}}
.fx .fdrn{{display:block;font-size:10px;background:var(--p);border:1px solid var(--r);border-top:0;
border-radius:0 0 6px 6px;padding:1px;color:var(--i2);font-variant-numeric:tabular-nums}}
.fx.blank{{opacity:.25}}
.stale{{background:var(--p);border:1px solid var(--r);border-radius:10px;padding:12px;font-size:13px;color:var(--i2)}}
footer{{color:var(--m);font-size:12px;text-align:center;margin-top:24px}}
</style></head><body><div class="w">
<h1>FPL Brief</h1>
<p class="sub">Gameweek {d['next_gw']} · deadline {esc(d['deadline'][:16].replace('T',' '))} UTC ·
{hrs:.0f}h remaining</p>
<section><h2>Needs your attention</h2>{alert_html}</section>
<section><h2>Newly flagged</h2><table>{chg('new_injuries')}</table></section>
<section><h2>Chance downgrades</h2><table>{chg('worsened', lambda p: f'{p["from"]}% to {p["to"]}%')}</table></section>
<section><h2>Recovered</h2><table>{chg('recovered')}</table></section>
<section><h2>Price falls</h2><table>{chg('price_falls', lambda p: f'£{p["from"]} to £{p["to"]}')}</table></section>
<section><h2>Price rises</h2><table>{chg('price_rises', lambda p: f'£{p["from"]} to £{p["to"]}')}</table></section>
<section><h2>All flagged players</h2><table><thead><tr><th>Player</th><th>Team</th><th class="num">Price</th>
<th class="num">Owned</th><th>Chance</th><th>Reason</th></tr></thead><tbody>{flag}</tbody></table></section>
<section><h2>Fixtures — next 5</h2><table><thead><tr><th>Team</th><th class="num">Avg</th>
<th>GW1</th><th>GW2</th><th>GW3</th><th>GW4</th><th>GW5</th></tr></thead><tbody>{ticker}</tbody></table></section>
<section><h2>Community layer</h2><div class="stale">Not included in the scheduled brief. Cloud scheduled
sessions cannot reach Chrome — the extension is proxied through the desktop bridge, which only attaches to
interactive sessions. Open Chrome, start a session and say <strong>“sweep”</strong> to refresh the eleven
expert timelines.</div></section>
<footer>Official FPL API · {d['totals']['players']} players · digest {esc(d['generated_at'][:16].replace('T',' '))} UTC</footer>
</div></body></html>"""

open("dashboard.html","w").write(HTML)
print("ALERTS_START")
for k, v in alerts: print(f"{k}: {v}")
print("ALERTS_END")
print(f"deadline_hours={hrs:.1f} flagged={d['totals']['flagged']} gw={d['next_gw']}", file=sys.stderr)
