from app.workers.tts_worker import TtsWorker
from app.tts.forced_alignment_srt import WordTiming, words_to_cues
from app.utils.korean_tts import normalize_korean_numbers_for_tts


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


def test_provider_character_alignment_preserves_the_hard_script_contract_when_whisper_is_noisy(monkeypatch):
    class WhisperWithNoisyNumericTranscript:
        def transcribe(self, *_args, **_kwargs):
            return [type("Segment", (), {"text": "금리는 삼 퍼센트입니다."})()], None

    worker = TtsWorker()
    monkeypatch.setattr(worker, "_get_whisper_model", lambda: WhisperWithNoisyNumericTranscript())
    provider_characters = _timed("금리는 3.75퍼센트입니다.")

    result = worker._verify_tts_narration(
        "unused.mp3",
        "금리는 3.75퍼센트입니다.",
        1,
        provider_characters=provider_characters,
    )

    assert result["passed"] is True
    assert result["provider_text_exact"] is True
    assert result["whisper_passed"] is False
    assert result["audio_review_required"] is True


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


def test_korean_delivery_preserves_sentence_boundaries_by_default():
    source = "3.56퍼센트입니다. 첫째입니다. 둘째입니다. 마지막입니다."
    delivery = TtsWorker._soften_korean_delivery_cadence(source)

    assert delivery == source


def test_korean_delivery_can_reproduce_legacy_thought_groups_when_explicitly_requested():
    source = "3.56퍼센트입니다. 첫째입니다. 둘째입니다. 마지막입니다."
    delivery = TtsWorker._soften_korean_delivery_cadence(source, group_size=3)

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


def test_forced_alignment_keeps_original_numeric_subtitle_text(monkeypatch):
    # 실제 API 키가 있는 개발 환경에서도 가짜 오디오 파일을 외부 정렬로
    # 보내지 않도록 기존 단어 정렬 폴백만 검증한다.
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.setattr(
        "app.tts.forced_alignment_srt.align_audio_to_text",
        lambda _audio, _script: [
            WordTiming("관세가", 0.0, 0.3),
            WordTiming("12.5퍼센트", 0.3, 1.0),
            WordTiming("붙었습니다.", 1.0, 1.8),
        ],
    )

    chunks = TtsWorker()._extract_timestamps_with_forced_alignment(
        "unused.mp3", "관세가 12.5퍼센트 붙었습니다."
    )

    assert len(chunks) == 1
    assert chunks[0]["text"] == "관세가 12.5퍼센트 붙었습니다."
    assert chunks[0]["start"] == 0.0
    assert chunks[0]["end"] == 1.8


def test_displayed_decimal_waits_for_its_full_spoken_form():
    words = [
        WordTiming("금리는", 0.0, 0.3),
        WordTiming("삼쩜칠오퍼센트야", 0.3, 1.2),
        WordTiming("다음", 1.35, 1.6),
        WordTiming("발표야", 1.6, 2.0),
    ]

    chunks = TtsWorker()._map_display_chunks_to_spoken_words(
        ["금리는 3.75퍼센트야.", "다음 발표야."], words
    )

    assert chunks[0]["text"] == "금리는 3.75퍼센트야."
    assert chunks[0]["end"] == 1.2
    assert chunks[1]["start"] == 1.35


def test_character_alignment_uses_the_final_spoken_decimal_character():
    class Character:
        def __init__(self, text, start, end):
            self.text = text
            self.start = start
            self.end = end

    text = "삼쩜칠오퍼센트야"
    characters = [Character(char, index * 0.1, (index + 1) * 0.1) for index, char in enumerate(text)]

    chunks = TtsWorker()._map_display_chunks_to_spoken_characters(
        ["3.75퍼센트야"], characters
    )

    assert chunks[0]["start"] == 0.0
    assert chunks[0]["end"] == round(len(text) * 0.1, 3)


def test_subtitle_split_rebalances_a_short_trailing_phrase():
    chunks = TtsWorker._split_script_into_chunks(
        "그래서 이번 발표는 그냥 넘겨도 된다고 생각하는 사람 많아.",
        max_chars=16,
        min_chars=8,
    )

    assert chunks[-2:] == ["넘겨도 된다고", "생각하는 사람 많아."]
    assert min(len(chunk) for chunk in chunks) >= 7


