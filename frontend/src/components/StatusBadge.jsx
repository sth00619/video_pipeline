import { STATUS_LABEL, STATUS_COLOR } from '../constants/jobStatus'

/**
 * Job 상태 뱃지.
 * small=true 는 리스트 셀에 표시할 컴팩트 형태.
 *
 * [UI 개선] small 버전이 text-xs(12px)였던 걸 text-sm(14px)으로 올려서
 * 리스트에서도 상태가 눈에 잘 들어오도록 함.
 */
export default function StatusBadge({ status, small = false }) {
  const label = STATUS_LABEL[status] || status
  const color = STATUS_COLOR[status] || 'bg-navy-700 text-navy-400'
  const size = small ? 'text-sm px-3 py-1' : 'text-base px-4 py-1.5'
  return (
    <span className={`${size} rounded-full font-semibold ${color}`}>
      {label}
    </span>
  )
}
