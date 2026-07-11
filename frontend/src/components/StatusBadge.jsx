import { STATUS_LABEL, STATUS_COLOR } from '../constants/jobStatus'

/**
 * Job 상태 뱃지.
 * small=true 는 리스트 셀에 표시할 컴팩트 형태.
 */
export default function StatusBadge({ status, small = false }) {
  const label = STATUS_LABEL[status] || status
  const color = STATUS_COLOR[status] || 'bg-navy-700 text-gray-400'
  const size = small ? 'text-xs px-2 py-0.5' : 'text-sm px-3 py-1.5'
  return (
    <span className={`${size} rounded-full font-medium ${color}`}>
      {label}
    </span>
  )
}
