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
  const buttonClass = 'min-w-8 h-8 px-2.5 rounded-xl border border-slate-200 bg-white text-xs font-semibold text-slate-600 transition hover:bg-slate-50 hover:border-slate-300 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-white disabled:hover:border-slate-200 disabled:hover:text-slate-600 shadow-sm'

  return (
    <nav aria-label="목록 페이지 이동" className="flex flex-wrap items-center justify-between gap-3 px-5 py-3.5 border-t border-slate-200 bg-slate-50/50">
      <span className="text-xs font-medium text-slate-500">총 <strong className="font-semibold text-slate-800">{total}</strong>개 중 {from}–{to} 표시</span>
      <div className="flex items-center gap-1.5" role="list">
        <button type="button" aria-label="첫 페이지" title="첫 페이지" onClick={() => onChange(1)} disabled={page === 1} className={buttonClass}>&lt;&lt;</button>
        <button type="button" aria-label="이전 페이지" title="이전 페이지" onClick={() => onChange(page - 1)} disabled={page === 1} className={buttonClass}>&lt;</button>
        {pages.map((number, index) => number === '…'
          ? <span key={`ellipsis-${index}`} className="w-5 text-center text-xs text-slate-400 font-medium" aria-hidden="true">…</span>
          : <button type="button" key={number} aria-label={`${number}페이지`} aria-current={number === page ? 'page' : undefined} onClick={() => onChange(number)} className={`min-w-8 h-8 px-2.5 rounded-xl border text-xs font-bold transition shadow-sm ${number === page ? 'border-accent-cyan bg-accent-cyan text-white shadow-glow-cyan' : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50 hover:border-slate-300 hover:text-slate-900'}`}>{number}</button>
        )}
        <button type="button" aria-label="다음 페이지" title="다음 페이지" onClick={() => onChange(page + 1)} disabled={page === pageCount} className={buttonClass}>&gt;</button>
        <button type="button" aria-label="마지막 페이지" title="마지막 페이지" onClick={() => onChange(pageCount)} disabled={page === pageCount} className={buttonClass}>&gt;&gt;</button>
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
