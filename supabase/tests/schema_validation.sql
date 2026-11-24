-- Manual check of the core schema (US 1.2.1, AB#206).
--
-- How to run: Supabase dashboard -> SQL Editor -> paste this file -> Run.
-- It changes nothing: everything happens in a transaction that is rolled back at the end.
-- A successful run ends with the notice "schema validation passed".

begin;

do $$
declare
  u1 constant uuid := '11111111-1111-1111-1111-111111111111';
  u2 constant uuid := '22222222-2222-2222-2222-222222222222';
  n int;
begin
  -- 1. A new Auth user gets a profile row from the trigger.
  insert into auth.users (id, email) values (u1, 'validation-1@example.test');
  insert into auth.users (id, email) values (u2, 'validation-2@example.test');
  select count(*) into n from public.users where id in (u1, u2);
  assert n = 2, 'check 1 failed: the on_auth_user_created trigger did not create the profile rows';

  -- 2. A course and tasks of student 1.
  insert into public.courses (user_id, moodle_course_id, name) values (u1, 100, 'Validation course');
  insert into public.tasks (user_id, moodle_id, moodle_course_id, title) values (u1, 'a-1', 100, 'Task with a course');
  insert into public.tasks (user_id, moodle_id, title) values (u1, 'a-2', 'Task without a course');

  -- 3. Uniqueness: the same Moodle assignment twice for one student is rejected.
  begin
    insert into public.tasks (user_id, moodle_id, title) values (u1, 'a-2', 'Duplicate');
    raise exception 'check 3 failed: a duplicate (user_id, moodle_id) was accepted';
  exception when unique_violation then
    null;
  end;

  -- 4. Uniqueness: the same Moodle course twice for one student is rejected.
  begin
    insert into public.courses (user_id, moodle_course_id, name) values (u1, 100, 'Duplicate');
    raise exception 'check 4 failed: a duplicate (user_id, moodle_course_id) was accepted';
  exception when unique_violation then
    null;
  end;

  -- 5. A task cannot point to a course of another student.
  begin
    insert into public.tasks (user_id, moodle_id, moodle_course_id, title) values (u2, 'b-1', 100, 'Wrong course owner');
    raise exception 'check 5 failed: a task was linked to a course of another student';
  exception when foreign_key_violation then
    null;
  end;

  -- 6. Status accepts only open or done.
  begin
    insert into public.tasks (user_id, moodle_id, title, status) values (u1, 'a-3', 'Bad status', 'late');
    raise exception 'check 6 failed: an invalid status was accepted';
  exception when check_violation then
    null;
  end;

  -- 7. Deleting a course deletes its tasks, and only those.
  delete from public.courses where user_id = u1 and moodle_course_id = 100;
  select count(*) into n from public.tasks where user_id = u1 and moodle_id = 'a-1';
  assert n = 0, 'check 7 failed: deleting a course did not delete its task';
  select count(*) into n from public.tasks where user_id = u1 and moodle_id = 'a-2';
  assert n = 1, 'check 7 failed: deleting a course deleted a task that has no course';

  -- 8. Deleting an Auth user deletes the profile and everything under it.
  delete from auth.users where id = u1;
  select count(*) into n from public.users where id = u1;
  assert n = 0, 'check 8 failed: the profile row was not deleted';
  select count(*) into n from public.tasks where user_id = u1;
  assert n = 0, 'check 8 failed: tasks of a deleted user were not deleted';

  raise notice 'schema validation passed';
end;
$$;

rollback;
