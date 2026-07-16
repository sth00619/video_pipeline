import { Filter, Search } from 'lucide-react'
import {
  CATEGORY_LIST, CATEGORY_LABEL, MODE_LIST, STATUS_LIST, STATUS_LABEL, formatAutonomy,
} from '../constants/jobStatus'

/**
 * 검색·카테고리·모드·상태 필터 4종 세트.
 *
 * [UI 개선] 기존 text-xs(12px)/text-[10px] 위주였던 걸 text-sm(14px) 기준으로
 * 올리고, 입력창/셀렉트 높이와 패딩도 넉넉하게 키웠습니다. 작은 글씨가
 * "사용하기 쉽지 않다"는 피드백의 주요 원인 중 하나였습니다.
 */
export default function JobFilterBar({
  searchQuery, onSearchChange,
  category, onCategoryChange,
  mode, onModeChange,
  status, onStatusChange,
  showAuthorSearch = false,
  onReset,
}) {
  const hasAnyFilter = searchQuery || category !== 'ALL' || mode !== 'ALL' || status !== 'ALL'

  const selectClass = "w-full bg-navy-700 border border-navy-600 rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-accent-cyan/60 focus:border-accent-cyan cursor-pointer hover:border-navy-500 transition"

  return (
    <div className="bg-navy-800 rounded-xl border border-navy-700 p-5 shadow-card">
      <div className="flex items-center gap-2 mb-4">
        <Filter size={18} className="text-accent-cyan" />
        <span className="text-base font-semibold">정밀 검색 및 필터</span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        {/* 검색 */}
        <div className="relative">
          <span className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none">
            <Search size={16} className="text-navy-400" />
          </span>
          <input
            type="text"
            value={searchQuery}
            onChange={e => onSearchChange(e.target.value)}
            placeholder={showAuthorSearch ? '제목, 작성자 검색...' : '작업 제목 검색...'}
            className="w-full bg-navy-700 border border-navy-600 rounded-lg pl-10 pr-3 py-2.5 text-sm text-white placeholder-navy-400 focus:outline-none focus:ring-2 focus:ring-accent-cyan/60 focus:border-accent-cyan hover:border-navy-500 transition"
          />
        </div>

        {/* 카테고리 */}
        <select value={category} onChange={e => onCategoryChange(e.target.value)} className={selectClass}>
          <option value="ALL">카테고리: 전체</option>
          {CATEGORY_LIST.filter(c => c !== 'ALL').map(cat => (
            <option key={cat} value={cat}>{CATEGORY_LABEL[cat] || cat}</option>
          ))}
        </select>

        {/* 모드 */}
        <select value={mode} onChange={e => onModeChange(e.target.value)} className={selectClass}>
          <option value="ALL">모드: 전체</option>
          {MODE_LIST.filter(m => m !== 'ALL').map(m => (
            <option key={m} value={m}>{formatAutonomy(m)}</option>
          ))}
        </select>

        {/* 상태 */}
        <select value={status} onChange={e => onStatusChange(e.target.value)} className={selectClass}>
          <option value="ALL">상태: 전체</option>
          {STATUS_LIST.filter(s => s !== 'ALL').map(s => (
            <option key={s} value={s}>{STATUS_LABEL[s] || s}</option>
          ))}
        </select>
      </div>

      {hasAnyFilter && onReset && (
        <div className="flex justify-end mt-4">
          <button
            onClick={onReset}
            className="text-sm text-accent-cyan hover:underline font-medium"
          >
            필터 전체 초기화
          </button>
        </div>
      )}
    </div>
  )
}
