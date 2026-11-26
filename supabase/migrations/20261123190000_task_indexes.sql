-- User Story 1.2.2 (AB#211): indexes for the task queries.
--
-- These are created by 001_initial_schema.sql and exist in project dsclfcysdrjchhyynggt.
-- This file documents what each one is for; every statement is idempotent, so running
-- it again changes nothing. See docs/performance/indexing.md.

-- Dashboard: "my tasks, soonest deadline first" (GET /api/tasks).
-- B-tree on (user_id, due_date): finds one student's rows and returns them already
-- ordered by due_date (ASC NULLS LAST, which is also the B-tree default).
create index if not exists idx_tasks_user_due on public.tasks using btree (user_id, due_date);

-- The tasks -> courses foreign key: deleting a course or a student cascades to their tasks
-- through this index instead of a full scan. Also the dashboard's course filter (US 4.3.2).
create index if not exists idx_tasks_user_course on public.tasks using btree (user_id, moodle_course_id);

-- Also in place, as unique constraints (they create their own B-tree indexes):
--   tasks   unique (user_id, moodle_id)         -> tasks_user_moodle_unique
--           used by the sync upsert (on_conflict) and the existing_tasks lookup
--   courses unique (user_id, moodle_course_id)  -> courses_user_moodle_course_unique
--           used by the course upsert and the tasks -> courses join
