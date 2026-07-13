"""
Nana Banana AI Image Provider — Fal.ai Flux + Gemini API + pollinations.ai fallback

■ 우선순위 (Sprint 3 업데이트)
  1. Fal.ai Flux (채널에 LoRA 모델 있을 시): fal-ai/flux-lora — 캐릭터 일관성 최강
  2. Fal.ai Flux (LoRA 없을 시): fal-ai/flux/schnell — 기본 고품질 생성
  3. Gemini API: gemini-3.1-flash-image — 무료 Tier 활용
  4. pollinations.ai: 무료 무인증 폴백 ($0)

■ 배경 전용 모드 (S2-1):
   - character_style_prompt="background_only" 전달 시 캐릭터 묘사 미주입
   - 캐릭터 라이브러리 overlay 합성용 순수 배경 생성

■ LoRA 캐릭터 일관성 (Sprint 3):
   - lora_model_id (safetensors CDN URL) 지정 시 fal-ai/flux-lora 엔드포인트 사용
   - loras=[{"path": lora_model_id, "scale": lora_scale}] 파라미터로 전달
   - 프롬프트 앞에 trigger_word 자동 삽입

■ Fal.ai 서킷 브레이커:
   - 계정 잠김/잔액 부족(403) 감지 시 즉시 Gemini로 폴백
   - 이후 모든 요청은 Gemini/Pollinations로 직행

v3.0 변경사항 (Sprint 3 LoRA 통합):
   [신규] fal-ai/flux-lora LoRA 추론 지원 — lora_model_id 파라미터
   [수정] Gemini 모델명 → gemini-3.1-flash-image (2026 라이브 API 확인 완료)
   [유지] background_only 모드, Fal.ai 서킷 브레이커
"""
import os
import json
import base64
import logging
import urllib.parse
import urllib.request
from pathlib import Path

from app.providers.base import ImageProvider

logger = logging.getLogger(__name__)

# 캐릭터 일관성 유지 프롬프트 (의인화된 금색 코인 마스코트 캐릭터)
CHARACTER_STYLE = (
    "featuring a cute gold coin mascot character, chibi cartoon style, round shiny gold coin with face, arms and legs, "
    "wearing small navy business suit with gold tie, "
)

# 금융 테마 프롬프트 스타일 수식어
FINANCE_STYLE = (
    "professional 3D render, vibrant colors, clean illustration, dark navy blue background (#0d1b2a), "
    "smooth shading, high-quality, cinematic lighting, no text, no letters, no words, no watermark, no UI elements"
)

# [S2-1] 배경 전용 모드 스타일 수식어 (캐릭터 없는 순수 배경용)
# 캐릭터 라이브러리 포즈 이미지와 FFmpeg overlay 합성될 배경 생성에 사용
BACKGROUND_ONLY_STYLE = (
    "no people, no characters, no mascots, no figures, "
    "cinematic wide establishing shot, "
    "professional financial broadcast background, "
    "dark navy blue gradient (#0d1b2a to #16213e), "
    "depth of field, ambient glow, ultra detailed, 8K quality, "
    "no text, no letters, no words, no watermark, no UI elements"
)

# [S2-1] 배경 전용 모드 트리거 키워드
BACKGROUND_ONLY_TRIGGER = "background_only"


