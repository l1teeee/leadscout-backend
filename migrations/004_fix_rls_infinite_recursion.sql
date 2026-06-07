-- Fix: infinite recursion in profiles_select RLS policy
-- Code 42P17: the profiles_select policy queries profiles from within
-- a policy ON profiles, causing PostgreSQL to recurse infinitely.
--
-- Solution: security-definer helper function that bypasses RLS when
-- looking up the caller's workspace_id.

-- ─── HELPER FUNCTION ────────────────────────────────────────────────────────

create or replace function public.get_my_workspace_id()
returns uuid
language sql
security definer
stable
set search_path = public
as $$
  select workspace_id from public.profiles where id = auth.uid()
$$;

-- ─── PROFILES ───────────────────────────────────────────────────────────────

drop policy if exists "profiles_select" on profiles;
create policy "profiles_select"
  on profiles for select
  using (workspace_id = get_my_workspace_id());

-- ─── WORKSPACES ─────────────────────────────────────────────────────────────

drop policy if exists "workspaces_select" on workspaces;
create policy "workspaces_select"
  on workspaces for select
  using (id = get_my_workspace_id());

drop policy if exists "workspaces_update" on workspaces;
create policy "workspaces_update"
  on workspaces for update
  using (
    id = get_my_workspace_id()
    and (select role from profiles where id = auth.uid()) in ('owner', 'admin')
  );

-- ─── LEADS ──────────────────────────────────────────────────────────────────

drop policy if exists "leads_workspace_select" on leads;
create policy "leads_workspace_select"
  on leads for select
  using (workspace_id = get_my_workspace_id());

drop policy if exists "leads_workspace_insert" on leads;
create policy "leads_workspace_insert"
  on leads for insert
  with check (
    workspace_id = get_my_workspace_id()
    and (select role from profiles where id = auth.uid()) in ('owner', 'admin', 'sales', 'analyst')
  );

drop policy if exists "leads_workspace_update" on leads;
create policy "leads_workspace_update"
  on leads for update
  using (
    workspace_id = get_my_workspace_id()
    and (select role from profiles where id = auth.uid()) in ('owner', 'admin', 'sales', 'analyst')
  );

drop policy if exists "leads_workspace_delete" on leads;
create policy "leads_workspace_delete"
  on leads for delete
  using (
    workspace_id = get_my_workspace_id()
    and (select role from profiles where id = auth.uid()) in ('owner', 'admin')
  );

-- ─── LEAD_ACTIVITIES (add if missing) ───────────────────────────────────────

drop policy if exists "lead_activities_select" on lead_activities;
create policy "lead_activities_select"
  on lead_activities for select
  using (workspace_id = get_my_workspace_id());

drop policy if exists "lead_activities_insert" on lead_activities;
create policy "lead_activities_insert"
  on lead_activities for insert
  with check (workspace_id = get_my_workspace_id());
