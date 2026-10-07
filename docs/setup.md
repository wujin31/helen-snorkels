# Setup and infrastructure

## What exists

| Piece | Where | Notes |
|---|---|---|
| Supabase project `snorkel-status` | ref `dujjlhiytnrtsebxshhw`, region us-west-1, free tier | Migrations in `supabase/migrations/` are applied |
| `archive` bucket | Supabase Storage, private | Raw snapshots and manifests |
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
| `SNORKEL_CONTACT` | An email for the User-Agent; NWS asks API clients for one |
| `SNORKEL_STORAGE` | Override storage, e.g. `s3:<bucket>` plus `S3_*` secrets, if we move to R2 |

## If scheduled runs stop

GitHub's cron schedules on this repository fire late, in bursts, or not at
all for hours (in practice nearly every run is dispatched by the pacemaker).
`pacemaker.yml` covers the gaps: it runs around the clock as a chain of ~5.5 h
runs, and every 5 minutes it dispatches Archive if its last run is 14+ minutes
old and Score if its last run is 58+ minutes old, within their daylight
windows. Each run queues its successor as soon as it starts; the concurrency
group holds that run until the current one ends, so even a lost runner (as on
2026-10-05) only ends one link. Archive and Score also restart the pacemaker
if no run is active or queued. Start it by hand any time from Actions →
Pacemaker → Run workflow.

Schedules run as whoever last edited the cron lines, so change `schedule:`
blocks in commits authored by the repo owner (see CLAUDE.md).

## One switch to flip: GitHub Pages

Settings → Pages → Build and deployment → Source: **GitHub Actions**. Until
then the Score workflow still scores and records history, and skips the
deploy with a warning.

## Looking at the archive

Supabase dashboard → Storage → `archive`. Raw snapshots are under
`raw/<source>/…` (gzipped), and each day's run log is
`manifest/YYYY-MM-DD/archive.jsonl`.

## Storage budget

About 3 MB of gzipped snapshots a day with twelve spots (measured 2026-10-07:
18 MB after ten days), mostly CDIP wave files. The free tier's 1 GB lasts
roughly a year. Before then, prune old raw snapshots (`Storage.delete`, also
supported by the gateway) or move to Cloudflare R2 (10 GB free) via
`SNORKEL_STORAGE`.
