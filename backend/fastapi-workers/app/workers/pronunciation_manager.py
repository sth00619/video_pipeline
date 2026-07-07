"""
ElevenLabs 발음 사전 관리자 — 금융 용어 커스텀 발음

핵심:
  ElevenLabs API의 Pronunciation Dictionary 기능을 활용하여
  금융/경제 전문 용어(FOMC, MACD, PER 등)의 TTS 발음을 교정합니다.
  
  이를 통해 스크립트 원문(자막에 표시되는 텍스트)은 "FOMC", "ETF" 등
  원래 표기 그대로 유지하면서, TTS 엔진만 올바르게 발음합니다.
  
  기존 _preprocess_for_tts() 정규식 전처리를 완전히 대체합니다.
"""
import os
import logging
import requests

logger = logging.getLogger(__name__)

# ── 금융 용어 발음 규칙 ─────────────────────────────────────────
FINANCIAL_PRONUNCIATION_RULES = [
    # 영문 약어 → 한국어 발음
    {"string_to_replace": "FOMC", "type": "alias", "alias": "에프오엠씨"},
    {"string_to_replace": "RSI", "type": "alias", "alias": "알에스아이"},
    {"string_to_replace": "MACD", "type": "alias", "alias": "맥디"},
    {"string_to_replace": "PER", "type": "alias", "alias": "피이알"},
    {"string_to_replace": "PBR", "type": "alias", "alias": "피비알"},
    {"string_to_replace": "S&P", "type": "alias", "alias": "에스앤피"},
    {"string_to_replace": "ETF", "type": "alias", "alias": "이티에프"},
    {"string_to_replace": "CPI", "type": "alias", "alias": "소비자물가지수"},
    {"string_to_replace": "GDP", "type": "alias", "alias": "국내총생산"},
    {"string_to_replace": "EPS", "type": "alias", "alias": "이피에스"},
    {"string_to_replace": "ROE", "type": "alias", "alias": "알오이"},
    {"string_to_replace": "KOSPI", "type": "alias", "alias": "코스피"},
    {"string_to_replace": "KOSDAQ", "type": "alias", "alias": "코스닥"},
    {"string_to_replace": "NASDAQ", "type": "alias", "alias": "나스닥"},
    {"string_to_replace": "NYSE", "type": "alias", "alias": "뉴욕증권거래소"},
    {"string_to_replace": "Fed", "type": "alias", "alias": "연준"},
    {"string_to_replace": "FED", "type": "alias", "alias": "연준"},
    {"string_to_replace": "BOJ", "type": "alias", "alias": "일본은행"},
    {"string_to_replace": "ECB", "type": "alias", "alias": "유럽중앙은행"},
    {"string_to_replace": "IPO", "type": "alias", "alias": "아이피오"},
    {"string_to_replace": "M&A", "type": "alias", "alias": "인수합병"},
    {"string_to_replace": "YoY", "type": "alias", "alias": "전년대비"},
    {"string_to_replace": "QoQ", "type": "alias", "alias": "전분기대비"},
    {"string_to_replace": "BPS", "type": "alias", "alias": "비피에스"},
    {"string_to_replace": "NAV", "type": "alias", "alias": "순자산가치"},
    {"string_to_replace": "VIX", "type": "alias", "alias": "빅스지수"},
    {"string_to_replace": "DXY", "type": "alias", "alias": "달러인덱스"},
    {"string_to_replace": "WTI", "type": "alias", "alias": "서부텍사스유"},
    # 단위 기호
    {"string_to_replace": "pt", "type": "alias", "alias": "포인트"},
]

DICTIONARY_NAME = "video_pipeline_financial_terms"


