-- Private bucket for cam frames, raw snapshots and manifests. Only the
-- service role writes to it (via the archive-gateway edge function); no
-- storage policies are added, so the anon key can't reach it.
insert into storage.buckets (id, name, public)
values ('archive', 'archive', false)
on conflict (id) do nothing;
