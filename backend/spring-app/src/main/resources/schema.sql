-- Backward-compatible local schema patch for databases created before
-- job-level verified data visualisation was introduced.
ALTER TABLE IF EXISTS video_job
    ADD COLUMN IF NOT EXISTS data_visuals_enabled boolean NOT NULL DEFAULT true;

ALTER TABLE IF EXISTS video_job
    ADD COLUMN IF NOT EXISTS gemini_image_budget_cap numeric(38,2);

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

-- 관리자 검증을 통과한 YouTube 레퍼런스 채널의 단일 저장소.
CREATE TABLE IF NOT EXISTS reference_channel (
    id                          BIGSERIAL PRIMARY KEY,
    display_name                VARCHAR(120) NOT NULL,
    channel_id                  VARCHAR(50)  NOT NULL UNIQUE,
    youtube_title               VARCHAR(200),
    youtube_handle              VARCHAR(120),
    thumbnail_url               TEXT,
    subscriber_count            BIGINT,
    subscriber_count_hidden     BOOLEAN NOT NULL DEFAULT FALSE,
    tier                        VARCHAR(20)  NOT NULL DEFAULT 'MEDIUM',
    validation_status           VARCHAR(20)  NOT NULL DEFAULT 'VALID',
    is_active                   BOOLEAN NOT NULL DEFAULT TRUE,
    display_order               INTEGER NOT NULL DEFAULT 0,
    last_validated_at           TIMESTAMP,
    created_by                  VARCHAR(100),
    created_at                  TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reference_channel_active_order
    ON reference_channel (is_active, display_order, id);

-- 진단에서 실채널 일치가 확인된 경제사냥꾼만 초기 활성 채널로 등록한다.
INSERT INTO reference_channel (
    display_name, channel_id, youtube_title, tier,
    validation_status, is_active, display_order, created_by
) VALUES (
    '경제사냥꾼', 'UC7usMJDHmtbs_oegmzQKKMA', '경제사냥꾼',
    'LARGE', 'VALID', TRUE, 10, 'system_seed'
) ON CONFLICT (channel_id) DO NOTHING;
