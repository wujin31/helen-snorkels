#!/usr/bin/env bash
# The live NWS SRF (SGX): period headers in each segment, and what parse_srf makes of them.
set -u
uv run python - <<'PY'
import httpx, re
from snorkel.parse.srf import parse_srf
c = httpx.Client(timeout=60, headers={"User-Agent": "snorkel-status (https://github.com/wujin31/helen-snorkels)", "Accept": "application/ld+json"})
listing = c.get("https://api.weather.gov/products/types/SRF/locations/SGX").json()
for p in listing["@graph"][:3]:
    print("listed:", p["id"], p["issuanceTime"])
latest = listing["@graph"][0]
body = c.get(f"https://api.weather.gov/products/{latest['id']}").content
import json
text = json.loads(body)["productText"]
for line in text.splitlines():
    if re.match(r"^\.[A-Z]", line) or line.endswith("Coastal Areas-") or re.match(r"^\d{3,4} [AP]M", line):
        print("  |", line)
f = parse_srf(body)
print("parsed:", f.issued, f.zone)
for p in f.periods:
    print("  ", p.name, p.day, p.rip_risk, p.surf_ft, p.water_temp_f)
PY
