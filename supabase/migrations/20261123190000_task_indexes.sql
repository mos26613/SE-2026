-- User Story 1.2.2 (AB#211): indexes for the task queries.
--
-- These already exist in project dsclfcysdrjchhyynggt (created by Epic 1 in the dashboard).
-- This file records them in version control; every statement is idempotent, so running
-- it again changes nothing. See docs/performance/indexing.md.

-- Dashboard: "my tasks, soonest deadline first" (GET /api/tasks).
-- B-tree on (user_id, due_date): finds one student's rows and returns them already
-- ordered by due_date (ASC NULLS LAST, which is also the B-tree default).
create index if not exists idx_tasks_user_due on public.tasks using btree (user_id, due_date);

-- Also in place, as unique constraints (they create their own B-tree indexes):
--   tasks   unique (user_id, moodle_id)         -> tasks_user_moodle_unique
--           used by the sync upsert (on_conflict) and the existing_ids lookup
--   courses unique (user_id, moodle_course_id)  -> courses_user_moodle_course_unique
--           used by the course upsert and the tasks -> courses join
