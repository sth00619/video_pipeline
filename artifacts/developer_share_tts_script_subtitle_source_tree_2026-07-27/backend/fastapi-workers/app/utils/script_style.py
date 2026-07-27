"""Original editorial profiles for spoken Korean finance scripts.

The profile deliberately captures reusable storytelling mechanics rather than
the wording, catchphrases, or distinctive voice of a named channel or writer.
Facts remain controlled by ScriptWorker's verified-facts boundary.
"""
from __future__ import annotations

import re
from typing import Any


DEFAULT_SCRIPT_STYLE_PROFILE = "original_finance_storyteller_v1"

FINANCE_STORYTELLER_GUIDE = """
<editorial_style_profile name="original_finance_storyteller_v1">
Write an original Korean finance-storytelling script. Do not imitate, name,
quote, paraphrase, or reproduce the distinctive phrasing of any existing
creator, channel, or source. Use only the general editorial mechanics below.

Narrative architecture:
1. Opening (first 10%): begin with one familiar situation, tension, contrast,
   or a precise viewer question. State why the topic matters before explaining
   terminology. Do not reveal the entire conclusion in the first sentence.
2. Context (next 20%): give only the background a viewer needs, then connect
   each fact to a concrete consequence rather than listing numbers.
3. Investigation (middle 40%): alternate "what happened → why it happened →
   what would change the interpretation". Place a small turn, trade-off, or
   uncertainty between major facts to maintain forward motion.
4. Decision frame (next 20%): separate observed facts from interpretation and
   present conditions to watch, not buy/sell instructions or predictions.
5. Closing (last 10%): return to the opening question and leave the viewer
   with one memorable monitoring point and a natural next-question.

Spoken Korean craft:
- Write as a calm, perceptive narrator speaking to one viewer. Prefer natural
  conversational endings such as "그런데 여기서 봐야 할 건…" only when they
  genuinely advance the reasoning; do not repeat a stock catchphrase.
- Mix short emphasis sentences with medium explanatory sentences. One scene
  must carry one idea, one emotional beat, and one transition to the next.
- Translate a number into scale, comparison, cause, or consequence in the
  same or following sentence. Do not pile up bare figures.
- Use rhetorical questions sparingly (roughly 2–5 per 10 minutes), and answer
  them with evidence. Avoid exaggerated urgency, manufactured fear, filler,
  and repetitive "정리하면" endings.
- Make uncertainty legible: say what is confirmed, what is an interpretation,
  and what data would invalidate it.

Integrity rules:
- The verified facts are a hard boundary. Never add an unverified statistic,
  date, source, quote, causal claim, or forecast merely to improve drama.
- Preserve the requested scene structure and all [대사]/visual/pose labels.
- This is an original house style, not a simulation of a particular channel.
</editorial_style_profile>
""".strip()


def get_script_style_guide(profile: str | None = None) -> str:
    """Return the supported original profile, safely falling back to default."""
    # Keeping one explicit profile makes future approved house-style variants
    # additive without allowing unreviewed creator imitation through a request.
    return FINANCE_STORYTELLER_GUIDE


def assess_storytelling(sections: list[dict[str, Any]], script: str) -> dict[str, Any]:
    """Provide transparent editorial QA without judging factual correctness.

    Scores are intentionally diagnostic: they flag a script that reads like an
    outline or number dump so an operator can revise it in semi-automatic mode.
    They never rewrite facts or claim that a named creator was replicated.
    """
    narration = " ".join(str(s.get("content") or s.get("text") or "") for s in sections).strip()
    source = narration or script or ""
    normalized = re.sub(r"\s+", " ", source)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", normalized) if s.strip()]
    question_count = sum("?" in s for s in sentences)
    direct_address_count = len(re.findall(r"(?:여러분|지금|우리가|보시면|생각해\s*볼)", normalized))
    transition_count = len(re.findall(r"(?:그런데|반대로|다만|그래서|문제는|여기서)", normalized))
    figure_count = len(re.findall(r"\d", normalized))
    avg_length = round(sum(len(s.replace(" ", "")) for s in sentences) / len(sentences), 1) if sentences else 0

    signals = {
        "opening_hook": bool(re.search(r"(?:왜|무엇|정말|바로|지금|처음|결국|상황)", normalized[:300])),
        "story_transitions": transition_count,
        "viewer_connection": direct_address_count,
        "evidence_translation": bool(figure_count and re.search(r"(?:의미|영향|이유|때문|보여|해석)", normalized)),
        "closing_monitoring_point": bool(re.search(r"(?:확인|지켜볼|봐야|관찰)", normalized[-500:])),
    }
    checks = sum(bool(value) for value in signals.values())
    score = min(100, 35 + checks * 11 + min(12, transition_count * 2) + (8 if 18 <= avg_length <= 58 else 0))
    suggestions: list[str] = []
    if not signals["opening_hook"]:
        suggestions.append("첫 씬에 시청자의 상황 또는 핵심 질문을 한 문장으로 추가하세요.")
    if transition_count < max(2, len(sections) // 12):
        suggestions.append("사실 나열 사이에 원인·반전·조건을 잇는 전환 문장을 보강하세요.")
    if figure_count and not signals["evidence_translation"]:
        suggestions.append("각 핵심 수치 뒤에 왜 중요한지 또는 비교 기준을 붙이세요.")
    if not signals["closing_monitoring_point"]:
        suggestions.append("마지막에 매수·매도 지시 대신 다음에 확인할 지표를 남기세요.")

    return {
        "profile": DEFAULT_SCRIPT_STYLE_PROFILE,
        "score": score,
        "signals": signals,
        "metrics": {
            "scene_count": len(sections),
            "sentence_count": len(sentences),
            "avg_sentence_chars": avg_length,
            "rhetorical_question_count": question_count,
        },
        "suggestions": suggestions,
    }
