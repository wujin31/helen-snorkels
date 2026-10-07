#!/usr/bin/env bash
# Cross-check the county's La Jolla Cove advisory (site 105) against the raw
# record and Swim Guide's public page. Text only.
set -u
uv run python - <<'PY'
import json, re, html
import httpx
from datetime import datetime, UTC
from snorkel.config import load_sources, load_spots
from snorkel.fetch.base import FetchContext
from snorkel.fetch import water_quality

sources = load_sources()
c = httpx.Client(timeout=60, follow_redirects=True, headers={"User-Agent": "snorkel-status (https://github.com/wujin31/helen-snorkels)"})
ctx = FetchContext(client=c, now=datetime.now(UTC), spots=load_spots(), params=sources.sources["water_quality.county"], location=sources.location)
items = water_quality.capture_county(ctx)
for it in items:
    if not hasattr(it, "content"):
        print("ERR", it); continue
    d = json.loads(it.content)
    rows = d["data"]["List"]["List"]
    for row in rows:
        site = row.get("Site", row)
        if str(site.get("Id")) in ("105", "106", "54", "50"):
            slim = {k: v for k, v in row.items() if k != "Site"}
            print(site.get("Id"), site.get("BeachName"), "|", site.get("LocationName"), "| row keys/values:", json.dumps(slim)[:600])
            print("   site keys:", json.dumps({k: v for k, v in site.items() if k not in ("Latitude", "Longitude")})[:600])
    counts = {}
    for row in rows:
        p = row.get("PriorityMax", row.get("Site", {}).get("PriorityMax"))
        counts[p] = counts.get(p, 0) + 1
    print("PriorityMax counts:", counts)
r = c.get("https://www.theswimguide.org/beach/1986")
t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(script|style).*?</\1>", " ", r.text))))
print("swimguide", r.status_code)
for m in list(re.finditer(r"(advisory|closed|closure|open|pass|fail|last sampled|last tested|updated)", t, re.I))[:12]:
    print("   ", t[max(0, m.start() - 90): m.end() + 90])
PY
