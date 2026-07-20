import json
import os

import requests


def main() -> None:
    generated_id = "KEo3H2UC7XebTpHFgc3B"
    response = requests.post(
        "https://api.elevenlabs.io/v1/text-to-voice",
        headers={
            "xi-api-key": os.environ["ELEVENLABS_API_KEY"],
            "Content-Type": "application/json",
        },
        json={
            "voice_name": "오리지널 금융 앵커",
            "voice_description": (
                "Original non-identifying Korean male finance narrator voice with clear, "
                "steady newsroom diction and warm low-mid resonance."
            ),
            "generated_voice_id": generated_id,
            "labels": {"language": "ko", "use_case": "finance_news", "source": "voice_design"},
        },
        timeout=60,
    )
    if response.status_code >= 400:
        print("elevenlabs_error", response.status_code, response.text)
    response.raise_for_status()
    payload = response.json()
    with open("artifacts/original_anchor_voice_created.json", "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
    print(json.dumps({"voice_id": payload.get("voice_id"), "name": payload.get("name")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
