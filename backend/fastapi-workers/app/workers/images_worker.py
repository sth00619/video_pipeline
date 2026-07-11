"""
이미지 생성 워커 v2 — 무료 대안 (Nano Banana Pro 승인 전 임시)

핵심 변경:
  단색 배경 + 텍스트만 → matplotlib 기반 실제 주식 차트/다이어그램
  섹션 유형별로 다른 시각화 자동 생성:
    - intro: 타이틀 카드 (그라데이션 배경 + 아이콘)
    - background: 라인 차트 (지수 추이 시뮬레이션)
    - data: 캔들스틱 차트 (OHLC 스타일)
    - scenario: 상승/하락 분기 다이어그램
    - action: 체크리스트 카드
    - conclusion: 요약 카드 (3포인트 정리)

비용: $0 (matplotlib은 로컬 렌더링, API 호출 없음)
목적: Nano Banana Pro 승인 전까지 1차 데모 완성도 확보
"""
import os
import logging
import random
from pathlib import Path
from app.utils.process_manager import is_job_stopped

logger = logging.getLogger(__name__)

import re


def _extract_market_signal(text: str) -> dict:
    """
    씬 텍스트에서 실제 언급된 등락 방향과 지수/수치를 추출합니다.
    matplotlib 폴백 차트가 대본 내용과 모순되는 방향·숫자로 그려지는 것을
    막기 위한 용도입니다 (예: "7,541.28pt, -3.28% 하락"인데 차트는
    임의로 3000대에서 상승하는 그림이 나오는 문제 방지).
    """
    if not text:
        return {"direction": None, "value": None, "pct": None}

    direction = None
    if any(k in text for k in ["상승", "급등", "올랐", "돌파", "반등", "강세", "최고치", "호재"]):
        direction = "up"
    if any(k in text for k in ["하락", "급락", "내렸", "붕괴", "꺾", "약세", "부진", "악재"]):
        direction = "down"

    pct_match = re.search(r'([+-]?\d+(?:\.\d+)?)\s*(?:퍼센트|%)', text)
    pct = float(pct_match.group(1)) if pct_match else None
    if pct is not None and direction is None:
        if pct > 0:
            direction = "up"
        elif pct < 0:
            direction = "down"
    # 원문에 부호가 없어도("3.28% 하락") 방향 키워드가 있으면 부호를 보정
    # (그래야 화면 라벨이 "+3.28%"처럼 실제와 반대로 표시되는 것을 방지)
    if pct is not None and direction == "down" and pct > 0:
        pct = -pct
    elif pct is not None and direction == "up" and pct < 0:
        pct = abs(pct)

    # 지수/가격으로 보이는 숫자 우선 추출 (콤마 포함 큰 수 또는 4자리 이상)
    value_match = re.search(r'(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d{4,}(?:\.\d+)?)', text)
    value = value_match.group(1) if value_match else None

    return {"direction": direction, "value": value, "pct": pct}

# 주식 플랫폼 컬러 팔레트 (네이비 테마 통일)
COLOR_BG = "#0d1b2a"
COLOR_BG2 = "#16213e"
COLOR_ACCENT_GOLD = "#e2b96f"
COLOR_ACCENT_CYAN = "#00d4ff"
COLOR_ACCENT_GREEN = "#00c896"
COLOR_ACCENT_RED = "#e94560"
COLOR_TEXT = "#ffffff"
COLOR_GRID = "#2a3f5f"

FONT_PATH = "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"


