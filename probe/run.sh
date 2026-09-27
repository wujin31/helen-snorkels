#!/usr/bin/env bash
# Discovery round 3: county status codes and site IDs, cam embed, CoastWatch, first real score.
set -u
section() { printf '\n\n======== %s ========\n' "$*"; }

section "County sites"
uv run snorkel probe water_quality.county --save-fixture | grep -E "^(OK|ERROR|  saved)"
uv run python - <<'PY'
import json, collections, glob
from snorkel.parse.county import parse_sites
raw = open(glob.glob("tests/fixtures/water_quality.county/*.json")[0], "rb").read()
sites = parse_sites(raw)
print(len(sites), "sites; PriorityMax counts:", collections.Counter(s.priority for s in sites))
for s in sites:
    if s.lat and 32.83 < s.lat < 32.88 and -117.29 < s.lon < -117.24:
        print(f"  {s.id:>5} p={s.priority} {s.beach} | {s.location} | {s.lat},{s.lon}")
print("non-zero priority sites:")
for s in sites:
    if s.priority:
        print(f"  {s.id:>5} p={s.priority} {s.beach} | {s.location}")
row = json.loads(raw)["data"]["List"]["List"][0]
print("row keys:", list(row.keys()))
PY
section "County JS: PriorityMax / legend context"
curl -s "https://cosdapps.sandiegocounty.gov/sdbeachinfo/scripts/CoSD_Beach_Water_CW.MainFlow.HomeBlockNew.mvc.js" | grep -oE ".{0,300}PriorityMax.{0,300}" | head -12
curl -s "https://cosdapps.sandiegocounty.gov/sdbeachinfo/scripts/CoSD_Beach_Water_CW.MainFlow.BlockLegend.mvc.js" | grep -oiE ".{0,200}(advisory|closure|warning).{0,200}" | head -12
curl -s "https://cosdapps.sandiegocounty.gov/sdbeachinfo/scripts/CoSD_Beach_Water_CW.MainFlow.HomeBlockNew.mvc.js" | grep -oiE ".{0,160}(Priority|EventType).{0,160}" | head -20

section "cam probe (embed)"
uv run snorkel probe cam.scripps_pier

section "CoastWatch kd490 + chla sector fixtures"
curl -s "https://coastwatch.noaa.gov/erddap/info/noaacwNPPVIIRSchlaSectorVYDaily/index.csv" | grep -E "^(variable|dimension)," | head -6
uv run snorkel probe coastwatch.viirs --save-fixture | grep -E "^(OK|ERROR|  saved)"

section "HABs fixture"
uv run snorkel probe sccoos.habs --save-fixture | grep -E "^(OK|ERROR|  saved)"

section "First real score"
uv run snorkel score --out probe/status.json
python3 -c "import json; d=json.load(open('probe/status.json')); print(json.dumps({k: d[k] for k in ('summary','best_bet')}, indent=1)); [print(s['id'], s['verdict'], s['confidence'], s['vis_ft'], '|', s['reason'], '| gates', s['gates'], '| cautions', s['cautions'], '| cond', s['conditions']) for s in d['spots']]; [print('  src', h['id'], h['ok'], h['stale'], h['error']) for h in d['sources']]"
