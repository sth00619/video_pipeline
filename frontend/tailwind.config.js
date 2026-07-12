/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // ══════════════════════════════════════════════════════════
        // [UI 개선 v3] 근본적인 팔레트 재작업
        //
        // 문제였던 것: navy 하나로만 명도 단계만 조정했더니 "여전히 같은
        // 색"으로 보인다는 피드백. 이번엔:
        //   1. 배경 자체를 순수 차가운 블루블랙(#0d1b2a)에서 아주 살짝
        //      더 따뜻하고 깊은 톤으로 재조정 (완전히 다른 색은 아니지만
        //      단조로움이 줄어듦)
        //   2. violet/amber 두 가지 새 포인트 색상 추가 — 카테고리 태그,
        //      2차 강조 요소에 써서 화면에 색상 다양성을 줌
        //   3. 기존 navy/accent 이름은 그대로 유지 (이미 만든 모든
        //      페이지의 className을 안 건드리고 값만 바꿔서 즉시 적용됨)
        // ══════════════════════════════════════════════════════════
        navy: {
          950: '#0a1220',  // 페이지 배경 — 기존보다 살짝 더 깊고 채도 낮춤
          900: '#0e1c30',
          800: '#142942',  // 카드 배경 — 기존(#16213e)보다 살짝 따뜻하게
          700: '#1d3552',  // 카드 보더/구분선
          600: '#2c4a6e',  // hover, 강조 보더
          500: '#3f6089',  // 밝은 강조, 아이콘
          400: '#6b83a8',  // 저채도 라벨 텍스트
        },
        accent: {
          gold: '#e8b95f',
          cyan: '#22d3ee',
          green: '#10d99a',
          red: '#f5556b',
          // [신규] 색상 다양성을 위한 2개 추가 — 카테고리 태그, 배지 등에
          // 골고루 분산해서 쓰면 화면 전체의 "칙칙함"이 크게 줄어듭니다.
          violet: '#a78bfa',
          amber: '#fbbf24',
        },
      },
      backgroundImage: {
        // [신규] 카드에 쓸 은은한 그라데이션 — 완전 평면(flat)이 아니라
        // 미세한 명암 차이로 입체감을 줌. 눈에 띄게 튀지 않으면서도
        // "단조롭다"는 인상을 줄여줍니다.
        'card-gradient': 'linear-gradient(145deg, #16294a 0%, #0f1d33 100%)',
        'hero-gradient': 'linear-gradient(135deg, #142942 0%, #0e1c30 60%, #1d3552 100%)',
        // 은은한 캔들스틱 모티프 배경 (대시보드 히어로 영역용 signature 요소)
        'candle-pattern': `repeating-linear-gradient(90deg, transparent, transparent 38px, rgba(232,185,95,0.035) 38px, rgba(232,185,95,0.035) 40px)`,
      },
      boxShadow: {
        'card': '0 4px 24px -4px rgba(0, 0, 0, 0.35)',
        'card-lg': '0 12px 40px -8px rgba(0, 0, 0, 0.45)',
        'glow-cyan': '0 0 24px -4px rgba(34, 211, 238, 0.4)',
        'glow-green': '0 0 24px -4px rgba(16, 217, 154, 0.4)',
        'glow-gold': '0 0 24px -4px rgba(232, 185, 95, 0.4)',
        'glow-violet': '0 0 24px -4px rgba(167, 139, 250, 0.35)',
      },
    },
  },
  plugins: [],
}
