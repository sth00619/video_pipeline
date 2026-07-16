import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowUpRight, ChevronLeft, ChevronRight, Plus, RefreshCw, Youtube } from 'lucide-react'
import apiClient from '../../api/client'

const PAGE_SIZE = 10
const fmt = (n) => n == null ? '-' : Number(n).toLocaleString('ko-KR', { maximumFractionDigits: 2 })

export default function DailyKeywordResearch({ onUseKeyword }) {
  const queryClient = useQueryClient()
  const [keyword, setKeyword] = useState('')
  const [note, setNote] = useState('')
  const [page, setPage] = useState(1)
  const { data, isLoading } = useQuery({ queryKey: ['daily-keywords'], queryFn: () => apiClient.get('/keywords/daily').then(r => r.data), refetchInterval: 5 * 60 * 1000 })
  const refresh = useMutation({ mutationFn: () => apiClient.post('/keywords/refresh'), onSuccess: () => queryClient.invalidateQueries({ queryKey: ['daily-keywords'] }) })
  const addManual = useMutation({
    mutationFn: () => apiClient.post('/keywords/manual', { keyword, category: 'CUSTOM', note }),
    onSuccess: () => { setKeyword(''); setNote(''); setPage(1); queryClient.invalidateQueries({ queryKey: ['daily-keywords'] }) },
  })
  const items = data?.items || []
  const totalPages = Math.max(1, Math.ceil(items.length / PAGE_SIZE))
  const pageItems = useMemo(() => items.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE), [items, page])
  useEffect(() => { if (page > totalPages) setPage(totalPages) }, [page, totalPages])

  return (
    <section className="bg-navy-800 rounded-xl border border-navy-700 overflow-hidden">
      <div className="px-5 py-4 border-b border-navy-700 flex flex-wrap items-center justify-between gap-3">
        <div><h2 className="font-semibold text-white">오늘의 키워드 리서치</h2><p className="text-[11px] text-gray-500 mt-1">한국시간 08:00까지의 데이터 · 매일 09:00 자동 갱신 · 구독자 대비 조회수는 공개 데이터로 계산</p><p className={`text-[11px] mt-1 ${data?.youtubeConfigured ? 'text-accent-green' : data ? 'text-accent-gold' : 'text-accent-red'}`}>{data?.youtubeConfigured ? 'YouTube Data API 연결됨' : data ? 'YouTube API 키 없음 · 실제 YouTube 지표는 unavailable로 표시' : '백엔드 연결 상태를 확인할 수 없습니다'}</p></div>
        <button onClick={() => refresh.mutate()} disabled={refresh.isPending} className="text-xs text-accent-cyan flex items-center gap-1.5 hover:underline disabled:opacity-50"><RefreshCw size={14} className={refresh.isPending ? 'animate-spin' : ''}/>새로고침</button>
      </div>
      <div className="px-5 py-3 border-b border-navy-700 flex gap-2"><input value={keyword} onChange={e => setKeyword(e.target.value)} placeholder="긴급 뉴스 키워드 직접 추가" className="flex-1 bg-navy-900 border border-navy-600 rounded-lg px-3 py-2 text-xs text-white"/><input value={note} onChange={e => setNote(e.target.value)} placeholder="메모 (선택)" className="w-32 bg-navy-900 border border-navy-600 rounded-lg px-3 py-2 text-xs text-white"/><button onClick={() => addManual.mutate()} disabled={!keyword.trim() || addManual.isPending} className="bg-accent-cyan text-navy-950 rounded-lg px-3 py-2 text-xs font-semibold flex items-center gap-1 disabled:opacity-50"><Plus size={14}/>추가</button></div>
      <div className="overflow-x-auto"><table className="w-full min-w-[720px] text-xs"><thead className="bg-navy-900/60 text-gray-400"><tr><th className="text-left px-5 py-2.5">키워드</th><th className="text-right px-2">조회수</th><th className="text-right px-2">구독자 대비</th><th className="text-right px-2">좋아요</th><th className="text-right px-2">시간당 증가</th><th className="px-5"/></tr></thead><tbody className="divide-y divide-navy-700">{isLoading && <tr><td colSpan="6" className="px-5 py-8 text-center text-gray-500">데이터를 불러오는 중입니다.</td></tr>}{!isLoading && items.length === 0 && <tr><td colSpan="6" className="px-5 py-8 text-center text-gray-500">수집된 후보가 없습니다. 새로고침하거나 키워드를 직접 추가해 주세요.</td></tr>}{pageItems.map((item, index) => <tr key={`${item.keyword}-${(page - 1) * PAGE_SIZE + index}`} className="hover:bg-navy-700/40"><td className="px-5 py-3"><div className="flex items-center gap-2"><span className="font-semibold text-white">{item.keyword}</span><span className={`text-[10px] px-1.5 py-0.5 rounded ${item.source === 'manual' ? 'bg-accent-gold/15 text-accent-gold' : 'bg-accent-cyan/10 text-accent-cyan'}`}>{item.source === 'manual' ? '직접 추가' : item.category}</span></div><div className="text-[10px] text-gray-500 mt-1 max-w-[340px] truncate">{item.reason || item.note || '공개 데이터 요약'}</div></td><td className="text-right px-2 text-gray-300">{fmt(item.views)}</td><td className="text-right px-2 text-accent-green">{item.viewsPerSubscriber == null ? 'unavailable' : `${fmt(item.viewsPerSubscriber)}x`}</td><td className="text-right px-2 text-gray-300">{item.likes == null ? 'unavailable' : fmt(item.likes)}</td><td className="text-right px-2 text-gray-300">{item.velocityVph == null ? '-' : fmt(item.velocityVph)}</td><td className="px-5 text-right"><button onClick={() => onUseKeyword?.(item.keyword)} className="text-accent-cyan hover:underline inline-flex items-center gap-1">이 주제로 사용 <ArrowUpRight size={12}/></button></td></tr>)}</tbody></table></div>
      {items.length > PAGE_SIZE && <PageControl page={page} totalPages={totalPages} total={items.length} onChange={setPage}/>}<div className="px-5 py-3 text-[10px] text-gray-500 border-t border-navy-700 flex items-center gap-1"><Youtube size={12}/>공개 YouTube Data API 지표만 표시합니다. 타 채널의 평균 시청 시간·CTR은 공개 API에서 제공되지 않아 unavailable입니다.</div>
    </section>
  )
}

