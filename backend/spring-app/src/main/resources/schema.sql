-- Backward-compatible local schema patch for databases created before
-- job-level verified data visualisation was introduced.
ALTER TABLE IF EXISTS video_job
    ADD COLUMN IF NOT EXISTS data_visuals_enabled boolean NOT NULL DEFAULT true;

ALTER TABLE IF EXISTS channel_profile
    ADD COLUMN IF NOT EXISTS watermark_path varchar(500);

ALTER TABLE IF EXISTS channel_profile
    ADD COLUMN IF NOT EXISTS reference_style_profile varchar(100) DEFAULT 'black_han_sans_v1';

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

-- Approved real-person photo registry.  The worker enforces this metadata a
-- second time immediately before compositing, so an unlicensed file cannot be
-- rendered through a direct API call.
CREATE TABLE IF NOT EXISTS person_asset (
    person_id VARCHAR(80) PRIMARY KEY,
    name_ko VARCHAR(120) NOT NULL,
    name_en VARCHAR(120),
    aliases_json TEXT
);

CREATE TABLE IF NOT EXISTS person_photo (
    photo_id VARCHAR(80) PRIMARY KEY,
    person_id VARCHAR(80) NOT NULL,
    original_path VARCHAR(700) NOT NULL,
    cutout_path VARCHAR(700),
    license_type VARCHAR(30) NOT NULL,
    license_ref TEXT,
    credit_text TEXT,
    author_name VARCHAR(200),
    emotion_tag VARCHAR(30),
    pose VARCHAR(30),
    content_sha256 VARCHAR(64),
    cutout_model VARCHAR(60),
    approved BOOLEAN NOT NULL DEFAULT FALSE,
    rights_review_status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    approved_by VARCHAR(100),
    approved_at TIMESTAMP,
    transformation_log TEXT,
    created_at TIMESTAMP
);
