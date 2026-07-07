"""
SFX 효과음 생성 워커 — ElevenLabs Sound Generation API

섹션별 효과음 자동 생성:
  - 인트로: 뉴스 오프닝 스팅어 (3초)
  - 섹션 전환: 디지털 우쉬 효과 (1초)
  - 핵심 데이터: 서스펜스 히트 (2초)
  - 결론: 리졸루션 차임 (2초)

API 비용: 생성당 200 크레딧
"""
import os
import logging
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

# 섹션 유형별 SFX 프롬프트 및 길이 정의
SFX_PRESETS: dict[str, dict] = {
    "인트로": {
        "prompt": "dramatic Korean news broadcast opening stinger, professional, 3 seconds",
        "duration": 3.0,
        "label": "intro",
    },
    "핵심 데이터": {
        "prompt": "tension building suspense hit, cinematic, 2 seconds",
        "duration": 2.0,
        "label": "data_hit",
    },
    "결론": {
        "prompt": "uplifting resolution chime, warm, 2 seconds",
        "duration": 2.0,
        "label": "conclusion",
    },
}

# 전환 효과음 (시장 배경 → 결론 사이의 모든 전환)
TRANSITION_PRESET = {
    "prompt": "subtle digital whoosh transition sound effect, clean, 1 second",
    "duration": 1.0,
    "label": "transition",
}

# 전환 효과음이 삽입될 섹션 범위 (시장 배경 ~ 결론 직전)
TRANSITION_SECTIONS = {"시장 배경", "핵심 데이터", "시나리오", "실행 가이드"}

ELEVENLABS_SFX_URL = "https://api.elevenlabs.io/v1/sound-generation"


class SfxWorker:
    """ElevenLabs Sound Generation API를 사용한 효과음 생성 워커"""

    def generate(self, job_id: int, sections: list[dict]) -> dict:
        """
        섹션 목록을 기반으로 효과음 MP3 파일을 생성한다.

        Args:
            job_id: 작업 고유 ID
            sections: 스크립트 섹션 리스트 (각 항목은 name, index 포함)

        Returns:
            생성된 SFX 파일 정보 딕셔너리
        """
        api_key = os.getenv("ELEVENLABS_API_KEY")
        if not api_key:
            logger.warning("ELEVENLABS_API_KEY 미설정 → SFX 생성 건너뜀")
            return {"job_id": job_id, "sfx_files": [], "count": 0}

        job_dir = Path(f"/app/data/jobs/{job_id}")
        job_dir.mkdir(parents=True, exist_ok=True)

        sfx_files: list[dict] = []

        for section in sections:
            section_name = section.get("name", "")
            section_index = section.get("index", 0)

            # 1) 섹션 고유 효과음 (인트로, 핵심 데이터, 결론)
            if section_name in SFX_PRESETS:
                preset = SFX_PRESETS[section_name]
                file_path = str(job_dir / f"sfx_{preset['label']}.mp3")

                result = self._call_sfx_api(
                    api_key=api_key,
                    prompt=preset["prompt"],
                    duration=preset["duration"],
                    output_path=file_path,
                )
                if result:
                    sfx_files.append({
                        "section": preset["label"],
                        "path": file_path,
                        "duration": preset["duration"],
                    })

            # 2) 섹션 간 전환 효과음
            if section_name in TRANSITION_SECTIONS:
                trans_path = str(job_dir / f"sfx_transition_{section_index}.mp3")

                result = self._call_sfx_api(
                    api_key=api_key,
                    prompt=TRANSITION_PRESET["prompt"],
                    duration=TRANSITION_PRESET["duration"],
                    output_path=trans_path,
                )
                if result:
                    sfx_files.append({
                        "section": f"transition_{section_index}",
                        "path": trans_path,
                        "duration": TRANSITION_PRESET["duration"],
                    })

        logger.info(f"SFX 생성 완료: job_id={job_id}, 총 {len(sfx_files)}개 파일")
        return {
            "job_id": job_id,
            "sfx_files": sfx_files,
            "count": len(sfx_files),
        }

    # ============================
    # ElevenLabs Sound Generation API 호출
    # ============================
    @staticmethod
    def _call_sfx_api(
        api_key: str,
        prompt: str,
        duration: float,
        output_path: str,
    ) -> bool:
        """
        ElevenLabs Sound Generation 엔드포인트를 호출하여 효과음을 생성한다.

        Args:
            api_key: ElevenLabs API 키
            prompt: 효과음 설명 텍스트
            duration: 생성할 효과음 길이 (초)
            output_path: 저장할 MP3 파일 경로

        Returns:
            성공 여부 (True/False)
        """
        headers = {
            "xi-api-key": api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "text": prompt,
            "duration_seconds": duration,
            "prompt_influence": 0.3,
        }

        try:
            resp = requests.post(
                ELEVENLABS_SFX_URL,
                json=payload,
                headers=headers,
                timeout=30,
            )
            if resp.status_code == 200:
                with open(output_path, "wb") as f:
                    f.write(resp.content)
                logger.info(f"SFX 저장 완료: {output_path} ({duration}초)")
                return True
            else:
                logger.error(
                    f"SFX API 오류: HTTP {resp.status_code} — {resp.text[:200]}"
                )
                return False
        except requests.exceptions.Timeout:
            logger.error(f"SFX API 타임아웃: prompt='{prompt[:40]}...'")
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"SFX API 요청 실패: {e}")
            return False
