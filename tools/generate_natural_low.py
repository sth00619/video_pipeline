import base64
import json
import os

import requests


DESCRIPTION = (
    "Create an original Korean male financial news narrator voice, not based on or "
    "imitating any real person. Keep a distinctly low mature baritone and warm chest "
    "resonance, but make the performance feel like a real person speaking close to a "
    "microphone: subtle audible inhalations at some sentence boundaries, soft natural "
    "breath release, small timing imperfections, varied sentence melody, and human "
    "micro-pauses. The voice should be calm, grounded, and conversational rather than "
    "perfectly polished. Keep Korean diction clear and consonants crisp, with a brisk "
    "finance-news pace. Avoid robotic evenness, constant breath noise, whispering, "
    "overacting, rumble, or any celebrity or identifiable-person impression."
)
TEXT = (
    "오늘 시장의 숫자만 보고 안심하면 안 됩니다.  "
    "지수의 방향과 외국인 수급, 환율의 흐름이 함께 움직이는지 차분하게 확인해야 합니다.\n\n"
    "숫자보다 중요한 것은, 그 변화가 시작된 이유입니다."
)


def main() -> None:
    response = requests.post(
        "https://api.elevenlabs.io/v1/text-to-voice/design",
        headers={
            "xi-api-key": os.environ["ELEVENLABS_API_KEY"],
            "Content-Type": "application/json",
        },
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
    payload = response.json()
    with open("/tmp/natural_low_design.json", "w", encoding="utf-8") as file:
        json.dump(
            {"description": DESCRIPTION, "text": TEXT, "response": payload},
            file,
            ensure_ascii=False,
            indent=2,
        )
    for index, preview in enumerate(payload.get("previews", [])):
        encoded = preview.get("audio_base_64")
        if encoded:
            with open(f"/tmp/natural_low_preview_{index}.mp3", "wb") as file:
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
                    for preview in payload.get("previews", [])
                ]
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
