/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // 주식 플랫폼 테마 - 네이비/블루 계열 (영상 이미지와 통일감)
        navy: {
          950: '#0d1b2a',
          900: '#0f3460',
          800: '#16213e',
          700: '#1a1a2e',
        },
        accent: {
          gold: '#e2b96f',
          cyan: '#00d4ff',
          green: '#00ff88',
          red: '#e94560',
        },
      },
    },
  },
  plugins: [],
}
