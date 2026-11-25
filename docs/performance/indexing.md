# Database indexing for task queries

User Story 1.2.2 (AB#211), tasks 1.2.2.1 to 1.2.2.4. Supabase project `dsclfcysdrjchhyynggt`.

Goal: the dashboard's task queries stay well under **100 ms** as the number of students and tasks grows.

## Indexes

| Table | Index | Columns | Serves |
|---|---|---|---|
| `tasks` | `idx_tasks_user_due` | `(user_id, due_date)` | `GET /api/tasks`: one student's tasks, soonest deadline first |
| `tasks` | `idx_tasks_user_course` | `(user_id, moodle_course_id)` | The `tasks -> courses` foreign key: deleting a course (or a student) cascades to their tasks without scanning the whole table. Also the course filter planned for the dashboard (US 4.3.2) |
| `tasks` | `tasks_user_moodle_unique` (unique) | `(user_id, moodle_id)` | `POST /api/tasks/sync`: the upsert's `on_conflict`, so a re-sync updates instead of duplicating |
| `courses` | `courses_user_moodle_course_unique` (unique) | `(user_id, moodle_course_id)` | The course upsert and the join that adds the course name to each task |
| all | primary keys | `id` | Lookups by id |

All are B-tree indexes. `user_id` comes first in every composite index because every query the backend sends is limited to one student (and Row Level Security adds `(select auth.uid()) = user_id` to every query anyway, see [docs/security/rls.md](../security/rls.md)). They are created by `supabase/migrations/001_initial_schema.sql` (the two `idx_` indexes and the unique constraints); `supabase/migrations/20261123190000_task_indexes.sql` documents what each one is for and is safe to re-run.

`due_date` ascending with nulls last is the B-tree default, and it is exactly the order the backend asks for (`order("due_date", desc=False, nullsfirst=False)` in `backend/app/db.py`), so Postgres can return rows already sorted.

## Verification

### Real database

On the real `tasks` table (`EXPLAIN` of the dashboard query, Nov 23 2026):

```
Index Scan using idx_tasks_user_due on tasks
  Index Cond: (user_id = ...)
  Filter: is_relevant
```

The real table only has a handful of rows, so this alone says little about speed at scale.

### Benchmark with 20,000 tasks

[`explain_tasks.sql`](explain_tasks.sql) builds temporary copies of `tasks` and `courses` with the same columns and indexes, fills them with **20,000 tasks for 200 students** (10 courses and 100 tasks each, 20% marked not relevant, 10% without a due date), runs `EXPLAIN ANALYZE` on the exact queries the backend sends, and rolls everything back. It never touches the real tables. Paste it into the Supabase SQL Editor to run it again.

> **The ERROR is expected.** The script ends with `raise exception` on purpose: that is how it shows the results and rolls everything back in one step. A successful run therefore shows an **error** whose message starts with `BENCHMARK RESULT`, followed by the plans. Any other error means something really failed.

Results (Nov 23 2026; index names have a `bench_` prefix because they are on the temporary copies):

| Query | Backend call | Plan | Execution time |
|---|---|---|---|
| Q1 | `GET /api/tasks` (relevant tasks + course name, sorted) | Bitmap Index Scan on `(user_id, due_date)` for tasks, Bitmap Index Scan on `(user_id, moodle_course_id)` for courses, hash join, in-memory sort of 83 rows (35 kB) | **0.25 ms** |
| Q2 | `GET /api/tasks?include_filtered=true` | **Index Scan** on `(user_id, due_date)`, already in order, no sort | **0.07 ms** |
| Q3 | Sync: which of 50 tasks already exist | Bitmap Index Scan on `(user_id, due_date)` + filter on `moodle_id` | **0.10 ms** |

No query reads the whole table (no `Seq Scan`), and all are about 400 times under the 100 ms target.

About Q1: with the course join and the `is_relevant` filter, Postgres prefers a *bitmap* index scan (it reads the index first, then fetches the student's rows in disk order) and then sorts the ~100 rows in memory. Both scan types use `idx_tasks_user_due`; the planner picks the cheaper one for the row count. For a single student's tasks the sort is negligible.

## Acceptance criteria

| Criterion | Status |
|---|---|
| Composite index `idx_tasks_user_due` on `(user_id, due_date)` | In place (Epic 1); recorded in `supabase/migrations/20261123190000_task_indexes.sql` |
| `EXPLAIN ANALYZE` confirms an index scan for task retrieval | Real table: Index Scan. 20,000-task benchmark: Index Scan (Q2) and Bitmap Index Scan (Q1, Q3), never a sequential scan; all under 0.3 ms. **For this criterion a Bitmap Index Scan counts as an index scan:** it reads the same `idx_tasks_user_due` index and only differs in how the rows are then fetched, and Postgres chooses it when it is cheaper. What the criterion rules out is a `Seq Scan` over the whole table |

## Not done (on purpose)

- **No separate index for `is_relevant`.** It is a filter on a student's ~100 rows; an index would cost more on every write than it saves.

Revisit if a student ever has thousands of tasks, or if new queries filter by something other than `user_id`.
