"""Attach attributable Korean article evidence to approved script scenes.

This planner never rewrites narration.  It selects a verified fact already
present in a scene, resolves an exact sentence from a reviewed public article,
captures that sentence with DOM coordinates, and attaches visual metadata to
the existing scene id.
"""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable

import httpx
from bs4 import BeautifulSoup

from app import runtime_config
from app.config import NAVER_CLIENT_ID, NAVER_CLIENT_SECRET, REDIS_HOST, REDIS_PORT
from app.models.article_evidence import (
    ArticleCandidate,
    ArticleSource,
    EvidenceCaptureRequest,
)
from app.services.article.source_policy import assert_korean, publisher_for_url
from app.services.article_discovery import ArticleDiscoveryService, ArticleDiscoveryUnavailable
from app.services.evidence_capture import (
    EvidenceCaptureService,
    validate_public_http_url,
)
from app.services.scene_frames.emphasis_policy import BodyEmphasis, EmphasisPlan
from app.services.verbatim_guard import validate as validate_verbatim

logger = logging.getLogger(__name__)
DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))

_NUMBER = re.compile(r"[+-]?\d[\d,]*(?:\.\d+)?\s*(?:%|퍼센트|원|달러|포인트|배|조|억|만)?")
_TOKEN = re.compile(r"[가-힣A-Za-z][가-힣A-Za-z0-9._-]{1,}")
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
_DIRECTION_GROUPS = (
    {"상승", "급등", "증가", "올랐", "반등", "강세", "돌파"},
    {"하락", "급락", "감소", "내렸", "약세", "붕괴"},
)
_STOPWORDS = {
    "그리고", "하지만", "때문", "대한", "관련", "시장", "현재", "이번",
    "것으로", "있습니다", "합니다", "했습니다", "입니다", "따르면",
    "오전", "오후", "거래일", "대비", "포인트",
}


class NarrationHashMismatch(RuntimeError):
    code = "NARRATION_HASH_MISMATCH"


@dataclass
class EvidencePlannerResult:
    scenes: list[dict[str, Any]]
    audit: dict[str, Any]


def narration_text(scene: dict[str, Any]) -> str:
    return str(scene.get("content") or scene.get("text") or "").strip()


def narration_hash(scene: dict[str, Any]) -> str:
    return hashlib.sha256(narration_text(scene).encode("utf-8")).hexdigest()


def _normalise(value: object) -> str:
    text = str(value or "").lower()
    text = text.replace("퍼센트", "%").replace(",", "")
    text = re.sub(r"(\d+(?:\.\d+)?)천", lambda m: str(float(m.group(1)) * 1000).removesuffix(".0"), text)
    return re.sub(r"\s+", "", text)


def _numbers(value: object) -> set[str]:
    return {_normalise(match.group(0)) for match in _NUMBER.finditer(str(value or ""))}


def _tokens(value: object) -> list[str]:
    values = []
    for token in _TOKEN.findall(str(value or "")):
        lowered = token.lower().strip("._-")
        if lowered not in _STOPWORDS and len(lowered) >= 2 and lowered not in values:
            values.append(lowered)
    return values


def _direction(value: str) -> int:
    for index, group in enumerate(_DIRECTION_GROUPS, start=1):
        if any(word in value for word in group):
            return index
    return 0


def _similarity(left: str, right: str) -> float:
    normal_left, normal_right = _normalise(left), _normalise(right)
    if normal_left and normal_right and (
        normal_left in normal_right or normal_right in normal_left
    ):
        return 1.0
    try:
        from rapidfuzz import fuzz

        return max(
            fuzz.ratio(left, right),
            fuzz.token_set_ratio(left, right),
            fuzz.partial_ratio(left, right),
        ) / 100.0
    except ImportError:
        # A source sentence often adds an attribution prefix. Compare both the
        # whole sentence and the best equal-length window so local/dev behavior
        # matches RapidFuzz's partial ratio used in the worker image.
        shorter, longer = sorted((normal_left, normal_right), key=len)
        windows = (
            SequenceMatcher(None, shorter, longer[start:start + len(shorter)]).ratio()
            for start in range(max(1, len(longer) - len(shorter) + 1))
        )
        return max(SequenceMatcher(None, normal_left, normal_right).ratio(), max(windows, default=0.0))


def _fact_text(fact: dict[str, Any]) -> str:
    values: list[str] = []
    normalized = ""
    for key in ("fact", "claim", "entity", "figure"):
        value = str(fact.get(key) or "").strip()
        if value and _normalise(value) not in normalized:
            values.append(value)
            normalized += _normalise(value)
    return " ".join(values)


