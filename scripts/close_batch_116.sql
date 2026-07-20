-- One-time recovery aid for legacy Gemini batch job 116.
-- The deployed polling service now marks failed batches terminally itself;
-- run this only when an old deployment must be silenced before that rollout.
UPDATE asset
SET meta_json = '{"status":"BATCH_FAILED","error":"POLL_STALLED legacy batch closed manually"}'
WHERE job_id = 116
  AND asset_type = 'IMAGE_BATCH'
  AND meta_json LIKE '%BATCH_PENDING%';

UPDATE video_job
SET status = 'IMAGES_RETRY_REQUIRED'
WHERE id = 116
  AND status = 'IMAGES_PENDING';
