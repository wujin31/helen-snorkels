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

# The proxy as configured, and refits, checked out of sample (fit Jul-Aug, test Sep-Oct).
import yaml
cfg = yaml.safe_load(open("config/scoring.yaml"))
v, tc = cfg["visibility"], cfg["turbidity"]
def measured(ntu): return min(v["max_ft"], tc["vis_ft_at_1_ntu"] / max(ntu, 0.05) ** tc["exponent"])
def penalties(r, chl_k=v["chl_ft_per_ug_l"], chl_thr=v["chl_threshold_ug_l"]):
    p = 0.0
    if r["chl"] is not None:
        p += min(v["chl_max_penalty_ft"], chl_k * max(0.0, r["chl"] - chl_thr))
    if r["rain5_mm"] >= 2.5: p += v["rain_recent_penalty_ft"]
    if r["wind_kt"] is not None: p += v["wind_ft_per_kt"] * max(0.0, r["wind_kt"] - v["wind_threshold_kt"])
    return p
def clamp(x): return min(v["max_ft"], max(v["min_ft"], x))
use = [r for r in rows if r["orb24"] is not None]
split = datetime(2026, 9, 1, tzinfo=UTC)
train = [r for r in use if r["t"] < split]
test = [r for r in use if r["t"] >= split]
print(f"\ntrain {len(train)} samples (Jul-Aug), test {len(test)} (Sep-Oct)")

def report(name, predict, data):
    pm = [(predict(r), measured(r["ntu"])) for r in data]
    sp = spearman([a for a, _ in pm], [b for _, b in pm])[0]
    mae = statistics.mean(abs(a - b) for a, b in pm)
    bias = statistics.mean(a - b for a, b in pm)
    cov = {f: sum(1 for a, b in pm if a * (1 - f) <= b <= a * (1 + f)) / len(pm) for f in (0.25, 0.35, 0.45)}
    # how often the Yes/No vis thresholds agree (10 ft yes floor, 6 ft no)
    agree10 = sum(1 for a, b in pm if (a >= 10) == (b >= 10)) / len(pm)
    print(f"  {name:34} spearman {sp:+.2f}  MAE {mae:5.1f}  bias {bias:+5.1f}  inside +/-25/35/45%: {cov[0.25]:.0%}/{cov[0.35]:.0%}/{cov[0.45]:.0%}  >=10ft agree {agree10:.0%}")

def fit_linear(data, with_chl):
    X = np.array([[1.0, r["orb24"]] + ([r["chl"] or 0.0] if with_chl else []) for r in data])
    y = np.array([measured(r["ntu"]) + penalties(r, chl_k=0.0 if with_chl else v["chl_ft_per_ug_l"]) for r in data])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    return coef

def fit_log(data):
    X = np.array([[1.0, r["orb24"], r["chl"] or 0.0] for r in data])
    y = np.array([math.log(max(r["ntu"], 0.05)) for r in data])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    return coef

CHL_TYPICAL = statistics.median([r["chl"] for r in use if r["chl"] is not None])
print("median pier chl", round(CHL_TYPICAL, 2))
def lchl(r, missing=False):
    return math.log(max(CHL_TYPICAL if (missing or r["chl"] is None) else r["chl"], 0.05))
def fit_logln(data):
    X = np.array([[1.0, r["orb24"], lchl(r)] for r in data])
    y = np.array([math.log(max(r["ntu"], 0.05)) for r in data])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ coef
    return coef, float(np.std(resid))
def fit_logorb(data):
    X = np.array([[1.0, r["orb24"]] for r in data])
    y = np.array([math.log(max(r["ntu"], 0.05)) for r in data])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    return coef

for label, data, fitset in (("in sample, all", use, use), ("out of sample, Sep-Oct", test, train), ("out of sample, Jul-Aug (fit Sep-Oct)", train, test)):
    g, sd = fit_logln(fitset)
    o = fit_logorb(fitset)
    print(f"\n{label}: ln NTU = {g[0]:.3f} {g[1]:+.3f}*orb {g[2]:+.3f}*ln(chl)  (resid sd {sd:.2f}) | waves only: {o[0]:.3f} {o[1]:+.3f}*orb")
    report("configured (20 - 22*orb)", lambda r: clamp(v["base_ft"] - v["orbital_ft_per_ms"] * r["orb24"] - penalties(r)), data)
    report("ln model, waves + ln chl", lambda r, g=g: clamp(measured(math.exp(g[0] + g[1] * r["orb24"] + g[2] * lchl(r))) - penalties(r, chl_k=0)), data)
    report("ln model, chl missing -> typical", lambda r, g=g: clamp(measured(math.exp(g[0] + g[1] * r["orb24"] + g[2] * lchl(r, True))) - penalties(r, chl_k=0)), data)
    report("ln model, waves only", lambda r, o=o: clamp(measured(math.exp(o[0] + o[1] * r["orb24"])) - penalties(r, chl_k=0)), data)
    report("linear 40 - 60*orb", lambda r: clamp(40 - 60 * r["orb24"] - penalties(r)), data)

g, _ = fit_logln(use)
print("\nwhat the all-data ln model says (ft, before rain/wind):")
for orb in (0.1, 0.2, 0.3, 0.4, 0.5, 0.7):
    cells = []
    for chl in (0.4, 0.6, 1.5, 5, 12, 30):
        cells.append(f"{measured(math.exp(g[0] + g[1] * orb + g[2] * math.log(chl))):5.1f}")
    print(f"  orb {orb:.1f}: chl 0.4/0.6/1.5/5/12/30 -> " + " ".join(cells))
PY
