# Snorkel Status SD

A calm, phone-first answer to "should we snorkel today, and where?" across 12
San Diego spots, from La Jolla (Cove, Shores, Shell Beach, Goldfish Point, the
Sea Caves, Turtle Town, Bird Rock) to Point Loma and Mission Bay (Sunset
Cliffs, Mission Point) and North County (Tide Beach, Cardiff Reef, Swami's),
built from public ocean data (CDIP
waves, NOAA tides and weather, SCCOOS pier sensors, county water quality).

- **Project brief:** [docs/brief.md](docs/brief.md)
- **Data sources and status:** [docs/sources.md](docs/sources.md)
- **Infrastructure and setup:** [docs/setup.md](docs/setup.md)

## Status

- **Archive** (every 15 min in daylight): raw snapshots of every source, in a
  private Supabase bucket.
- **v0 scorer + page** (hourly): transparent rules per spot (water quality,
  NWS hazards, rain, waves, wind gates; a visibility estimate from wave
  physics, pier turbidity and chlorophyll; the best window by tide and wind),
  published to GitHub Pages with the answer baked into the HTML.

## Develop

```sh
uv sync && uv run pytest            # Python: fetchers, parsers, scorer
uv run snorkel score --out web/public/status.json
cd web && npm ci && npm test && npm run dev
```
