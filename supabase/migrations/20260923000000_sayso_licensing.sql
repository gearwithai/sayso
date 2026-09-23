-- Sayso: devices get a free trial automatically; a license key unlocks unlimited use.
-- Only the sayso-api edge function (service role) touches these tables.

create table public.licenses (
  id uuid primary key default gen_random_uuid(),
  key text not null unique,
  email text,
  plan text not null default 'pro' check (plan in ('pro')),
  status text not null default 'active' check (status in ('active', 'cancelled', 'refunded')),
  seats int not null default 3 check (seats > 0),
  expires_at timestamptz,
  source text,              -- 'manual', 'stripe', ...
  source_ref text,          -- payment / subscription id
  created_at timestamptz not null default now()
);

create table public.devices (
  id uuid primary key default gen_random_uuid(),
  token_hash text not null unique,
  machine_hash text,
  app_version text,
  words_used bigint not null default 0,
  word_limit int not null default 2000,
  license_id uuid references public.licenses(id) on delete set null,
  created_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now()
);
create index devices_machine_hash_idx on public.devices (machine_hash);
create index devices_license_id_idx on public.devices (license_id);

create table public.usage_daily (
  device_id uuid not null references public.devices(id) on delete cascade,
  day date not null default current_date,
  words int not null default 0,
  primary key (device_id, day)
);

alter table public.licenses enable row level security;
alter table public.devices enable row level security;
alter table public.usage_daily enable row level security;
-- No policies on purpose: the public/anon key can read or write nothing.

create or replace function public.sayso_add_usage(p_device uuid, p_words int)
returns void
language sql
security invoker
set search_path = ''
as $$
  update public.devices set words_used = words_used + p_words, last_seen_at = now() where id = p_device;
  insert into public.usage_daily (device_id, day, words) values (p_device, current_date, p_words)
  on conflict (device_id, day) do update set words = public.usage_daily.words + excluded.words;
$$;
revoke all on function public.sayso_add_usage(uuid, int) from public, anon, authenticated;
grant execute on function public.sayso_add_usage(uuid, int) to service_role;
