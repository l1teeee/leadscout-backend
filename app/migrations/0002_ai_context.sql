ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS ai_business_context TEXT;
ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS ai_constraints TEXT;
ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS ai_context_updated_at TIMESTAMPTZ;
