"""
LoRA 캐릭터 파인튜닝 워커 (Sprint 3)

Fal.ai flux-lora-fast-training 을 사용해 채널 마스코트 캐릭터의 LoRA 모델을
학습시키고, 학습 완료 후 safetensors CDN URL을 반환합니다.

■ 워크플로우
  1. POST /workers/lora/train
     - ZIP 파일(캐릭터 이미지 묶음) 업로드 → FastAPI 로컬 임시 저장
     - fal_client.upload_file() 로 Fal.ai CDN에 업로드 → images_data_url 확보
     - fal_client.submit("fal-ai/flux-lora-fast-training", ...) → request_id 반환
  2. GET /workers/lora/status/{request_id}
     - fal_client.queue.status() 폴링
     - 완료 시 diffusers_lora_file.url(= safetensors URL) 반환

■ 검증된 Fal.ai 스펙 (2025-2026)
  - 학습 응답 키: result['diffusers_lora_file']['url']
  - 추론 파라미터: loras=[{"path": safetensors_url, "scale": 0.8~1.2}]
  - 학습 비용: ~$3-5 / 회 (캐릭터 변경 시에만 1회 실행 권장)
  - 학습 소요시간: 약 5~15분 (이미지 수/품질에 따라 상이)

■ 주의
  - FAL_KEY 환경변수 필수
  - 학습 이미지: 최소 10~20장, 다양한 각도/표정 권장
  - trigger_word: 한 단어, 알파벳+숫자만 (예: "mycoin", "goldcoin2025")
"""

