import hashlib
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from app.models.article_evidence import EvidenceCaptureRequest, QuoteCardRequest
from app.services import evidence_capture
from app.services.evidence_capture import EvidenceCaptureService


@pytest.fixture()
def public_article_server(tmp_path):
    quote = "조사 대상이 된 한국 등 나머지 45개국에 대해서는 12.5%의 추가 관세를 부과하겠다고 밝혔습니다."
    (tmp_path / "article.html").write_text(
        "<html><head><meta charset='utf-8'><title>한글 기사 테스트</title><meta property='og:site_name' content='테스트 언론사'>"
        "<meta property='article:published_time' content='2026-07-22'></head>"
        f"<body><article><p style='font-size:32px;width:360px;line-height:1.8'>{quote}</p></article></body></html>",
        encoding="utf-8",
    )
    handler = lambda *args, **kwargs: SimpleHTTPRequestHandler(*args, directory=str(tmp_path), **kwargs)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/article.html", quote
    finally:
        server.shutdown(); thread.join()


@pytest.mark.integration
def test_dom_capture_preserves_korean_and_multi_line_bboxes(monkeypatch, tmp_path, public_article_server):
    pytest.importorskip("playwright")
    try:
        EvidenceCaptureService._browser_instance()
    except Exception as exc:
        pytest.skip(f"Playwright Chromium is not installed: {exc}")
    monkeypatch.setattr(evidence_capture, "DATA_DIR", tmp_path)
    monkeypatch.setattr(evidence_capture, "validate_public_http_url", lambda url: url)
    monkeypatch.setattr(evidence_capture, "_is_public_host", lambda host: True)
    monkeypatch.setattr(EvidenceCaptureService, "_upload_minio", staticmethod(lambda *_: None))
    url, quote = public_article_server
    key_phrase = "12.5%의 추가 관세"
    result = EvidenceCaptureService().capture_dom(EvidenceCaptureRequest(
        job_id=11,
        source_url=url,
        quote=quote,
        key_phrase=key_phrase,
    ))
    assert Path(result.local_path).exists()
    assert result.publisher == "테스트 언론사"
    assert len(result.quote_bboxes) >= 2
    assert result.key_phrase == key_phrase
    assert result.key_phrase_bboxes
    assert result.bbox_source == "dom_range"
    assert result.image_sha256 == hashlib.sha256(Path(result.local_path).read_bytes()).hexdigest()


def test_quote_card_is_labelled_editorial_asset(monkeypatch, tmp_path):
    monkeypatch.setattr(evidence_capture, "DATA_DIR", tmp_path)
    monkeypatch.setattr(EvidenceCaptureService, "_upload_minio", staticmethod(lambda *_: None))
    result = EvidenceCaptureService().render_quote_card(QuoteCardRequest(
        job_id=12, quote="12.5%의 추가 관세를 부과한다.", publisher="테스트 언론사", published_at="2026.07.22",
    ))
    assert result.source_title == "기사 인용"
    assert result.capture_mode == "dom"
    assert Path(result.local_path).exists()


def test_private_url_is_rejected():
    with pytest.raises(evidence_capture.EvidenceCaptureError):
        evidence_capture.validate_public_http_url("http://127.0.0.1/internal")