def _source_ref_indexes(scene: dict[str, Any]) -> set[int]:
    indexes: set[int] = set()
    for raw in scene.get("source_refs") or []:
        match = re.fullmatch(r"(?:verified_)?facts\[(\d+)]", str(raw))
        if match:
            indexes.add(int(match.group(1)))
    return indexes


def _scene_fact_score(scene: dict[str, Any], fact: dict[str, Any], index: int) -> float:
    text = narration_text(scene)
    if index in _source_ref_indexes(scene):
        return 12.0
    fact_text = _fact_text(fact)
    figure = str(fact.get("figure") or "")
    score = 0.0
    if figure and _normalise(figure) in _normalise(text):
        score += 3.0
    phase = str(scene.get("phase") or scene.get("section") or "").lower()
    if phase in {"hook", "intro", "twist", "transition"}:
        score += 2.0
    terms = _tokens(fact_text)
    shared = [term for term in terms if term in text.lower()]
    score += min(3.0, len(shared))
    if re.search(r"[A-Z][A-Za-z0-9._-]+|[가-힣]{2,}(?:전자|그룹|정부|대통령|위원회|지수)", fact_text):
        score += 1.0
    return score


def _query_for(scene: dict[str, Any], fact: dict[str, Any]) -> tuple[str, list[str]]:
    fact_text = _fact_text(fact)
    terms = _tokens(fact_text)
    figure = str(fact.get("figure") or "").strip()
    entity = str(fact.get("entity") or "").strip()
    selected = [entity] if entity else []
    for term in terms:
        if entity and _normalise(entity) in _normalise(term):
            continue
        selected.append(term)
        if len(selected) >= 5:
            break
    if figure:
        selected.append(figure)
    if len(selected) < 2:
        selected.extend(_tokens(scene.get("title") or narration_text(scene))[:3])
    return " ".join(dict.fromkeys(selected))[:100], selected


def _key_phrase(quote: str, preferred_numbers: set[str] | None = None) -> str | None:
    matches = list(_NUMBER.finditer(quote))
    preferred = preferred_numbers or set()
    match = next(
        (item for item in matches if _normalise(item.group(0)) in preferred),
        matches[0] if matches else None,
    )
    if not match:
        return None
    left, right = match.start(), match.end()
    if left > 0 and quote[left - 1] in "([":
        left -= 1
    if right < len(quote) and quote[right] in ")]":
        right += 1
    # Include the following predicate token ("상승한", "감소했다") while
    # retaining an exact DOM-searchable source slice.
    next_start = right
    while next_start < len(quote) and quote[next_start].isspace():
        next_start += 1
    next_end = next_start
    while next_end < len(quote) and not quote[next_end].isspace():
        next_end += 1
    if next_end > next_start:
        right = next_end
    return quote[left:right].strip(" ,.")


