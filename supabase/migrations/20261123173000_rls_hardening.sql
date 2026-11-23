-- User Story 1.3.1 (AB#226): Multi-tenant Row Level Security hardening.
--
-- The tables and their RLS policies were created in the Supabase dashboard (Epic 1).
-- Each of users, courses and tasks already has RLS enabled and one policy for the
-- `authenticated` role that allows a row only when auth.uid() matches its owner, for
-- SELECT, INSERT, UPDATE and DELETE. See docs/security/rls.md.
--
-- This migration removes privileges that RLS does not protect:

-- 1. TRUNCATE ignores RLS entirely (it would empty the table for every student).
--    TRIGGER and REFERENCES are not needed by the Data API either.
--    SELECT/INSERT/UPDATE/DELETE for `authenticated` stay: RLS limits them to own rows.
revoke truncate, trigger, references on table public.users, public.courses, public.tasks
  from anon, authenticated;

-- 2. rls_auto_enable() is the event-trigger function that turns RLS on for every new
--    table. Postgres runs it for DDL without checking EXECUTE, so nobody needs to call
--    it through /rest/v1/rpc (Supabase security advisor lints 0028 and 0029).
revoke execute on function public.rls_auto_enable() from public, anon, authenticated;
