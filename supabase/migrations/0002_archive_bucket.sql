-- Private bucket for cam frames, raw snapshots and manifests. The archiver
-- writes through the S3 endpoint with S3 access keys, which bypass RLS; no
-- policies are added, so the bucket is unreachable with the anon key.
insert into storage.buckets (id, name, public)
values ('archive', 'archive', false)
on conflict (id) do nothing;
