-- LeadScout AI - Search Audit Logs
-- Run in Supabase SQL editor after initial_schema.sql

create table if not exists search_audit_logs (
    id             uuid          primary key default gen_random_uuid(),
    user_id        uuid          not null,
    workspace_id   uuid          not null references workspaces(id) on delete cascade,
    query          text          not null,
    location       text,
    category       text,
    radius_km      double precision,
    latitude       double precision,
    longitude      double precision,
    results_count  int           not null default 0,
    saved_new      int           not null default 0,
    created_at     timestamptz   not null default now()
);

-- Workspace-scoped queries (analytics, admin view)
create index if not exists search_audit_workspace_created_idx
    on search_audit_logs(workspace_id, created_at desc);

-- Per-user query history
create index if not exists search_audit_user_created_idx
    on search_audit_logs(user_id, created_at desc);

alter table search_audit_logs enable row level security;

-- Server uses service role key — INSERT bypasses RLS.
-- This policy covers direct client access if ever exposed.
create policy "search_audit_insert"
    on search_audit_logs for insert
    with check (true);

-- Users can read audit logs scoped to their workspace
create policy "search_audit_select"
    on search_audit_logs for select
    using (
        workspace_id in (
            select workspace_id from profiles where id = auth.uid()
        )
    );
