/**
 * 작업 상태·카테고리·자율성 모드에 대한 공통 라벨과 색상.
 *
 * [UI 개선 v3] 기존에는 진행중 상태(KEYWORD/SCRIPT/TTS/IMAGES/ASSEMBLING)가
 * 전부 accent-cyan 하나로만 뭉쳐 있어서, 리스트에 여러 Job이 있어도 화면이
 * 단색으로 보이는 원인이었습니다. 파이프라인 단계별로 violet/amber를
 * 섞어서 시각적으로 "지금 어느 단계인지"도 더 잘 구분되고, 색상도
 * 다양해지도록 조정했습니다.
 */

export const CATEGORIES = [
  { value: 'KOSPI', label: 'KOSPI', desc: '코스피' },
  { value: 'KOSDAQ', label: 'KOSDAQ', desc: '코스닥' },
  { value: 'US_STOCKS', label: '미국 주식', desc: 'S&P 500, 나스닥, 다우' },
  { value: 'INDIVIDUAL_STOCK', label: '개별 종목', desc: '개별 종목 분석' },
  { value: 'ASSOCIATED_STOCKS', label: '연관 종목군', desc: '테마·섹터 묶음' },
  { value: 'GLOBAL_MACRO', label: '글로벌 매크로', desc: 'FOMC·환율·거시경제' },
  { value: 'CRYPTO', label: '암호화폐', desc: '비트코인·이더리움' },
  { value: 'CUSTOM', label: '직접 입력', desc: '기타 주제' },
]

export const CATEGORY_LIST = ['ALL', ...CATEGORIES.map(c => c.value)]
export const CATEGORY_LABEL = Object.fromEntries([
  ['ALL', '전체'],
  ...CATEGORIES.map(c => [c.value, c.label]),
])

// [신규] 카테고리별 포인트 색상 — 리스트/태그에서 카테고리를 색으로도
// 구분할 수 있도록 (기존엔 전부 무채색 텍스트였음)
export const CATEGORY_COLOR = {
  KOSPI: 'text-accent-cyan bg-accent-cyan/10 border-accent-cyan/20',
  KOSDAQ: 'text-accent-violet bg-accent-violet/10 border-accent-violet/20',
  US_STOCKS: 'text-accent-green bg-accent-green/10 border-accent-green/20',
  INDIVIDUAL_STOCK: 'text-accent-gold bg-accent-gold/10 border-accent-gold/20',
  ASSOCIATED_STOCKS: 'text-accent-amber bg-accent-amber/10 border-accent-amber/20',
  GLOBAL_MACRO: 'text-accent-violet bg-accent-violet/10 border-accent-violet/20',
  CRYPTO: 'text-accent-gold bg-accent-gold/10 border-accent-gold/20',
  CUSTOM: 'text-navy-400 bg-navy-700/40 border-navy-600',
}

export const MODE_LIST = ['ALL', 'AUTO', 'GUIDED', 'MANUAL']
export const AUTONOMY_LABEL = { AUTO: '자동', GUIDED: '반자동', MANUAL: '수동' }
export const AUTONOMY_STYLE = {
  AUTO: 'bg-accent-green/20 text-accent-green border-accent-green/30',
  GUIDED: 'bg-accent-cyan/20 text-accent-cyan border-accent-cyan/30',
  MANUAL: 'bg-accent-gold/20 text-accent-gold border-accent-gold/30',
}

// Job 상태 - Spring Boot JobStatus enum과 1:1 매핑되어야 함
export const STATUS_LIST = [
  'ALL', 'DRAFT', 'KEYWORD_PENDING', 'SCRIPT_PENDING', 'TTS_PENDING', 'IMAGES_PENDING',
  'ASSEMBLING', 'PREVIEW_PENDING', 'SHORTS_SEGMENTS_PENDING', 'SHORTS_GENERATING',
  'SHORTS_PREVIEW_PENDING', 'READY', 'PUBLISHED', 'BUDGET_BLOCKED', 'FAILED',
]

export const STATUS_LABEL = {
  ALL: '전체',
  DRAFT: '초안',
  KEYWORD_PENDING: '키워드 검토중',
  SCRIPT_PENDING: '스크립트 생성중',
  TTS_PENDING: 'TTS 생성중',
  IMAGES_PENDING: '이미지 생성중',
  ASSEMBLING: '영상 조립중',
  PREVIEW_PENDING: '미리보기 대기',
  SHORTS_SEGMENTS_PENDING: '쇼츠 구간 검토',
  SHORTS_GENERATING: '쇼츠 생성중',
  SHORTS_PREVIEW_PENDING: '쇼츠 미리보기',
  READY: '완료',
  PUBLISHED: '업로드 완료',
  BUDGET_BLOCKED: '예산 초과',
  FAILED: '오류',
}

/** 상태 뱃지에 적용할 Tailwind 유틸 클래스 — 파이프라인 단계별로 색상 분산 */
export const STATUS_COLOR = {
  DRAFT: 'bg-navy-700 text-navy-400',
  KEYWORD_PENDING: 'bg-accent-cyan/10 text-accent-cyan',
  SCRIPT_PENDING: 'bg-accent-violet/10 text-accent-violet',
  TTS_PENDING: 'bg-accent-amber/10 text-accent-amber',
  IMAGES_PENDING: 'bg-accent-cyan/10 text-accent-cyan',
  ASSEMBLING: 'bg-accent-violet/20 text-accent-violet',
  PREVIEW_PENDING: 'bg-accent-gold/20 text-accent-gold',
  SHORTS_SEGMENTS_PENDING: 'bg-accent-amber/10 text-accent-amber',
  SHORTS_GENERATING: 'bg-accent-cyan/20 text-accent-cyan',
  SHORTS_PREVIEW_PENDING: 'bg-accent-gold/10 text-accent-gold',
  READY: 'bg-accent-green/20 text-accent-green',
  PUBLISHED: 'bg-accent-green/20 text-accent-green',
  BUDGET_BLOCKED: 'bg-accent-red/20 text-accent-red',
  FAILED: 'bg-accent-red/20 text-accent-red',
}

/** 상태를 진행/완료/오류 3분류로 축약 (대시보드 카드용) */
export const IN_PROGRESS_STATUSES = [
  'KEYWORD_PENDING', 'SCRIPT_PENDING', 'TTS_PENDING', 'IMAGES_PENDING',
  'ASSEMBLING', 'PREVIEW_PENDING', 'SHORTS_SEGMENTS_PENDING',
  'SHORTS_GENERATING', 'SHORTS_PREVIEW_PENDING',
]
export const COMPLETED_STATUSES = ['READY', 'PUBLISHED']
export const ERROR_STATUSES = ['FAILED', 'BUDGET_BLOCKED']

export function isInProgress(status) { return IN_PROGRESS_STATUSES.includes(status) }
export function isCompleted(status) { return COMPLETED_STATUSES.includes(status) }
export function isError(status) { return ERROR_STATUSES.includes(status) }
