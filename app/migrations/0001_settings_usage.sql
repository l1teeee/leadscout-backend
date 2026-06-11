-- Settings usage / audit / plan migration.
-- Apply once in the Supabase SQL editor. Idempotent (safe to re-run).

-- 1. Plan tier per workspace.
alter table public.workspaces
  add column if not exists plan text not null default 'starter';

-- 2. AI token usage log (one row per AI call).
create table if not exists public.ai_usage_logs (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  user_id uuid,
  kind text not null default 'analyze',
  input_tokens integer not null default 0,
  output_tokens integer not null default 0,
  total_tokens integer not null default 0,
  created_at timestamptz not null default now()
);
create index if not exists idx_ai_usage_logs_ws_created
  on public.ai_usage_logs (workspace_id, created_at);

-- 3. Ensure the search audit log has a timestamp (monthly count + recent activity).
alter table public.search_audit_logs
  add column if not exists created_at timestamptz not null default now();
create index if not exists idx_search_audit_logs_ws_created
  on public.search_audit_logs (workspace_id, created_at);
