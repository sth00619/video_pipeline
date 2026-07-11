import { Filter, Search } from 'lucide-react'
import {
  CATEGORY_LIST, CATEGORY_LABEL, MODE_LIST, STATUS_LIST, STATUS_LABEL,
} from '../constants/jobStatus'

/**
 * 검색·카테고리·모드·상태 필터 4종 세트.
 *
 * Jobs.jsx / Dashboard.jsx / Admin.jsx 세 페이지가 각자 거의 동일한 필터 마크업을
 * 100줄 넘게 복붙하고 있어서 하나의 컴포넌트로 분리했습니다.
 * showAuthorSearch=true를 넘기면 Admin 페이지처럼 "제목/작성자" 검색으로 표시됩니다.
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

  return (
    <div className="bg-navy-800 rounded-xl border border-navy-700 p-4">
      <div className="flex items-center gap-2 mb-3">
        <Filter size={16} className="text-accent-cyan" />
        <span className="text-sm font-semibold">정밀 검색 및 필터</span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        {/* 검색 */}
        <div className="relative">
          <span className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
            <Search size={14} className="text-gray-400" />
          </span>
          <input
            type="text"
            value={searchQuery}
            onChange={e => onSearchChange(e.target.value)}
            placeholder={showAuthorSearch ? '제목, 작성자 검색...' : '작업 제목 검색...'}
            className="w-full bg-navy-700 border border-navy-600 rounded-lg pl-9 pr-3 py-2 text-xs text-white placeholder-gray-400 focus:outline-none focus:ring-1 focus:ring-accent-cyan"
          />
        </div>

        {/* 카테고리 */}
        <select
          value={category}
          onChange={e => onCategoryChange(e.target.value)}
          className="w-full bg-navy-700 border border-navy-600 rounded-lg px-2.5 py-2 text-xs text-white focus:outline-none focus:ring-1 focus:ring-accent-cyan cursor-pointer"
        >
          <option value="ALL">카테고리: 전체</option>
          {CATEGORY_LIST.filter(c => c !== 'ALL').map(cat => (
            <option key={cat} value={cat}>{CATEGORY_LABEL[cat] || cat}</option>
          ))}
        </select>

        {/* 모드 */}
        <select
          value={mode}
          onChange={e => onModeChange(e.target.value)}
          className="w-full bg-navy-700 border border-navy-600 rounded-lg px-2.5 py-2 text-xs text-white focus:outline-none focus:ring-1 focus:ring-accent-cyan cursor-pointer"
        >
          <option value="ALL">모드: 전체</option>
          {MODE_LIST.filter(m => m !== 'ALL').map(m => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>

        {/* 상태 */}
        <select
          value={status}
          onChange={e => onStatusChange(e.target.value)}
          className="w-full bg-navy-700 border border-navy-600 rounded-lg px-2.5 py-2 text-xs text-white focus:outline-none focus:ring-1 focus:ring-accent-cyan cursor-pointer"
        >
          <option value="ALL">상태: 전체</option>
          {STATUS_LIST.filter(s => s !== 'ALL').map(s => (
            <option key={s} value={s}>{STATUS_LABEL[s] || s}</option>
          ))}
        </select>
      </div>

      {hasAnyFilter && onReset && (
        <div className="flex justify-end mt-3">
          <button
            onClick={onReset}
            className="text-[11px] text-accent-cyan hover:underline"
          >
            필터 전체 초기화
          </button>
        </div>
      )}
    </div>
  )
}
