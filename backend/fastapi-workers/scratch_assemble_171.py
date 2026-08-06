import psycopg2
import json
import logging
from app.workers.longform_worker import get_longform_worker

logging.basicConfig(level=logging.INFO)

conn = psycopg2.connect(
    dbname="ai_video_pipeline",
    user="pipeline_user",
    password="",
    host="pipeline_postgres",
    port=5432
)
cur = conn.cursor()

# 1. Fetch TTS asset
cur.execute("SELECT meta_json FROM asset WHERE job_id = 171 AND asset_type = 'TTS_AUDIO' ORDER BY created_at DESC LIMIT 1;")
tts_row = cur.fetchone()
if not tts_row:
    print("TTS asset not found!")
    exit(1)
tts_meta = tts_row[0]

# 2. Fetch SCENE_IMAGE assets
cur.execute("SELECT meta_json FROM asset WHERE job_id = 171 AND asset_type = 'SCENE_IMAGE' ORDER BY id ASC;")
scene_rows = cur.fetchall()
scene_metas = [r[0] for r in scene_rows]
scenes_json = json.dumps(scene_metas)

# 3. Fetch SCENE_GIF assets
cur.execute("SELECT meta_json FROM asset WHERE job_id = 171 AND asset_type = 'SCENE_GIF' ORDER BY id ASC;")
gif_rows = cur.fetchall()
gif_metas = [r[0] for r in gif_rows]
gifs_json = json.dumps(gif_metas)

print(f"Loaded {len(scene_metas)} scenes for job 171. Triggering assemble...")

worker = get_longform_worker()
res = worker.assemble(
    tts_meta_json=tts_meta,
    scenes_meta_json=scenes_json,
    gifs_meta_json=gifs_json,
    job_id=171
)

print("Assembly complete! Result:", res)

# Update job status in Postgres
cur.execute("UPDATE video_job SET status = 'COMPLETED', output_path = %s, updated_at = NOW() WHERE id = 171;", (res.get("output_path", ""),))
conn.commit()
print("Postgres status updated to COMPLETED.")