import os
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class LoraTrainerWorker:
    """
    Fal.ai flux-lora-fast-training 연동 워커.
    채널 마스코트 캐릭터 이미지(ZIP)로 개인화 LoRA 모델을 학습합니다.
    """

    LORA_DATA_DIR = Path("/app/data/lora")

    def train(
        self,
        channel_id: str,
        zip_path: str,
        trigger_word: str = "mycoin",
        steps: int = 1000,
        is_style: bool = False,
    ) -> dict:
        """
        ZIP 파일을 Fal.ai CDN에 업로드하고 LoRA 학습을 시작합니다.

        Args:
            channel_id:   채널 고유 ID (저장 경로 분류용)
            zip_path:     로컬 ZIP 파일 절대 경로 (캐릭터 이미지 묶음)
            trigger_word: LoRA 활성화 트리거 단어 (영문/숫자만, 1단어)
            steps:        학습 스텝 수 (기본 1000, 이미지 수가 많으면 1500~2000 권장)
            is_style:     True면 스타일 LoRA, False면 캐릭터/주제 LoRA

        Returns:
            {
              "status": "queued",
              "request_id": "...",
              "channel_id": "...",
              "trigger_word": "...",
              "message": "..."
            }
        """
        fal_key = os.getenv("FAL_KEY") or os.getenv("FAL_API_KEY")
        if not fal_key:
            raise RuntimeError("FAL_KEY 환경변수가 설정되지 않았습니다.")

        if not zip_path or not Path(zip_path).exists():
            raise FileNotFoundError(f"학습 ZIP 파일 없음: {zip_path}")

        # trigger_word 유효성 검사 (영문+숫자만)
        import re
        if not re.match(r'^[a-zA-Z0-9_]+$', trigger_word):
            raise ValueError(
                f"trigger_word는 영문+숫자+언더스코어만 허용됩니다: '{trigger_word}'"
            )

        logger.info(
            f"[LoRA 학습] 시작: channel_id={channel_id}, "
            f"zip={zip_path}, trigger_word={trigger_word}, steps={steps}"
        )

        # 1. ZIP 파일을 Fal.ai CDN에 업로드
        try:
            import fal_client
            logger.info("[LoRA 학습] Fal.ai CDN에 ZIP 업로드 중...")
            images_data_url = fal_client.upload_file(zip_path)
            logger.info(f"[LoRA 학습] 업로드 완료: {images_data_url}")
        except Exception as e:
            raise RuntimeError(f"Fal.ai 파일 업로드 실패: {e}") from e

        # 2. 학습 작업 제출 (비동기 큐)
        try:
            handler = fal_client.submit(
                "fal-ai/flux-lora-fast-training",
                arguments={
                    "images_data_url": images_data_url,
                    "trigger_word": trigger_word,
                    "steps": steps,
                    "is_style": is_style,
                    # 캐릭터 LoRA: 얼굴/포즈 학습을 위해 아래 옵션 권장
                    "create_masks": not is_style,  # 주제 분리 마스크 생성
                },
            )
            request_id = handler.request_id
            logger.info(f"[LoRA 학습] 큐 등록 완료: request_id={request_id}")
        except Exception as e:
            raise RuntimeError(f"Fal.ai 학습 작업 제출 실패: {e}") from e

        # 3. 채널별 학습 메타데이터 저장 (상태 추적용)
        self._save_training_meta(channel_id, request_id, trigger_word)

        return {
            "status": "queued",
            "request_id": request_id,
            "channel_id": channel_id,
            "trigger_word": trigger_word,
            "message": (
                f"LoRA 학습이 시작되었습니다. "
                f"GET /workers/lora/status/{request_id} 로 진행 상황을 확인하세요. "
                f"학습 완료까지 약 5~15분 소요됩니다."
            ),
        }

    def get_status(self, request_id: str) -> dict:
        """
        LoRA 학습 작업의 현재 상태를 반환합니다.

        Returns:
            {
              "status": "IN_QUEUE" | "IN_PROGRESS" | "COMPLETED" | "FAILED",
              "lora_model_url": "https://..." (COMPLETED 시에만),
              "progress": 0.0~1.0 (가능한 경우),
              "request_id": "..."
            }
        """
        fal_key = os.getenv("FAL_KEY") or os.getenv("FAL_API_KEY")
        if not fal_key:
            raise RuntimeError("FAL_KEY 환경변수가 설정되지 않았습니다.")

        try:
            import fal_client
            # 큐 상태 조회
            status = fal_client.queue.status(
                "fal-ai/flux-lora-fast-training",
                request_id=request_id,
                with_logs=False,
            )

            status_str = getattr(status, "status", None) or str(status)
            logger.info(f"[LoRA 상태] request_id={request_id}, status={status_str}")

            # 상태가 COMPLETED인 경우 결과 URL 추출
            if "COMPLETED" in str(status_str).upper():
                result = fal_client.queue.result(
                    "fal-ai/flux-lora-fast-training",
                    request_id=request_id,
                )
                lora_url = self._extract_lora_url(result)
                logger.info(f"[LoRA 완료] safetensors URL: {lora_url}")
                return {
                    "status": "COMPLETED",
                    "lora_model_url": lora_url,
                    "request_id": request_id,
                    "message": (
                        f"학습이 완료되었습니다. "
                        f"이 URL을 채널 프로필의 loraModelId에 저장하세요: {lora_url}"
                    ),
                }

            # IN_QUEUE / IN_PROGRESS
            progress = getattr(status, "progress", None)
            return {
                "status": str(status_str),
                "lora_model_url": None,
                "request_id": request_id,
                "progress": float(progress) if progress is not None else None,
                "message": "학습이 진행 중입니다. 잠시 후 다시 확인해 주세요.",
            }

        except Exception as e:
            logger.error(f"[LoRA 상태 조회 실패] request_id={request_id}: {e}")
            return {
                "status": "ERROR",
                "lora_model_url": None,
                "request_id": request_id,
                "error": str(e),
            }

    # ──────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────

    @staticmethod
    def _extract_lora_url(result) -> str:
        """
        Fal.ai 학습 결과 객체에서 safetensors URL을 추출합니다.

        응답 구조 (검증된 2025-2026 스펙):
          result.diffusers_lora_file.url  ← 주요 경로
          result['diffusers_lora_file']['url']  ← dict 접근 시
          result.lora_file.url  ← 대안 경로 (일부 버전)
        """
        # 1) 속성 방식 접근
        for attr in ("diffusers_lora_file", "lora_file"):
            obj = getattr(result, attr, None)
            if obj:
                url = getattr(obj, "url", None)
                if url:
                    return url

        # 2) dict 방식 접근
        if isinstance(result, dict):
            for key in ("diffusers_lora_file", "lora_file"):
                obj = result.get(key)
                if obj and isinstance(obj, dict):
                    url = obj.get("url")
                    if url:
                        return url

        # 3) 전체 결과에서 URL 패턴 검색 (폴백)
        result_str = str(result)
        import re
        urls = re.findall(r'https?://[^\s\'"]+\.safetensors[^\s\'"]*', result_str)
        if urls:
            logger.warning(f"[LoRA URL 추출] 폴백 패턴 매칭으로 URL 추출: {urls[0]}")
            return urls[0]

        raise RuntimeError(
            f"학습 결과에서 safetensors URL을 찾을 수 없습니다. "
            f"원본 결과 확인 필요: {result}"
        )

    def _save_training_meta(self, channel_id: str, request_id: str, trigger_word: str):
        """채널별 학습 메타 정보를 JSON으로 저장합니다."""
        import json
        self.LORA_DATA_DIR.mkdir(parents=True, exist_ok=True)
        meta_path = self.LORA_DATA_DIR / f"{channel_id}_training.json"
        meta = {
            "channel_id": channel_id,
            "request_id": request_id,
            "trigger_word": trigger_word,
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        logger.info(f"[LoRA] 학습 메타데이터 저장: {meta_path}")

    def get_channel_training_meta(self, channel_id: str) -> dict:
        """저장된 채널 학습 메타 정보 조회"""
        import json
        meta_path = self.LORA_DATA_DIR / f"{channel_id}_training.json"
        if not meta_path.exists():
            return {}
        with open(meta_path, encoding="utf-8") as f:
            return json.load(f)
