create table if not exists public.action_queue (
  id uuid primary key,
  domain text not null,
  action text not null,
  payload jsonb not null default '{}'::jsonb,
  status text not null default 'pending',
  priority integer not null default 0,
  source text,
  created_at timestamptz not null default now(),
  claimed_at timestamptz,
  finished_at timestamptz,
  result jsonb,
  error text
);

create index if not exists action_queue_pending_idx
  on public.action_queue (domain, status, priority desc, created_at asc);

create index if not exists action_queue_toy_stop_idx
  on public.action_queue (domain, action, status, priority desc, created_at asc);

alter table public.action_queue enable row level security;
