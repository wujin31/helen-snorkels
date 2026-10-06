#!/usr/bin/env bash
# Backtest the visibility proxy against the Scripps Pier turbidity sensor,
# Jul-Oct 2026: does near-bottom wave motion (and chlorophyll, wind, rain)
# track measured clarity at the pier? Text only.
set -u
uv run python - <<'PY'
import csv, io, math, statistics, time
from datetime import datetime, timedelta, timezone
import httpx
import numpy as np
from snorkel.fetch.cdip import dataset_subset_bytes
from snorkel.parse.cdip import parse_waves
from snorkel.features.waves import spectral_orbital_velocity, bottom_orbital_velocity, decayed_mean

UTC = timezone.utc
START = datetime(2026, 7, 1, tzinfo=UTC)
END = datetime(2026, 10, 6, tzinfo=UTC)
c = httpx.Client(timeout=180, headers={"User-Agent": "snorkel-status (https://github.com/wujin31/helen-snorkels)"})

def t(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))

# 1. Pier turbidity and chlorophyll, hourly-ish, good QC only.
url = ("https://erddap.cencoos.org/erddap/tabledap/scripps-pier-automated-shore-sta-1.csv"
       "?time,sea_water_turbidity_eco,sea_water_turbidity_eco_qc_agg,"
       "mass_concentration_of_chlorophyll_in_sea_water_eco,mass_concentration_of_chlorophyll_in_sea_water_eco_qc_agg"
       f"&time>={START:%Y-%m-%dT%H:%M:%SZ}&time<={END:%Y-%m-%dT%H:%M:%SZ}")
pier = []
for row in list(csv.reader(io.StringIO(c.get(url).text)))[2:]:
    try:
        when = t(row[0])
    except ValueError:
        continue
    def good(i):
        try:
            v = float(row[i])
        except ValueError:
            return None
        return v if row[i + 1] in ("1", "2") and v == v else None
    pier.append((when, good(1), good(3)))
print("pier rows", len(pier))

# 2. MOP nowcast at the Marine Room (D0496) and the Cove (D0482), full spectra.
waves = {}
for mop in ("D0496", "D0482"):
    for attempt in range(3):
        try:
            body, meta = dataset_subset_bytes(f"https://thredds.cdip.ucsd.edu/thredds/dodsC/cdip/model/MOP_alongshore/{mop}_nowcast.nc", START - timedelta(days=3))
            waves[mop] = parse_waves(body, "mop", mop)
            print(mop, "obs", len(waves[mop].obs), meta)
            break
        except Exception as e:
            print(mop, "attempt", attempt, type(e).__name__, str(e)[:200])
            time.sleep(30)

# 3. Pier wind (CO-OPS 9410230), hourly.
wind = {}
d = START
while d < END:
    e = min(d + timedelta(days=30), END)
    r = c.get("https://api.tidesandcurrents.noaa.gov/api/prod/datagetter", params={
        "product": "wind", "station": "9410230", "begin_date": f"{d:%Y%m%d}", "end_date": f"{e:%Y%m%d}",
        "time_zone": "gmt", "units": "metric", "interval": "h", "format": "csv", "application": "snorkel-status"})
    for row in list(csv.reader(io.StringIO(r.text)))[1:]:
        try:
            wind[datetime.strptime(row[0], "%Y-%m-%d %H:%M").replace(tzinfo=UTC)] = float(row[1])
        except (ValueError, IndexError):
            pass
    d = e
print("wind hours", len(wind))

# 4. Daily rain at La Jolla (Open-Meteo archive).
r = c.get("https://archive-api.open-meteo.com/v1/archive", params={
    "latitude": 32.85, "longitude": -117.26, "start_date": f"{START - timedelta(days=6):%Y-%m-%d}", "end_date": f"{END:%Y-%m-%d}",
    "daily": "precipitation_sum", "timezone": "UTC"}).json()
rain = dict(zip(r["daily"]["time"], r["daily"]["precipitation_sum"]))
print("rain days", len(rain), "days with >=2.5 mm:", sum(1 for v in rain.values() if v and v >= 2.5))

