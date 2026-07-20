"""Conservative Eleven v3 control-tag mapping; tags never alter narration facts."""
from __future__ import annotations

DEFAULT = {
    "neutral": ("", "[calmly]"), "highlight": ("[emphatically]", "[serious]"),
    "surprised": ("[surprised]", "[curious]"), "worried": ("[concerned]", "[nervous]"),
    "happy": ("[happy]", "[amused]"),
}
PHASE = {
    "hook": {"neutral": "[curious]", "highlight": "[intriguingly]", "surprised": "[shocked]", "worried": "[urgently]"},
    "context": {"highlight": "[emphatically]", "surprised": "[surprised]", "worried": "[concerned]", "happy": "[amused]"},
    "twist": {"highlight": "[dramatically]", "surprised": "[amazed]", "worried": "[worried]", "happy": "[relieved]"},
    "resolution": {"neutral": "[warmly]", "highlight": "[emphatically]", "happy": "[happy]"},
}

def map_emotion_to_elevenlabs(emotion_tag: str, phase: str, fallback: bool = False) -> dict:
    emotion = emotion_tag if emotion_tag in DEFAULT else "neutral"
    tag = None if fallback else PHASE.get(phase, {}).get(emotion)
    primary, backup = DEFAULT[emotion]
    return {"audio_tag": tag if tag is not None else (backup if fallback else primary),
            "stability_mode": "Natural" if phase in {"hook", "resolution"} else "Robust"}
