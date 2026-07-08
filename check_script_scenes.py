import psycopg2
import json

try:
    conn = psycopg2.connect("host=localhost port=5432 dbname=ai_video_pipeline user=pipeline_user password=pass1234")
    cur = conn.cursor()
    cur.execute("SELECT id, meta_json FROM asset WHERE job_id = 58 AND asset_type = 'SCRIPT' ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    if not row:
        print("No script asset found for Job 58.")
    else:
        asset_id, val = row
        print(f"Asset ID: {asset_id}")
        print("Raw meta_json length:", len(val))
        data = json.loads(val)
        if isinstance(data, str):
            data = json.loads(data)
        print("Parsed type:", type(data))
        if isinstance(data, dict):
            print("Keys:", list(data.keys()))
            sections = data.get("sections", [])
            print("Sections type:", type(sections))
            print("Sections length:", len(sections))
            if len(sections) > 0:
                print("First section keys:", list(sections[0].keys()))
                print("First section content:", sections[0])
            else:
                print("Full data preview:", str(data)[:1000])
        else:
            print("Data is not a dict:", data)
except Exception as e:
    print("Error:", e)
