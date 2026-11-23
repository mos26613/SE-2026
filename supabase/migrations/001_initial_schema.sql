create table if not exists public.users (
  id uuid primary key references auth.users(id) on delete cascade,
  email text not null,
  created_at timestamptz default now() not null
);


create table if not exists public.courses (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  moodle_course_id int not null,
  name text not null,
  created_at timestamptz default now() not null,
  constraint courses_user_moodle_course_unique unique (user_id, moodle_course_id)
);


create table if not exists public.tasks (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  moodle_id text not null,
  moodle_course_id int not null,
  title text not null,
  description text,
  moodle_url text,
  due_date timestamptz,
  status text not null default 'open' check (status in ('open', 'done')),
  is_modified boolean default false not null,  -- סימון עריכה ידנית של המשתמש
  is_relevant boolean not null default true,
  ai_category text,
  ai_priority smallint check (ai_priority between 1 and 5),
  ai_summary text,
  created_at timestamptz default now() not null,
  updated_at timestamptz not null default now(),
  constraint tasks_user_moodle_unique unique (user_id, moodle_id),
  constraint tasks_course_fk
    foreign key (user_id, moodle_course_id)
    references public.courses (user_id, moodle_course_id)
    on delete cascade
);


create index if not exists idx_tasks_user_due on public.tasks (user_id, due_date);
create index if not exists idx_tasks_user_course on public.tasks (user_id, moodle_course_id);


create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists tasks_set_updated_at on public.tasks;
create trigger tasks_set_updated_at
  before update on public.tasks
  for each row
  execute function public.set_updated_at();


alter table public.users   enable row level security;
alter table public.courses enable row level security;
alter table public.tasks   enable row level security;


drop policy if exists "Users can view and edit their own profile" on public.users;
create policy "Users can view and edit their own profile"
  on public.users for all
  to authenticated
  using ((select auth.uid()) = id)
  with check ((select auth.uid()) = id);

drop policy if exists "Users can manage their own courses" on public.courses;
create policy "Users can manage their own courses"
  on public.courses for all
  to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

drop policy if exists "Users can manage their own tasks" on public.tasks;
create policy "Users can manage their own tasks"
  on public.tasks for all
  to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);


create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.users (id, email)
  values (new.id, coalesce(new.email, ''))
  on conflict (id) do nothing;
  return new;
end;
$$;


revoke execute on function public.handle_new_user() from public, anon, authenticated;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row
  execute function public.handle_new_user();


insert into public.users (id, email)
select id, coalesce(email, '')
from auth.users
on conflict (id) do nothing;


grant select, insert, update, delete
  on public.users, public.courses, public.tasks
  to authenticated;
