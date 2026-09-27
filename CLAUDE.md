# Snorkel Status SD

Phone-first yes / maybe / no for snorkeling at La Jolla Cove and Marine Room /
La Jolla Shores, built from public ocean data and the Scripps Pier underwater
cam. **Read `docs/brief.md`** (goals, sources, physics, design) before
changing behavior; `docs/sources.md` tracks what each source is and what's
still unconfirmed.

## Commands

```sh
uv sync                              # install (add --extra browser for the cam's headless fallback)
uv run pytest                        # tests (fixtures only, no network)
uv run ruff check && uv run ruff format --check && uv run pyright
uv run snorkel archive --storage local:.archive           # capture everything due
uv run snorkel archive --storage local:.archive --force --only tides.observed
uv run snorkel probe cdip.buoy --save-fixture             # hit one live source, save a fixture
uv run snorkel check-storage --storage local:.archive     # storage round trip
```

## Layout

- `config/spots.yaml`: spot registry (`SpotConfig`). `config/sources.yaml`: archiver cadence and per-source params.
- `src/snorkel/fetch/`: one module per provider. A capture function takes a `FetchContext` and returns `RawSnapshot | ItemError` items; `fetch/__init__.py` registers source ids.
- `src/snorkel/archive.py`: runs due sources and writes to storage + the daily manifest.
- `src/snorkel/storage.py`: `LocalStorage`, `GatewayStorage` (prod: Supabase edge function authenticated by GitHub Actions OIDC, no secrets) and `S3Storage` (R2 escape hatch).
- `supabase/migrations/`: swim-log table (RLS) and the private archive bucket. `supabase/functions/archive-gateway/`: the storage gateway. Supabase project ref `dujjlhiytnrtsebxshhw`; see `docs/setup.md`.
- `.github/workflows/`: `ci.yml`, `archive.yml` (15-min cron), `keepalive.yml`.

## Conventions

- **UTC and SI internally.** Timezone-aware datetimes only; convert to America/Los_Angeles, ft, °F and kt at display time. Watch DST in tide/window math.
- **Pydantic models are the data contracts** (`src/snorkel/models.py`).
- **Every fetcher is independent.** Nothing raises past a source boundary; failures become manifest rows. The page must always render with whatever is fresh and say what's stale.
- **Raw first.** The archiver stores responses untouched (gzipped) so parsers can be rewritten and re-run later. Parsing lives in separate pure functions tested against saved fixtures in `tests/fixtures/`.
- **Tests never touch the network.** Use `httpx.MockTransport` or fixtures captured with `snorkel probe --save-fixture`.
- **Be polite to sources.** Respect cadences in `config/sources.yaml`; identify via the User-Agent (`SNORKEL_CONTACT`). No Surfline scraping. The cam is one still per 15 min, kept private until Scripps OKs more.
- **Never say "safe"** in user-facing copy. Say "conditions look good" and keep the short lifeguard note.
- **Nothing private in git:** no frames, raw snapshots, swim logs, or secrets. The repo is public.
- Every threshold and heuristic is a *prior to validate*; keep them in config, not code.
