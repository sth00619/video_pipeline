import pytest

from app.providers.real import trending


class _RecordingRedis:
    def __init__(self) -> None:
        self.values: dict[str, int] = {}
        self.written_keys: list[str] = []
        self.expired_keys: list[tuple[str, int]] = []

    def get(self, key: str):  # noqa: ANN201
        return self.values.get(key)

    def incr(self, key: str) -> int:
        self.written_keys.append(key)
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]

    def decr(self, key: str) -> int:
        self.written_keys.append(key)
        self.values[key] = self.values.get(key, 0) - 1
        return self.values[key]

    def incrby(self, key: str, units: int) -> int:
        self.written_keys.append(key)
        self.values[key] = self.values.get(key, 0) + units
        return self.values[key]

    def expire(self, key: str, seconds: int) -> bool:
        self.expired_keys.append((key, seconds))
        return True


@pytest.fixture
def quota_day(monkeypatch):  # noqa: ANN001, ANN201
    monkeypatch.setattr(trending, "_quota_day_key", lambda: "2026-08-14")


def test_search_quota_uses_dedicated_daily_key(quota_day):  # noqa: ANN001
    redis = _RecordingRedis()

    assert trending._consume_search_quota(redis) is True

    assert redis.values == {"youtube:quota:search:2026-08-14": 1}
    assert "youtube:quota:2026-08-14" not in redis.written_keys
    assert redis.expired_keys == [("youtube:quota:search:2026-08-14", 24 * 60 * 60)]


def test_shared_quota_does_not_touch_search_bucket(quota_day):  # noqa: ANN001
    redis = _RecordingRedis()

    assert trending._consume_quota(redis, 1, "channels.list") is True

    assert redis.values == {"youtube:quota:2026-08-14": 1}
    assert "youtube:quota:search:2026-08-14" not in redis.written_keys


@pytest.mark.parametrize(
    ("call_count", "expected"),
    [(99, True), (100, True), (101, False)],
)
def test_search_quota_hard_limit_at_one_hundred_calls(
    quota_day,  # noqa: ANN001
    call_count: int,
    expected: bool,
):
    redis = _RecordingRedis()
    redis.values["youtube:quota:search:2026-08-14"] = call_count - 1

    assert trending._consume_search_quota(redis) is expected


def test_search_quota_rolls_back_rejected_increment(quota_day):  # noqa: ANN001
    redis = _RecordingRedis()
    key = "youtube:quota:search:2026-08-14"
    redis.values[key] = 100

    assert trending._consume_search_quota(redis) is False
    assert redis.values[key] == 100


def test_search_quota_allows_request_without_redis():
    assert trending._consume_search_quota(None) is True


def test_keyword_search_uses_dedicated_quota_counter(monkeypatch):
    dedicated_calls: list[object] = []
    shared_operations: list[str] = []

    monkeypatch.setattr(
        trending,
        "_consume_search_quota",
        lambda redis_client: dedicated_calls.append(redis_client) or True,
    )

    def _record_shared(redis_client, units: int, operation: str):  # noqa: ANN001
        shared_operations.append(operation)
        return True

    monkeypatch.setattr(trending, "_consume_quota", _record_shared)

    class _Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, list]:
            return {"items": []}

    monkeypatch.setattr(trending.requests, "get", lambda *args, **kwargs: _Response())

    analyzer = trending.YouTubeTrendingAnalyzer.__new__(trending.YouTubeTrendingAnalyzer)
    analyzer.api_key = "test-key"
    analyzer.base_url = "https://www.googleapis.com/youtube/v3"
    analyzer._redis = object()

    result = analyzer._collect_keyword_search("KOSPI", "반도체", limit=5, recent_hours=168)

    assert result == []
    assert dedicated_calls == [analyzer._redis]
    assert "search.list" not in shared_operations
