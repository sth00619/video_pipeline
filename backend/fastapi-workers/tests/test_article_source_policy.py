import pytest

from app.models.article_evidence import ArticleSource, EvidenceCaptureRequest
from app.services.article.source_policy import NonKoreanArticleError, PublisherNotAllowedError, assert_article_source, assert_korean, korean_mirror_url


def test_english_article_is_rejected():
    with pytest.raises(NonKoreanArticleError):
        assert_korean("<html lang='en'>", "English article", "This English article has no Korean body.")


def test_allowlist_requires_reviewed_publisher(monkeypatch):
    request = EvidenceCaptureRequest(job_id=1, source_url="https://example.com/a", quote="인용문", source=ArticleSource(url="https://example.com/a", publisher="예시"))
    with pytest.raises(PublisherNotAllowedError):
        assert_article_source(request)


def test_yna_english_url_normalizes_to_korean_mirror():
    assert korean_mirror_url("https://en.yna.co.kr/view/AEN20260723") == "https://www.yna.co.kr/view/AEN20260723"
