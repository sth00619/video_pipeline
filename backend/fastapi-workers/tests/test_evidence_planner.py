from pathlib import Path

from app.models.article_evidence import ArticleCandidate, ArticleCapture, NormalizedBBox
from app.services.article.evidence_planner import ArticleEvidencePlanner, narration_hash


class FakeDiscovery:
    def discover(self, query, terms, limit):
        return [
            ArticleCandidate(
                title="코스피 반도체 상승",
                url="https://www.yna.co.kr/test",
                publisher="연합뉴스",
                published_at="2026-07-22",
                summary="코스피가 반도체 투톱 상승으로 12.5% 올랐다.",
            )
        ]


class FakeResolver:
    def __init__(self, sentences):
        self._sentences = sentences

    def sentences(self, candidate):
        return list(self._sentences)


class FakeCapture:
    def capture_dom(self, request):
        bbox = NormalizedBBox(x=.1, y=.3, width=.7, height=.1)
        key = NormalizedBBox(x=.42, y=.3, width=.18, height=.1)
        return ArticleCapture(
            source_url=request.source_url,
            source_title=request.source_title,
            publisher=request.publisher,
            published_at=request.published_at,
            captured_at="2026-07-23T00:00:00Z",
            capture_mode="dom",
            quote=request.quote,
            key_phrase=request.key_phrase,
            image_sha256="a" * 64,
            target_bbox=bbox,
            quote_bboxes=[bbox],
            key_phrase_bboxes=[key],
            local_path="/tmp/article.png",
        )


def _planner(tmp_path, sentences):
    planner = ArticleEvidencePlanner(
        discovery=FakeDiscovery(),
        capture=FakeCapture(),
        sentence_resolver=FakeResolver(sentences),
        audit_dir=tmp_path,
    )
    planner._redis = staticmethod(lambda: None)
    return planner


def test_planner_attaches_exact_article_without_changing_narration(tmp_path):
    scene = {
        "scene_id": "scene-3",
        "phase": "twist",
        "content": "코스피가 반도체 투톱 상승으로 12.5퍼센트 올랐습니다.",
        "source_refs": ["facts[0]"],
    }
    before = narration_hash(scene)
    result = _planner(
        tmp_path,
        ["한국거래소에 따르면 코스피가 반도체 투톱 상승으로 12.5% 올랐다."],
    ).attach(
        job_id=77,
        scenes=[scene],
        verified_facts=[{
            "fact": "코스피가 반도체 투톱 상승으로 12.5% 올랐다.",
            "figure": "12.5%",
        }],
    )
    planned = result.scenes[0]
    assert planned["content"] == scene["content"]
    assert narration_hash(planned) == before
    assert planned["visual_kind"] == "article_scene"
    assert planned["emphasis_plan"]["body"] == "highlight_underline"
    assert planned["article_capture"]["quote"].endswith("12.5% 올랐다.")
    assert result.audit["selected_count"] == 1
    assert Path(tmp_path / "jobs/77/evidence/evidence_plan.json").is_file()


def test_unverified_article_keeps_original_scene(tmp_path):
    scene = {"scene_id": "scene-1", "content": "코스피가 12.5퍼센트 올랐습니다."}
    result = _planner(
        tmp_path,
        ["전혀 다른 회사의 매출이 3% 감소했다."],
    ).attach(
        job_id=78,
        scenes=[scene],
        verified_facts=[{"fact": "코스피가 12.5% 올랐다.", "figure": "12.5%"}],
    )
    assert "article_capture" not in result.scenes[0]
    assert result.audit["selected_count"] == 0
