import base64
import json
import os

import requests


DESCRIPTION = (
    "Create an original Korean male financial news narrator voice, not based on or "
    "imitating any real person. The voice must be unmistakably low baritone with "
    "warm chest resonance and a dark, grounded lower register, clearly heavier and "
    "lower than a bright announcer. Mature, calm, clean broadcast diction, crisp "
    "consonants, controlled breath, natural sentence pauses, and brisk but "
    "conversational pacing for YouTube finance explainers. Keep the low tone stable "
    "without rumbling, whispering, theatrical boom, or celebrity impression."
)
TEXT = (
    "오늘 시장이 반등했다고 바로 안심하기는 이릅니다. 지수는 올랐지만, "
    "외국인 수급과 원화 흐름이 같은 방향을 가리키는지 먼저 확인해야 합니다. "
    "숫자 하나보다 중요한 건 그 숫자가 만들어진 순서입니다."
)


def main() -> None:
    key = os.environ["ELEVENLABS_API_KEY"]
    response = requests.post(
        "https://api.elevenlabs.io/v1/text-to-voice/design",
        headers={"xi-api-key": key, "Content-Type": "application/json"},
        json={
            "voice_description": DESCRIPTION,
            "model_id": "eleven_ttv_v3",
            "text": TEXT,
            "auto_generate_text": False,
        },
        timeout=180,
    )
    if response.status_code >= 400:
        print("elevenlabs_error", response.status_code, response.text)
    response.raise_for_status()
    data = response.json()
    with open("/tmp/deep_low_design.json", "w", encoding="utf-8") as file:
        json.dump(
            {"description": DESCRIPTION, "text": TEXT, "response": data},
            file,
            ensure_ascii=False,
            indent=2,
        )
    for index, preview in enumerate(data.get("previews", [])):
        encoded = preview.get("audio_base_64")
        if encoded:
            with open(f"/tmp/deep_low_preview_{index}.mp3", "wb") as file:
                file.write(base64.b64decode(encoded))
    print(
        json.dumps(
            {
                "previews": [
                    {
                        "generated_voice_id": preview.get("generated_voice_id"),
                        "duration_secs": preview.get("duration_secs"),
                        "language": preview.get("language"),
                    }
                    for preview in data.get("previews", [])
                ]
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
