# Snorkel Status: San Diego Go/No-Go (Project Brief)

> Handoff doc for Claude Code. It distills a planning conversation: goals, research, competitive landscape, technical strategy, design direction, and a build plan. **Read "Guiding principles" and "First sessions" before writing code.**
>
> **Changes since this brief (2026-10-06).** The swim log was cut: no user interaction. The Scripps Pier cam was dropped: permission to embed or analyze it wasn't granted, capture stopped and archived frames were deleted. Visibility now comes from wave physics, pier sensors, satellite water color and NWS forecasts, calibrated against public dive reports. Tier 2 and 3 spots are being added. Sections below that rely on the cam or her logs are historical.

---

## 1. Goal

A mobile-first web page that gives one person (Jay's girlfriend) an at-a-glance **yes / maybe / no** on snorkeling today, plus **"where's best today?"** across San Diego's popular snorkel spots. Every verdict is backed by the best available public data and measurement, and explains itself in one line, e.g.:

> **Yes · Marine Room · 7:00–9:30** · ~12–15 ft · 1–2 ft SW swell, incoming tide, cam shows 3 of 4 pilings.
> **Cove: No** · county bacteria advisory.

Her home spots are **La Jolla Cove** and **Marine Room / La Jolla Shores**. She already checks the **Scripps Pier underwater cam** to judge conditions, so the app should formalize and extend what she does by eye.

**Ambition:** win on technical depth (measurement, physics, calibrated probabilities) and on design (answer-first, evidence-backed), not on number of spots.

---

## 2. Guiding principles

1. **Answer first, evidence second, raw data last.**
2. **Measure where possible, model where necessary, and always show confidence.**
3. **Start collecting data on day one.** The archive is the moat, and missed days can't be recovered.
4. **Every data source can fail.** Each fetcher is independent. The page always renders with whatever is fresh and says what's stale.
5. **Never say "safe."** Say "conditions look good." Include a small, non-naggy note that ocean conditions change and to check with lifeguards on site. Rip currents, surge, and wildlife are her call in the water.
6. **Public data and respectful access only.** No Surfline scraping. Ask before relying on the cam stream. Check terms on dive-report archives.
7. **Keep v0 small.** Two spots, rules, one page, then iterate with her feedback.

---

## 3. Core insight

What she cares about most is **visibility**, and almost no public sensor measures it directly. The system is a **visibility estimator + safety/comfort gates** (swell and surge, wind, water quality, closures, rain, temperature). Quality comes from proxies, the one near-direct measurement (pier cam), and ground truth (her logs + historical dive reports).

---

## 4. Spot registry

| Tier | Spot | Area | Type / difficulty | Key sensitivities & notes |
|---|---|---|---|---|
| 1 | **La Jolla Cove** | La Jolla | Rocky reef, kelp. All levels, easiest access | Faces north. Exposed to W/NW swell, protected from south swell. Frequent bacteria advisories (sea lions/birds). Best mornings, incoming tide. |
| 1 | **Marine Room / La Jolla Shores** | La Jolla | Sand flats to rocky reef. Shores all levels; Marine Room reef advanced | Leopard sharks in summer/fall. Surge on south swell. Low tide limits entry and depth. Pier cam nearby. |
| 2 | Turtle Town | La Jolla | Rocky reef, advanced, strenuous swim | Same inputs as the Shores. Sea turtles. |
| 2 | Seven Sea Caves / Clam Cave | East of Cove | Caves, strenuous | **Tide + swell gated.** Surge risk inside caves. |
| 2 | Devil's Slide | La Jolla | Rocky reef, advanced, hard access | Horn sharks. |
| 2 | Boomer's kelp beds | West of Cove | Kelp, advanced | Sea lion colony. More exposed than the Cove. |
| 2 | Shell Beach / Wipeout Beach | South La Jolla | Reef, exposed | Open to swell. Water quality varies. |
| 2 | Bird Rock kelp | La Jolla | Kelp, advanced, strenuous | Giant sea bass. Exposed. |
| 3 | Mission Point Park | Mission Bay channel | Rocky jetty, sheltered | Tide-direction sensitive (flood = ocean water, ebb = bay water; heuristic to validate). Mission Bay advisories common. |
| 3 | Sunset Cliffs | Point Loma | Kelp, advanced, strenuous | Exposed. Needs Point Loma wave data. |
| 3 | Cardiff Reef | North County | Reef | Warmer than La Jolla. Best low swell, incoming tide, calm mornings. |
| — | ~~Children's Pool~~ | La Jolla | — | **Excluded.** Closed Dec 15–May 15 (harbor seal pupping); chronic bacteria advisory since 1997. |
| — | Coronado Islands | Boat only | — | Out of scope. Maybe a future "trip planner" mode. |

All heuristics are **priors to be validated by data**. The build starts with Tier 1 only.

### Spot config schema (`spots.yaml`)

```yaml
- id: la-jolla-cove
  name: La Jolla Cove
  lat: 32.8506
  lon: -117.2713
  tier: 1
  difficulty: easy            # easy | moderate | advanced
  access: shore               # shore | strenuous | boat
  bottom_depth_m: 5           # typical snorkel-zone depth, for near-bottom wave calc
  cdip_mop_id: TODO           # nearest MOP alongshore point
  cdip_buoy: TODO             # nearest buoy fallback
  tide_station: "9410230"     # NOAA CO-OPS La Jolla
  water_quality_ids: [TODO]   # sdbeachinfo / Swim Guide station(s)
  exposure_deg:               # swell directions that reach the spot
    exposed: [250, 330]
    sheltered: [150, 230]
  thresholds: { max_hs_ft: 2.5, max_wind_kt: 10 }
  tide_rules: { prefer: incoming }
  seasonal_closures: []
  cam: null                   # scripps_pier_underwater for nearby spots
  notes: ""
```

---

## 5. Data sources

### 5.1 Scripps Pier underwater cam (flagship measurement)
- Page: https://coollab.ucsd.edu/pierviz/ · Stream (HDOnTap): https://hdontap.com/stream/018408/scripps-pier-underwater-live-webcam/
- About 4 m (13 ft) deep on a pier piling. Run by Scripps' Coastal Ocean Observing Lab / Shore Stations Program.
- **Built-in visibility ruler** (per COOL lab): nearest right piling 1.2 m (4 ft), back-right 3.4 m (11 ft), back-left 4.3 m (14 ft, clear days only), second left piling 9 m (30 ft, rare).
- **Color cues:** light blue = clear; dark green / reddish-brown = phytoplankton bloom; fast-moving particles = surf or current stirring sand.
- **Caveats:** daylight only; lens fouling; outages (it came back online 7/14/26 after a stretch down); ROIs may shift after repairs; access terms TBD. Jay works with SIO through SPF, so ask the Shore Stations team (sioshorestation@gmail.com) about still-frame access once there's a prototype to show.
- **Spatial use:** strong for the Shores / Marine Room / Turtle Town; a learned proxy elsewhere in La Jolla; a regional bloom signal.

### 5.2 CDIP waves (Scripps; covers every spot)
- Buoys: 30-min directional wave data **including full spectra** (energy by frequency and direction), plus SST.
- **MOP alongshore model:** hourly nowcasts and forecasts at 10 m depth, ~100 m alongshore spacing in SoCal, accounting for island blocking, refraction, and shoaling. The backbone of per-spot scoring. San Diego County MOPs are numbered south→north.
- Docs: https://cdip.ucsd.edu/documents/index/product_docs/mops/mop_intro.html (THREDDS/OPeNDAP).

### 5.3 SCCOOS Scripps Pier Automated Shore Station
- Temperature, salinity, **chlorophyll**, pH, O₂ at ~5 m MLLW, every few minutes.
- ERDDAP: `scripps-pier-automated-shore-sta-1` at https://erddap.cencoos.org/erddap/
- No turbidity sensor found. Weekly HAB sampling: https://habs.sccoos.org/scripps-pier (red tide flag).

### 5.4 Satellite ocean color (NOAA CoastWatch ERDDAP)
- VIIRS **Kd490** (light attenuation, a clarity proxy) and chlorophyll, daily, with 750 m regional sectors (IDs like `noaacwNPPVIIRSkd490Sector??Daily`). Sample slightly offshore of each spot.
- Main clarity signal for Tier 3 spots. Caveats: noisy near-shore pixels; marine layer blocks retrievals.
- Rough rule: horizontal visibility ≈ Secchi depth × 1.5–2.5.

### 5.5 Tides and pier weather
- NOAA CO-OPS **9410230** (La Jolla) and other stations for Mission Bay / Point Loma. Free JSON API.
- NDBC **LJPC1** (Scripps Pier): wind.

### 5.6 Weather and rain
- NWS API (api.weather.gov) and/or Open-Meteo (weather + marine, no key), per spot.
- Hard gate: the county's standard guidance to avoid water contact for 72 h after significant rain.

### 5.7 Water quality and closures
- San Diego County DEHQ: https://www.sdbeachinfo.com (advisories/closures). Mirror: Swim Guide / Coastkeeper (La Jolla Cove: https://www.theswimguide.org/beach/1986). Sampling is roughly weekly.
- Active advisory or closure → hard **No**. Seasonal closures come from spot config.

### 5.8 Ground truth
- **Her logs** (primary).
- **Historical dive reports:** Just Get Wet / DiveViz archives (La Jolla, ~2020 onward) include vis/swell/temp. Extract with an LLM into structured rows. Check terms; personal use only.
- **Her underwater photos** (later): EXIF timestamp + image-based visibility estimate = effortless labels.

---

## 6. Competitive landscape

| Tool | What it does | Gap we exploit |
|---|---|---|
| **La Jolla Freedive Club conditions page** | "AI visibility" grade from Scripps Pier data, cam links, spot guide, resource links | Club marketing mixed into the tool; static spot ranges; links out instead of combining sources; freediver framing; answer loads after the page (see §9). Their real edge: a community in the water every week. |
| **DiveProCA / DiveProSD** | La Jolla vis forecast + tide/wind/swell | Generic, 4 spots. |
| **SpearFactor** | Vis estimate in feet for 30+ CA sites, 7-day forecast | Spearfishing focus, breadth over depth. |
| **Nautical Nick / Ocean Oracle** | VIIRS chlorophyll + Open-Meteo + diver reports → vis score | Good reference architecture; no cam measurement. |
| **Marla Blue** | ML vis forecast incl. California | Calibrated mostly on UK/Ireland data. |
| **Just Get Wet / DiveViz reports** | Human daily La Jolla reports | Great **labels**, not a product competitor. |

None of these, as far as we found, **measure** visibility from the pier cam, publish an accuracy record, or give a personal, calibrated, snorkel-specific decision.

---

## 7. Technical edge and moat

The moat is **data you started collecting early** plus a **proven accuracy record**. Clever code alone can be copied.

1. **Day-one archiver.** Every 10–15 min during daylight, save a cam frame and snapshot every data source. A year of cam-derived visibility aligned with waves, chlorophyll, tide, and wind is likely a unique record, and it can't be backfilled.
2. **Near-bottom wave physics, not just wave height.** Sediment gets stirred up when wave motion reaches the bottom. From CDIP spectra, compute near-bottom orbital velocity at each spot's depth with linear wave theory: for each frequency, solve the dispersion relation for wavenumber k, then u_b ∝ ω·a / sinh(k·h), summed across frequencies. Long-period swell reaches the bottom far more than short chop of the same height. Expect this to beat Hs as a predictor.
3. **Recovery dynamics.** Visibility has memory. Features: exponentially decayed swell energy (try half-lives of 12–72 h), days since the last swell or rain event, cumulative rain. Learn how fast each spot recovers. That enables **1–3 day forecasts** from CDIP/NWS forecasts.
4. **Latent-state fusion.** Treat each spot's visibility as a hidden state with uncertainty, updated by every source as it arrives: cam (strong), reports and logs (strong but sparse), satellite (weak), proxies (prior). Use a Kalman filter or a simple Bayesian state-space model. The cam going down widens the uncertainty band instead of breaking the page.
5. **Spatial transfer.** Learn the relationship between pier-cam visibility and logged visibility at other spots, conditioned on swell direction and tide. The pier becomes a La Jolla-wide sensor.
6. **Probabilistic outputs.** e.g. "P(vis ≥ 15 ft) = 0.7". Evaluate with Brier score, reliability plots, and MAE in feet.
7. **Published track record.** Show a small accuracy panel ("right 17 of the last 20 days") and log competitors' daily calls as baselines to beat.
8. **Low-friction ground truth.** Two-tap logging, and later photo-based labels.

### Cam CV plan
- The camera is fixed, so hand-label an ROI per piling plus background ROIs. Store them in `cam_rois.yaml` with a version and date.
- Per ROI features: local contrast (e.g. RMS contrast or Laplacian variance), edge density, and contrast relative to the background ROI. Mean hue/saturation for the water-color class. Frame differencing for particle motion.
- **v0 classifier:** thresholds per piling → "visible / not visible" → vis bin (<4, 4–11, 11–14, 14–30, 30+ ft). Hand-label ~100–200 frames across varied conditions to set thresholds, then consider a small model.
- **Quality checks:** night / low light (mean brightness), lens obstruction (a lobster on the lens is real), a frozen stream (identical frames), camera shift (feature matching against a reference frame → flag ROI recalibration).
- Only store downscaled frames + ROI crops to keep storage small (see §10).

---

## 8. Scoring

**v0: transparent rules, per spot**
- **Hard gates → No:** water quality advisory/closure, seasonal closure, rain in the last 72 h, spot Hs above threshold, strong onshore wind, spot-specific gates (e.g. caves).
- **Vis estimate:** cam bin where applicable and fresh; otherwise a proxy blend (decayed near-bottom wave energy weighted by exposure, chlorophyll, Kd490, wind, tide phase).
- **Outputs per spot:** verdict, vis range, confidence (high/med/low), one-line reason, best window today, wetsuit suggestion.
- **Ranking:** "Best bet today," filtered by her difficulty preference.

**v1: calibrated model**
- Labels: her logs + extracted historical reports. Features as in §7.
- Start simple (ordinal/logistic regression or small gradient boosting), with spot-exposure features so it generalizes. Lean on physics priors for spots with few labels.
- A **backtest harness** is required before any model replaces the rules. Report metrics per spot.

---

## 9. Design direction

### What to beat (LJFC conditions page)
Club promos, signup, and donation links mixed into conditions; static per-spot vis ranges; cams and data as outbound links ("the sources we check every morning"), so the user still has to combine them; freediver framing; data loads client-side after a "Reading the ocean…" state, so no answer if the feed fails.

### Our design
1. **Answer-first hero, mobile-first.** Verdict + spot + window. Color **and** icon **and** text (sunlight-readable, not color-only).
2. **Evidence card.** Latest cam frame with piling outlines and labels ("3 of 4 pilings visible → ~12 ft"), timestamped.
3. **Small, meaningful charts.** 7-day visibility history + 3-day forecast with an uncertainty band. Tide curve with the best window shaded. Swell and wind arrows drawn relative to the spot's orientation.
4. **Tap-to-expand "why".** Factor contributions (swell −, incoming tide +, rain 5 days ago ~).
5. **Spot list with live chips.** Verdict + confidence dot, sorted by today's best bet. Tier 1 as large cards, others compact.
6. **Honest freshness.** "Updated 6:02 · cam live" vs. "Cam offline: estimate from wave + satellite data." Stale data looks stale.
7. **Fast and installable.** Pre-computed JSON (answer in first paint), PWA / add to home screen, dark mode for dawn, readable in glare, big tap targets.
8. **Two-tap post-swim log.** Spot (pre-selected), vis slider in ft, 1–5 rating, optional note.
   *Cut 2026-09-27: no user interaction. Ground truth comes from the pier cam and dive reports.*
9. **Useful touches.** Wetsuit recommendation from water temp; "around this week" (leopard shark season, bat rays, bloom warning); a one-sentence morning summary.
10. **Tone.** Calm, oceanic, no marketing, no clutter. Nothing on the page that isn't helping her decide.

Consider a quick mockup pass (layout + component list) before building the frontend.

---

## 10. Architecture

- **Language:** Python for fetchers, scoring, CV, and modeling (managed with uv; typed with pydantic models as data contracts). Frontend: a static site (plain HTML/TS or a lightweight framework) reading JSON.
- **Pipeline:** `fetch_*` (independent, retrying, cached, each writes a raw snapshot) → `normalize` (UTC timestamps, SI units internally, convert to ft/°F for display) → `score` per spot → `status.json` + `history.jsonl`.
- **Scheduler:** GitHub Actions cron (hourly 5am–6pm PT, plus a 6am morning run; the archiver runs every 10–15 min in daylight). Crons can be delayed several minutes; that's fine.
- **Storage:**
  - Status + history JSON: in the repo or object storage.
  - Frames: **not in git.** Use object storage (e.g. Supabase Storage or Cloudflare R2). Rough budget: ~80 frames/day. At ~100–150 KB downscaled that's ~10 MB/day, ~4 GB/year. Store ROI crops alongside for cheap reprocessing.
  - Logs: a Supabase table, or a small authenticated endpoint. Keep her logs private.
- **Hosting:** GitHub Pages or Vercel.
- **Timezones:** everything stored in UTC; display America/Los_Angeles. Watch DST in tide and "best window" math.
- **Observability:** a small "source health" section (last success per source) on a hidden debug page.

### Suggested repo layout
```
snorkel-status/
  CLAUDE.md               # conventions + pointer to this brief
  docs/brief.md           # this file
  config/spots.yaml
  config/cam_rois.yaml
  src/snorkel/
    fetch/                # cdip.py, sccoos.py, coastwatch.py, tides.py, weather.py, water_quality.py, cam.py
    features/             # waves_physics.py, decay.py, tides.py
    cv/                   # pier_cam.py (ROIs, contrast, classifier, QC)
    score/                # rules.py, fusion.py (later), model.py (later)
    publish/              # build status.json / history
  web/                    # static frontend
  notebooks/              # exploration, labeling, backtests
  tests/                  # fixtures from saved raw snapshots
  .github/workflows/      # archive.yml, score.yml
```

---

## 11. Build phases

0. **Archiver (day one).** Cam frames + raw snapshots of every source on a schedule. Nothing else.
1. **Data plumbing.** Fetchers + normalization + tests from saved fixtures. `spots.yaml` with Tier 1. Look up MOP IDs, buoys, and water-quality stations.
2. **v0 scorer + page (Tier 1).** Rules, verdicts, reasons, freshness, log form. Deploy. She starts using and logging.
3. **Pier cam CV.** ROI labeling, per-piling visibility, color/particle features, QC. Evidence card on the page.
4. **Physics features.** Near-bottom orbital velocity from spectra; decayed energy; recovery features.
5. **Historical backfill + backtest.** Archived data + extracted report labels. Compare rules vs. a simple model per spot.
6. **Tier 2 spots + ranking + difficulty filter.**
7. **Fusion + forecasts.** Latent-state model, 1–3 day forecasts, probability outputs, accuracy panel.
8. **Tier 3 spots**, photo-based labels, morning notification, polish.

---

## 12. First sessions in Claude Code

1. Scaffold the repo (layout above), `CLAUDE.md`, and a uv project. Put this file in `docs/brief.md`.
2. Build the **archiver**: figure out a respectful, reliable way to grab a still frame from the pier cam (confirm the stream format; if unclear, capture from the public page and flag it for permission). Snapshot CDIP, SCCOOS, tides, weather, and water quality raw responses. Schedule with GitHub Actions. Upload frames to object storage.
3. Look up and fill in `spots.yaml` IDs for the Cove and the Marine Room.
4. Build normalized fetchers with tests against saved snapshots.
5. v0 rules + a minimal answer-first page.

---

## 13. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Cam outage / access revoked | Fusion model falls back to proxies; ask Scripps early for sanctioned still access. |
| Cam moves after maintenance | Reference-frame matching → auto-flag ROI recalibration. |
| Sparse ground truth outside La Jolla | Confidence labels; physics priors; encourage logging at those spots. |
| Overconfidence leads to a bad day | Probabilities + ranges; never "safe"; publish accuracy. |
| Source API changes | Independent fetchers, saved fixtures, source-health panel. |
| Scraping/terms issues | Public government data first; ask permission; personal use only for report archives. |
| Scope creep | Tier 1 first; phases above; each phase ships something she can use. |

---

## 14. Open questions

- Pier cam frame access method and permission.
- Exact MOP IDs, buoys, tide stations, and water-quality stations per spot.
- Which spots she actually cares about beyond the Cove / Marine Room, and her difficulty comfort.
- Her thresholds: minimum vis, surge tolerance, time-of-day preference, water temp / wetsuit.
- Whether she'd log from photos vs. a form.
- Terms of use for dive-report archives.
- Validate: Mission Bay tide-direction heuristic, per-spot swell exposure windows, and "incoming tide = better" lore.
