# Setup and infrastructure

## What exists

| Piece | Where | Notes |
|---|---|---|
| Supabase project `snorkel-status` | ref `dujjlhiytnrtsebxshhw`, region us-west-1, free tier | Migrations in `supabase/migrations/` are applied |
| `swim_logs` table | Postgres, row-level security on | Each signed-in user sees only their own rows |
| `archive` bucket | Supabase Storage, private | Cam frames, raw snapshots, manifests |
| `archive-gateway` edge function | `https://dujjlhiytnrtsebxshhw.supabase.co/functions/v1/archive-gateway` | Source in `supabase/functions/archive-gateway/` |
| Archive workflow | `.github/workflows/archive.yml` | Every 15 min in daylight, from `main` |

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

## Still to do by hand (later phases)

- **Swim-log sign-in:** in the Supabase dashboard, Authentication → Sign In /
  Providers: turn off "Allow new users to sign up", then invite the two of you
  by email (magic link). Needed when the log form ships.
- **GitHub Pages:** Settings → Pages → Source: **GitHub Actions**. Needed when
  the page ships.

## Looking at the archive

Supabase dashboard → Storage → `archive`. Frames are under
`frames/cam.scripps_pier/YYYY/MM/DD/`, raw snapshots under `raw/<source>/…`
(gzipped), and each day's run log is `manifest/YYYY-MM-DD/archive.jsonl`.

## Storage budget

About 50 cam frames/day at ~60 KB plus a few MB of gzipped snapshots, roughly
3–4 MB/day. The free tier's 1 GB lasts about 9–10 months. Before then, move
frames to Cloudflare R2 (10 GB free) via `SNORKEL_STORAGE`, or upgrade.
