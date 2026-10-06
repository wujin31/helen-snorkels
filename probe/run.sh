#!/usr/bin/env bash
# Does NOAA VIIRS Kd490 (750 m, daily) near La Jolla track the Scripps Pier
# turbidity and chlorophyll sensors? Jul 1 - Oct 6 2026. Text only.
set -u
uv run python - <<'PY'
import csv, io, statistics, collections, time
import httpx

c = httpx.Client(timeout=120, headers={"User-Agent": "snorkel-status (https://github.com/wujin31/helen-snorkels)"})
CW = "https://coastwatch.noaa.gov/erddap/griddap"
boxes = {"lajolla": (32.80, 32.90, -117.32, -117.24), "lajolla_near": (32.84, 32.88, -117.29, -117.25)}

def viirs(ds, var, box, alt=True):
    la0, la1, lo0, lo1 = box
    q = f"{var}[(2026-07-05T00:00:00Z):1:(last)]" + ("[(0.0)]" if alt else "") + f"[({la1}):1:({la0})][({lo0}):1:({lo1})]"
    for attempt in range(4):
        r = c.get(f"{CW}/{ds}.csv?{q}")
        if r.status_code == 200:
            break
        time.sleep(20)
    print(ds, box, r.status_code, len(r.content))
    if r.status_code != 200:
        print(r.text[:300]); return {}
    per = collections.defaultdict(list)
    for row in list(csv.reader(io.StringIO(r.text)))[2:]:
        try:
            v = float(row[-1])
        except ValueError:
            continue
        if v == v:
            per[row[0][:10]].append(v)
    return {d: (statistics.median(vs), len(vs)) for d, vs in per.items()}

kd = {name: viirs("noaacwNPPVIIRSkd490SectorVYDaily", "kd_490", b) for name, b in boxes.items()}
chl_v = {name: viirs("noaacwNPPVIIRSchlaSectorVYDaily", "chlor_a", b) for name, b in boxes.items()}

url = ("https://erddap.cencoos.org/erddap/tabledap/scripps-pier-automated-shore-sta-1.csv"
       "?time,sea_water_turbidity_eco,sea_water_turbidity_eco_qc_agg,mass_concentration_of_chlorophyll_in_sea_water_eco,mass_concentration_of_chlorophyll_in_sea_water_eco_qc_agg"
       "&time>=2026-07-01T00:00:00Z&time<=2026-10-06T00:00:00Z")
r = c.get(url)
print("pier", r.status_code, len(r.content))
turb, chl = collections.defaultdict(list), collections.defaultdict(list)
for row in list(csv.reader(io.StringIO(r.text)))[2:]:
    if len(row[0]) < 13 or not row[0][11:13].isdigit():
        continue
    d, h = row[0][:10], int(row[0][11:13])
    if not 17 <= h <= 22:   # around the afternoon VIIRS pass (~20-21 UTC)
        continue
    for idx, out in ((1, turb), (3, chl)):
        try:
            v, q = float(row[idx]), row[idx + 1]
        except (ValueError, IndexError):
            continue
        if q in ("1", "2") and v == v:
            out[d].append(v)
turb = {d: statistics.median(v) for d, v in turb.items()}
chl = {d: statistics.median(v) for d, v in chl.items()}

def rank(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i]); r = [0.0] * len(xs)
    for k, i in enumerate(order): r[i] = k
    return r
def spearman(a, b):
    if len(a) < 5: return float("nan")
    ra, rb = rank(a), rank(b); ma, mb = statistics.mean(ra), statistics.mean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = (sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb)) ** 0.5
    return num / den if den else float("nan")

print(f"{'day':10} {'NTU':>6} {'chl':>6} | " + " ".join(f"{k:>16}" for k in boxes))
days = sorted(set(turb) | set(kd["lajolla"]))
for d in days:
    cells = " ".join(f"{kd[k][d][0]:10.3f} ({kd[k][d][1]:3d})" if d in kd[k] else f"{'':>16}" for k in boxes)
    print(f"{d} {turb.get(d, float('nan')):6.2f} {chl.get(d, float('nan')):6.2f} | {cells}")
for k in boxes:
    both_v = [d for d in chl_v[k] if d in chl]
    print(k, "viirs chl days:", len(chl_v[k]), "| spearman viirs chl vs pier chl", round(spearman([chl_v[k][d][0] for d in both_v], [chl[d] for d in both_v]), 2), f"(n={len(both_v)})")
    both = [d for d in kd[k] if d in turb]
    both_c = [d for d in kd[k] if d in chl]
    print(k, "days with kd:", len(kd[k]), "| spearman vs NTU", round(spearman([kd[k][d][0] for d in both], [turb[d] for d in both]), 2), f"(n={len(both)})",
          "| vs chl", round(spearman([kd[k][d][0] for d in both_c], [chl[d] for d in both_c]), 2), f"(n={len(both_c)})")
PY

uv run python - <<'PY'
import re, html, time
import httpx
c = httpx.Client(timeout=60, follow_redirects=True, headers={"User-Agent": "snorkel-status (https://github.com/wujin31/helen-snorkels)"})
def text(body):
    body = re.sub(r"(?is)<(script|style|noscript|svg).*?</\1>", " ", body)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", body))).strip()
def get(url):
    time.sleep(3)
    try:
        r = c.get(url)
        print("##", url, r.status_code, len(r.content))
        return r
    except Exception as e:
        print("##", url, "ERR", type(e).__name__, e)
        return None
for host in ("justgetwet.com", "diveviz.com"):
    print("\n==========", host)
    r = get(f"https://{host}/robots.txt")
    if r is not None and r.status_code == 200:
        for line in r.text.splitlines():
            if line.lower().startswith(("disallow: /blogs", "allow: /blogs", "user-agent: *", "crawl-delay")) or "blog" in line.lower():
                print("   robots:", line)
    r = get(f"https://{host}/policies/terms-of-service")
    if r is not None and r.status_code == 200:
        t = text(r.text)
        i = t.find("OVERVIEW") if "OVERVIEW" in t else 0
        print("   tos chars:", len(t))
        for m in re.finditer(r"[^.]*\b(scrap\w*|crawl\w*|spider\w*|reproduce|duplicate|robot\w*|automat\w*|data mining)\b[^.]*\.", t, re.I):
            print("   tos:", m.group(0).strip()[:400])
    for path in ("/blogs/dive-reports-and-conditions", "/blogs/daily-dive-report"):
        r = get(f"https://{host}{path}")
        if r is None or r.status_code != 200:
            continue
        posts = re.findall(r'href="(/blogs/[^"/]+/[^"?#]+)"', r.text)
        dates = re.findall(r'datetime="([^"]+)"', r.text)
        print("   posts on page 1:", len(set(posts)), "dates:", sorted(set(d[:10] for d in dates), reverse=True)[:20])
        for p in list(dict.fromkeys(posts))[:2]:
            rp = get(f"https://{host}{p}")
            if rp is not None and rp.status_code == 200:
                t = text(rp.text)
                for m in list(re.finditer(r"vis", t, re.I))[:4]:
                    print("     vis:", t[max(0, m.start() - 100): m.end() + 100])
PY
