"""
캐릭터 포즈 라이브러리 워커 (S2-2)

역할:
  - 채널별 마스코트 캐릭터의 포즈/감정별 이미지를 배치 생성
  - 배경 제거(rembg) 후 투명 PNG 형태로 /app/data/characters/<channel_id>/poses/ 에 저장
  - 이후 images_worker.py에서 배경 이미지 위에 FFmpeg overlay 합성

지원 포즈:
  neutral, happy, surprised, worried, thinking, explaining, pointing

사용법:
  POST /workers/character-library/generate
  {
    "channel_id": "finance_hunter",
    "character_description": "cute gold coin mascot, chibi cartoon, ...",
    "regenerate": false
  }
"""
import os
import logging
import json
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# 지원 포즈 목록 및 각 포즈별 프롬프트 접미사
POSE_CONFIGS = {
    "neutral": {
        "desc": "standing upright, calm expression, arms relaxed at sides, professional analyst pose",
        "ko": "기본 중립 포즈, 차분한 표정"
    },
    "happy": {
        "desc": "cheering with both arms raised, big smile, eyes sparkling, celebrating good news",
        "ko": "양팔을 들고 기뻐하는 포즈, 활짝 웃는 표정"
    },
    "surprised": {
        "desc": "wide eyes, mouth open in surprise, both hands on cheeks, shocked expression",
        "ko": "놀란 표정, 양손으로 볼을 감싸는 포즈"
    },
    "worried": {
        "desc": "furrowed brow, one hand on chin thinking, slight frown, concerned look",
        "ko": "걱정스러운 표정, 턱에 손을 얹고 고민하는 포즈"
    },
    "thinking": {
        "desc": "head tilted, finger pointing to temple, thoughtful expression, curious look",
        "ko": "고개를 기울이고 관자놀이에 손가락을 대는 생각하는 포즈"
    },
    "explaining": {
        "desc": "one arm extended forward, palm open, confident expression, presenting gesture",
        "ko": "한 팔을 뻗어 설명하는 포즈, 자신감 있는 표정"
    },
    "pointing": {
        "desc": "index finger pointing to the right side, direct gaze, assertive confident expression",
        "ko": "오른쪽을 손가락으로 가리키는 포즈, 단호한 표정"
    },
}

# 캐릭터 이미지 기본 크기 (합성 시 영상 대비 비율로 조정됨)
POSE_CONFIGS.update({
    "engineer": {
        "desc": "wearing a yellow safety helmet and industrial workwear, holding a small chip and wrench, focused expression",
        "ko": "factory engineer pose",
    },
    "scientist": {
        "desc": "wearing a clean white lab coat and smart goggles, holding a glowing chip sample, curious expression",
        "ko": "research scientist pose",
    },
    "analyst": {
        "desc": "wearing a clean broadcaster jacket, holding a report folder, confident editorial analyst expression",
        "ko": "editorial analyst pose",
    },
    "teacher": {
        "desc": "wearing a warm teacher cardigan, holding a pointer and notebook, explaining expression",
        "ko": "teacher explanation pose",
    },
    "explorer": {
        "desc": "wearing a field explorer vest and utility cap, holding a magnifying glass, curious expression",
        "ko": "field explorer pose",
    },
    "hero_business": {
        "desc": "wearing a tailored navy business suit with a gold accent, standing proudly with one hand raised",
        "ko": "business hero pose",
    },
})

CHAR_WIDTH = 480
CHAR_HEIGHT = 854  # 9:16 비율 (세로형 캐릭터)


