"""
script_pattern_analyzer.py — 레퍼런스 대본의 구조 패턴을 정량 측정.

목적: "후킹이 강해야 한다" 같은 주관적 지침을 측정 가능한 숫자로 바꾼다.
      Codex가 하우스 스타일을 재현할 때 자의적 해석을 막는 기준선이 된다.

⚠️ 저작권: 이 도구는 특정 문장을 복제하지 않는다. 문장 길이 분포, 전환어 빈도,
   훅 유형, 종결어미 패턴 같은 "구조 통계"만 추출한다. 추출된 것은 스타일 지문이지
   내용이 아니다. 생성 시에도 이 통계에 맞추되 문장은 새로 쓴다.

측정 항목:
  1. 훅 유형 분류 (질문형/숫자쇼크형/직접호명형/선언리듬형/스토리콜드오픈형)
  2. 문장 길이 분포 (평균/중앙값/최대 — 호흡 단위)
  3. 전환어 빈도 및 간격 (근데/하지만/그래서/자 — 리듬 전환)
  4. 종결어미 패턴 (해요체/해체 — 친근함 톤)
  5. 청자 호명 빈도 (님들/여러분/우리 — 참여 유도)
  6. 숫자 등장 밀도 (경제 콘텐츠 특성)
  7. 수사적 질문 빈도 (궁금증 유발)
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field, asdict


# ---------------------------------------------------------------------------
# 훅 유형 사전 (전사본 10개에서 관찰된 실제 오프닝 패턴)
# ---------------------------------------------------------------------------
HOOK_SIGNALS = {
    "question": [           # 질문으로 궁금증 유발
        r"볼까요", r"알고\s*있었어", r"뭔지\s*알", r"떠올려", r"아세요", r"할까요",
    ],
    "number_shock": [       # 숫자를 먼저 던져 충격
        r"^\s*[\d,]+\s*(달러|원|만|억|조|%|배|퍼센트)",
        r"[\d,]+\s*(달러|원)\b",
    ],
    "direct_address": [     # 청자 직접 호명
        r"^님들", r"^여러분", r"우리\s*계좌", r"우리가\s*미리",
    ],
    "story_cold_open": [    # 이야기로 시작 (인물/사건)
        r"한\s*남자가", r"한\s*달\s*전", r"태어났", r"시작했",
    ],
    "declarative_rhythm": [ # 짧은 선언 나열로 리듬
        r"^\w+는\s+\w+,\s+\w+는",  # "여자는 백, 남자는 시계"
    ],
}

# 전환어 (리듬 전환 신호)
TRANSITION_WORDS = ["근데", "하지만", "그래서", "그런데", "자,", "자 ", "반면", "심지어",
                    "결국", "왜냐면", "왜냐하면", "특히", "그리고", "물론", "다음으로"]

# 청자 호명어
ADDRESS_WORDS = ["님들", "여러분", "우리", "구독자", "여기서", "봐봐", "생각해 봐", "기억해"]

# 종결어미 패턴
ENDING_HAEYO = [r"요\.", r"요\?", r"에요", r"예요", r"거예요", r"습니다", r"습니까"]  # 해요체/합쇼체
ENDING_HAE = [r"거야\.", r"이야\.", r"봐\.", r"어\.", r"지\.", r"야\.", r"돼\.", r"줄게"]  # 해체(반말)


@dataclass
class ScriptStats:
    label: str
    total_chars: int
    sentence_count: int
    avg_sentence_len: float
    median_sentence_len: float
    max_sentence_len: int
    hook_types: list[str]
    opening_text: str            # 첫 2문장 (훅 확인용)
    transition_count: int
    transition_per_100sent: float
    address_count: int
    haeyo_ratio: float           # 해요체 비율
    hae_ratio: float             # 해체(반말) 비율
    number_density: float        # 100자당 숫자 등장
    rhetorical_q_count: int      # 수사적 질문


def _split_sentences(text: str) -> list[str]:
    """숫자 안전 문장 분리 — 소수점(16.5)을 문장 경계로 오인하지 않음."""
    # 마침표 뒤에 숫자가 오면 소수점으로 간주해 분리하지 않음
    protected = re.sub(r"(\d)\.(\d)", r"\1<DOT>\2", text)
    parts = re.split(r"(?<=[.!?])\s+", protected)
    return [p.replace("<DOT>", ".").strip() for p in parts if p.strip()]


def _classify_hooks(opening: str) -> list[str]:
    found = []
    for hook_type, patterns in HOOK_SIGNALS.items():
        for pat in patterns:
            if re.search(pat, opening):
                found.append(hook_type)
                break
    return found or ["other"]


def analyze_script(text: str, label: str = "") -> ScriptStats:
    text = text.strip()
    sentences = _split_sentences(text)
    lengths = [len(s) for s in sentences] or [0]
    opening = " ".join(sentences[:2])

    # 전환어
    trans = sum(text.count(w) for w in TRANSITION_WORDS)
    # 호명
    addr = sum(text.count(w) for w in ADDRESS_WORDS)
    # 종결어미
    haeyo = sum(len(re.findall(p, text)) for p in ENDING_HAEYO)
    hae = sum(len(re.findall(p, text)) for p in ENDING_HAE)
    ending_total = max(1, haeyo + hae)
    # 숫자 밀도
    numbers = len(re.findall(r"[\d,]+", text))
    # 수사적 질문
    rhetorical = text.count("?") + text.count("까요") + text.count("을까")

    return ScriptStats(
        label=label,
        total_chars=len(text),
        sentence_count=len(sentences),
        avg_sentence_len=round(statistics.mean(lengths), 1),
        median_sentence_len=round(statistics.median(lengths), 1),
        max_sentence_len=max(lengths),
        hook_types=_classify_hooks(opening),
        opening_text=opening[:120],
        transition_count=trans,
        transition_per_100sent=round(trans / max(1, len(sentences)) * 100, 1),
        address_count=addr,
        haeyo_ratio=round(haeyo / ending_total, 2),
        hae_ratio=round(hae / ending_total, 2),
        number_density=round(numbers / max(1, len(text)) * 100, 2),
        rhetorical_q_count=rhetorical,
    )


def compare_channels(scripts: dict[str, list[str]]) -> dict:
    """채널별 스크립트 묶음을 받아 채널 평균 프로파일을 만든다.

    scripts = {"지식한입": [text1, text2, ...], "경제사냥꾼": [...]}
    """
    profiles = {}
    for channel, texts in scripts.items():
        stats = [analyze_script(t, f"{channel}_{i}") for i, t in enumerate(texts)]
        profiles[channel] = {
            "n_scripts": len(stats),
            "avg_sentence_len": round(statistics.mean(s.avg_sentence_len for s in stats), 1),
            "median_sentence_len": round(statistics.mean(s.median_sentence_len for s in stats), 1),
            "hae_ratio": round(statistics.mean(s.hae_ratio for s in stats), 2),
            "haeyo_ratio": round(statistics.mean(s.haeyo_ratio for s in stats), 2),
            "transition_per_100sent": round(statistics.mean(s.transition_per_100sent for s in stats), 1),
            "number_density": round(statistics.mean(s.number_density for s in stats), 2),
            "common_hooks": _most_common_hooks(stats),
            "sample_openings": [s.opening_text[:80] for s in stats[:3]],
        }
    return profiles


def _most_common_hooks(stats: list[ScriptStats]) -> dict:
    from collections import Counter
    c = Counter()
    for s in stats:
        c.update(s.hook_types)
    return dict(c.most_common())


if __name__ == "__main__":
    import json
    # 데모: 실제 전사본 오프닝으로 훅 분류 테스트
    samples = {
        "지식한입": [
            "인도라는 나라에 대한 이미지를 한번 떠올려 볼까요? 가난하고 위생적이지 못하고 카스트라는 관습이 족세가 되고 있는 나라.",
            "여자는 백, 남자는 시계, 시계하면 롤렉스. 시계 쪽에서 인지도로는 롤렉스가 최고죠.",
        ],
        "경제사냥꾼": [
            "님들, 우리가 미리 알고 있어야 할 2026년 주가 하락장. 뭔지 알고 있었어?",
            "1,600달러. 지금 환율로 바꾸면 236만 원 정도야. 한 남자가 이 돈을 빌려서 시작했어.",
        ],
    }
    profiles = compare_channels(samples)
    print(json.dumps(profiles, ensure_ascii=False, indent=2))
