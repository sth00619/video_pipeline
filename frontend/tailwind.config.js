/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // A안: Linear 스타일의 밝은 쿨그레이 + 인디고 토큰
        navy: {
          950: '#f7f8fa',
          900: '#f8fafc',
          800: '#ffffff',
          700: '#e5e7eb',
          600: '#d1d5db',
          500: '#94a3b8',
          400: '#64748b',
        },
        accent: {
          gold: '#d97706',
          cyan: '#5e6ad2',
          green: '#16a34a',
          red: '#dc2626',
          violet: '#7c3aed',
          amber: '#d97706',
        },
      },
      backgroundImage: {
        'card-gradient': 'linear-gradient(145deg, #ffffff 0%, #f8fafc 100%)',
        'hero-gradient': 'linear-gradient(135deg, #ffffff 0%, #f7f8fa 60%, #eef2ff 100%)',
        'candle-pattern': 'repeating-linear-gradient(90deg, transparent, transparent 38px, rgba(94,106,210,0.035) 38px, rgba(94,106,210,0.035) 40px)',
      },
      boxShadow: {
        card: '0 2px 10px rgba(15, 23, 42, 0.06)',
        'card-lg': '0 12px 32px rgba(15, 23, 42, 0.08)',
        'glow-cyan': '0 0 20px -6px rgba(94, 106, 210, 0.45)',
        'glow-green': '0 0 20px -6px rgba(22, 163, 74, 0.35)',
        'glow-gold': '0 0 20px -6px rgba(217, 119, 6, 0.35)',
        'glow-violet': '0 0 20px -6px rgba(124, 58, 237, 0.35)',
      },
    },
  },
  plugins: [],
}
