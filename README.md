# Snorkel Status SD

A calm, phone-first answer to "should we snorkel today, and where?" for La Jolla
Cove and Marine Room / La Jolla Shores, built from public ocean data (CDIP
waves, NOAA tides and weather, SCCOOS pier sensors, county water quality) and
the Scripps Pier underwater cam.

- **Project brief:** [docs/brief.md](docs/brief.md)
- **Data sources and status:** [docs/sources.md](docs/sources.md)
- **One-time setup (Supabase, secrets, Pages):** [docs/setup.md](docs/setup.md)

## Status

Phase 0: the archiver runs every 15 minutes in daylight and stores raw snapshots
of every source plus one pier-cam still in private object storage. Scoring and
the page come next.

## Develop

```sh
uv sync
uv run pytest
uv run snorkel archive --storage local:.archive --force
```
