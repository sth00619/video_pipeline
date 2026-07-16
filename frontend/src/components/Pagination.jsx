/**
 * 모든 목록에 사용하는 10개 단위 페이지네이션.
 *
 * 순서는 항상 처음(<<) · 이전(<) · 페이지 번호 · 다음(>) · 마지막(>>)으로
 * 고정한다. 긴 목록에서는 현재 페이지와 인접 페이지를 유지하고, 가운데는
 * 생략 부호로 압축해 버튼이 화면 밖으로 밀려나지 않게 한다.
 */
export default function Pagination({ total, currentPage, onChange, pageSize = 10 }) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize))

  const page = Math.min(Math.max(1, currentPage), pageCount)
  const from = Math.min((page - 1) * pageSize + 1, total)
  const to = Math.min(page * pageSize, total)
  const pages = pageNumbers(page, pageCount)
  const buttonClass = 'min-w-8 h-8 px-2 rounded-md border border-navy-600 text-xs font-semibold transition disabled:cursor-not-allowed disabled:opacity-35'

  return (
    <nav aria-label="목록 페이지 이동" className="flex flex-wrap items-center justify-between gap-3 px-5 py-3.5 border-t border-navy-700 bg-navy-950/30">
      <span className="text-xs text-gray-500">총 {total}개 중 {from}–{to} 표시</span>
      <div className="flex items-center gap-1" role="list">
        <button type="button" aria-label="첫 페이지" title="첫 페이지" onClick={() => onChange(1)} disabled={page === 1} className={`${buttonClass} bg-navy-800 text-gray-300 hover:bg-navy-700`}>&lt;&lt;</button>
        <button type="button" aria-label="이전 페이지" title="이전 페이지" onClick={() => onChange(page - 1)} disabled={page === 1} className={`${buttonClass} bg-navy-800 text-gray-300 hover:bg-navy-700`}>&lt;</button>
        {pages.map((number, index) => number === '…'
          ? <span key={`ellipsis-${index}`} className="w-5 text-center text-xs text-gray-500" aria-hidden="true">…</span>
          : <button type="button" key={number} aria-label={`${number}페이지`} aria-current={number === page ? 'page' : undefined} onClick={() => onChange(number)} className={`min-w-8 h-8 px-2 rounded-md border text-xs font-bold transition ${number === page ? 'border-accent-cyan bg-accent-cyan text-navy-950 shadow-glow-cyan' : 'border-navy-700 bg-navy-800 text-gray-400 hover:bg-navy-700 hover:text-white'}`}>{number}</button>
        )}
        <button type="button" aria-label="다음 페이지" title="다음 페이지" onClick={() => onChange(page + 1)} disabled={page === pageCount} className={`${buttonClass} bg-navy-800 text-gray-300 hover:bg-navy-700`}>&gt;</button>
        <button type="button" aria-label="마지막 페이지" title="마지막 페이지" onClick={() => onChange(pageCount)} disabled={page === pageCount} className={`${buttonClass} bg-navy-800 text-gray-300 hover:bg-navy-700`}>&gt;&gt;</button>
      </div>
    </nav>
  )
}

function pageNumbers(current, total) {
  if (total <= 7) return Array.from({ length: total }, (_, index) => index + 1)
  const visible = new Set([1, total, current - 1, current, current + 1])
  const sorted = [...visible].filter(number => number >= 1 && number <= total).sort((a, b) => a - b)
  const result = []
  sorted.forEach((number, index) => {
    if (index && number - sorted[index - 1] > 1) result.push('…')
    result.push(number)
  })
  return result
}