class NanaBananaProvider(ImageProvider):
    """
    Nano Banana Pro (Google Gemini API) 및 pollinations.ai 기반 이미지 생성 프로바이더.
    """
    _gemini_disabled = False
    # [신규] Fal.ai 계정 잠김/잔액 부족 감지 시 켜지는 서킷 브레이커.
    # 기존에는 매 씬마다 Fal.ai를 먼저 시도했다가 403(잔액 부족)을 받고서야
    # Gemini/Pollinations로 넘어갔는데, 잔액 부족은 그 Job이 끝날 때까지
    # (혹은 사람이 충전할 때까지) 절대 저절로 풀리지 않는 상태이므로, 매번
    # 다시 시도하는 건 순전히 시간 낭비였습니다. 한 번 감지되면 이후 요청은
    # Fal.ai를 건너뛰고 바로 Gemini/Pollinations로 갑니다.
    _fal_disabled = False

    def __init__(self):
        self.fallback_url = "https://image.pollinations.ai/prompt"
        self.width = 1920
        self.height = 1080

    def generate_image(self, prompt: str, output_path: str, **kwargs) -> str:
        """images_worker.py에서 호출하는 메서드 별칭"""
        return self.generate(prompt=prompt, output_path=output_path, **kwargs)

    def generate_with_lora(self, prompt: str, output_path: str,
                           lora_model_id: str, trigger_word: str = "",
                           lora_scale: float = 1.0, **kwargs) -> str:
        """[Sprint 3] LoRA 모델을 명시적으로 지정하여 이미지 생성"""
        return self.generate(
            prompt=prompt,
            output_path=output_path,
            lora_model_id=lora_model_id,
            lora_trigger_word=trigger_word,
            lora_scale=lora_scale,
            **kwargs
        )

    def generate(self, prompt: str, output_path: str, **kwargs) -> str:
        """
        프롬프트를 기반으로 AI 이미지를 생성하여 output_path에 저장.

        [Sprint 3] LoRA 파라미터:
          - lora_model_id: safetensors CDN URL (fal-ai/flux-lora 사용)
          - lora_trigger_word: LoRA 활성화 트리거 단어 (프롬프트 앞에 자동 삽입)
          - lora_scale: LoRA 적용 강도 (0.8~1.2, 기본 1.0)

        [S2-1] character_style_prompt="background_only" 전달 시:
          - 캐릭터 묘사 일절 미주입
          - BACKGROUND_ONLY_STYLE 수식어만 추가
          - 캐릭터 라이브러리 overlay 합성에 사용되는 순수 배경 이미지 생성
        """
        char_style = kwargs.get("character_style_prompt", "")
        is_background_only = (char_style == BACKGROUND_ONLY_TRIGGER)

        # [Sprint 3] LoRA 파라미터 추출
        lora_model_id = kwargs.get("lora_model_id")
        lora_trigger_word = kwargs.get("lora_trigger_word", "")
        lora_scale = float(kwargs.get("lora_scale", 1.0))

        # [S2-1] 배경 전용 모드
        if is_background_only:
            is_english = all(ord(c) < 128 for c in prompt.replace(" ", "").replace(",", "").replace(".", ""))
            if not is_english or len(prompt) < 20:
                section = kwargs.get("section", "financial")
                keyword = kwargs.get("keyword", "stock market")
                base_prompt = f"Financial news background scene for {keyword}, {section} theme. " + BACKGROUND_ONLY_STYLE
            else:
                base_prompt = prompt + ", " + BACKGROUND_ONLY_STYLE
            logger.info(f"[배경전용] 이미지 생성 요청: prompt_len={len(base_prompt)}")

        # 기존 캐릭터 포함 모드
        else:
            # LoRA 모델이 있으면 CHARACTER_STYLE 프롬프트 주입 불필요
            # (LoRA 자체가 캐릭터 외형 정보를 보유)
            if lora_model_id:
                char_prompt = ""  # LoRA가 캐릭터를 담당
            elif char_style == "none" or char_style == "disable":
                char_prompt = ""
            elif char_style:
                char_prompt = char_style
            else:
                char_prompt = CHARACTER_STYLE

            is_english = all(ord(c) < 128 for c in prompt.replace(" ", "").replace(",", "").replace(".", ""))
            if not is_english or len(prompt) < 30:
                section = kwargs.get("section", "default")
                keyword = kwargs.get("keyword", "stock market KOSPI")
                base_prompt = f"A scene representing {keyword} and {section}. " + char_prompt + FINANCE_STYLE
            else:
                base_prompt = prompt
                if char_prompt and "banknote" not in base_prompt.lower() and "coin" not in base_prompt.lower():
                    base_prompt = char_prompt + base_prompt
                if "vector" not in base_prompt.lower() and "cartoon" not in base_prompt.lower():
                    base_prompt = base_prompt + ", " + FINANCE_STYLE

            # [Sprint 3] LoRA trigger_word 프롬프트 앞에 삽입
            if lora_model_id and lora_trigger_word:
                base_prompt = f"{lora_trigger_word}, " + base_prompt
                logger.info(f"[LoRA] trigger_word='{lora_trigger_word}' 프롬프트에 삽입")

            logger.info(f"NanaBanana 이미지 생성 요청: prompt_len={len(base_prompt)}, lora={bool(lora_model_id)}")

        # 디렉토리 생성
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # 1. Fal.ai (최우선, 서킷 브레이커 열려있지 않은 경우만)
        fal_key = os.getenv("FAL_KEY") or os.getenv("FAL_API_KEY")
        if fal_key and not self.__class__._fal_disabled:
            try:
                # [Sprint 3] LoRA 모델 지정 시 flux-lora 엔드포인트 사용
                if lora_model_id:
                    if self._generate_fal_flux_lora(
                        base_prompt, output_path, fal_key,
                        lora_model_id, lora_scale
                    ):
                        logger.info(f"Fal.ai Flux-LoRA 이미지 생성 성공: {output_path}")
                        return output_path
                else:
                    if self._generate_fal_flux(base_prompt, output_path, fal_key):
                        logger.info(f"Fal.ai Flux 이미지 생성 성공: {output_path}")
                        return output_path
            except Exception as e:
                logger.warning(f"Fal.ai 이미지 생성 실패, Gemini 시도: {e}")
        elif fal_key and self.__class__._fal_disabled:
            logger.debug("Fal.ai 서킷 브레이커 열림 상태 — Gemini로 바로 진행")

        # 2. 공식 Gemini API 시도
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if api_key and not self.__class__._gemini_disabled:
            try:
                character_image_path = kwargs.get("character_image_path")
                if self._generate_gemini_api(base_prompt, output_path, api_key, character_image_path):
                    logger.info(f"공식 Gemini API 이미지 생성 성공: {output_path}")
                    return output_path
            except Exception as e:
                logger.warning(f"공식 Gemini API 호출 실패, 무료 프록시로 폴백: {e}")

        # 3. 무료 pollinations.ai 프록시 폴백
        return self._generate_pollinations(base_prompt, output_path)

    def _generate_fal_flux_lora(self, prompt: str, output_path: str,
                                fal_key: str, lora_model_id: str,
                                lora_scale: float = 1.0) -> bool:
        """
        [Sprint 3] Fal.ai flux-lora 엔드포인트로 LoRA 적용 이미지 생성.

        검증된 파라미터 (2025-2026 스펙):
          - model: "fal-ai/flux-lora"
          - loras: [{"path": safetensors_url, "scale": 0.8~1.2}]
          - prompt: trigger_word가 앞에 삽입된 완성 프롬프트
        """
        import requests
        model_id = "fal-ai/flux-lora"
        submit_url = f"https://queue.fal.run/{model_id}"
        headers = {
            "Authorization": f"Key {fal_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "prompt": prompt,
            "image_size": "landscape_16_9",
            "num_inference_steps": 28,  # flux-lora 권장값
            "guidance_scale": 3.5,
            "loras": [
                {
                    "path": lora_model_id,
                    "scale": lora_scale,
                }
            ],
            "sync_mode": True,
        }

        logger.info(
            f"[LoRA 추론] fal-ai/flux-lora 요청: "
            f"lora_scale={lora_scale}, prompt_len={len(prompt)}"
        )
        try:
            resp = requests.post(submit_url, json=payload, headers=headers, timeout=60)

            if resp.status_code == 403:
                logger.error(f"Fal.ai 계정 잠김/잔액 부족 (403): {resp.text[:200]}")
                self.__class__._fal_disabled = True
                return False

            if resp.status_code == 200:
                resp_json = resp.json()
                images = resp_json.get("images", [])
                if images:
                    img_url = images[0].get("url")
                    if img_url:
                        img_bytes = requests.get(img_url, timeout=30).content
                        with open(output_path, "wb") as f:
                            f.write(img_bytes)
                        logger.info(f"[LoRA 추론] 이미지 생성 완료: {output_path}")
                        return True

            # 비동기 폴백
            payload["sync_mode"] = False
            resp = requests.post(submit_url, json=payload, headers=headers, timeout=30)
            if resp.status_code == 403:
                self.__class__._fal_disabled = True
                return False
            if resp.status_code != 200:
                logger.warning(f"flux-lora 제출 실패 ({resp.status_code}): {resp.text[:200]}")
                return False

            resp_json = resp.json()
            request_id = resp_json.get("request_id")
            if not request_id:
                return False

            import time
            status_url = f"https://queue.fal.run/{model_id}/requests/{request_id}/status"
            result_url = f"https://queue.fal.run/{model_id}/requests/{request_id}"
            for _ in range(20):
                time.sleep(2)
                st = requests.get(status_url, headers=headers, timeout=15)
                if st.status_code not in (200, 202):
                    continue
                status = st.json().get("status")
                if status == "COMPLETED":
                    res = requests.get(result_url, headers=headers, timeout=15)
                    if res.status_code == 200:
                        images = res.json().get("images", [])
                        if images:
                            img_url = images[0].get("url")
                            if img_url:
                                img_bytes = requests.get(img_url, timeout=30).content
                                with open(output_path, "wb") as f:
                                    f.write(img_bytes)
                                return True
                    return False
                elif status in ("FAILED", "CANCELLED"):
                    return False
            return False
        except Exception as e:
            logger.error(f"[LoRA 추론] Fal.ai flux-lora 예외: {e}")
            return False

    def _generate_fal_flux(self, prompt: str, output_path: str, fal_key: str) -> bool:
        """
        Fal.ai HTTP Queue API를 통해 Flux Schnell 이미지 생성.
        """
        import requests
        import time
        model_id = "fal-ai/flux/schnell"
        submit_url = f"https://queue.fal.run/{model_id}"
        headers = {
            "Authorization": f"Key {fal_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "prompt": prompt,
            "image_size": "landscape_16_9",
            "sync_mode": True
        }
        
        logger.info(f"Fal.ai Flux 이미지 생성 요청 시작: prompt_len={len(prompt)}")
        try:
            # 동기 모드로 즉시 생성 시도
            resp = requests.post(submit_url, json=payload, headers=headers, timeout=20)

            # [신규] 계정 잠김/잔액 부족 감지 → 서킷 브레이커 즉시 작동
            if resp.status_code == 403:
                logger.error(f"Fal.ai 계정 잠김/잔액 부족 감지 (403): {resp.text[:200]}")
                self.__class__._fal_disabled = True
                logger.warning(
                    "Fal.ai 서킷 브레이커 작동 — 이 프로세스가 살아있는 동안 "
                    "이후 이미지 생성은 Fal.ai를 건너뛰고 Gemini/Pollinations로 바로 진행합니다."
                )
                return False

            if resp.status_code == 200:
                resp_json = resp.json()
                images = resp_json.get("images", [])
                if images:
                    img_url = images[0].get("url")
                    if img_url:
                        img_bytes = requests.get(img_url, timeout=30).content
                        with open(output_path, "wb") as f:
                            f.write(img_bytes)
                        return True
            
            # 비동기 대기 모드로 재시도
            payload["sync_mode"] = False
            resp = requests.post(submit_url, json=payload, headers=headers, timeout=30)

            if resp.status_code == 403:
                logger.error(f"Fal.ai 계정 잠김/잔액 부족 감지 (403, 비동기 모드): {resp.text[:200]}")
                self.__class__._fal_disabled = True
                logger.warning("Fal.ai 서킷 브레이커 작동 — 이후 이미지 생성은 Gemini/Pollinations로 바로 진행합니다.")
                return False

            if resp.status_code != 200:
                logger.warning(f"Fal.ai Flux 제출 실패 ({resp.status_code}): {resp.text}")
                return False
                
            resp_json = resp.json()
            request_id = resp_json.get("request_id")
            if not request_id:
                return False
                
            status_url = resp_json.get("status_url") or f"https://queue.fal.run/{model_id}/requests/{request_id}/status"
            result_url = resp_json.get("response_url") or f"https://queue.fal.run/{model_id}/requests/{request_id}"
            
            for i in range(10):
                time.sleep(1.5)
                status_resp = requests.get(status_url, headers=headers, timeout=15)
                if status_resp.status_code not in (200, 202):
                    continue
                status_data = status_resp.json()
                status = status_data.get("status")
                if status == "COMPLETED":
                    res_resp = requests.get(result_url, headers=headers, timeout=15)
                    if res_resp.status_code == 200:
                        res_data = res_resp.json()
                        images = res_data.get("images", [])
                        if images:
                            img_url = images[0].get("url")
                            if img_url:
                                img_bytes = requests.get(img_url, timeout=30).content
                                with open(output_path, "wb") as f:
                                    f.write(img_bytes)
                                return True
                    return False
                elif status in ("FAILED", "CANCELLED"):
                    return False
            return False
        except Exception as e:
            logger.error(f"Fal.ai Flux API 예외 발생: {e}")
            return False

    def _generate_gemini_api(self, prompt: str, output_path: str, api_key: str, character_image_path: str = None) -> bool:
        """
        Google AI Studio 공식 Gemini 이미지 생성 API 호출 (429 Rate Limit 대응 재시도 탑재).

        모델: gemini-3.1-flash-image
        (검증 기준: 2026 Google AI Studio 공식 API list)
        """
        import requests
        import time
        # 검증된 Gemini 이미지 생성 모델명 (2026)
        GEMINI_IMAGE_MODEL = "gemini-3.1-flash-image"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_IMAGE_MODEL}:generateContent?key={api_key}"
        
        # [Scenario A] Identity Anchor 및 다중 레퍼런스 포뮬러 주입
        anchor_prefix = ""
        parts = []
        if character_image_path and os.path.exists(character_image_path):
            try:
                with open(character_image_path, "rb") as f:
                    img_b64 = base64.b64encode(f.read()).decode()
                mime = "image/png" if character_image_path.lower().endswith(".png") else "image/jpeg"
                parts.append({
                    "inlineData": {
                        "mimeType": mime,
                        "data": img_b64
                    }
                })
                anchor_prefix = (
                    "Use the attached reference image as an identity anchor. "
                    "Strictly maintain the exact character features (face shape, suit, expression style, hairstyle) across all generated scenes. "
                    "Generate the following scene while keeping the character identity 100% consistent:\n\n"
                )
                logger.info(f"Gemini API 요청에 Identity Anchor 이미지 및 프롬프트 주입 완료: {character_image_path}")
            except Exception as e:
                logger.warning(f"캐릭터 레퍼런스 이미지 로드/인코딩 실패: {e}")

        parts.append({"text": f"{anchor_prefix}{prompt}"})

        payload = {
            "contents": [
                {
                    "parts": parts
                }
            ],
            "generationConfig": {
                "responseModalities": ["IMAGE"]
            }
        }
        headers = {"Content-Type": "application/json"}
        
        # Free Tier Rate Limit (2 RPM) 대응: 최대 5회 재시도 (매번 35초 대기)
        MAX_ATTEMPTS = 5
        for attempt in range(MAX_ATTEMPTS):
            resp = requests.post(url, json=payload, headers=headers, timeout=60)
            if resp.status_code == 200:
                data = resp.json()
                try:
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            inline_data = parts[0].get("inlineData", {})
                            if inline_data and "data" in inline_data:
                                img_bytes = base64.b64decode(inline_data["data"])
                                with open(output_path, "wb") as f:
                                    f.write(img_bytes)
                                return True
                except Exception as e:
                    logger.error(f"Gemini API 응답 파싱 에러: {e}")
                    return False
            elif resp.status_code == 429:
                wait_time = 35
                logger.warning(f"Gemini API 할당량 초과(429) 감지. {wait_time}초 후 재시도합니다. (시도 {attempt + 1}/{MAX_ATTEMPTS})")
                time.sleep(wait_time)
            else:
                logger.warning(f"Gemini API HTTP 에러 ({resp.status_code}): {resp.text}")
                return False
                
        logger.error(f"Gemini API 재시도 횟수 초과로 이미지 생성 실패: {prompt[:40]}...")
        self.__class__._gemini_disabled = True
        logger.warning("공식 Gemini API 실패로 인해 서킷 브레이커가 작동합니다. 이후 이미지 생성은 Pollinations로 즉시 폴백합니다.")
        return False

    def _generate_pollinations(self, prompt: str, output_path: str) -> str:
        """
        Pollinations.ai 기반 무료 AI 이미지 생성 (폴백).
        """
        encoded = urllib.parse.quote(prompt)
        url = f"{self.fallback_url}/{encoded}?width={self.width}&height={self.height}&nologo=true&seed={hash(prompt) % 100000}"

        req = urllib.request.Request(url, headers={
            "User-Agent": "VideoPipeline/1.0"
        })
        with urllib.request.urlopen(req, timeout=30) as response:
            image_data = response.read()

        if len(image_data) < 1000:
            raise ValueError(f"이미지 크기 비정상: {len(image_data)} bytes")

        with open(output_path, "wb") as f:
            f.write(image_data)

        logger.info(f"NanaBanana(Pollinations) 이미지 저장 완료: {output_path} ({len(image_data)/1024:.1f}KB)")
        return output_path