class CharacterLibraryWorker:
    """
    채널별 캐릭터 포즈 라이브러리를 생성·관리합니다.
    """

    POSES_BASE_DIR = Path("/app/data/characters")

    @staticmethod
    def _safe_channel_id(channel_id: str) -> str:
        """Keep a user supplied channel id inside the character asset root."""
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,50}", channel_id or ""):
            raise ValueError("channel_id must use letters, numbers, underscores, or hyphens")
        return channel_id

    def generate_library(
        self,
        channel_id: str,
        character_description: str,
        regenerate: bool = False,
    ) -> dict:
        """
        채널 ID에 해당하는 포즈 라이브러리 전체를 생성(또는 재생성)합니다.

        Returns:
            {
              "channel_id": ...,
              "poses_dir": ...,
              "generated": [...],
              "skipped": [...],
              "errors": [...]
            }
        """
        channel_id = self._safe_channel_id(channel_id)
        poses_dir = self.POSES_BASE_DIR / channel_id / "poses"
        poses_dir.mkdir(parents=True, exist_ok=True)

        results = {
            "channel_id": channel_id,
            "poses_dir": str(poses_dir),
            "generated": [],
            "skipped": [],
            "errors": [],
        }

        # AI 이미지 프로바이더 로드
        ai_provider = None
        try:
            from app.providers.factory import get_image_provider
            ai_provider = get_image_provider()
            logger.info("캐릭터 라이브러리 생성: AI 프로바이더 로드 성공")
        except Exception as e:
            logger.error(f"AI 프로바이더 로드 실패: {e}")
            results["errors"].append(f"AI 프로바이더 로드 실패: {e}")
            return results

        for pose_name, pose_config in POSE_CONFIGS.items():
            raw_path = poses_dir / f"{pose_name}_raw.png"
            final_path = poses_dir / f"{pose_name}.png"

            # 이미 존재하고 재생성 요청이 없으면 스킵
            if final_path.exists() and not regenerate:
                logger.info(f"포즈 '{pose_name}' 이미 존재함, 스킵")
                results["skipped"].append(pose_name)
                continue

            # 1. 캐릭터 포즈 이미지 생성 (배경 있는 버전)
            prompt = self._build_character_prompt(character_description, pose_config["desc"])
            logger.info(f"포즈 '{pose_name}' 생성 중... prompt_len={len(prompt)}")

            try:
                ai_provider.generate_image(
                    prompt=prompt,
                    output_path=str(raw_path),
                    character_style_prompt="none",  # 프로바이더의 CHARACTER_STYLE 중복 주입 방지
                    image_provider="gemini",
                    gemini_model="gemini-3-pro-image",
                    gemini_image_size="2K",
                )
            except Exception as e:
                logger.error(f"포즈 '{pose_name}' 이미지 생성 실패: {e}")
                results["errors"].append(f"{pose_name}: 이미지 생성 실패 - {e}")
                continue

            # 2. 배경 제거 (rembg)
            try:
                removed_path = self._remove_background(raw_path, final_path)
                logger.info(f"포즈 '{pose_name}' 배경 제거 완료: {removed_path}")
                results["generated"].append({
                    "pose": pose_name,
                    "path": str(final_path),
                    "ko": pose_config["ko"],
                })
            except Exception as e:
                logger.warning(f"포즈 '{pose_name}' 배경 제거 실패, raw 이미지 사용: {e}")
                # 배경 제거 실패 시 raw 이미지를 final로 복사
                import shutil
                shutil.copy2(str(raw_path), str(final_path))
                results["generated"].append({
                    "pose": pose_name,
                    "path": str(final_path),
                    "ko": pose_config["ko"],
                    "note": "배경 제거 미적용",
                })

        # 라이브러리 메타데이터 저장
        meta_path = poses_dir / "library_meta.json"
        meta = {
            "channel_id": channel_id,
            "character_description": character_description,
            "poses": {
                p["pose"]: {"path": p["path"], "ko": p["ko"]}
                for p in results["generated"]
            },
        }
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        logger.info(
            f"캐릭터 라이브러리 생성 완료: channel={channel_id}, "
            f"생성={len(results['generated'])}, 스킵={len(results['skipped'])}, 오류={len(results['errors'])}"
        )
        return results

    def get_pose_path(self, channel_id: str, pose: str) -> str | None:
        """
        채널 ID와 포즈명으로 해당 캐릭터 투명 PNG 경로를 반환합니다.
        포즈가 없을 경우 'neutral'로 폴백하고, neutral도 없으면 None 반환.
        """
        channel_id = self._safe_channel_id(channel_id)
        poses_dir = self.POSES_BASE_DIR / channel_id / "poses"

        # 요청한 포즈 확인
        target = poses_dir / f"{pose}.png"
        if target.exists():
            return str(target)

        # neutral 폴백
        neutral = poses_dir / "neutral.png"
        if neutral.exists():
            logger.warning(f"포즈 '{pose}' 없음, neutral 폴백")
            return str(neutral)

        logger.warning(f"채널 '{channel_id}'의 캐릭터 라이브러리가 없음 (포즈: {pose})")
        return None

    def list_channels(self) -> list:
        """생성된 모든 채널 라이브러리 목록 반환"""
        if not self.POSES_BASE_DIR.exists():
            return []
        return [
            d.name
            for d in self.POSES_BASE_DIR.iterdir()
            if d.is_dir() and (d / "poses" / "library_meta.json").exists()
        ]

    def get_library_status(self, channel_id: str) -> dict:
        """Return usable pose metadata without exposing container file paths."""
        channel_id = self._safe_channel_id(channel_id)
        poses_dir = self.POSES_BASE_DIR / channel_id / "poses"
        meta_path = poses_dir / "library_meta.json"
        if not meta_path.exists():
            return {"channel_id": channel_id, "exists": False, "poses": [], "pose_count": 0}

        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            meta = {}

        poses = []
        for pose_name, pose_config in POSE_CONFIGS.items():
            if (poses_dir / f"{pose_name}.png").exists():
                poses.append({"pose": pose_name, "label": pose_config["ko"]})

        return {
            "channel_id": channel_id,
            "exists": bool(poses),
            "poses": poses,
            "pose_count": len(poses),
            "character_description": meta.get("character_description", ""),
        }

    @staticmethod
    def _build_character_prompt(character_description: str, pose_desc: str) -> str:
        """
        캐릭터 설명 + 포즈 설명을 조합하여 이미지 생성 프롬프트 구성.
        배경 제거(rembg)가 효과적으로 작동하도록 단색 배경 지정.
        """
        base = character_description.strip().rstrip(",")
        return (
            f"{base}, {pose_desc}, "
            "full body view, character centered, "
            "isolated on solid white background, "
            "no props no scenery no text, "
            "high detail, clean edges, 4K quality"
        )

    @staticmethod
    def _remove_background(input_path: Path, output_path: Path) -> str:
        """
        rembg를 사용해 배경 제거 후 투명 PNG로 저장.
        rembg가 설치되지 않은 경우 fallback으로 PIL 기반 흰색 배경 제거.
        """
        try:
            from rembg import remove
            from PIL import Image
            import io

            with open(input_path, "rb") as f:
                input_data = f.read()

            output_data = remove(input_data)
            img = Image.open(io.BytesIO(output_data)).convert("RGBA")
            img.save(str(output_path), "PNG")
            return str(output_path)

        except ImportError:
            logger.warning("rembg 미설치 — PIL 흰색 배경 제거 폴백 사용")
            return CharacterLibraryWorker._remove_white_background_fallback(input_path, output_path)

    @staticmethod
    def _remove_white_background_fallback(input_path: Path, output_path: Path) -> str:
        """
        PIL 기반 흰색 배경 단순 제거 (rembg 미설치 시 폴백).
        흰색 또는 밝은 회색 픽셀을 투명 처리.
        """
        from PIL import Image
        import numpy as np

        img = Image.open(str(input_path)).convert("RGBA")
        data = np.array(img)

        r, g, b, a = data[:, :, 0], data[:, :, 1], data[:, :, 2], data[:, :, 3]
        # 흰색에 가까운 픽셀 (RGB 모두 220 이상) → 투명 처리
        white_mask = (r > 220) & (g > 220) & (b > 220)
        data[white_mask, 3] = 0

        result = Image.fromarray(data, "RGBA")
        result.save(str(output_path), "PNG")
        return str(output_path)
