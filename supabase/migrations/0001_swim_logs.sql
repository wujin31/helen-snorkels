-- Her post-swim logs: the primary ground truth. Private per user.
create table public.swim_logs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  spot_id text not null,
  swam_at timestamptz not null default now(),
  vis_ft numeric(4, 1) check (vis_ft >= 0 and vis_ft <= 100),
  rating smallint check (rating between 1 and 5),
  note text check (char_length(note) <= 2000),
  created_at timestamptz not null default now()
);

create index swim_logs_user_swam_at on public.swim_logs (user_id, swam_at desc);

alter table public.swim_logs enable row level security;

-- Signed-in users see and edit only their own rows. The pipeline reads all
-- rows with the service-role key, which bypasses RLS.
create policy "own logs: select" on public.swim_logs
  for select to authenticated using ((select auth.uid()) = user_id);
create policy "own logs: insert" on public.swim_logs
  for insert to authenticated with check ((select auth.uid()) = user_id);
create policy "own logs: update" on public.swim_logs
  for update to authenticated
  using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy "own logs: delete" on public.swim_logs
  for delete to authenticated using ((select auth.uid()) = user_id);
