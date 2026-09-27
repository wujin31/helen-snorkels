-- The swim log is cut: the page asks nothing of anyone. Ground truth for the
-- visibility estimate comes from the pier cam and dive reports instead.
-- Both tables were empty. The archive bucket and its gateway are unaffected.

drop function if exists public.recent_swims(text, integer);
drop function if exists public.log_swim(text, text, numeric, smallint, text, timestamptz);
drop function if exists public.log_key_owner(text);
drop table if exists public.log_keys;
drop table if exists public.swim_logs;
