from app.utils.elevenlabs_mapper import map_emotion_to_elevenlabs
from app.utils.script_delivery import annotate_sections, validate_delivery


def test_annotation_never_rewrites_narration():
    original = "삼성전자가 71,300원으로 마감했고, 상승률은 2.4퍼센트입니다."
    scenes = annotate_sections([{"title": "수치", "content": original, "pose": "pointing"}], 60)
    assert scenes[0]["content"] == original
    assert scenes[0]["text_for_tts"] == original
    assert scenes[0]["sentences"][0]["text"] == original


def test_elevenlabs_phase_emotion_matrix_is_complete():
    for phase in ("hook", "context", "twist", "resolution"):
        for emotion in ("neutral", "highlight", "surprised", "worried", "happy"):
            mapped = map_emotion_to_elevenlabs(emotion, phase)
            assert mapped["stability_mode"] in {"Natural", "Robust"}
            assert "audio_tag" in mapped


def test_forbidden_expression_is_reported_not_rewritten():
    original = "이 종목은 무조건 오른다고 말할 수 없습니다."
    scenes = annotate_sections([{"title": "경고", "content": original, "pose": "neutral"}], 60)
    report = validate_delivery(scenes)
    assert scenes[0]["content"] == original
    assert any(row["type"] == "FORBIDDEN_PHRASE" for row in report["violations"])
