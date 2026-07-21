-- Backward-compatible local schema patch for databases created before
-- job-level verified data visualisation was introduced.
ALTER TABLE IF EXISTS video_job
    ADD COLUMN IF NOT EXISTS data_visuals_enabled boolean NOT NULL DEFAULT true;

-- Hibernate's enum update does not widen an existing PostgreSQL CHECK
-- constraint.  Keep databases created by older versions able to persist the
-- recovery states used by keyword evidence validation and image retries.
ALTER TABLE IF EXISTS video_job
    DROP CONSTRAINT IF EXISTS video_job_status_check;

ALTER TABLE IF EXISTS video_job
    ADD CONSTRAINT video_job_status_check CHECK (status IN (
        'DRAFT',
        'KEYWORD_PENDING',
        'TOPIC_EVIDENCE_REQUIRED',
        'SCRIPT_PENDING',
        'TTS_PENDING',
        'IMAGES_PENDING',
        'IMAGES_RETRY_REQUIRED',
        'ASSEMBLING',
        'PREVIEW_PENDING',
        'SHORTS_SEGMENTS_PENDING',
        'SHORTS_GENERATING',
        'SHORTS_PREVIEW_PENDING',
        'READY',
        'PUBLISHED',
        'BUDGET_BLOCKED',
        'FAILED'
    ));
