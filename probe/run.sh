#!/usr/bin/env bash
# Does NOAA VIIRS Kd490 (750 m, daily) near La Jolla track the Scripps Pier
# turbidity and chlorophyll sensors? Jul 1 - Oct 6 2026. Text only.
set -u
uv run python - <<'PY'
import csv, io, statistics, collections
import httpx

c = httpx.Client(timeout=120, headers={"User-Agent": "snorkel-status (https://github.com/wujin31/helen-snorkels)"})
CW = "https://coastwatch.noaa.gov/erddap/griddap"
boxes = {"lajolla": (32.80, 32.90, -117.32, -117.24), "northcounty": (32.98, 33.08, -117.34, -117.26),
         "pointloma": (32.68, 32.78, -117.30, -117.22)}

def viirs(ds, var, box, alt=True):
    la0, la1, lo0, lo1 = box
    q = f"{var}[(2026-07-05T00:00:00Z):1:(2026-10-06T00:00:00Z)]" + ("[(0.0)]" if alt else "") + f"[({la1}):1:({la0})][({lo0}):1:({lo1})]"
    r = c.get(f"{CW}/{ds}.csv?{q}")
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
for ds in ("noaacwNPPVIIRSchlaSectorVYDaily", "noaacwNPPN20VIIRSkd490SectorVYDaily", "noaacwN20VIIRSkd490SectorVYDaily"):
    try:
        r = c.get(f"{CW}/{ds}.das")
        print(ds, r.status_code)
    except Exception as e:
        print(ds, e)

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
    both = [d for d in kd[k] if d in turb]
    both_c = [d for d in kd[k] if d in chl]
    print(k, "days with kd:", len(kd[k]), "| spearman vs NTU", round(spearman([kd[k][d][0] for d in both], [turb[d] for d in both]), 2), f"(n={len(both)})",
          "| vs chl", round(spearman([kd[k][d][0] for d in both_c], [chl[d] for d in both_c]), 2), f"(n={len(both_c)})")
PY

# Dive-report sources: what they publish, how often, and their terms. Text only.
uv run python - <<'PY'
import re, html
import httpx
c = httpx.Client(timeout=60, follow_redirects=True, headers={"User-Agent": "snorkel-status (https://github.com/wujin31/helen-snorkels)"})
def text(body):
    body = re.sub(r"(?is)<(script|style).*?</\1>", " ", body)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", body))).strip()
def show(url, n=600, grep=None):
    try:
        r = c.get(url)
    except Exception as e:
        print("##", url, "ERR", e); return ""
    t = text(r.text)
    print("##", url, r.status_code, r.headers.get("content-type"), len(r.content))
    if grep:
        for m in re.finditer(grep, t, re.I):
            print("   ...", t[max(0, m.start() - 200): m.end() + 250])
    else:
        print("  ", t[:n])
    return r.text
feed = show("https://justgetwet.com/blogs/dive-reports-and-conditions.atom", 0)
for e in re.findall(r"(?s)<entry>(.*?)</entry>", feed)[:40]:
    title = re.search(r"<title>(.*?)</title>", e, re.S); pub = re.search(r"<published>(.*?)</published>", e)
    print(" -", pub.group(1)[:10] if pub else "?", html.unescape(title.group(1)).strip() if title else "?")
first = re.findall(r"(?s)<entry>(.*?)</entry>", feed)[:3]
for e in first:
    body = re.search(r"(?s)<content[^>]*>(.*?)</content>", e)
    if body:
        t = text(html.unescape(body.group(1)))
        for m in re.finditer(r"vis", t, re.I):
            print("   vis:", t[max(0, m.start() - 120): m.end() + 120]); 
show("https://justgetwet.com/robots.txt", 1200)
show("https://justgetwet.com/policies/terms-of-service", grep=r"(scrap|automat|robot|crawl|reproduc|copy|intellectual|content)")
show("https://www.divebums.com/", 1500)
show("https://www.divebums.com/robots.txt", 800)
for u in ("https://www.divebums.com/DiveReports/", "https://www.divebums.com/reports/", "https://www.divebums.com/local-info/visitor-info-general-conditions.html"):
    show(u, 500)
PY