class ImagesWorker:

    def generate(self, scenes_meta: list = None, job_id: int = 0,
                 tts_meta_json: str = None, script_meta_json: str = None,
                 character_image_path: str = None, character_style_prompt: str = None) -> dict:
        # scenes_meta가 주어지지 않은 경우 script_meta_json에서 복원
        if not scenes_meta and script_meta_json:
            try:
                import json
                script_data = json.loads(script_meta_json)
                if isinstance(script_data, str):
                    script_data = json.loads(script_data)
                scenes_meta = script_data.get("sections") or script_data.get("scenes") or []
                if not scenes_meta and script_data.get("script"):
                    import re
                    raw_script = script_data.get("script", "").strip()
                    parts = [p.strip() for p in re.split(r'(?m)^##\s*|\n{2,}', raw_script) if p.strip()]
                    total_parts = len(parts)
                    # section 키를 "scene_N" 같은 더미값이 아니라 실제 6종 중
                    # 하나로 배정 (matplotlib 폴백 렌더러가 정상 동작하도록)
                    section_keys = ["intro", "background", "data", "scenario", "action", "conclusion"]
                    for idx, part in enumerate(parts):
                        ratio = idx / max(total_parts - 1, 1) if total_parts > 1 else 0
                        section_type = section_keys[min(int(ratio * len(section_keys)), len(section_keys) - 1)]
                        scenes_meta.append({
                            "title": f"Scene {idx + 1}",
                            "content": part,
                            "text": part,
                            "prompt": (
                                f"A cute gold coin mascot character, chibi cartoon style, round shiny gold coin with face, arms and legs, "
                                f"wearing small navy business suit with gold tie, showing a neutral, calm and professional analyst pose, "
                                f"generic plain smooth surface with no currency symbol. professional financial news studio background, dark navy blue background (#0d1b2a), glowing data screen, 3D render, smooth shading, anime cartoon style"
                            ),
                            "section": section_type
                        })
                logger.info(f"script_meta_json에서 {len(scenes_meta)}개 씬 복원 성공")
            except Exception as e:
                logger.error(f"script_meta_json에서 씬 목록 추출 실패: {e}")
                scenes_meta = []

        if not scenes_meta:
            scenes_meta = []

        # AI 이미지 프로바이더 로드 (모든 씬에 일러스트 적용)
        ai_provider = None
        try:
            from app.providers.factory import get_image_provider
            ai_provider = get_image_provider()
            logger.info("일러스트 전용 모드 활성화: 모든 씬에 AI 캐릭터 일러스트 생성")
        except Exception as e:
            logger.warning(f"AI 이미지 프로바이더 로드 실패: {e}")

        job_dir = Path(f"/app/data/jobs/{job_id}/images")
        job_dir.mkdir(parents=True, exist_ok=True)

        generated = []
        for i, scene in enumerate(scenes_meta):
            if is_job_stopped(job_id):
                raise RuntimeError(f"Job {job_id} stopped by user.")
            section = scene.get("section", f"scene_{i}")
            narration = scene.get("content") or scene.get("text") or ""
            visual_prompt = scene.get("prompt") or narration or scene.get("title") or ""
            img_path = str(job_dir / f"scene_{i:03d}.png")

            # AI 이미지 생성
            if ai_provider:
                try:
                    ai_provider.generate_image(
                        prompt=visual_prompt,
                        output_path=img_path,
                        section=section,
                        keyword=visual_prompt[:30],
                        character_image_path=character_image_path,
                        character_style_prompt=character_style_prompt
                    )
                    generated.append({
                        "index": i,
                        "section": section,
                        "image_path": img_path,
                        "generation_method": "nana_banana_ai",
                        "prompt": visual_prompt,
                        "text": narration,
                    })
                    logger.info(f"씬 {i} AI 이미지 생성 완료 (prompt={visual_prompt[:50]}...)")
                    continue
                except Exception as e:
                    logger.warning(f"씬 {i} AI 이미지 실패, 폴백 Solid 배경 생성: {e}")

            # 로컬 폴백 (Matplotlib 고체 단색 배경 렌더링)
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            try:
                self._render_fallback(narration, img_path, plt)
                generated.append({
                    "index": i,
                    "section": section,
                    "image_path": img_path,
                    "generation_method": "fallback_solid",
                    "prompt": narration,
                    "text": narration,
                })
            except Exception as e:
                logger.error(f"씬 {i} 로컬 폴백 최종 실패: {e}")

        logger.info(f"이미지 생성 완료: {len(generated)}개")
        return {
            "job_id": job_id,
            "scenes": generated,
            "scene_count": len(generated),
            "gifs": [],
            "gif_count": 0
        }

    # ============================
    # 섹션별 시각화 라우팅
    # ============================
    def _render_section(self, section, text, img_path, plt):
        renderers = {
            "intro": self._render_title_card,
            "background": self._render_line_chart,
            "data": self._render_candlestick,
            "scenario": self._render_scenario_split,
            "action": self._render_checklist,
            "conclusion": self._render_summary_card,
        }
        renderer = renderers.get(section, self._render_line_chart)
        renderer(text, img_path, plt)

    # ── 인트로: 타이틀 카드 ──
    def _render_title_card(self, text, img_path, plt):
        fig, ax = plt.subplots(figsize=(19.2, 10.8), dpi=100)
        fig.patch.set_facecolor(COLOR_BG)
        ax.set_facecolor(COLOR_BG)
        ax.axis("off")

        # 그라데이션 느낌의 원형 장식
        for r, alpha in [(4.5, 0.08), (3.5, 0.12), (2.5, 0.18)]:
            circle = plt.Circle((0.5, 0.55), r/10, color=COLOR_ACCENT_CYAN, alpha=alpha, transform=ax.transAxes)
            ax.add_patch(circle)

        # 핵심 키워드만 추출 (첫 문장, 최대 20자)
        title = self._extract_title(text, max_chars=20)
        ax.text(0.5, 0.55, title, fontsize=52, color=COLOR_TEXT, ha="center", va="center",
                weight="bold", transform=ax.transAxes)
        ax.text(0.5, 0.35, "📈 주식 시장 분석", fontsize=24, color=COLOR_ACCENT_GOLD,
                ha="center", va="center", transform=ax.transAxes)

        plt.savefig(img_path, facecolor=COLOR_BG, bbox_inches="tight")
        plt.close(fig)

    # ── 시장 배경: 지수 추이 라인 차트 ──
    def _render_line_chart(self, text, img_path, plt):
        import numpy as np
        # [버그 수정] 기존에는 np.random.randn()으로 완전 무작위 추세를 그려서,
        # 대본이 "하락했습니다"라고 말해도 차트가 상승으로 나오는 등 내용과
        # 모순되는 이미지가 나올 수 있었습니다 (예: 실제 7541.28pt/-3.28%인데
        # 차트는 임의로 3000대에서 상승하는 그림). 씬 텍스트에서 등락 방향과
        # 실제 언급된 수치를 추출해 최소한 그 방향/수치와는 어긋나지 않게
        # 그립니다. (완벽히 정확한 차트는 아니지만 모순은 방지)
        signal = _extract_market_signal(text)

        fig, ax2 = plt.subplots(figsize=(19.2, 10.8), dpi=100)
        fig.patch.set_facecolor(COLOR_BG)

        ax2.set_facecolor(COLOR_BG2)
        days = np.arange(30)
        base = 2600
        if signal["direction"] == "up":
            drift = abs(np.random.randn()) * 3 + 1.5
            trend = np.cumsum(np.random.randn(30) * 6 + drift) + base
        elif signal["direction"] == "down":
            drift = -(abs(np.random.randn()) * 3 + 1.5)
            trend = np.cumsum(np.random.randn(30) * 6 + drift) + base
        else:
            trend = np.cumsum(np.random.randn(30) * 8) + base
        color = COLOR_ACCENT_GREEN if trend[-1] > trend[0] else COLOR_ACCENT_RED
        ax2.plot(days, trend, color=color, linewidth=3)
        ax2.fill_between(days, trend, trend.min() - 20, color=color, alpha=0.15)

        # 씬에서 실제 언급된 수치가 있으면 차트 위에 그대로 표기 (임의 축 눈금과 혼동 방지)
        if signal["value"]:
            label = signal["value"]
            if signal["pct"] is not None:
                label += f" ({signal['pct']:+.2f}%)"
            ax2.text(0.98, 0.92, label, transform=ax2.transAxes, ha="right", va="top",
                      fontsize=24, color=COLOR_ACCENT_GOLD, weight="bold")

        # 상단에 씬 키워드만 짧게 (최대 20자)
        short_title = self._extract_title(text, max_chars=20)
        ax2.set_title(short_title, color=COLOR_TEXT, fontsize=28, pad=20, weight="bold")
        ax2.tick_params(colors=COLOR_TEXT, labelsize=14)
        ax2.grid(color=COLOR_GRID, alpha=0.3)
        for spine in ax2.spines.values():
            spine.set_color(COLOR_GRID)

        plt.tight_layout()
        plt.savefig(img_path, facecolor=COLOR_BG, bbox_inches="tight")
        plt.close(fig)

    # ── 핵심 데이터: 캔들스틱 스타일 차트 ──
    def _render_candlestick(self, text, img_path, plt):
        import numpy as np
        signal = _extract_market_signal(text)

        fig, ax2 = plt.subplots(figsize=(19.2, 10.8), dpi=100)
        fig.patch.set_facecolor(COLOR_BG)

        ax2.set_facecolor(COLOR_BG2)
        n = 20
        if signal["direction"] == "up":
            drift = abs(np.random.randn()) * 2 + 1.0
        elif signal["direction"] == "down":
            drift = -(abs(np.random.randn()) * 2 + 1.0)
        else:
            drift = 0
        opens = np.cumsum(np.random.randn(n) * 5 + drift) + 2600
        closes = opens + np.random.randn(n) * 15
        # 마지막 캔들(최신 시점)은 대본에서 확인된 방향과 반드시 일치시킴
        if signal["direction"] == "up":
            closes[-1] = opens[-1] + abs(np.random.randn() * 15) + 5
        elif signal["direction"] == "down":
            closes[-1] = opens[-1] - abs(np.random.randn() * 15) - 5
        highs = np.maximum(opens, closes) + np.abs(np.random.randn(n) * 5)
        lows = np.minimum(opens, closes) - np.abs(np.random.randn(n) * 5)

        for i in range(n):
            color = COLOR_ACCENT_GREEN if closes[i] >= opens[i] else COLOR_ACCENT_RED
            ax2.plot([i, i], [lows[i], highs[i]], color=color, linewidth=1.5)
            ax2.add_patch(plt.Rectangle(
                (i - 0.35, min(opens[i], closes[i])), 0.7, abs(closes[i] - opens[i]),
                color=color
            ))

        if signal["value"]:
            label = signal["value"]
            if signal["pct"] is not None:
                label += f" ({signal['pct']:+.2f}%)"
            ax2.text(0.98, 0.92, label, transform=ax2.transAxes, ha="right", va="top",
                      fontsize=24, color=COLOR_ACCENT_GOLD, weight="bold")

        short_title = self._extract_title(text, max_chars=20)
        ax2.set_title(short_title, color=COLOR_TEXT, fontsize=28, pad=20, weight="bold")
        ax2.tick_params(colors=COLOR_TEXT, labelsize=14)
        ax2.grid(color=COLOR_GRID, alpha=0.3)
        for spine in ax2.spines.values():
            spine.set_color(COLOR_GRID)

        plt.tight_layout()
        plt.savefig(img_path, facecolor=COLOR_BG, bbox_inches="tight")
        plt.close(fig)

    # ── 시나리오: 상승/하락 분기 ──
    def _render_scenario_split(self, text, img_path, plt):
        fig, ax = plt.subplots(figsize=(19.2, 10.8), dpi=100)
        fig.patch.set_facecolor(COLOR_BG)
        ax.set_facecolor(COLOR_BG)
        ax.axis("off")
        ax.set_xlim(0, 10); ax.set_ylim(0, 10)

        # 상단에 짧은 제목만
        short_title = self._extract_title(text, max_chars=22)
        ax.text(5, 9.2, short_title, fontsize=26, color=COLOR_TEXT, ha="center", weight="bold")

        # 상승 시나리오 박스
        ax.add_patch(plt.Rectangle((0.5, 1), 4, 6.5, facecolor=COLOR_ACCENT_GREEN, alpha=0.15,
                                     edgecolor=COLOR_ACCENT_GREEN, linewidth=2))
        ax.text(2.5, 6.5, "▲ 상승 시나리오", fontsize=24, color=COLOR_ACCENT_GREEN, ha="center", weight="bold")
        ax.text(2.5, 4, "외국인 순매수 지속\n거래량 증가\n저항선 돌파", fontsize=18, color=COLOR_TEXT, ha="center")

        # 하락 시나리오 박스
        ax.add_patch(plt.Rectangle((5.5, 1), 4, 6.5, facecolor=COLOR_ACCENT_RED, alpha=0.15,
                                     edgecolor=COLOR_ACCENT_RED, linewidth=2))
        ax.text(7.5, 6.5, "▼ 하락 시나리오", fontsize=24, color=COLOR_ACCENT_RED, ha="center", weight="bold")
        ax.text(7.5, 4, "기관 매도 전환\n거래량 감소\n지지선 이탈", fontsize=18, color=COLOR_TEXT, ha="center")

        plt.savefig(img_path, facecolor=COLOR_BG, bbox_inches="tight")
        plt.close(fig)

    # ── 실행 가이드: 체크리스트 ──
    def _render_checklist(self, text, img_path, plt):
        fig, ax = plt.subplots(figsize=(19.2, 10.8), dpi=100)
        fig.patch.set_facecolor(COLOR_BG)
        ax.set_facecolor(COLOR_BG)
        ax.axis("off")
        ax.set_xlim(0, 10); ax.set_ylim(0, 10)

        short_title = self._extract_title(text, max_chars=22)
        ax.text(5, 9.2, short_title, fontsize=28, color=COLOR_ACCENT_GOLD, ha="center", weight="bold")

        items = ["거래량 변화 확인", "외국인·기관 매매 동향", "주요 지지·저항선", "글로벌 지수 연동성"]
        for i, item in enumerate(items):
            y = 6.5 - i * 1.5
            ax.add_patch(plt.Circle((1.5, y), 0.3, facecolor=COLOR_ACCENT_CYAN))
            ax.text(1.5, y, "✓", fontsize=20, color=COLOR_BG, ha="center", va="center", weight="bold")
            ax.text(2.5, y, item, fontsize=22, color=COLOR_TEXT, va="center")

        plt.savefig(img_path, facecolor=COLOR_BG, bbox_inches="tight")
        plt.close(fig)

    # ── 결론: 요약 카드 ──
    def _render_summary_card(self, text, img_path, plt):
        fig, ax = plt.subplots(figsize=(19.2, 10.8), dpi=100)
        fig.patch.set_facecolor(COLOR_BG)
        ax.set_facecolor(COLOR_BG)
        ax.axis("off")
        ax.set_xlim(0, 10); ax.set_ylim(0, 10)

        ax.text(5, 9.2, "오늘의 핵심 정리", fontsize=36, color=COLOR_ACCENT_GOLD, ha="center", weight="bold")

        # 핵심 포인트 3개 (텍스트 전체 대신 요약 포인트 고정)
        points = ["✅ 시장 핵심 데이터 확인", "✅ 상승·하락 시나리오 분석", "✅ 다음 영상도 구독하세요!"]
        for i, pt in enumerate(points):
            y = 6.0 - i * 1.8
            ax.text(5, y, pt, fontsize=26, color=COLOR_TEXT, ha="center", va="center", weight="bold")

        plt.savefig(img_path, facecolor=COLOR_BG, bbox_inches="tight")
        plt.close(fig)

    # ── 폴백: 단색 배경 ──
    def _render_fallback(self, text, img_path, plt):
        fig, ax = plt.subplots(figsize=(19.2, 10.8), dpi=100)
        fig.patch.set_facecolor(COLOR_BG)
        ax.set_facecolor(COLOR_BG)
        ax.axis("off")
        wrapped = self._wrap_text(text, 20)
        ax.text(0.5, 0.5, wrapped, fontsize=28, color=COLOR_TEXT, ha="center", va="center",
                transform=ax.transAxes)
        plt.savefig(img_path, facecolor=COLOR_BG, bbox_inches="tight")
        plt.close(fig)

    @staticmethod
    def _extract_title(text: str, max_chars: int = 20) -> str:
        """텍스트에서 첫 문장(또는 첫 max_chars자)만 추출하여 제목으로 사용"""
        import re
        if not text:
            return ""
        # 첫 문장 추출 (마침표, 요, 다, 죠 등으로 종결)
        first_sent = re.split(r'(?<=[다요죠네.!?])\s', text.strip())[0]
        first_sent = first_sent.strip()
        if len(first_sent) <= max_chars:
            return first_sent
        return first_sent[:max_chars] + "…"

    @staticmethod
    def _wrap_text(text: str, width: int) -> str:
        import textwrap
        return "\n".join(textwrap.wrap(text, width)) if text else ""