# Hourly samples, 8 am-5 pm PDT (15-00 UTC).
def near(series, when, k, hours=1.0):
    vals = [row[k] for row in series if row[k] is not None and abs((row[0] - when).total_seconds()) <= hours * 3600]
    return statistics.median(vals) if vals else None

pier.sort(key=lambda r: r[0])
times_p = np.array([r[0].timestamp() for r in pier])
def window(when, k, hours=1.0):
    lo, hi = np.searchsorted(times_p, [when.timestamp() - hours * 3600, when.timestamp() + hours * 3600])
    vals = [pier[i][k] for i in range(lo, hi) if pier[i][k] is not None]
    return statistics.median(vals) if vals else None

def ub_series(ws, depth):
    out = []
    for o in ws.obs:
        if o.energy_m2_hz and ws.freqs_hz and ws.bandwidths_hz:
            ub = spectral_orbital_velocity(o.energy_m2_hz, ws.freqs_hz, ws.bandwidths_hz, depth)
        else:
            ub = bottom_orbital_velocity(o.hs_m, o.tp_s or 10.0, depth)
        out.append((o.time, ub, o.hs_m))
    return out

ubs = {m: ub_series(w, 4.0) for m, w in waves.items()}
def orbital(m, when, half_life):
    s = [(tt, u) for tt, u, _ in ubs.get(m, []) if when - timedelta(hours=72) <= tt <= when]
    return decayed_mean(s, when, half_life)
def hs_now(m, when):
    s = [(tt, h) for tt, _, h in ubs.get(m, []) if when - timedelta(hours=2) <= tt <= when]
    return s[-1][1] if s else None

rows = []
when = START + timedelta(days=3)
while when < END:
    if when.hour >= 15 or when.hour == 0:
        ntu, chl = window(when, 1), window(when, 2)
        if ntu is not None and ntu >= 0.15:
            w = wind.get(when)
            day = when.date()
            rain5 = sum((rain.get(f"{day - timedelta(days=k):%Y-%m-%d}") or 0) for k in range(0, 6))
            rows.append({"t": when, "ntu": ntu, "chl": chl, "wind_kt": w * 1.94384 if w is not None else None, "rain5_mm": rain5,
                         "hs": hs_now("D0496", when),
                         **{f"orb{h}": orbital("D0496", when, h) for h in (6, 12, 24, 48)},
                         "orb24_cove": orbital("D0482", when, 24)})
    when += timedelta(hours=1)
print("samples", len(rows))

def rank(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i]); r = [0.0] * len(xs)
    for k, i in enumerate(order): r[i] = k
    return r
def spearman(a, b):
    pairs = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
    if len(pairs) < 10: return float("nan"), len(pairs)
    ra, rb = rank([p[0] for p in pairs]), rank([p[1] for p in pairs])
    return float(np.corrcoef(ra, rb)[0, 1]), len(pairs)

def daily(rows, key):
    by = {}
    for r in rows:
        by.setdefault(r["t"].date(), []).append(r)
    return [(statistics.median([x["ntu"] for x in v]),
             statistics.median([x[key] for x in v if x[key] is not None]) if any(x[key] is not None for x in v) else None)
            for v in by.values()]

print("\nSpearman vs pier NTU (hourly | daily medians):")
for key in ("hs", "orb6", "orb12", "orb24", "orb48", "orb24_cove", "chl", "wind_kt", "rain5_mm"):
    h = spearman([r[key] for r in rows], [r["ntu"] for r in rows])
    dd = daily(rows, key)
    dly = spearman([x[1] for x in dd], [x[0] for x in dd])
    print(f"  {key:11} {h[0]:+.2f} (n={h[1]}) | {dly[0]:+.2f} (n={dly[1]})")

# The proxy as configured (no turbidity blend) vs vis from the sensor.
import yaml
cfg = yaml.safe_load(open("config/scoring.yaml"))
v, tc = cfg["visibility"], cfg["turbidity"]
def measured(ntu): return min(v["max_ft"], tc["vis_ft_at_1_ntu"] / max(ntu, 0.05) ** tc["exponent"])
def proxy(r, base=v["base_ft"], k=v["orbital_ft_per_ms"]):
    if r["orb24"] is None: return None
    p = k * r["orb24"]
    if r["chl"] is not None:
        p += min(v["chl_max_penalty_ft"], v["chl_ft_per_ug_l"] * max(0.0, r["chl"] - v["chl_threshold_ug_l"]))
    if r["rain5_mm"] >= 2.5: p += v["rain_recent_penalty_ft"]
    if r["wind_kt"] is not None: p += v["wind_ft_per_kt"] * max(0.0, r["wind_kt"] - v["wind_threshold_kt"])
    return min(v["max_ft"], max(v["min_ft"], base - p))
