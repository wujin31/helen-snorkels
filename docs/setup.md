# Setup and infrastructure

## What exists

| Piece | Where | Notes |
|---|---|---|
| Supabase project `snorkel-status` | ref `dujjlhiytnrtsebxshhw`, region us-west-1, free tier | Migrations in `supabase/migrations/` are applied |
| `swim_logs` table | Postgres, row-level security on | Unreadable to clients; written only through `log_swim()` |
| `log_keys` table | Postgres, RLS on, no policies | bcrypt hashes of private log keys; invisible to clients |
| `archive` bucket | Supabase Storage, private | Cam frames, raw snapshots, manifests |
| `archive-gateway` edge function | `https://dujjlhiytnrtsebxshhw.supabase.co/functions/v1/archive-gateway` | Source in `supabase/functions/archive-gateway/` |
| Archive workflow | `.github/workflows/archive.yml` | Every 15 min in daylight, from `main` |
| Score workflow | `.github/workflows/score.yml` | Hourly: scores, appends history to the `data` branch, deploys the page |
| Pacemaker | `.github/workflows/pacemaker.yml` | Always-on chain that dispatches archive/score whenever GitHub's cron leaves a gap (below) |
| Page | https://wujin31.github.io/helen-snorkels/ | GitHub Pages, once enabled (below) |

## How the archiver writes without secrets

GitHub Actions can mint a short-lived OIDC token that proves "this is a
workflow run in wujin31/helen-snorkels". The archive workflow asks for one
(`permissions: id-token: write`) and sends it to the `archive-gateway` edge
function. The function checks the token's signature against GitHub's public
keys, checks its audience (`snorkel-status`) and repository id, and only then
writes to the private bucket using the service role, which never leaves
Supabase. There's nothing to paste into GitHub secrets and nothing to rotate.

CI (`ci.yml`, job `gateway`) proves on every push that a round trip works and
that anonymous or wrong-audience requests get 401.

## Optional settings

Settings → Secrets and variables → Actions → Variables:

| Variable | Effect |
|---|---|
| `CAM_CAPTURE_ENABLED` | Set to `false` to pause cam capture (e.g. if Scripps asks) |
| `SNORKEL_CONTACT` | An email for the User-Agent; NWS asks API clients for one |
| `SNORKEL_STORAGE` | Override storage, e.g. `s3:<bucket>` plus `S3_*` secrets, if we move to R2 |

## If scheduled runs stop

GitHub's cron schedules on this repository fire late, in bursts, or not at
all for hours. `pacemaker.yml` covers the gaps: it runs around the clock as a
chain (re-dispatching itself every ~5.5 h), and every 5 minutes it dispatches
Archive if its last run is 14+ minutes old and Score if its last run is 58+
minutes old, within their daylight windows. When the scheduler is healthy it
finds nothing overdue. Archive and Score restart the pacemaker at the end of
every run if its chain ever broke, so the two keep each other going. Start it
by hand any time from Actions → Pacemaker → Run workflow.

Schedules run as whoever last edited the cron lines, so change `schedule:`
blocks in commits authored by the repo owner (see CLAUDE.md).

## One switch to flip: GitHub Pages

Settings → Pages → Build and deployment → Source: **GitHub Actions**. Until
then the Score workflow still scores and records history, and skips the
deploy with a warning.

## The swim log

No accounts and no email. A private link, `https://wujin31.github.io/helen-snorkels/#key=…`,
opened once on her phone stores a long random key in the browser (and strips
it from the URL). The page then shows **Log a swim**, which calls the
`log_swim()` Postgres function with that key. The function checks the key
against a bcrypt hash in `log_keys` and inserts the row; `recent_swims()`
reads her last few back. Nothing else can read or write `swim_logs`.

- New key (e.g. a lost phone): insert a new row in `log_keys` with
  `extensions.crypt('<key>', extensions.gen_salt('bf', 10))`, and set
  `revoked_at` on the old one.
- Supabase's security advisor flags the two functions as "SECURITY DEFINER
  callable by anon" and `log_keys` as "RLS with no policies". Both are the
  design: the functions are the only door, and they check the key.

## Looking at the archive

Supabase dashboard → Storage → `archive`. Frames are under
`frames/cam.scripps_pier/YYYY/MM/DD/`, raw snapshots under `raw/<source>/…`
(gzipped), and each day's run log is `manifest/YYYY-MM-DD/archive.jsonl`.

## Storage budget

About 50 cam frames/day at ~60 KB plus a few MB of gzipped snapshots, roughly
3–4 MB/day. The free tier's 1 GB lasts about 9–10 months. Before then, move
frames to Cloudflare R2 (10 GB free) via `SNORKEL_STORAGE`, or upgrade.
