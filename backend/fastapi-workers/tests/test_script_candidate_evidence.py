from __future__ import annotations

from app import main
from app.workers.script_worker import _candidate_evidence_context


class _RecordingScriptWorker:
    def __init__(self) -> None:
        self.candidate_evidence = "not-called"

    def generate(self, **kwargs):  # noqa: ANN003, ANN201
        self.candidate_evidence = kwargs.get("candidate_evidence")
        return {"status": "ok"}


def test_candidate_evidence_is_received_in_request(monkeypatch):
    worker = _RecordingScriptWorker()
    monkeypatch.setattr(main, "get_script_worker", lambda: worker)
    evidence = {
        "source_videos": [{"video_id": "video-1", "title": "반도체 실적 분석"}],
        "evidence_video_ids": ["video-1"],
    }

    result = main.script_generate(main.ScriptGenerateRequest(
        keyword="반도체 전망",
        target_minutes=5,
        candidate_evidence=evidence,
    ))

    assert result == {"status": "ok"}
    assert worker.candidate_evidence == evidence


def test_no_candidate_evidence_proceeds_gracefully(monkeypatch):
    worker = _RecordingScriptWorker()
    monkeypatch.setattr(main, "get_script_worker", lambda: worker)

    result = main.script_generate(main.ScriptGenerateRequest(
        keyword="반도체 전망",
        target_minutes=5,
    ))

    assert result == {"status": "ok"}
    assert worker.candidate_evidence is None


def test_evidence_news_merged_with_collected_news_by_url():
    collected = [
        {"title": "기존 기사", "url": "https://news.example/1", "outlet": "한국경제"},
        {"title": "두 번째 기사", "url": "https://news.example/2", "outlet": "연합뉴스"},
    ]
    candidate_evidence = {
        "news_articles": [
            {"title": "중복 기사", "link": "https://news.example/1", "outlet": "한국경제"},
            {"title": "추가 기사", "link": "https://news.example/3", "outlet": "머니투데이"},
            {"title": "출처 없는 기사", "link": "https://news.example/4"},
        ],
        "source_videos": [{"video_id": "video-1"}],
        "evidence_video_ids": ["video-1", "video-1"],
    }

    context = _candidate_evidence_context(collected, candidate_evidence)

    assert [row.get("url") or row.get("link") for row in context["merged_news"]] == [
        "https://news.example/1",
        "https://news.example/2",
        "https://news.example/3",
    ]
    assert context["source_videos"] == [{"video_id": "video-1"}]
    assert context["evidence_video_ids"] == ["video-1"]
