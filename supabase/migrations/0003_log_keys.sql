-- Two-tap logging without accounts or email: a private link carries a long
-- random key that the page keeps on her phone. These functions check the key's
-- bcrypt hash and only then insert or read her logs. The tables stay locked
-- behind RLS; the functions are the only way in for the anon role.

create extension if not exists pgcrypto with schema extensions;

alter table public.swim_logs alter column user_id drop not null;
alter table public.swim_logs add column logged_by text;
alter table public.swim_logs
  add constraint swim_logs_spot_id_len check (char_length(spot_id) between 1 and 64);

create table public.log_keys (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  key_hash text not null,
  created_at timestamptz not null default now(),
  revoked_at timestamptz
);
alter table public.log_keys enable row level security; -- no policies: invisible to clients

create or replace function public.log_key_owner(p_key text)
returns text
language sql
stable
security definer
set search_path = ''
as $$
  select k.name
  from public.log_keys k
  where k.revoked_at is null
    and p_key is not null
    and char_length(p_key) >= 20
    and k.key_hash = extensions.crypt(p_key, k.key_hash)
  limit 1
$$;

create or replace function public.log_swim(
  p_key text,
  p_spot_id text,
  p_vis_ft numeric,
  p_rating smallint,
  p_note text default null,
  p_swam_at timestamptz default null
)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_owner text := public.log_key_owner(p_key);
  v_id uuid;
begin
  if v_owner is null then
    raise exception 'invalid log key' using errcode = '28000';
  end if;
  insert into public.swim_logs (spot_id, swam_at, vis_ft, rating, note, logged_by)
  values (p_spot_id, coalesce(p_swam_at, now()), p_vis_ft, p_rating, nullif(trim(p_note), ''), v_owner)
  returning id into v_id;
  return v_id;
end
$$;

create or replace function public.recent_swims(p_key text, p_limit integer default 5)
returns table (
  id uuid,
  spot_id text,
  swam_at timestamptz,
  vis_ft numeric,
  rating smallint,
  note text
)
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  v_owner text := public.log_key_owner(p_key);
begin
  if v_owner is null then
    raise exception 'invalid log key' using errcode = '28000';
  end if;
  return query
    select s.id, s.spot_id, s.swam_at, s.vis_ft, s.rating, s.note
    from public.swim_logs s
    where s.logged_by = v_owner
    order by s.swam_at desc
    limit least(greatest(p_limit, 1), 50);
end
$$;

revoke all on function public.log_key_owner(text) from public, anon, authenticated;
revoke all on function public.log_swim(text, text, numeric, smallint, text, timestamptz) from public;
revoke all on function public.recent_swims(text, integer) from public;
grant execute on function public.log_swim(text, text, numeric, smallint, text, timestamptz) to anon, authenticated;
grant execute on function public.recent_swims(text, integer) to anon, authenticated;