pm = [(proxy(r), measured(r["ntu"])) for r in rows if proxy(r) is not None]
sp = spearman([a for a, _ in pm], [b for _, b in pm])
mae = statistics.mean(abs(a - b) for a, b in pm)
bias = statistics.mean(a - b for a, b in pm)
inside = sum(1 for a, b in pm if a * (1 - v["spread_fraction"]) <= b <= a * (1 + v["spread_fraction"])) / len(pm)
print(f"\nproxy as configured vs sensor vis: spearman {sp[0]:+.2f} (n={sp[1]}), MAE {mae:.1f} ft, bias {bias:+.1f} ft, sensor inside the +/-{v['spread_fraction']:.0%} band {inside:.0%}")
meas = [b for _, b in pm]
print("sensor vis ft: p10/p50/p90", [round(float(np.percentile(meas, q)), 1) for q in (10, 50, 90)])
print("proxy vis ft:  p10/p50/p90", [round(float(np.percentile([a for a, _ in pm], q)), 1) for q in (10, 50, 90)])
print("orb24 m/s: p10/p50/p90", [round(float(np.percentile([r["orb24"] for r in rows if r["orb24"] is not None], q)), 3) for q in (10, 50, 90)])

# Least squares: sensor vis ~ a - b * orb24 (hourly) and the same on log NTU.
X = np.array([[1.0, r["orb24"]] for r in rows if r["orb24"] is not None])
y = np.array([measured(r["ntu"]) for r in rows if r["orb24"] is not None])
coef, *_ = np.linalg.lstsq(X, y, rcond=None)
pred = X @ coef
r2 = 1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum()
print(f"fit: vis = {coef[0]:.1f} {coef[1]:+.1f} * orb24   R^2 {r2:.2f}   (config: {v['base_ft']} - {v['orbital_ft_per_ms']} * orb)")
for lo, hi in ((0, 0.1), (0.1, 0.2), (0.2, 0.3), (0.3, 0.45), (0.45, 9)):
    sel = [measured(r["ntu"]) for r in rows if r["orb24"] is not None and lo <= r["orb24"] < hi]
    if sel:
        print(f"  orb24 {lo:.2f}-{hi:.2f}: n={len(sel):4d} sensor vis median {statistics.median(sel):5.1f} ft  p25 {np.percentile(sel,25):5.1f}  p75 {np.percentile(sel,75):5.1f}")

# Murkiest days: what was going on?
by = {}
for r in rows:
    by.setdefault(r["t"].date(), []).append(r)
days = sorted(by.items(), key=lambda kv: -statistics.median([x["ntu"] for x in kv[1]]))
print("\nmurkiest days (median NTU, hs ft, orb24, chl, wind kt, rain5 mm):")
for day, v_ in days[:10]:
    med = lambda k: statistics.median([x[k] for x in v_ if x[k] is not None]) if any(x[k] is not None for x in v_) else float("nan")
    print(f"  {day} {med('ntu'):5.2f} NTU  hs {med('hs')*3.281 if med('hs')==med('hs') else float('nan'):4.1f} ft  orb {med('orb24'):.2f}  chl {med('chl'):.2f}  wind {med('wind_kt'):4.1f}  rain {med('rain5_mm'):.1f}")
print("clearest days:")
for day, v_ in days[-5:]:
    med = lambda k: statistics.median([x[k] for x in v_ if x[k] is not None]) if any(x[k] is not None for x in v_) else float("nan")
    print(f"  {day} {med('ntu'):5.2f} NTU  hs {med('hs')*3.281 if med('hs')==med('hs') else float('nan'):4.1f} ft  orb {med('orb24'):.2f}  chl {med('chl'):.2f}  wind {med('wind_kt'):4.1f}  rain {med('rain5_mm'):.1f}")
PY
