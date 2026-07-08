import requests
import json
import sys

base_url = "http://localhost:8080"

# 1. Register or login
username = "test_editor_p1"
password = "pass1234_password"

# Try registering
try:
    reg_resp = requests.post(f"{base_url}/api/auth/register", json={
        "username": username,
        "password": password,
        "email": "test@pipeline.com",
        "role": "EDITOR"
    })
    print("Register response:", reg_resp.status_code, reg_resp.text[:100])
except Exception as e:
    print("Register failed (might already exist):", e)

# Login
login_resp = requests.post(f"{base_url}/api/auth/login", json={
    "username": username,
    "password": password
})
if login_resp.status_code != 200:
    print("Login failed:", login_resp.status_code, login_resp.text)
    sys.exit(1)

token = login_resp.json().get("token")
print("Login successful! Token acquired.")

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

# 2. Create Job
job_payload = {
    "title": "반도체 주가 전망 분석",
    "keyword": "삼성전자, 하이닉스 반도체 주가 전망 분석",
    "category": "KOSPI",
    "autonomy": "AUTO",
    "format": "FACELESS_NARRATION",
    "renderProfile": "LONGFORM_16x9",
    "makeShorts": False,
    "longformTargetMinutes": 15
}

job_resp = requests.post(f"{base_url}/api/jobs", json=job_payload, headers=headers)
if job_resp.status_code != 200:
    print("Job creation failed:", job_resp.status_code, job_resp.text)
    sys.exit(1)

job_id = job_resp.json().get("id")
print(f"Job created successfully! Job ID: {job_id}")

# 3. Start Keyword Search
search_payload = {
    "seedKeyword": "반도체 주가 전망",
    "limit": 5,
    "category": "KOSPI"
}

search_resp = requests.post(f"{base_url}/api/jobs/{job_id}/keyword/search", json=search_payload, headers=headers)
if search_resp.status_code != 200:
    print("Keyword search initiation failed:", search_resp.status_code, search_resp.text)
    sys.exit(1)

print(f"Pipeline started successfully for Job {job_id} in AUTO mode!")
print("Check logs or open http://localhost:3000/jobs/{} in your browser.".format(job_id))
