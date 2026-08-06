import json
import logging
from app.workers.longform_worker import LongformWorker

logging.basicConfig(level=logging.INFO)

def load_text(path):
    for enc in ['utf-8', 'utf-16', 'utf-8-sig', 'cp949', 'euc-kr']:
        try:
            with open(path, 'r', encoding=enc) as f:
                return f.read().strip()
        except Exception:
            continue
    raise RuntimeError(f"Could not decode file {path}")

tts_meta = load_text('/app/tts_171.json')
scenes_raw = load_text('/app/scenes_171.json')
scenes_list = json.loads(scenes_raw)
scenes_json = json.dumps([json.dumps(s) if isinstance(s, dict) else s for s in scenes_list])

worker = LongformWorker()
print(f"Starting assembly for Job 171 with {len(scenes_list)} scenes...")
res = worker.assemble(
    tts_meta_json=tts_meta,
    scenes_meta_json=scenes_json,
    gifs_meta_json="[]",
    job_id=171
)
print("ASSEMBLY_SUCCESS_RESULT:", res)
