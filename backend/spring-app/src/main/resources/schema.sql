-- Backward-compatible local schema patch for databases created before
-- job-level verified data visualisation was introduced.
ALTER TABLE IF EXISTS video_job
    ADD COLUMN IF NOT EXISTS data_visuals_enabled boolean NOT NULL DEFAULT true;
