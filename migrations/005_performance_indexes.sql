-- Performance indexes for the leads table
-- Run in Supabase SQL Editor

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_leads_workspace_created
    ON leads (workspace_id, created_at DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_leads_workspace_status
    ON leads (workspace_id, status);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_leads_workspace_priority
    ON leads (workspace_id, priority);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_leads_workspace_score
    ON leads (workspace_id, score DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_leads_place_workspace
    ON leads (google_place_id, workspace_id)
    WHERE google_place_id IS NOT NULL;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_leads_name_gin
    ON leads USING gin(to_tsvector('spanish', name));
