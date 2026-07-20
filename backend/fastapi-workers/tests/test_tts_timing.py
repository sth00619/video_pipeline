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


def test_cer_ignores_whitespace_and_punctuation_only_differences():
    assert TtsWorker._char_error_rate("Market rises.", "Market   rises!") == 0


def test_sentence_pause_shifts_only_the_following_sentence():
    characters = [
        {"text": "A", "start": 0.0, "end": 0.1},
        {"text": ".", "start": 0.1, "end": 0.2},
        {"text": " ", "start": 0.2, "end": 0.22},
        {"text": "B", "start": 0.22, "end": 0.32},
        {"text": "!", "start": 0.32, "end": 0.42},
    ]

    pauses = TtsWorker._sentence_pause_points(characters)
    assert len(pauses) == 1
    assert pauses[0][0] == 0.2

    shifted = TtsWorker._shift_character_timings_for_pauses(characters, pauses)
    assert shifted[1]["end"] == 0.2  # Sentence-ending punctuation is unchanged.
    assert shifted[3]["start"] > characters[3]["start"]
