-- Direct check of the Row Level Security configuration (US 1.3.1, AB#226).
--
-- backend/tests/test_rls.py proves the behaviour (student B can't read or change
-- student A's data). This script checks the configuration itself, so the first
-- acceptance criterion ("RLS enabled on courses and tasks") does not rest on behaviour alone.
--
-- How to run: Supabase dashboard -> SQL Editor -> paste this file -> Run. It only reads.
-- A successful run ends with the notice "rls check passed"; any problem stops it with
-- an error that names the check.

do $$
declare
  t text;
  n int;
begin
  foreach t in array array['users', 'courses', 'tasks'] loop
    -- 1. RLS is enabled on the table.
    select count(*) into n
    from pg_class
    where relnamespace = 'public'::regnamespace and relname = t and relrowsecurity;
    assert n = 1, format('check 1 failed: RLS is not enabled on public.%s', t);

    -- 2. There is a policy for `authenticated` covering every command (FOR ALL), and its
    --    USING and WITH CHECK both compare auth.uid() with the owner column.
    select count(*) into n
    from pg_policies
    where schemaname = 'public' and tablename = t
      and cmd = 'ALL'
      and 'authenticated' = any(roles)
      and qual ilike '%auth.uid()%'
      and with_check ilike '%auth.uid()%';
    assert n >= 1, format('check 2 failed: no FOR ALL auth.uid() policy for authenticated on public.%s', t);

    -- 3. No policy at all for anon.
    select count(*) into n
    from pg_policies
    where schemaname = 'public' and tablename = t and ('anon' = any(roles) or 'public' = any(roles));
    assert n = 0, format('check 3 failed: public.%s has a policy for anon or public', t);

    -- 4. TRUNCATE (which ignores RLS) is revoked from anon and authenticated.
    assert not has_table_privilege('authenticated', format('public.%I', t), 'TRUNCATE'),
      format('check 4 failed: authenticated can TRUNCATE public.%s', t);
    assert not has_table_privilege('anon', format('public.%I', t), 'TRUNCATE'),
      format('check 4 failed: anon can TRUNCATE public.%s', t);
  end loop;

  -- 5. rls_auto_enable() (created by Supabase's automatic RLS, if present) can't be
  --    called through the API.
  if to_regprocedure('public.rls_auto_enable()') is not null then
    assert not has_function_privilege('anon', 'public.rls_auto_enable()', 'EXECUTE'),
      'check 5 failed: anon can execute rls_auto_enable()';
    assert not has_function_privilege('authenticated', 'public.rls_auto_enable()', 'EXECUTE'),
      'check 5 failed: authenticated can execute rls_auto_enable()';
  end if;

  raise notice 'rls check passed';
end;
$$;
