-- Apply only after the final wake stability test is complete.

alter table public.action_queue
  add column if not exists expires_at timestamptz,
  add column if not exists superseded_at timestamptz,
  add column if not exists superseded_by uuid,
  add column if not exists claimed_by text;

create index if not exists action_queue_stackchan_pending_idx
  on public.action_queue (domain, status, priority desc, created_at asc)
  where domain = 'stackchan';

create or replace function public.stackchan_enqueue(
  p_action text,
  p_payload jsonb,
  p_ttl_seconds integer default null,
  p_replace_pending boolean default false,
  p_source text default 'xiaoke-actions'
)
returns setof public.action_queue
language plpgsql
security definer
set search_path = public
as $$
declare
  new_id uuid := gen_random_uuid();
  new_expires_at timestamptz;
begin
  if p_action not in ('speak', 'emote', 'move_head', 'wiggle') then
    raise exception 'invalid_stackchan_action';
  end if;

  if p_ttl_seconds is not null then
    new_expires_at := now() + make_interval(secs => greatest(1, p_ttl_seconds));
  end if;

  if p_replace_pending then
    update public.action_queue
       set status = 'superseded',
           superseded_at = now(),
           superseded_by = new_id,
           finished_at = now()
     where domain = 'stackchan'
       and action = p_action
       and status = 'pending';
  end if;

  return query
  insert into public.action_queue (
    id, domain, action, payload, status, priority, source, expires_at
  )
  values (
    new_id, 'stackchan', p_action, coalesce(p_payload, '{}'::jsonb),
    'pending', 0, p_source, new_expires_at
  )
  returning *;
end;
$$;

create or replace function public.stackchan_claim_next(p_device_id text)
returns setof public.action_queue
language plpgsql
security definer
set search_path = public
as $$
declare
  claimed_id uuid;
begin
  update public.action_queue
     set status = 'expired',
         finished_at = now(),
         error = 'ttl_expired_before_claim'
   where domain = 'stackchan'
     and status = 'pending'
     and expires_at is not null
     and expires_at <= now();

  select id into claimed_id
    from public.action_queue
   where domain = 'stackchan'
     and status = 'pending'
     and (expires_at is null or expires_at > now())
   order by priority desc, created_at asc
   for update skip locked
   limit 1;

  if claimed_id is null then
    return;
  end if;

  return query
  update public.action_queue
     set status = 'running',
         claimed_at = now(),
         claimed_by = nullif(trim(p_device_id), '')
   where id = claimed_id
   returning *;
end;
$$;

create or replace function public.stackchan_finish(
  p_id uuid,
  p_ok boolean,
  p_result jsonb default '{}'::jsonb,
  p_error text default null
)
returns setof public.action_queue
language sql
security definer
set search_path = public
as $$
  update public.action_queue
     set status = case when p_ok then 'done' else 'error' end,
         finished_at = now(),
         result = coalesce(p_result, '{}'::jsonb),
         error = case when p_ok then null else coalesce(p_error, 'device_error') end
   where id = p_id
     and domain = 'stackchan'
     and status = 'running'
  returning *;
$$;

create or replace function public.stackchan_cancel(p_id uuid)
returns setof public.action_queue
language sql
security definer
set search_path = public
as $$
  update public.action_queue
     set status = 'cancelled',
         finished_at = now(),
         error = 'cancelled_by_xiaoke'
   where id = p_id
     and domain = 'stackchan'
     and status = 'pending'
  returning *;
$$;

revoke all on function public.stackchan_enqueue(text, jsonb, integer, boolean, text) from public;
revoke all on function public.stackchan_claim_next(text) from public;
revoke all on function public.stackchan_finish(uuid, boolean, jsonb, text) from public;
revoke all on function public.stackchan_cancel(uuid) from public;

grant execute on function public.stackchan_enqueue(text, jsonb, integer, boolean, text) to service_role;
grant execute on function public.stackchan_claim_next(text) to service_role;
grant execute on function public.stackchan_finish(uuid, boolean, jsonb, text) to service_role;
grant execute on function public.stackchan_cancel(uuid) to service_role;
