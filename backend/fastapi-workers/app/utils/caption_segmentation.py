"""승인 대본에서 화면 자막 청크를 만드는 단일 분할 규칙."""

from __future__ import annotations

import re

from app.utils.sentence_splitter import split_sentences


def split_script_into_caption_chunks(
    script: str, max_chars: int = 22, min_chars: int = 8,
) -> list[str]:
    """단어·조사·관형 관계를 보존해 원문을 화면 자막 단위로 분할한다.

    SCRIPT 단계의 예상 청크와 실제 TTS 강제 정렬 청크가 반드시 같은 함수를
    사용하도록 워커 밖에 둔다. 이 함수는 문자나 숫자를 바꾸지 않는다.
    """
    clean_script = re.sub(r"^##\s*.+$", "", script, flags=re.MULTILINE).strip()
    raw_sentences = split_sentences(clean_script)

    def has_modifier_ending(word: str) -> bool:
        """관형형 어미(한·는·ㄴ·ㄹ)로 끝나는 어절인지 판별한다."""
        if not word:
            return False
        if word.endswith("는"):
            return True
        last = ord(word[-1])
        if not (0xAC00 <= last <= 0xD7A3):
            return False
        jongseong = (last - 0xAC00) % 28
        return jongseong in {4, 8}

    def requires_left_context(word: str) -> bool:
        """자막 첫머리에 단독으로 두면 어색한 조사·연결 표현을 찾는다."""
        return bool(re.search(
            r"(?:에서도|에서|에게|에도|으로|부터|까지|처럼|보다|만|은|는|이|가|을|를|와|과|의)$",
            word,
        ))

    natural_sentence_max = min(max_chars + 2, 20)
    text_chunks: list[str] = []
    for sentence in raw_sentences:
        if len(sentence) <= natural_sentence_max:
            text_chunks.append(sentence)
            continue

        bound_particles = {
            "은", "는", "이", "가", "을", "를", "와", "과", "의", "만", "도",
            "에", "에서", "에게", "에도", "으로", "부터", "까지", "보다", "처럼",
            "라도", "마저", "조차", "밖에",
        }
        source_words = sentence.split()
        words: list[str] = []
        for word_index, raw_word in enumerate(source_words):
            next_word = source_words[word_index + 1] if word_index + 1 < len(source_words) else ""
            demonstrative_determiner = raw_word == "이" and bool(re.match(
                r"^(?:한|두|세|네|몇|모든|각|다음|이전|첫|마지막|같은|다른)",
                next_word,
            ))
            if raw_word in bound_particles and words and not demonstrative_determiner:
                words[-1] += raw_word
            else:
                words.append(raw_word)

        lines: list[list[str]] = []
        current_line: list[str] = []
        current_len = 0
        for word in words:
            new_len = current_len + len(word) + (1 if current_line else 0)
            if new_len > max_chars and current_line:
                lines.append(current_line)
                current_line = [word]
                current_len = len(word)
            else:
                current_line.append(word)
                current_len = new_len
        if current_line:
            lines.append(current_line)

        if len(lines) > 1 and len(" ".join(lines[-1])) < min_chars:
            previous, trailing = lines[-2], lines[-1]
            while len(" ".join(trailing)) < min_chars and len(previous) > 1:
                current_shortest = min(len(" ".join(previous)), len(" ".join(trailing)))
                moved_shortest = min(
                    len(" ".join(previous[:-1])),
                    len(" ".join([previous[-1], *trailing])),
                )
                if moved_shortest <= current_shortest:
                    break
                trailing.insert(0, previous.pop())

        semantic_hard_max = natural_sentence_max
        for line_index in range(len(lines) - 1):
            previous, following = lines[line_index], lines[line_index + 1]
            if len(previous) <= 1 or not following:
                continue
            candidate = previous[-1]
            if not (has_modifier_ending(candidate) or requires_left_context(following[0])):
                continue
            remaining = " ".join(previous[:-1])
            bound_following = " ".join([candidate, *following])
            if len(remaining) < min_chars or len(bound_following) > semantic_hard_max:
                continue
            following.insert(0, previous.pop())
        text_chunks.extend(" ".join(line) for line in lines)

    return text_chunks
