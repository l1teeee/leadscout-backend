-- LeadScout AI - Initial Schema for Supabase
-- Run this in the Supabase SQL editor

-- ─── TABLES ────────────────────────────────────────────────────────────────

create table if not exists workspaces (
  id         uuid        primary key default gen_random_uuid(),
  name       text        not null,
  slug       text        unique not null,
  country    text        not null default 'El Salvador',
  timezone   text        not null default 'America/El_Salvador',
  currency   text        not null default 'USD',
  industry   text,
  city       text,
  phone      text,
  website    text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists profiles (
  id           uuid        primary key,
  workspace_id uuid        not null references workspaces(id) on delete cascade,
  email        text        not null,
  full_name    text,
  avatar_url   text,
  role         text        not null default 'viewer',
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  constraint profiles_role_valid check (role in ('owner', 'admin', 'sales', 'analyst', 'viewer'))
);

create table if not exists leads (
  id              uuid          primary key default gen_random_uuid(),
  workspace_id    uuid          not null references workspaces(id) on delete cascade,
  name            text          not null,
  category        text          not null,
  location        text,
  address         text,
  latitude        double precision,
  longitude       double precision,
  score           int           not null default 0,
  status          text          not null default 'nuevo',
  priority        text          not null default 'media',
  issues          text[]        not null default '{}',
  phone           text,
  website         text,
  google_place_id text,
  source          text          not null default 'manual',
  last_contact    date,
  created_at      timestamptz   not null default now(),
  updated_at      timestamptz   not null default now(),
  constraint leads_score_range    check (score >= 0 and score <= 100),
  constraint leads_status_valid   check (status in ('nuevo', 'contactado', 'calificado', 'perdido')),
  constraint leads_priority_valid check (priority in ('alta', 'media', 'baja')),
  constraint leads_source_valid   check (source in ('manual', 'explorer'))
);

create table if not exists lead_activities (
  id           uuid        primary key default gen_random_uuid(),
  lead_id      uuid        not null references leads(id) on delete cascade,
  workspace_id uuid        not null references workspaces(id) on delete cascade,
  user_id      uuid        references profiles(id) on delete set null,
  type         text        not null,
  note         text,
  created_at   timestamptz not null default now(),
  constraint lead_activities_type_valid check (
    type in ('created', 'status_changed', 'note_added', 'contacted', 'qualified', 'lost')
  )
);

-- ─── INDICES ────────────────────────────────────────────────────────────────

-- Workspace isolation (most queries filter by workspace_id)
create index if not exists leads_workspace_id_idx
  on leads(workspace_id);

-- Composite indices for common filter patterns
create index if not exists leads_workspace_status_idx
  on leads(workspace_id, status);

create index if not exists leads_workspace_priority_idx
  on leads(workspace_id, priority);

create index if not exists leads_workspace_category_idx
  on leads(workspace_id, category);

create index if not exists leads_workspace_created_at_idx
  on leads(workspace_id, created_at desc);

create index if not exists leads_score_idx
  on leads(score);

-- Partial index: only indexed when google_place_id exists
create index if not exists leads_google_place_id_idx
  on leads(google_place_id)
  where google_place_id is not null;

-- Unique constraint to prevent duplicate leads per workspace per place
create unique index if not exists leads_workspace_place_uniq
  on leads(workspace_id, google_place_id)
  where google_place_id is not null;

-- Activity lookups
create index if not exists lead_activities_lead_id_idx
  on lead_activities(lead_id);

create index if not exists lead_activities_workspace_created_at_idx
  on lead_activities(workspace_id, created_at desc);

-- ─── RLS ────────────────────────────────────────────────────────────────────

alter table workspaces     enable row level security;
alter table profiles       enable row level security;
alter table leads          enable row level security;
alter table lead_activities enable row level security;

-- Workspaces: users see and edit only their own workspace
create policy "workspaces_select"
  on workspaces for select
  using (id in (select workspace_id from profiles where id = auth.uid()));

create policy "workspaces_update"
  on workspaces for update
  using (id in (
    select workspace_id from profiles
    where id = auth.uid() and role in ('owner', 'admin')
  ));

-- Profiles: users see teammates and update only their own row
create policy "profiles_select"
  on profiles for select
  using (workspace_id in (select workspace_id from profiles where id = auth.uid()));

create policy "profiles_update"
  on profiles for update
  using (id = auth.uid());

-- Users only see data from their own workspace
create policy "leads_workspace_select"
  on leads for select
  using (workspace_id in (
    select workspace_id from profiles where id = auth.uid()
  ));

create policy "leads_workspace_insert"
  on leads for insert
  with check (workspace_id in (
    select workspace_id from profiles
    where id = auth.uid() and role in ('owner', 'admin', 'sales', 'analyst')
  ));

create policy "leads_workspace_update"
  on leads for update
  using (workspace_id in (
    select workspace_id from profiles
    where id = auth.uid() and role in ('owner', 'admin', 'sales', 'analyst')
  ));

create policy "leads_workspace_delete"
  on leads for delete
  using (workspace_id in (
    select workspace_id from profiles
    where id = auth.uid() and role in ('owner', 'admin')
  ));

-- ─── TRIGGERS ───────────────────────────────────────────────────────────────

-- Auto-update updated_at on leads
create or replace function update_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create trigger leads_updated_at
  before update on leads
  for each row execute function update_updated_at();

create trigger workspaces_updated_at
  before update on workspaces
  for each row execute function update_updated_at();

create trigger profiles_updated_at
  before update on profiles
  for each row execute function update_updated_at();
