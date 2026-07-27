from app.workers.tts_worker import TtsWorker


def _timed(text: str, step: float = 0.05):
    return [
        {"text": char, "start": index * step, "end": (index + 1) * step}
        for index, char in enumerate(text)
    ]


def test_v3_intro_tag_is_excluded_from_subtitle_timing():
    worker = TtsWorker()
    canonical = "Market rises."
    normalized = worker._preprocess_for_tts(canonical)
    timings = _timed(f"[curious] {normalized}")

    chunks = worker._extract_timestamps_from_elevenlabs_response(
        canonical, timings, subtitle_max_chars=50
    )

    assert len(chunks) == 1
    assert chunks[0]["text"] == canonical
    # The intro tag consumes source time but must never become subtitle text.
    assert chunks[0]["start"] > 0
    assert chunks[0]["end"] > chunks[0]["start"]


def test_elevenlabs_request_text_begins_with_the_korean_script():
    script = "6월 22일이었습니다."
    prepared = TtsWorker._prepare_elevenlabs_text(script)
    assert prepared == script
    assert not prepared.startswith("[")


def test_audio_tags_are_only_preserved_for_v3_natural_provider_copy():
    tagged = "[curious] 6월 22일이었습니다."
    assert TtsWorker._prepare_elevenlabs_text(tagged, "eleven_v3", "natural") == tagged
    assert TtsWorker._prepare_elevenlabs_text(tagged, "eleven_v3", "robust") == "6월 22일이었습니다."
    assert TtsWorker._prepare_elevenlabs_text(tagged, "eleven_multilingual_v2", "legacy") == "6월 22일이었습니다."


def test_v3_stability_maps_to_documented_delivery_modes():
    assert TtsWorker._stability_mode("eleven_v3", 0.0) == "creative"
    assert TtsWorker._stability_mode("eleven_v3", 0.5) == "natural"
    assert TtsWorker._stability_mode("eleven_v3", 1.0) == "robust"


def test_default_voice_resolves_to_requested_korean_reference_voice(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_VOICE_ID", raising=False)
    assert TtsWorker._resolve_elevenlabs_voice_id("gtts_whisper_ko") == "dlKJ5VptCbYxal4doUO5"
    assert TtsWorker._resolve_elevenlabs_voice_id("custom_voice") == "custom_voice"


def test_cer_ignores_whitespace_and_punctuation_only_differences():
    assert TtsWorker._char_error_rate("Market rises.", "Market   rises!") == 0


def test_default_delivery_inserts_reference_sized_sentence_pauses():
    characters = [
        {"text": "A", "start": 0.0, "end": 0.1},
        {"text": ".", "start": 0.1, "end": 0.2},
        {"text": " ", "start": 0.2, "end": 0.22},
        {"text": "B", "start": 0.22, "end": 0.32},
        {"text": "!", "start": 0.32, "end": 0.42},
    ]

    pauses = TtsWorker._sentence_pause_points(characters)
    # The pause starts at the next spoken character, after the provider's
    # complete sentence tail and native whitespace.
    assert pauses == [(0.22, 0.35)]


def test_sentence_pause_preserves_korean_terminal_tail_before_native_whitespace():
    characters = [
        {"text": "요", "start": 1.70, "end": 1.78},
        {"text": ".", "start": 1.78, "end": 1.80},
        {"text": "\n", "start": 1.80, "end": 1.94},
        {"text": "다", "start": 1.94, "end": 2.02},
    ]

    assert TtsWorker._sentence_pause_points(characters) == [(1.94, 0.35)]


def test_korean_delivery_groups_short_statements_without_touching_numbers_or_finale():
    source = "3.56퍼센트입니다. 첫째입니다. 둘째입니다. 마지막입니다."
    delivery = TtsWorker._soften_korean_delivery_cadence(source)

    assert delivery == "3.56퍼센트입니다, 첫째입니다, 둘째입니다. 마지막입니다."


def test_thought_group_pause_replaces_individual_sentence_breaths():
    characters = [
        {"text": "다", "start": 0.0, "end": 0.1},
        {"text": ".", "start": 0.1, "end": 0.12},
        {"text": " ", "start": 0.12, "end": 0.2},
        {"text": "음", "start": 0.2, "end": 0.3},
    ]

    assert TtsWorker._sentence_pause_points(characters, pause_ms_override=1100) == [(0.2, 1.1)]


def test_timing_shift_only_affects_the_following_sentence():
    characters = [
        {"text": "A", "start": 0.0, "end": 0.1},
        {"text": ".", "start": 0.1, "end": 0.2},
        {"text": " ", "start": 0.2, "end": 0.22},
        {"text": "B", "start": 0.22, "end": 0.32},
    ]
    pauses = [(0.22, 0.32)]

    shifted = TtsWorker._shift_character_timings_for_pauses(characters, pauses)
    assert shifted[1]["end"] == 0.2  # Sentence-ending punctuation is unchanged.
    assert shifted[3]["start"] > characters[3]["start"]