class ArticleBodyResolver:
    """Read only reviewed public article containers and return source sentences."""

    def sentences(self, candidate: ArticleCandidate) -> list[str]:
        url = validate_public_http_url(candidate.url)
        rule = publisher_for_url(url)
        if bool(runtime_config.value("article_allowed_publishers_only")) and rule is None:
            return []
        response = httpx.get(
            url,
            timeout=12,
            follow_redirects=False,
            headers={"User-Agent": "VideoPipelineEvidence/3.0 (public-source-resolver)"},
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for selector in (rule.excludes if rule else ("header", "nav", "aside", "footer")):
            for node in soup.select(selector):
                node.decompose()
        containers = []
        for selector in (rule.containers if rule else ("article",)):
            containers.extend(soup.select(selector))
        body = " ".join(node.get_text(" ", strip=True) for node in containers)
        assert_korean(str(soup)[:2000], soup.title.get_text(" ", strip=True) if soup.title else "", body[:4000])
        return [
            re.sub(r"\s+", " ", sentence).strip()
            for sentence in _SENTENCE.split(body)
            if 15 <= len(re.sub(r"\s+", " ", sentence).strip()) <= 500
        ]


class ArticleEvidencePlanner:
    def __init__(
        self,
        *,
        discovery: ArticleDiscoveryService | None = None,
        capture: EvidenceCaptureService | None = None,
        sentence_resolver: ArticleBodyResolver | None = None,
        audit_dir: Path | None = None,
    ):
        self._discovery_injected = discovery is not None
        self.discovery = discovery or ArticleDiscoveryService()
        self.capture = capture or EvidenceCaptureService()
        self.sentence_resolver = sentence_resolver or ArticleBodyResolver()
        self.audit_dir = audit_dir or DATA_DIR

    def attach(
        self,
        *,
        job_id: int,
        scenes: list[dict[str, Any]],
        verified_facts: list[dict[str, Any]],
    ) -> EvidencePlannerResult:
        output = copy.deepcopy(scenes)
        hashes_before = {str(scene.get("scene_id") or index): narration_hash(scene) for index, scene in enumerate(output)}
        audit: dict[str, Any] = {
            "job_id": job_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "completed",
            "selected": [],
            "skipped": [],
        }
        if not bool(runtime_config.value("article_evidence_auto_enabled")):
            audit["status"] = "disabled"
            return EvidencePlannerResult(output, audit)
        if not verified_facts or (
            (not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET)
            and not self._discovery_injected
        ):
            audit["status"] = "unavailable"
            audit["reason"] = "verified_facts_or_naver_credentials_missing"
            self._persist_audit(job_id, audit)
            return EvidencePlannerResult(output, audit)

        candidates: list[tuple[float, int, int]] = []
        for scene_index, scene in enumerate(output):
            if scene.get("article_capture"):
                continue
            for fact_index, fact in enumerate(verified_facts):
                score = _scene_fact_score(scene, fact, fact_index)
                if score >= 3.0:
                    candidates.append((score, scene_index, fact_index))
        candidates.sort(key=lambda item: (-item[0], item[1], item[2]))

        used_scenes: set[int] = set()
        max_scenes = max(0, int(runtime_config.value("evidence_max_scenes")))
        for evidence_score, scene_index, fact_index in candidates:
            if len(used_scenes) >= max_scenes:
                break
            if scene_index in used_scenes:
                continue
            scene = output[scene_index]
            fact = verified_facts[fact_index]
            result = self._resolve_scene(job_id, scene, fact, fact_index, evidence_score)
            if result is None:
                audit["skipped"].append({
                    "scene_id": str(scene.get("scene_id") or scene_index),
                    "fact_index": fact_index,
                    "reason": "EVIDENCE_SENTENCE_UNVERIFIED",
                })
                continue
            capture, plan, selected_audit = result
            scene["visual_kind"] = "article_scene"
            scene["visual_type"] = "article_evidence"
            scene["article_capture"] = capture.model_dump(mode="json")
            scene["emphasis_plan"] = plan.model_dump(mode="json")
            scene["key_phrase"] = capture.key_phrase or ""
            scene["source_credit"] = f"출처: {capture.publisher} · {capture.published_at or ''}".rstrip(" ·")
            scene["evidence_match"] = selected_audit
            scene.setdefault("verified_facts", verified_facts)
            used_scenes.add(scene_index)
            audit["selected"].append(selected_audit)

        for index, scene in enumerate(output):
            scene_id = str(scene.get("scene_id") or index)
            after = narration_hash(scene)
            if hashes_before[scene_id] != after:
                raise NarrationHashMismatch(f"NARRATION_HASH_MISMATCH: scene={scene_id}")
        audit["narration_hashes"] = hashes_before
        audit["selected_count"] = len(audit["selected"])
        self._persist_audit(job_id, audit)
        return EvidencePlannerResult(output, audit)

    def _resolve_scene(
        self,
        job_id: int,
        scene: dict[str, Any],
        fact: dict[str, Any],
        fact_index: int,
        evidence_score: float,
    ):
        query, terms = _query_for(scene, fact)
        if not query:
            return None
        try:
            article_candidates = self._discover_cached(
                query,
                terms,
                max(3, int(runtime_config.value("evidence_max_searches_per_scene"))),
            )
        except (ArticleDiscoveryUnavailable, httpx.HTTPError, ValueError) as exc:
            logger.warning("article discovery unavailable for scene %s: %s", scene.get("scene_id"), exc)
            return None
        checked_urls: list[str] = []
        for candidate in article_candidates[: int(runtime_config.value("evidence_max_searches_per_scene"))]:
            checked_urls.append(candidate.url)
            publisher_rule = publisher_for_url(candidate.url)
            publisher = str(
                candidate.publisher
                or (publisher_rule.name if publisher_rule is not None else "")
            ).strip()
            if not publisher:
                logger.info("article candidate rejected without attributable publisher: %s", candidate.url)
                continue
            try:
                sentences = self.sentence_resolver.sentences(candidate)
            except Exception as exc:
                logger.info("article candidate rejected before quote resolution: %s (%s)", candidate.url, exc)
                continue
            match = self._best_sentence(narration_text(scene), fact, sentences)
            if match is None:
                continue
            similarity, quote = match
            key = _key_phrase(quote, _numbers(fact.get("figure") or ""))
            requested_body = self._body_policy(quote)
            request = EvidenceCaptureRequest(
                job_id=job_id,
                source_url=candidate.url,
                quote=quote,
                key_phrase=key,
                source_title=candidate.title,
                publisher=publisher,
                published_at=candidate.published_at,
                source=ArticleSource(
                    url=candidate.url,
                    publisher=publisher,
                ),
            )
            try:
                capture = self.capture.capture_dom(request)
            except Exception as exc:
                logger.info("article quote capture rejected: %s (%s)", candidate.url, exc)
                continue
            plan = EmphasisPlan(body=requested_body)
            downgraded = False
            if requested_body == BodyEmphasis.RECT and not capture.key_phrase_bboxes:
                plan = EmphasisPlan(body=BodyEmphasis.HIGHLIGHT)
                downgraded = True
            selected_audit = {
                "scene_id": str(scene.get("scene_id") or scene.get("id") or ""),
                "query": query,
                "terms": terms,
                "candidate_urls": checked_urls,
                "selected_url": candidate.url,
                "publisher": publisher,
                "quote": quote,
                "key_phrase": capture.key_phrase,
                "similarity": round(similarity, 4),
                "evidence_score": evidence_score,
                "fact_ref": f"facts[{fact_index}]",
                "requested_body": requested_body.value,
                "effective_body": plan.body.value,
                "downgraded": downgraded,
                "narration_sha256": narration_hash(scene),
            }
            return capture, plan, selected_audit
        return None

    @staticmethod
    def _best_sentence(scene_text: str, fact: dict[str, Any], sentences: list[str]) -> tuple[float, str] | None:
        fact_text = _fact_text(fact)
        required_numbers = _numbers(fact_text)
        fact_direction = _direction(fact_text)
        fact_terms = set(_tokens(fact_text)[:8])
        threshold = float(runtime_config.value("evidence_min_sentence_similarity"))
        ranked: list[tuple[float, str]] = []
        for sentence in sentences:
            if required_numbers and not required_numbers <= _numbers(sentence):
                continue
            if fact_direction and _direction(sentence) not in {0, fact_direction}:
                continue
            if fact_terms and not (fact_terms & set(_tokens(sentence))):
                continue
            numeric_gate = validate_verbatim(sentence, {"verified_facts": [fact]})
            if required_numbers and not numeric_gate.passed:
                continue
            similarity = max(_similarity(fact_text, sentence), _similarity(scene_text, sentence))
            if similarity >= threshold:
                ranked.append((similarity, sentence))
        return max(ranked, default=None, key=lambda item: item[0])

    @staticmethod
    def _body_policy(quote: str) -> BodyEmphasis:
        if _numbers(quote):
            return BodyEmphasis.HIGHLIGHT_UNDERLINE
        if any(marker in quote for marker in ('"', "'", "말했다", "밝혔다", "설명했다")):
            return BodyEmphasis.HIGHLIGHT
        return BodyEmphasis.RECT if len(quote) <= 45 else BodyEmphasis.HIGHLIGHT

    def _discover_cached(self, query: str, terms: list[str], limit: int) -> list[ArticleCandidate]:
        key = "article:discover:v3:" + hashlib.sha256(
            json.dumps([query, terms, limit], ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        client = self._redis()
        if client is not None:
            try:
                cached = client.get(key)
                if cached:
                    return [ArticleCandidate.model_validate(item) for item in json.loads(cached)]
            except Exception:
                pass
        result = self.discovery.discover(query, terms, limit)
        if client is not None:
            try:
                client.setex(key, 86_400, json.dumps([item.model_dump(mode="json") for item in result], ensure_ascii=False))
            except Exception:
                pass
        return result

    @staticmethod
    def _redis():
        try:
            import redis

            return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True, socket_timeout=1)
        except Exception:
            return None

    def _persist_audit(self, job_id: int, audit: dict[str, Any]) -> None:
        target = self.audit_dir / "jobs" / str(job_id) / "evidence" / "evidence_plan.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
        client = self._redis()
        if client is not None:
            try:
                client.setex(f"evidence:audit:{job_id}", 7 * 86_400, json.dumps(audit, ensure_ascii=False))
            except Exception as exc:
                logger.warning("evidence audit Redis persistence deferred: %s", exc)
