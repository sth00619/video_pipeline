#!/usr/bin/env python3
"""사람 녹음 작업자에게 전달할 낭독 대본과 주의사항을 만든다."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.utils.korean_tts import normalize_korean_numbers_for_tts
from app.workers.tts_worker import TtsWorker


def build_guide(display_script: str) -> str:
    worker = TtsWorker()
    spoken_script = worker._soften_korean_delivery_cadence(worker._preprocess_for_tts(display_script))
    decimals = list(dict.fromkeys(re.findall(r"(?<!\d)(\d+\.\d+)(?!\d)", display_script)))
    pronunciation_rows = [
        f"- `{value}` → **{normalize_korean_numbers_for_tts(value)}**"
        for value in decimals
    ] or ["- 숫자·약어는 아래 낭독용 대본 표기를 그대로 읽습니다."]
    return f"""# 사람 녹음 작업 가이드

## 1. 녹음 대본

아래 **낭독용 대본**을 한 글자도 임의로 고치지 말고 읽어 주세요. 화면에는 원문이
표시되며, 낭독용 대본은 자막과 음성을 정확히 맞추기 위한 발음 표기입니다.

### 화면 원문

{display_script}

### 낭독용 대본

{spoken_script}

## 2. 주의사항

- 조용한 실내에서 녹음하고, 배경 음악·효과음·노이즈 제거 앱은 사용하지 않습니다.
- WAV 44.1 kHz 이상, 모노 또는 스테레오로 녹음합니다. MP4로 전달해도 됩니다.
- 시작과 끝에 각각 1초 정도의 여백을 남기되, 문장 사이에 인위적인 무음 편집을 넣지 않습니다.
- 문장 끝은 자연스럽게 마무리하고, 다음 문장은 실제 생각의 전환이 있을 때만 짧게 쉽니다.
- 중간에 틀리면 처음부터 다시 녹음하거나, 틀린 문장 앞뒤로 1초 이상 남긴 별도 테이크를 제공합니다.
- 원문·낭독 대본을 임의로 요약, 재배열하거나 숫자·약어를 다른 방식으로 읽지 않습니다.

## 3. 발음 시 중요한 포인트

{chr(10).join(pronunciation_rows)}

- 소수는 `점`을 따로 끊지 않고 자연스럽게 연결합니다. 예: `3.75`는 **삼쩜칠오**,
  `17.91`은 **십칠쩜구일**입니다.
- 약어와 단위는 낭독용 대본에 적힌 한글 표기를 우선합니다.
- 숫자 뒤 단위·조사는 붙여 자연스럽게 읽습니다. 예: `3.75퍼센트`는 **삼쩜칠오퍼센트**입니다.

## 전달 방법

녹음 MP4 또는 WAV/MP3와 이 가이드의 화면 원문 대본을 함께 전달해 주세요. 수령 후에는
최종 음성에서 문자 단위 강제 정렬을 수행해 화면 원문 자막을 생성합니다.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="사람 녹음 작업 가이드 Markdown을 생성합니다.")
    parser.add_argument("--script", required=True, help="화면 원문 UTF-8 TXT")
    parser.add_argument("--out", required=True, help="출력 Markdown 경로")
    args = parser.parse_args()
    script = Path(args.script).read_text(encoding="utf-8").strip()
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_guide(script), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
