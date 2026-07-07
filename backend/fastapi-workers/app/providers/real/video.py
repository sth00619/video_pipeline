"""
Kling AI Video Provider — Official Kling 3.0 API + FFmpeg fallback

1. 공식 API 연동 (Kling 3.0):
   - KLING_ACCESS_KEY / KLING_SECRET_KEY (또는 KLING_API_KEY) 설정 시 공식 API 호출
   - 오프닝(8초) 및 씬 전환(5초) 고품질 AI 모션 영상 클립 생성
   
2. 무료 폴백 엔진:
   - API 키 미설정 시 정적 PNG를 5초짜리 MP4 모션 클립(줌인 효과)으로 변환하는 FFmpeg 폴백 사용 ($0)
"""
import os
import time
import logging
import requests
import tempfile
from pathlib import Path

from app.providers.base import VideoProvider, GeneratedAsset

logger = logging.getLogger(__name__)


class KlingProvider(VideoProvider):
    """
    Kling 3.0 (Official API) 및 FFmpeg 기반 비디오 클립 생성 프로바이더.
    """

    def __init__(self):
        self.api_url = "https://api.klingai.com/v1/videos/text2video"

    def generate(self, prompt: str, duration: int = 5, **kwargs) -> GeneratedAsset:
        """
        텍스트 프롬프트 또는 이미지를 기반으로 5~8초 길이의 비디오 클립 생성.
        """
        output_path = kwargs.get("output_path")
        if not output_path:
            output_path = tempfile.mktemp(suffix=".mp4")
            
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Kling 비디오 클립 생성 요청: duration={duration}s, prompt_len={len(prompt)}")

        # 1. 공식 Kling 3.0 API 시도
        api_key = os.getenv("KLING_API_KEY") or os.getenv("KLING_ACCESS_KEY")
        if api_key:
            try:
                if self._generate_kling_api(prompt, output_path, duration, api_key):
                    logger.info(f"공식 Kling 3.0 API 비디오 생성 성공: {output_path}")
                    return GeneratedAsset(asset_type="video", local_path=output_path, duration=duration)
            except Exception as e:
                logger.warning(f"Kling API 호출 실패, FFmpeg 모션 폴백: {e}")

        # 2. FFmpeg 줌인 모션 폴백
        image_path = kwargs.get("image_path")
        self._generate_ffmpeg_fallback(output_path, duration, image_path)
        return GeneratedAsset(asset_type="video", local_path=output_path, duration=duration)

    def _generate_kling_api(self, prompt: str, output_path: str, duration: int, api_key: str) -> bool:
        """
        Kling AI v1/videos/text2video API 호출 (비동기 폴링).
        """
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model_name": "kling-v3",
            "prompt": prompt,
            "duration": str(duration),
            "aspect_ratio": "16:9"
        }
        
        # 1. 생성 요청 (Task 생성)
        resp = requests.post(self.api_url, json=payload, headers=headers, timeout=30)
        if resp.status_code != 200:
            logger.warning(f"Kling API 요청 실패: {resp.status_code} {resp.text}")
            return False
            
        task_id = resp.json().get("data", {}).get("task_id")
        if not task_id:
            return False
            
        # 2. 상태 폴링 (최대 120초 대기)
        poll_url = f"https://api.klingai.com/v1/videos/text2video/{task_id}"
        for _ in range(24):
            time.sleep(5)
            poll_resp = requests.get(poll_url, headers=headers, timeout=30)
            if poll_resp.status_code == 200:
                data = poll_resp.json().get("data", {})
                status = data.get("task_status")
                if status == "succeed":
                    video_url = data.get("task_result", {}).get("videos", [{}])[0].get("url")
                    if video_url:
                        video_bytes = requests.get(video_url, timeout=60).content
                        with open(output_path, "wb") as f:
                            f.write(video_bytes)
                        return True
                elif status == "failed":
                    logger.warning(f"Kling 생성 Task 실패: {data}")
                    return False
        return False

    def _generate_ffmpeg_fallback(self, output_path: str, duration: int, image_path: str = None):
        """
        이미지(또는 검정 배경)를 FFmpeg의 zoompan 필터로 부드러운 줌인 영상으로 변환.
        """
        if image_path and os.path.exists(image_path):
            # 씬 이미지에 부드러운 줌인 효과 적용하여 동영상 클립화
            cmd = (
                f'ffmpeg -loop 1 -i "{image_path}" -f lavfi -i anullsrc=r=44100:cl=stereo '
                f'-filter_complex "zoompan=z=\'min(zoom+0.0015,1.15)\':d={duration*30}:s=1920x1080" '
                f'-t {duration} -c:v libx264 -pix_fmt yuv420p -c:a aac -b:a 128k '
                f'-y "{output_path}" -loglevel error'
            )
        else:
            # 기본 검정 배경 모션
            cmd = (
                f'ffmpeg -f lavfi -i color=c=#0d1b2a:s=1920x1080:d={duration} '
                f'-f lavfi -i anullsrc=r=44100:cl=stereo '
                f'-t {duration} -c:v libx264 -c:a aac "{output_path}" -y -loglevel quiet'
            )
        os.system(cmd)
        logger.info(f"FFmpeg 모션 클립 폴백 생성 완료: {output_path}")
