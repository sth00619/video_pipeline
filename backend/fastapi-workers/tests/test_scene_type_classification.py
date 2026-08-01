from app.workers.script_worker import ScriptWorker, _classify_scene_types


def test_scene_type_classification_keeps_reason_for_each_supported_type():
    scenes = _classify_scene_types([
        {
            "section": "data",
            "content": "고점과 종가의 변화를 추이 차트로 비교합니다.",
            "visual_intent": "두 시점의 하락 폭을 선 그래프로 보여 줍니다.",
        },
        {
            "section": "scenario",
            "content": "공급망의 단계와 연결 관계를 차례로 설명합니다.",
        },
        {
            "section": "data",
            "content": "시가총액 규모와 월간 낙폭을 확인합니다.",
        },
        {
            "section": "background",
            "content": "이 용어의 의미를 먼저 정리합니다.",
        },
        {
            "section": "action",
            "content": "투자자가 확인할 관점을 설명합니다.",
        },
    ])

    assert [scene["scene_type"] for scene in scenes] == [
        "graph", "diagram", "metric", "text", "general",
    ]
    assert all(scene["selection_reason"] for scene in scenes)


def test_graph_signal_has_priority_over_data_section_metric_fallback():
    scene = _classify_scene_types([{
        "section": "data",
        "content": "일별 등락률을 막대그래프로 비교합니다.",
    }])[0]

    assert scene["scene_type"] == "graph"
    assert "그래프형" in scene["selection_reason"]


def test_mock_script_response_also_contains_scene_type_contract():
    result = ScriptWorker()._mock_generate("코스피", "코스피", 1, 1)

    assert result["sections"]
    assert all(scene["scene_type"] in {"general", "metric", "graph", "diagram", "text"} for scene in result["sections"])
    assert all(scene["selection_reason"] for scene in result["sections"])
