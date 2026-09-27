# One-time setup

The pipeline runs on GitHub Actions and stores everything private in a Supabase
project. These are the steps only a repo/account owner can do.

## 1. Supabase project

1. Create a free project (region: `us-west-1` is closest). Claude can do this
   through the Supabase connector once you say so.
2. Apply the migrations in `supabase/migrations/` (the connector can do this
   too): the private `swim_logs` table with row-level security, and the private
   `archive` bucket.
3. **Storage → S3 Connection**: note the endpoint and region, then create an
   access key pair.
4. **Authentication → Sign In / Providers**: turn off "Allow new users to sign
   up", then invite the two of you by email (magic-link sign-in).

## 2. GitHub secrets and variables

Settings → Secrets and variables → Actions.

| Kind | Name | Value |
|---|---|---|
| Secret | `S3_ENDPOINT` | e.g. `https://<ref>.storage.supabase.co/storage/v1/s3` |
| Secret | `S3_REGION` | the project region, e.g. `us-west-1` |
| Secret | `S3_BUCKET` | `archive` |
| Secret | `S3_ACCESS_KEY_ID` | from step 1.3 |
| Secret | `S3_SECRET_ACCESS_KEY` | from step 1.3 |
| Variable | `SNORKEL_CONTACT` | an email for the User-Agent (NWS asks for one) |
| Variable | `CAM_CAPTURE_ENABLED` | leave unset; set to `false` to pause cam capture |

Later (scorer + page): `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` (secrets),
`VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` (variables), and
Settings → Pages → Source: **GitHub Actions**.

## 3. Start archiving

Scheduled workflows only run from the default branch, so collection starts when
this lands on `main`. Then Actions → Archive → Run workflow (tick "force") to
check that frames and snapshots arrive in the bucket.

## Storage budget

About 50 cam frames/day at ~60 KB plus a few MB of gzipped snapshots, so roughly
3–4 MB/day. The free tier's 1 GB lasts about 9–10 months. Before then, move to
Cloudflare R2 (10 GB free) by changing the `S3_*` secrets, or upgrade.
