-- Add social_profiles JSONB column to leads table
-- Run in Supabase SQL Editor

ALTER TABLE leads
    ADD COLUMN IF NOT EXISTS social_profiles JSONB DEFAULT NULL;

COMMENT ON COLUMN leads.social_profiles IS 'Detected social media profiles from website scraping. Array of {platform, url} objects.';
