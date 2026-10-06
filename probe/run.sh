#!/usr/bin/env bash
# Discovery for the next spots and the NWS surf zone forecast. Text only.
set -u
section() { printf '\n\n======== %s ========\n' "$*"; }
UA="snorkel-status (https://github.com/wujin31/helen-snorkels)"

section "Nearest CDIP MOP points for every spot"
uv run snorkel discover-mops --window 25 2>&1 | grep -vE "^\s*$" | awk '/^[a-z-]+ \(/ {print; n=0; next} {if (n<3) print; n++}'

section "NWS SGX product types"
curl -sS -A "$UA" "https://api.weather.gov/products/locations/SGX/types" | python3 -c "import json,sys; d=json.load(sys.stdin); print([t['productCode'] for t in d.get('@graph',[])])"

section "Latest SRF (Surf Zone Forecast) for SGX"
id=$(curl -sS -A "$UA" "https://api.weather.gov/products/types/SRF/locations/SGX" | python3 -c "import json,sys; g=json.load(sys.stdin).get('@graph',[]); print(g[0]['id'] if g else '')")
echo "product id: $id"
[ -n "$id" ] && curl -sS -A "$UA" "https://api.weather.gov/products/$id" | python3 -c "import json,sys; print(json.load(sys.stdin)['productText'])" | head -150

section "CDIP buoys near Point Loma / North County (latest realtime list)"
curl -sS -A "$UA" "https://cdip.ucsd.edu/data_access/justdar.cdip?stations" 2>/dev/null | head -5
curl -sS -A "$UA" "https://thredds.cdip.ucsd.edu/thredds/catalog/cdip/realtime/catalog.xml" | grep -oE "[0-9]{3}p1_rt\.nc" | sort -u | head -60 | tr '\n' ' '
