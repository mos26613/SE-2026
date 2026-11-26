-- User Story 1.3.1 (AB#226): Multi-tenant Row Level Security hardening.
--
-- The tables and their RLS policies are created by 001_initial_schema.sql (Epic 1).
-- Each of users, courses and tasks has RLS enabled and one policy for the
-- `authenticated` role that allows a row only when auth.uid() matches its owner, for
-- SELECT, INSERT, UPDATE and DELETE. See docs/security/rls.md.
--
-- This migration removes privileges that RLS does not protect:

-- 1. TRUNCATE ignores RLS entirely (it would empty the table for every student).
--    TRIGGER and REFERENCES are not needed by the Data API either.
--    SELECT/INSERT/UPDATE/DELETE for `authenticated` stay: RLS limits them to own rows.
revoke truncate, trigger, references on table public.users, public.courses, public.tasks
  from anon, authenticated;

-- 2. rls_auto_enable() is the event-trigger function behind the `ensure_rls` event trigger,
--    which turns RLS on for every new table in `public`. Supabase creates it when a project
--    is set up with automatic RLS, so it exists in our hosted project but not in a database
--    built only from these migrations (local or CI). Postgres runs it for DDL without
--    checking EXECUTE, so nobody needs to call it through /rest/v1/rpc (Supabase security
--    advisor lints 0028 and 0029). Revoke only where it exists, so this migration also
--    applies cleanly to a fresh database.
do $$
begin
  if to_regprocedure('public.rls_auto_enable()') is not null then
    revoke execute on function public.rls_auto_enable() from public, anon, authenticated;
  end if;
end;
$$;
