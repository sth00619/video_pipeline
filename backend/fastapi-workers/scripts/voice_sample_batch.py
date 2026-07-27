#!/usr/bin/env python3
"""
voice_sample_batch.py — 영상 없이 "음성만" 빠르게 뽑아 담당자 피드백 루프를 도는 도구.

목적: 확정된 두 voice_id로, 대본 텍스트만 바꿔가며 mp3를 대량 생성하고
      담당자가 바로 들어볼 수 있는 목록(HTML/텍스트)까지 자동으로 만든다.
      이미지·영상 렌더링을 거치지 않으므로 반복 주기가 몇 초~분 단위로 빨라진다.

사용 흐름:
  1. sample_scripts/ 안에 대본 .txt 파일을 넣는다 (파일 하나 = 샘플 하나)
  2. voices.json 에 확정된 voice_id 2개를 채운다 (Codex가 보유)
  3. python scripts/voice_sample_batch.py 실행
  4. out/voice_samples/ 에 mp3 + index.html(공유용 목록) 생성됨
  5. 담당자 피드백 받으면 voices.json의 stability 등만 조정 → 다시 3번

담당자 공유는 index.html을 그대로 전달하거나, out/voice_samples/ 폴더를
압축해서 보내면 됨 (재생 가능한 mp3 + 어떤 설정으로 만들었는지 메타 포함).

의존성: requests
환경변수: ELEVENLABS_API_KEY
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.tts.forced_alignment_srt import AlignmentError, tts_with_timestamps
from app.utils.korean_tts import normalize_korean_numbers_for_tts

# 독립 실행 시에도 저장소 루트의 환경 설정을 읽되, 키 값은 출력하지 않는다.
load_dotenv(ROOT.parent.parent / ".env")


DEFAULT_VOICES_JSON = ROOT / "voices.json"
DEFAULT_SCRIPTS_DIR = ROOT / "sample_scripts"
DEFAULT_OUT_DIR = ROOT / "out" / "voice_samples"


def load_voices(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} 없음. voices.json을 만들고 확정된 voice_id 2개를 채우세요.\n"
            f"예시:\n{json.dumps(EXAMPLE_VOICES, ensure_ascii=False, indent=2)}"
        )
    return json.loads(path.read_text(encoding="utf-8"))


EXAMPLE_VOICES = {
    "voices": [
        {
            "name": "original_anchor",
            "voice_id": "여기에_Codex가_가진_voice_id_입력",
            "model_id": "eleven_multilingual_v2",
            "stability": 0.40,
            "similarity_boost": 0.75,
            "style": 0.0,
            "use_speaker_boost": True,
        },
        {
            "name": "ivc_news_anchor_with_pauses",
            "voice_id": "여기에_Codex가_가진_voice_id_입력",
            "model_id": "eleven_multilingual_v2",
            "stability": 0.40,
            "similarity_boost": 0.75,
            "style": 0.0,
            "use_speaker_boost": True,
        },
    ]
}


def load_scripts(scripts_dir: Path) -> list[tuple[str, str]]:
    """(파일명_stem, 텍스트) 목록. sample_scripts/*.txt 를 정렬해서 읽는다."""
    if not scripts_dir.exists() or not any(scripts_dir.glob("*.txt")):
        raise FileNotFoundError(
            f"{scripts_dir}에 .txt 대본 파일이 없습니다. "
            f"예: {scripts_dir}/01_intro_hook.txt"
        )
    out = []
    for p in sorted(scripts_dir.glob("*.txt")):
        text = p.read_text(encoding="utf-8").strip()
        if text:
            out.append((p.stem, text))
    return out


def generate_one(voice_cfg: dict, script_name: str, text: str, out_dir: Path) -> dict:
    """음성 1개 생성. 실패해도 배치 전체를 죽이지 않고 에러를 기록."""
    voice_dir = out_dir / voice_cfg["name"]
    voice_dir.mkdir(parents=True, exist_ok=True)
    mp3_path = voice_dir / f"{script_name}.mp3"

    t0 = time.monotonic()
    try:
        # 화면/자막에는 원문을 유지하고, 음성 API에 보내는 입력만 숫자 낭독형으로 바꾼다.
        narration_text = normalize_korean_numbers_for_tts(text)
        audio, words = tts_with_timestamps(
            narration_text,
            voice_id=voice_cfg["voice_id"],
            model_id=voice_cfg.get("model_id", "eleven_multilingual_v2"),
            stability=voice_cfg.get("stability", 0.40),
            similarity_boost=voice_cfg.get("similarity_boost", 0.75),
            style=voice_cfg.get("style", 0.0),
        )
        mp3_path.write_bytes(audio)
        dt = time.monotonic() - t0
        return {
            "voice": voice_cfg["name"], "script": script_name,
            "status": "ok", "seconds": round(dt, 1),
            "chars": len(text), "words": len(words),
            "audio_duration": round(words[-1].end, 1) if words else None,
            "path": str(mp3_path.relative_to(out_dir.parent)),
            "settings": {k: v for k, v in voice_cfg.items() if k != "voice_id"},
        }
    except AlignmentError as e:
        return {
            "voice": voice_cfg["name"], "script": script_name,
            "status": f"failed: {e}", "seconds": round(time.monotonic() - t0, 1),
        }


def build_index_html(results: list[dict], out_dir: Path, voices: list[dict]) -> None:
    """담당자가 브라우저로 바로 열어 듣고 비교할 수 있는 목록 페이지."""
    voice_names = [v["name"] for v in voices]
    scripts = sorted(set(r["script"] for r in results))
    by_key = {(r["voice"], r["script"]): r for r in results}

    rows = []
    for script in scripts:
        cells = []
        for vname in voice_names:
            r = by_key.get((vname, script))
            if not r or r["status"] != "ok":
                cells.append("<td>❌ 생성 실패</td>")
                continue
            dur = r.get("audio_duration", "?")
            cells.append(
                f"<td><audio controls src='{vname}/{script}.mp3'></audio>"
                f"<br><small>{dur}s</small></td>"
            )
        rows.append(f"<tr><th>{script}</th>{''.join(cells)}</tr>")

    settings_note = ""
    for v in voices:
        s = {k: v.get(k) for k in ("model_id", "stability", "similarity_boost", "style")}
        settings_note += f"<li><b>{v['name']}</b>: {json.dumps(s, ensure_ascii=False)}</li>"

    html = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<title>음성 샘플 비교</title>
<style>
body {{ font-family: -apple-system, sans-serif; margin: 24px; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #ddd; padding: 10px; text-align: left; vertical-align: top; }}
th {{ background: #f5f5f5; }}
audio {{ width: 220px; }}
</style></head>
<body>
<h2>음성 샘플 비교 — {time.strftime('%Y-%m-%d %H:%M')}</h2>
<p>현재 설정:</p>
<ul>{settings_note}</ul>
<table>
<tr><th>대본</th>{''.join(f'<th>{v}</th>' for v in voice_names)}</tr>
{''.join(rows)}
</table>
</body></html>"""
    (out_dir / "index.html").write_text(html, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--voices", type=Path, default=DEFAULT_VOICES_JSON)
    ap.add_argument("--scripts-dir", type=Path, default=DEFAULT_SCRIPTS_DIR)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = ap.parse_args()

    if not os.environ.get("ELEVENLABS_API_KEY"):
        raise RuntimeError("ELEVENLABS_API_KEY 미설정. 저장소 루트 .env 또는 실행 환경을 확인하세요.")

    voices = load_voices(args.voices)["voices"]
    for voice in voices:
        voice_id = str(voice.get("voice_id", "")).strip()
        if not voice_id or voice_id.startswith("PUT_VOICE_ID_HERE"):
            raise ValueError(f"{voice.get('name', 'unnamed')}의 voice_id를 ElevenLabs 대시보드에서 채우세요.")
    scripts = load_scripts(args.scripts_dir)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    print(f"보이스 {len(voices)}개 × 대본 {len(scripts)}개 = {len(voices)*len(scripts)}개 생성\n")

    results = []
    for voice_cfg in voices:
        for script_name, text in scripts:
            r = generate_one(voice_cfg, script_name, text, args.out_dir)
            results.append(r)
            # Windows 기본 콘솔(cp949)에서도 배치 진행 상황을 안정적으로 출력한다.
            status = "[성공]" if r["status"] == "ok" else "[실패]"
            dur = r.get("audio_duration", "-")
            print(f"  {status} [{voice_cfg['name']}] {script_name} "
                  f"({r['seconds']}s, 오디오 {dur}s) {r['status'] if r['status']!='ok' else ''}")

    (args.out_dir / "_manifest.json").write_text(
        json.dumps({"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    build_index_html(results, args.out_dir, voices)

    ok = sum(1 for r in results if r["status"] == "ok")
    print(f"\n완료: {ok}/{len(results)} 성공")
    print(f"담당자 공유용: {args.out_dir}/index.html (폴더째 압축해서 전달)")


if __name__ == "__main__":
    main()
