"""
BGM 배경음악 생성 워커 — ElevenLabs Music Generation API

카테고리별 맞춤 배경음악 자동 생성:
  - KOSPI/KOSDAQ: 한국 금융 뉴스 스타일 (피아노 + 전자음)
  - US_STOCKS: 미국 주식 분석 스타일 (피아노 + 현악기)
  - GLOBAL_MACRO: 글로벌 경제 다큐멘터리 스타일 (오케스트라)
  - CRYPTO: 암호화폐 분석 스타일 (전자음 + 사이버펑크)
  - CUSTOM/기본: 금융 뉴스 중립 스타일

API 비용: 오디오 1분당 900 크레딧
스트리밍 응답을 청크 단위로 저장하여 메모리 효율 확보
"""
import os
import logging
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

# 카테고리별 BGM 프롬프트 매핑
BGM_PROMPTS: dict[str, str] = {
    "KOSPI": (
        "Korean financial news background music, professional and calm, stable melody, "
        "subtle electronic beats with piano, steady tempo, "
        "broadcast quality, instrumental only"
    ),
    "KOSDAQ": (
        "Korean financial news background music, professional and calm, stable melody, "
        "subtle electronic beats with piano, steady tempo, "
        "broadcast quality, instrumental only"
    ),
    "US_STOCKS": (
        "American stock market analysis background music, "
        "modern corporate ambient, calm piano with subtle strings, "
        "confident tone, instrumental only"
    ),
    "GLOBAL_MACRO": (
        "Global economics documentary background music, "
        "dramatic orchestral, slow cinematic build, "
        "serious analytical mood, instrumental only"
    ),
    "CRYPTO": (
        "Cryptocurrency market analysis music, "
        "futuristic electronic ambient, minimal digital beats, "
        "cyberpunk atmosphere, instrumental only"
    ),
}

# 위 매핑에 없는 카테고리(CUSTOM 포함)에 사용할 기본 프롬프트
DEFAULT_PROMPT = (
    "Professional financial news broadcast background music, "
    "neutral analytical tone, subtle and non-distracting, "
    "instrumental only"
)

ELEVENLABS_MUSIC_URL = "https://api.elevenlabs.io/v1/music/generate"

# 스트리밍 청크 크기 (8 KB)
STREAM_CHUNK_SIZE = 8192


class BgmWorker:
    """ElevenLabs Music Generation API를 사용한 배경음악 생성 워커"""

    def generate(
        self,
        job_id: int,
        category: str,
        duration_seconds: int = 60,
    ) -> dict:
        """
        영상 카테고리에 맞는 배경음악 MP3를 생성한다.

        Args:
            job_id: 작업 고유 ID
            category: 영상 카테고리 (KOSPI, US_STOCKS, GLOBAL_MACRO, CRYPTO, CUSTOM)
            duration_seconds: 배경음악 길이 (초, 기본 60초)

        Returns:
            생성된 BGM 파일 정보 딕셔너리
        """
        api_key = os.getenv("ELEVENLABS_API_KEY")
        if not api_key:
            logger.warning("ELEVENLABS_API_KEY 미설정 → BGM 생성 건너뜀")
            return {
                "job_id": job_id,
                "bgm_path": "",
                "duration_seconds": 0,
                "category": category,
            }

        job_dir = Path(f"/app/data/jobs/{job_id}")
        job_dir.mkdir(parents=True, exist_ok=True)
        bgm_path = str(job_dir / "bgm.mp3")

        # 카테고리에 해당하는 프롬프트 선택
        prompt = BGM_PROMPTS.get(category.upper(), DEFAULT_PROMPT)
        logger.info(
            f"BGM 생성 시작: job_id={job_id}, category={category}, "
            f"duration={duration_seconds}초"
        )

        success = self._call_music_api(
            api_key=api_key,
            prompt=prompt,
            duration_seconds=duration_seconds,
            output_path=bgm_path,
        )

        if success:
            logger.info(f"BGM 생성 완료: {bgm_path}")
            return {
                "job_id": job_id,
                "bgm_path": bgm_path,
                "duration_seconds": duration_seconds,
                "category": category,
            }
        else:
            logger.error(f"BGM 생성 실패: job_id={job_id}, category={category}")
            return {
                "job_id": job_id,
                "bgm_path": "",
                "duration_seconds": 0,
                "category": category,
            }

    # ============================
    # ElevenLabs Music Generation API 호출
    # ============================
    @staticmethod
    def _call_music_api(
        api_key: str,
        prompt: str,
        duration_seconds: int,
        output_path: str,
    ) -> bool:
        """
        ElevenLabs Music Generation 엔드포인트를 호출하여 BGM을 생성한다.
        스트리밍 응답을 청크 단위로 파일에 기록하여 대용량 오디오도 안정적으로 저장한다.

        Args:
            api_key: ElevenLabs API 키
            prompt: 음악 스타일 설명 텍스트
            duration_seconds: 생성할 음악 길이 (초)
            output_path: 저장할 MP3 파일 경로

        Returns:
            성공 여부 (True/False)
        """
        headers = {
            "xi-api-key": api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "prompt": prompt,
            "music_length_ms": duration_seconds * 1000,
            "force_instrumental": True,
        }

        try:
            # 스트리밍 모드로 요청 (대용량 오디오 대응)
            resp = requests.post(
                ELEVENLABS_MUSIC_URL,
                json=payload,
                headers=headers,
                timeout=120,
                stream=True,
            )

            if resp.status_code == 200:
                bytes_written = 0
                with open(output_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=STREAM_CHUNK_SIZE):
                        if chunk:
                            f.write(chunk)
                            bytes_written += len(chunk)

                logger.info(
                    f"BGM 저장 완료: {output_path} "
                    f"({bytes_written / 1024:.1f} KB, {duration_seconds}초)"
                )
                return True
            else:
                logger.error(
                    f"BGM API 오류: HTTP {resp.status_code} — {resp.text[:200]}"
                )
                return False
        except requests.exceptions.Timeout:
            logger.error(
                f"BGM API 타임아웃: duration={duration_seconds}초 요청 초과"
            )
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"BGM API 요청 실패: {e}")
            return False
