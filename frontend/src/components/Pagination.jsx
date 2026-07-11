/**
 * 페이지네이션 컴포넌트 (10개씩 표시 기준, 페이지 번호 · 이전/다음 버튼).
 *
 * Jobs.jsx / Dashboard.jsx / Admin.jsx가 동일한 페이지네이션 마크업을 반복하고
 * 있어서 단일 컴포넌트로 통합했습니다. pageSize 기본 10.
 */
export default function Pagination({ total, currentPage, onChange, pageSize = 10 }) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize))
  if (pageCount <= 1) return null

  const from = Math.min((currentPage - 1) * pageSize + 1, total)
  const to = Math.min(currentPage * pageSize, total)

  return (
    <div className="flex items-center justify-between px-6 py-4 border-t border-navy-700 bg-navy-900/20">
      <div className="text-xs text-gray-400">
        총 {total}개 중 {from} - {to} 표시
      </div>
      <div className="flex items-center gap-1">
        <button
          onClick={() => onChange(Math.max(currentPage - 1, 1))}
          disabled={currentPage === 1}
          className="px-2.5 py-1.5 rounded-lg bg-navy-700 border border-navy-600 text-xs font-semibold hover:bg-navy-600 transition disabled:opacity-30 disabled:hover:bg-navy-700"
        >
          이전
        </button>
        {Array.from({ length: pageCount }).map((_, i) => {
          const n = i + 1
          return (
            <button
              key={n}
              onClick={() => onChange(n)}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition border ${
                currentPage === n
                  ? 'bg-accent-cyan text-navy-950 border-accent-cyan shadow-sm shadow-accent-cyan/20'
                  : 'bg-navy-800 text-gray-300 border-navy-700 hover:bg-navy-700'
              }`}
            >
              {n}
            </button>
          )
        })}
        <button
          onClick={() => onChange(Math.min(currentPage + 1, pageCount))}
          disabled={currentPage === pageCount}
          className="px-2.5 py-1.5 rounded-lg bg-navy-700 border border-navy-600 text-xs font-semibold hover:bg-navy-600 transition disabled:opacity-30 disabled:hover:bg-navy-700"
        >
          다음
        </button>
      </div>
    </div>
  )
}
