-- User Story 1.2.2 (AB#211): check that the backend's task queries use the indexes,
-- with realistic data volume. See docs/performance/indexing.md.
--
-- SAFE TO RUN: it does not touch the real tables or their data. It builds TEMPORARY
-- copies of tasks and courses (same columns and indexes), fills them with 20,000 fake
-- tasks for 200 fake students, runs EXPLAIN ANALYZE on the exact queries the backend
-- sends, and then raises an error on purpose so that everything is rolled back.
--
-- How to run: paste the whole file into Supabase -> SQL Editor -> Run.
-- The result appears as an ERROR whose message starts with "BENCHMARK RESULT".
-- That "error" is expected: it is how the script reports and rolls back in one step.

do $$
declare
  student uuid;
  ids text[];
  line text;
  report text := '';
  q text;
begin
  perform setseed(0.211);

  -- 1. Temporary copies with the same columns, defaults and INDEXES as the real tables
  --    (foreign keys are not copied, so no fake auth users are needed).
  create temp table bench_courses (like public.courses including defaults including constraints including indexes) on commit drop;
  create temp table bench_tasks   (like public.tasks   including defaults including constraints including indexes) on commit drop;

  -- 2. 200 students x 10 courses, and 100 tasks each = 20,000 tasks.
  insert into bench_courses (user_id, moodle_course_id, name)
  select u, c, 'Course ' || c
  from (select gen_random_uuid() u from generate_series(1, 200)) s, generate_series(1, 10) c;

  insert into bench_tasks (user_id, moodle_id, title, moodle_course_id, due_date, is_relevant, ai_priority)
  select c.user_id,
         'm' || c.moodle_course_id || '-' || n,
         'Task ' || n,
         c.moodle_course_id,
         case when random() < 0.1 then null else now() + (random() * 120 - 30) * interval '1 day' end,
         random() > 0.2,
         1 + floor(random() * 5)::int
  from bench_courses c, generate_series(1, 10) n;

  analyze bench_courses;
  analyze bench_tasks;

  select user_id into student from bench_tasks limit 1;
  select array_agg(moodle_id) into ids from (select moodle_id from bench_tasks where user_id = student limit 50) x;

  report := report || format(E'rows: %s tasks, %s courses, %s students\n',
    (select count(*) from bench_tasks), (select count(*) from bench_courses),
    (select count(distinct user_id) from bench_tasks));

  -- 3. The queries the backend sends (backend/app/db.py).
  -- Q1: GET /api/tasks (dashboard): own relevant tasks with the course name, soonest first.
  q := format($q$
    select t.*, c.name
    from bench_tasks t
    left join bench_courses c on c.user_id = t.user_id and c.moodle_course_id = t.moodle_course_id
    where t.user_id = %L and t.is_relevant
    order by t.due_date asc nulls last$q$, student);
  report := report || E'\n== Q1 GET /api/tasks ==\n';
  for line in execute 'explain (analyze, costs off, summary on) ' || q loop report := report || line || E'\n'; end loop;

  -- Q2: GET /api/tasks?include_filtered=true
  q := format($q$
    select * from bench_tasks where user_id = %L order by due_date asc nulls last$q$, student);
  report := report || E'\n== Q2 GET /api/tasks?include_filtered=true ==\n';
  for line in execute 'explain (analyze, costs off, summary on) ' || q loop report := report || line || E'\n'; end loop;

  -- Q3: POST /api/tasks/sync, "what is saved for these 50 tasks?" (existing_tasks)
  q := format($q$
    select moodle_id from bench_tasks where user_id = %L and moodle_id = any(%L::text[])$q$, student, ids);
  report := report || E'\n== Q3 sync: existing_tasks (50 ids) ==\n';
  for line in execute 'explain (analyze, costs off, summary on) ' || q loop report := report || line || E'\n'; end loop;

  -- 4. Report and roll back everything.
  raise exception E'BENCHMARK RESULT (everything rolled back)\n%', report;
end $$;
