-- US 1.2.1 (AB#206): document the core schema.
--
-- Comments only: no table, column, index or policy changes, so it is safe to run on a
-- database that already has 001_initial_schema.sql. Re-running it is harmless.

comment on table public.users is
  'Student profile. One row per Supabase Auth user (id = auth.users.id), created by the on_auth_user_created trigger.';

comment on table public.courses is
  'A Moodle course of a student. Unique per (user_id, moodle_course_id). The course name lives here, not in tasks.';

comment on table public.tasks is
  'An assignment collected from Moodle. Unique per (user_id, moodle_id). Linked to courses by (user_id, moodle_course_id).';

-- 001 described is_modified as "manual edit by the user". In this project the column means
-- something else: Moodle details of the task (for example the due date) changed after we
-- first saved it. The dashboard uses it for the "Recently Modified" badge. Nothing sets it
-- yet: change detection is User Story 3.3.1.
comment on column public.tasks.is_modified is
  'True when the task details changed on Moodle after it was first saved (for example the lecturer moved the due date). Drives the "Recently Modified" badge. Set by change detection (US 3.3.1).';
