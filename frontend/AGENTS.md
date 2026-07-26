# React 프론트엔드 작업 규칙

- React 18, Vite 5, TailwindCSS 구성을 따른다.
- 파일 다운로드는 JWT 인증 `fetch` 후 Blob URL 패턴만 사용한다.
- 캐릭터 스타일은 채널별 프로필로 관리한다. 채널 간 스타일 오염을 막기 위해 전역 `CHARACTER_STYLE` 환경 변수는 사용하지 않는다.
- UI 텍스트는 한국어로 작성한다.