function PageControl({ page, totalPages, total, onChange }) {
  const numbers = pageNumbers(page, totalPages)
  return <div className="px-5 py-3 border-t border-navy-700 flex items-center justify-between text-xs"><span className="text-gray-500">{total}개 중 {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, total)}</span><div className="flex items-center gap-1"><button aria-label="이전 페이지" disabled={page === 1} onClick={() => onChange(page - 1)} className="border border-navy-600 p-1.5 rounded disabled:opacity-40"><ChevronLeft size={14}/></button>{numbers.map((number, index) => number === '…' ? <span key={`ellipsis-${index}`} className="px-1.5 text-gray-500">…</span> : <button key={number} onClick={() => onChange(number)} className={`min-w-7 h-7 rounded ${number === page ? 'bg-accent-cyan text-navy-950 font-bold' : 'text-gray-400 hover:bg-navy-700'}`}>{number}</button>)}<button aria-label="다음 페이지" disabled={page === totalPages} onClick={() => onChange(page + 1)} className="border border-navy-600 p-1.5 rounded disabled:opacity-40"><ChevronRight size={14}/></button></div></div>
}

function pageNumbers(current, total) {
  if (total <= 7) return Array.from({ length: total }, (_, index) => index + 1)
  const middle = [current - 1, current, current + 1].filter(number => number > 1 && number < total)
  return [1, ...(middle[0] > 2 ? ['…'] : []), ...middle, ...(middle.at(-1) < total - 1 ? ['…'] : []), total]
}
