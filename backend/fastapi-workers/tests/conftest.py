"""단위 테스트는 운영 영속 요청 저장소를 열지 않는다."""
import pytest


@pytest.fixture(autouse=True)
def isolated_image_request_state(tmp_path, monkeypatch):
    from app import config, runtime_config
    path = str(tmp_path / "request_state.sqlite3")
    monkeypatch.setattr(config, "GEMINI_REQUEST_STATE_PATH", path)
    monkeypatch.setitem(runtime_config._state, "gemini_request_state_path", path)
