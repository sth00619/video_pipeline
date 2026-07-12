/**
 * 페이지네이션 컴포넌트 (10개씩 표시 기준, 페이지 번호 · 이전/다음 버튼).
 *
 * [UI 개선] 버튼이 너무 작아서 누르기 불편하다는 피드백 반영 — 패딩과
 * 글자 크기를 한 단계씩 키웠습니다.
 */
export default function Pagination({ total, currentPage, onChange, pageSize = 10 }) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize))
  if (pageCount <= 1) return null

  const from = Math.min((currentPage - 1) * pageSize + 1, total)
  const to = Math.min(currentPage * pageSize, total)

  return (
    <div className="flex items-center justify-between px-6 py-5 border-t border-navy-700 bg-navy-950/30">
      <div className="text-sm text-navy-400">
        총 {total}개 중 {from} - {to} 표시
      </div>
      <div className="flex items-center gap-1.5">
        <button
          onClick={() => onChange(Math.max(currentPage - 1, 1))}
          disabled={currentPage === 1}
          className="px-3.5 py-2 rounded-lg bg-navy-700 border border-navy-600 text-sm font-semibold hover:bg-navy-600 hover:border-navy-500 transition disabled:opacity-30 disabled:hover:bg-navy-700"
        >
          이전
        </button>
        {Array.from({ length: pageCount }).map((_, i) => {
          const n = i + 1
          return (
            <button
              key={n}
              onClick={() => onChange(n)}
              className={`px-4 py-2 rounded-lg text-sm font-bold transition border ${
                currentPage === n
                  ? 'bg-accent-cyan text-navy-950 border-accent-cyan shadow-glow-cyan'
                  : 'bg-navy-800 text-navy-400 border-navy-700 hover:bg-navy-700 hover:text-white'
              }`}
            >
              {n}
            </button>
          )
        })}
        <button
          onClick={() => onChange(Math.min(currentPage + 1, pageCount))}
          disabled={currentPage === pageCount}
          className="px-3.5 py-2 rounded-lg bg-navy-700 border border-navy-600 text-sm font-semibold hover:bg-navy-600 hover:border-navy-500 transition disabled:opacity-30 disabled:hover:bg-navy-700"
        >
          다음
        </button>
      </div>
    </div>
  )
}
