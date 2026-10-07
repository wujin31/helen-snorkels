# Snorkel Status SD

Phone-first yes / maybe / no for snorkeling at San Diego spots, starting with
La Jolla Cove and Marine Room / La Jolla Shores, built from public ocean data.
**Read `docs/brief.md`** (goals, sources, physics, design) before
changing behavior; `docs/sources.md` tracks what each source is and what's
still unconfirmed.

## Commands

```sh
uv sync                              # install
uv run pytest                        # tests (fixtures only, no network)
uv run ruff check && uv run ruff format --check && uv run pyright
uv run snorkel archive --storage local:.archive           # capture everything due
uv run snorkel archive --storage local:.archive --force --only tides.observed
uv run snorkel probe cdip.buoy --save-fixture             # hit one live source, save a fixture
uv run snorkel check-storage --storage local:.archive     # storage round trip
uv run snorkel score --out web/public/status.json         # fetch, score, write the page's data
cd web && npm ci && npm test && npm run build             # page (Vite + TS, no framework)
```

## Layout

- `config/spots.yaml`: spot registry (`SpotConfig`). `config/sources.yaml`: archiver cadence and per-source params.
- `src/snorkel/fetch/`: one module per provider. A capture function takes a `FetchContext` and returns `RawSnapshot | ItemError` items; `fetch/__init__.py` registers source ids.
- `src/snorkel/archive.py`: runs due sources and writes to storage + the daily manifest.
- `src/snorkel/storage.py`: `LocalStorage`, `GatewayStorage` (prod: Supabase edge function authenticated by GitHub Actions OIDC, no secrets) and `S3Storage` (R2 escape hatch).
- `supabase/migrations/`: the private archive bucket (the swim log was cut in `0004`). `supabase/functions/archive-gateway/`: the storage gateway. Supabase project ref `dujjlhiytnrtsebxshhw`; see `docs/setup.md`.
- `src/snorkel/parse/`: pure parsers (raw bytes → `observations.py` models), tested on real fixtures.
- `src/snorkel/pipeline.py`: gathers fresh `Conditions`; `score/rules.py`: v0 rules; `publish/status.py`: `status.json`.
- `config/scoring.yaml`: every threshold and heuristic (priors to validate).
- `web/`: the page. `src/render.ts` renders HTML strings from `status.json`, at build time (answer in first paint) and in the browser: verdict first, then details.
- `.github/workflows/`: `ci.yml`, `archive.yml` (15-min cron), `score.yml` (hourly score + history + Pages deploy), `pacemaker.yml` (fills cron gaps), `probe.yml` (live probes from `probe/**` branches), `keepalive.yml`.

## Conventions

- **UTC and SI internally.** Timezone-aware datetimes only; convert to America/Los_Angeles, ft, °F and kt at display time. Watch DST in tide/window math.
- **Pydantic models are the data contracts** (`src/snorkel/models.py`).
- **Every fetcher is independent.** Nothing raises past a source boundary; failures become manifest rows. The page must always render with whatever is fresh and say what's stale.
- **Raw first.** The archiver stores responses untouched (gzipped) so parsers can be rewritten and re-run later. Parsing lives in separate pure functions tested against saved fixtures in `tests/fixtures/`.
- **Tests never touch the network.** Use `httpx.MockTransport` or fixtures captured with `snorkel probe --save-fixture`.
- **Be polite to sources.** Respect cadences in `config/sources.yaml`; identify via the User-Agent (`SNORKEL_CONTACT`). No Surfline scraping. The Scripps Pier cam is not used (no permission to embed or analyze it, and capture stopped on 2026-10-06): link to Scripps' page only; never capture, proxy, rehost or spoof a `Referer` to reach it.
- **Never say "safe"** in user-facing copy. Say "conditions look good" and keep the short lifeguard note.
- **Nothing private in git:** no frames, raw snapshots, or secrets. The repo is public.
- Every threshold and heuristic is a *prior to validate*; keep them in config, not code.
- **Cron lines must be committed as the repo owner.** GitHub runs a schedule as whoever last edited its cron syntax; a commit authored by an account without access to this repo (e.g. a local `git commit` from a Claude session) leaves the schedule silently never firing. Change `schedule:` blocks through the GitHub API/MCP (commits authored as `wujin31`), not local commits.