def test_subtitle_split_keeps_korean_modifier_with_its_noun_phrase():
    chunks = TtsWorker._split_script_into_chunks(
        "성명 첫 줄만 보면 멈춘 발표처럼 보이지.",
        max_chars=16,
        min_chars=8,
    )

    assert chunks == ["성명 첫 줄만 보면", "멈춘 발표처럼 보이지."]


def test_subtitle_split_keeps_a_short_formal_sentence_as_one_meaning_unit():
    chunks = TtsWorker._split_script_into_chunks(
        "고용도 크게 흔들리지 않았습니다.",
        max_chars=16,
        min_chars=8,
    )

    assert chunks == ["고용도 크게 흔들리지 않았습니다."]


def test_subtitle_split_never_starts_a_cue_with_a_detached_particle():
    chunks = TtsWorker._split_script_into_chunks(
        "다음 발표에서는 이 세 줄 만 비교하면 충분히 판단할 수 있습니다.",
        max_chars=16,
        min_chars=8,
    )

    assert all(not chunk.startswith("만 ") for chunk in chunks)
    assert any("줄만" in chunk for chunk in chunks)


def test_subtitle_split_keeps_a_compound_postposition_with_its_noun():
    chunks = TtsWorker._split_script_into_chunks(
        "연준은 경제활동이 불확실성 속에서도 견조한 속도로 확대되고 있다고 설명했어.",
        max_chars=16,
        min_chars=8,
    )

    assert chunks[:2] == ["연준은 경제활동이", "불확실성 속에서도 견조한 속도로"]


def test_subtitle_split_keeps_a_demonstrative_determiner_separate_from_a_particle():
    chunks = TtsWorker._split_script_into_chunks(
        "다음 발표에서도 이 세 가지가 어떻게 달라졌는지만 보면 됩니다.",
        max_chars=18,
        min_chars=8,
    )

    assert all("에서도이" not in chunk for chunk in chunks)
    assert any("이 세 가지" in chunk for chunk in chunks)
    assert max(map(len, chunks)) <= 20


def test_subtitle_timing_starts_on_or_after_forced_alignment_frame():
    chunks = TtsWorker._snap_subtitle_timings_to_render_frames(
        [
            {"index": 1, "text": "첫 구절", "start": 0.299, "end": 0.801, "duration": 0.502},
            {"index": 2, "text": "다음 구절", "start": 0.812, "end": 1.101, "duration": 0.289},
        ],
        frame_rate=30,
    )

    assert chunks[0]["start"] == 0.3
    assert chunks[0]["end"] == 0.833333
    assert chunks[1]["start"] >= 0.812
    assert chunks[1]["start"] >= chunks[0]["end"]
    assert chunks[1]["end"] >= 1.101


def test_subtitle_timing_uses_the_nearest_frame_for_a_balanced_start():
    chunks = TtsWorker._snap_subtitle_timings_to_render_frames(
        [{"index": 1, "text": "구절", "start": 0.281, "end": 0.401}],
        frame_rate=30,
        start_frame_policy="nearest",
    )

    # 0.281초는 0.267초 프레임에 더 가깝다. ceil 정책의 0.300초보다
    # 덜 늦고, 한 프레임 앞당김 정책보다도 음성 경계에 가깝다.
    assert chunks[0]["start"] == 0.266667


def test_decimal_is_read_in_natural_korean_tts_form():
    assert normalize_korean_numbers_for_tts("3.75퍼센트") == "삼쩜칠오퍼센트"


def test_subtitle_cue_does_not_exceed_the_requested_character_limit():
    cues = words_to_cues(
        [
            WordTiming("경제활동은", 0.0, 0.4),
            WordTiming("견조한", 0.4, 0.7),
            WordTiming("속도로", 0.7, 1.0),
        ],
        max_chars=8,
    )

    assert [cue.text for cue in cues] == ["경제활동은", "견조한 속도로"]
