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

logger = logging.getLogger(__name__)

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
                 tts_meta_json: str = None, script_meta_json: str = None) -> dict:
        # scenes_meta가 주어지지 않은 경우 script_meta_json에서 복원
        if not scenes_meta and script_meta_json:
            try:
                import json
                script_data = json.loads(script_meta_json)
                if isinstance(script_data, str):
                    script_data = json.loads(script_data)
                scenes_meta = script_data.get("sections", [])
                logger.info(f"script_meta_json에서 {len(scenes_meta)}개 씬 복원 성공")
            except Exception as e:
                logger.error(f"script_meta_json에서 씬 목록 추출 실패: {e}")
                scenes_meta = []

        if not scenes_meta:
            scenes_meta = []

        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.font_manager as fm

        if os.path.exists(FONT_PATH):
            fm.fontManager.addfont(FONT_PATH)
            plt.rcParams["font.family"] = fm.FontProperties(fname=FONT_PATH).get_name()
        plt.rcParams["axes.unicode_minus"] = False

        # AI 이미지 프로바이더 로드 (하이브리드 모드)
        ai_provider = None
        AI_SECTIONS = {"intro", "action", "conclusion"}
        try:
            from app.providers.factory import get_image_provider
            ai_provider = get_image_provider()
            logger.info("하이브리드 모드 활성화: AI 이미지 + Matplotlib 차트")
        except Exception as e:
            logger.warning(f"AI 이미지 프로바이더 로드 실패, 전체 Matplotlib: {e}")

        job_dir = Path(f"/app/data/jobs/{job_id}/images")
        job_dir.mkdir(parents=True, exist_ok=True)

        generated = []
        for i, scene in enumerate(scenes_meta):
            section = scene.get("section", "background")
            text = scene.get("text", "")
            img_path = str(job_dir / f"scene_{i:03d}.png")

            # 하이브리드 분기: AI 일러스트 vs Matplotlib 차트
            if ai_provider and section in AI_SECTIONS:
                try:
                    ai_provider.generate_image(
                        prompt=text,
                        output_path=img_path,
                        section=section,
                        keyword=text[:30]
                    )
                    generated.append({
                        "index": i,
                        "section": section,
                        "image_path": img_path,
                        "generation_method": "nana_banana_ai",
                        "prompt": text[:100],
                    })
                    logger.info(f"씬 {i} AI 이미지 생성 완료 (section={section})")
                    continue
                except Exception as e:
                    logger.warning(f"씬 {i} AI 이미지 실패, Matplotlib 폴백: {e}")

            # Matplotlib 차트 렌더링 (기존 로직)
            try:
                self._render_section(section, text, img_path, plt)
                generated.append({
                    "index": i,
                    "section": section,
                    "image_path": img_path,
                    "generation_method": "matplotlib_chart",
                })
            except Exception as e:
                logger.error(f"씬 {i} 이미지 생성 실패: {e}, 폴백 사용")
                self._render_fallback(text, img_path, plt)
                generated.append({
                    "index": i, "section": section,
                    "image_path": img_path, "generation_method": "fallback_solid",
                })

        logger.info(f"이미지 생성 완료: {len(generated)}개 (하이브리드 모드)")
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

        title = (text[:24] + "…") if len(text) > 24 else text
        ax.text(0.5, 0.55, title, fontsize=52, color=COLOR_TEXT, ha="center", va="center",
                weight="bold", transform=ax.transAxes)
        ax.text(0.5, 0.35, "📈 주식 시장 분석", fontsize=24, color=COLOR_ACCENT_GOLD,
                ha="center", va="center", transform=ax.transAxes)

        plt.savefig(img_path, facecolor=COLOR_BG, bbox_inches="tight")
        plt.close(fig)

    # ── 시장 배경: 지수 추이 라인 차트 ──
    def _render_line_chart(self, text, img_path, plt):
        import numpy as np
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(19.2, 10.8), dpi=100,
                                        gridspec_kw={"width_ratios": [1, 2]})
        fig.patch.set_facecolor(COLOR_BG)

        # 왼쪽: 섹션 텍스트
        ax1.set_facecolor(COLOR_BG)
        ax1.axis("off")
        wrapped = self._wrap_text(text, 16)
        ax1.text(0.05, 0.5, wrapped, fontsize=26, color=COLOR_TEXT, va="center", ha="left",
                  weight="bold", transform=ax1.transAxes)

        # 오른쪽: 시뮬레이션 라인 차트 (실제 데이터 아님, 시각적 표현용)
        ax2.set_facecolor(COLOR_BG2)
        days = np.arange(30)
        base = 2600
        trend = np.cumsum(np.random.randn(30) * 8) + base
        color = COLOR_ACCENT_GREEN if trend[-1] > trend[0] else COLOR_ACCENT_RED
        ax2.plot(days, trend, color=color, linewidth=3)
        ax2.fill_between(days, trend, trend.min() - 20, color=color, alpha=0.15)
        ax2.set_title("지수 추이 (예시)", color=COLOR_TEXT, fontsize=18, pad=15)
        ax2.tick_params(colors=COLOR_TEXT, labelsize=12)
        ax2.grid(color=COLOR_GRID, alpha=0.3)
        for spine in ax2.spines.values():
            spine.set_color(COLOR_GRID)

        plt.tight_layout()
        plt.savefig(img_path, facecolor=COLOR_BG, bbox_inches="tight")
        plt.close(fig)

    # ── 핵심 데이터: 캔들스틱 스타일 차트 ──
    def _render_candlestick(self, text, img_path, plt):
        import numpy as np
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(19.2, 10.8), dpi=100,
                                        gridspec_kw={"width_ratios": [1, 2]})
        fig.patch.set_facecolor(COLOR_BG)

        ax1.set_facecolor(COLOR_BG)
        ax1.axis("off")
        wrapped = self._wrap_text(text, 16)
        ax1.text(0.05, 0.5, wrapped, fontsize=26, color=COLOR_TEXT, va="center", ha="left",
                  weight="bold", transform=ax1.transAxes)

        ax2.set_facecolor(COLOR_BG2)
        n = 15
        opens = np.cumsum(np.random.randn(n) * 5) + 2600
        closes = opens + np.random.randn(n) * 15
        highs = np.maximum(opens, closes) + np.abs(np.random.randn(n) * 5)
        lows = np.minimum(opens, closes) - np.abs(np.random.randn(n) * 5)

        for i in range(n):
            color = COLOR_ACCENT_GREEN if closes[i] >= opens[i] else COLOR_ACCENT_RED
            ax2.plot([i, i], [lows[i], highs[i]], color=color, linewidth=1)
            ax2.add_patch(plt.Rectangle(
                (i - 0.3, min(opens[i], closes[i])), 0.6, abs(closes[i] - opens[i]),
                color=color
            ))
        ax2.set_title("일별 캔들 차트 (예시)", color=COLOR_TEXT, fontsize=18, pad=15)
        ax2.tick_params(colors=COLOR_TEXT, labelsize=12)
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

        wrapped = self._wrap_text(text, 20)
        ax.text(5, 9, wrapped, fontsize=22, color=COLOR_TEXT, ha="center", weight="bold")

        # 상승 시나리오 박스
        ax.add_patch(plt.Rectangle((0.5, 1), 4, 6, facecolor=COLOR_ACCENT_GREEN, alpha=0.15,
                                     edgecolor=COLOR_ACCENT_GREEN, linewidth=2))
        ax.text(2.5, 6, "▲ 상승 시나리오", fontsize=24, color=COLOR_ACCENT_GREEN, ha="center", weight="bold")
        ax.text(2.5, 4, "외국인 순매수 지속\n거래량 증가\n저항선 돌파", fontsize=16, color=COLOR_TEXT, ha="center")

        # 하락 시나리오 박스
        ax.add_patch(plt.Rectangle((5.5, 1), 4, 6, facecolor=COLOR_ACCENT_RED, alpha=0.15,
                                     edgecolor=COLOR_ACCENT_RED, linewidth=2))
        ax.text(7.5, 6, "▼ 하락 시나리오", fontsize=24, color=COLOR_ACCENT_RED, ha="center", weight="bold")
        ax.text(7.5, 4, "기관 매도 전환\n거래량 감소\n지지선 이탈", fontsize=16, color=COLOR_TEXT, ha="center")

        plt.savefig(img_path, facecolor=COLOR_BG, bbox_inches="tight")
        plt.close(fig)

    # ── 실행 가이드: 체크리스트 ──
    def _render_checklist(self, text, img_path, plt):
        fig, ax = plt.subplots(figsize=(19.2, 10.8), dpi=100)
        fig.patch.set_facecolor(COLOR_BG)
        ax.set_facecolor(COLOR_BG)
        ax.axis("off")
        ax.set_xlim(0, 10); ax.set_ylim(0, 10)

        wrapped = self._wrap_text(text, 20)
        ax.text(5, 9, wrapped, fontsize=22, color=COLOR_TEXT, ha="center", weight="bold")

        items = ["거래량 변화 확인", "외국인·기관 매매 동향", "주요 지지·저항선", "글로벌 지수 연동성"]
        for i, item in enumerate(items):
            y = 6.5 - i * 1.5
            ax.add_patch(plt.Circle((1.2, y), 0.25, facecolor=COLOR_ACCENT_CYAN))
            ax.text(1.2, y, "✓", fontsize=18, color=COLOR_BG, ha="center", va="center", weight="bold")
            ax.text(2, y, item, fontsize=20, color=COLOR_TEXT, va="center")

        plt.savefig(img_path, facecolor=COLOR_BG, bbox_inches="tight")
        plt.close(fig)

    # ── 결론: 요약 카드 ──
    def _render_summary_card(self, text, img_path, plt):
        fig, ax = plt.subplots(figsize=(19.2, 10.8), dpi=100)
        fig.patch.set_facecolor(COLOR_BG)
        ax.set_facecolor(COLOR_BG)
        ax.axis("off")
        ax.set_xlim(0, 10); ax.set_ylim(0, 10)

        ax.text(5, 9, "오늘의 핵심 정리", fontsize=32, color=COLOR_ACCENT_GOLD, ha="center", weight="bold")

        wrapped = self._wrap_text(text, 24)
        ax.text(5, 4.5, wrapped, fontsize=20, color=COLOR_TEXT, ha="center", va="center")

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
    def _wrap_text(text: str, width: int) -> str:
        import textwrap
        return "\n".join(textwrap.wrap(text, width)) if text else ""