class PronunciationManager:
    """
    ElevenLabs 발음 사전 싱글턴 관리자.
    
    서버 시작 시 한 번 초기화하면, 이후 TTS 호출 시
    pronunciation_dictionary_locators 파라미터로 전달하여
    원본 텍스트를 훼손하지 않고 올바른 발음을 적용합니다.
    """

    _instance = None
    _dictionary_id = None
    _version_id = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._api_key = os.getenv("ELEVENLABS_API_KEY")
        self._initialized = False

    def initialize(self) -> dict:
        """발음 사전을 ElevenLabs에 등록 (이미 존재하면 재사용)"""
        if not self._api_key:
            logger.warning("ELEVENLABS_API_KEY 미설정 — 발음 사전 초기화 건너뜀")
            return {"status": "skipped", "reason": "no_api_key"}

        if self._initialized and self._dictionary_id:
            logger.info(f"발음 사전 이미 초기화됨: {self._dictionary_id}")
            return {
                "status": "already_initialized",
                "dictionary_id": self._dictionary_id,
                "version_id": self._version_id,
            }

        try:
            # 1. 기존 사전 검색
            existing = self._find_existing_dictionary()
            if existing:
                self._dictionary_id = existing["id"]
                self._version_id = existing["version_id"]
                self._initialized = True
                logger.info(f"기존 발음 사전 발견 및 재사용: {self._dictionary_id}")
                return {
                    "status": "reused",
                    "dictionary_id": self._dictionary_id,
                    "version_id": self._version_id,
                }

            # 2. 새 사전 등록
            result = self._create_dictionary()
            if result:
                self._dictionary_id = result["id"]
                self._version_id = result["version_id"]
                self._initialized = True
                logger.info(f"발음 사전 신규 생성 완료: {self._dictionary_id}")
                return {
                    "status": "created",
                    "dictionary_id": self._dictionary_id,
                    "version_id": self._version_id,
                    "rules_count": len(FINANCIAL_PRONUNCIATION_RULES),
                }

            return {"status": "failed", "reason": "creation_failed"}

        except Exception as e:
            logger.error(f"발음 사전 초기화 오류: {e}")
            return {"status": "error", "reason": str(e)}

    def get_locators(self) -> list[dict] | None:
        """TTS 호출 시 전달할 pronunciation_dictionary_locators 반환"""
        if not self._initialized or not self._dictionary_id:
            # 아직 초기화되지 않았으면 시도
            self.initialize()

        if self._dictionary_id and self._version_id:
            return [{
                "pronunciation_dictionary_id": self._dictionary_id,
                "version_id": self._version_id,
            }]
        return None

    def _find_existing_dictionary(self) -> dict | None:
        """이미 등록된 금융 용어 사전이 있는지 검색"""
        try:
            resp = requests.get(
                "https://api.elevenlabs.io/v1/pronunciation-dictionaries",
                headers={"xi-api-key": self._api_key},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                dictionaries = data.get("pronunciation_dictionaries", [])
                for d in dictionaries:
                    if d.get("name") == DICTIONARY_NAME:
                        return {
                            "id": d["id"],
                            "version_id": d.get("latest_version_id", d.get("version_id", "")),
                        }
        except Exception as e:
            logger.warning(f"발음 사전 검색 실패: {e}")
        return None

    def _create_dictionary(self) -> dict | None:
        """새 발음 사전 생성"""
        try:
            resp = requests.post(
                "https://api.elevenlabs.io/v1/pronunciation-dictionaries/add-from-rules",
                headers={
                    "xi-api-key": self._api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "name": DICTIONARY_NAME,
                    "description": "주식/경제 영상 자동화 파이프라인용 금융 전문 용어 발음 사전",
                    "rules": FINANCIAL_PRONUNCIATION_RULES,
                },
                timeout=15,
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                return {
                    "id": data.get("id"),
                    "version_id": data.get("version_id"),
                }
            else:
                logger.warning(f"발음 사전 생성 실패: {resp.status_code} {resp.text}")
                return None
        except Exception as e:
            logger.error(f"발음 사전 생성 오류: {e}")
            return None
