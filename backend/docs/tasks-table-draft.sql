-- DRAFT for discussion with the Epic 1 (database) owner. Not applied to Supabase.
-- Matches the columns used by app/db.py.

-- Moodle Assignment Organizer: tasks table
-- Run this in Supabase: SQL Editor -> New query -> paste -> Run

create table public.tasks (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null references auth.users (id) on delete cascade,

  -- What the extension scrapes from Moodle
  moodle_id     text not null,              -- Moodle's own ID for the assignment
  title         text not null,
  course_name   text,
  description   text,
  due_date      timestamptz,
  moodle_url    text,

  -- What Gemini adds
  is_relevant   boolean default true,       -- false = AI filtered it out (e.g. not a real assignment)
  ai_category   text,                       -- e.g. 'homework', 'exam', 'project', 'reading'
  ai_priority   smallint check (ai_priority between 1 and 5),
  ai_summary    text,

  -- Student-side state
  status        text not null default 'open' check (status in ('open', 'done')),

  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),

  -- One row per Moodle assignment per student, so a re-sync updates instead of duplicating
  unique (user_id, moodle_id)
);

create index tasks_user_due_idx on public.tasks (user_id, due_date);

-- Keep updated_at current on every update
create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger tasks_set_updated_at
before update on public.tasks
for each row execute function public.set_updated_at();

-- Row Level Security: each student can only see and change their own tasks
alter table public.tasks enable row level security;

create policy "Students manage their own tasks"
on public.tasks
for all
using (auth.uid() = user_id)
with check (auth.uid() = user_id);
