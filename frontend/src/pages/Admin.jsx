import { useQuery } from '@tanstack/react-query'
import { Shield, Users, DollarSign, Video } from 'lucide-react'
import Layout from '../components/Layout'
import apiClient from '../api/client'

export default function Admin() {
  const { data: jobs = [] } = useQuery({
    queryKey: ['admin-jobs'],
    queryFn: () => apiClient.get('/jobs').then(r => r.data),
  })

  const totalCost = jobs.reduce((sum, j) => sum + (parseFloat(j.costAccumulated) || 0), 0)
  const completedJobs = jobs.filter(j => ['READY', 'PUBLISHED'].includes(j.status))
  const failedJobs = jobs.filter(j => ['FAILED', 'BUDGET_BLOCKED'].includes(j.status))

  return (
    <Layout>
      <div className="flex items-center gap-3 mb-6">
        <Shield className="text-accent-gold" size={24} />
        <div>
          <h1 className="text-2xl font-bold">관리자</h1>
          <p className="text-gray-400 text-sm mt-0.5">시스템 현황 및 통계</p>
        </div>
      </div>

      {/* 통계 카드 */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        <div className="bg-navy-800 rounded-xl border border-navy-700 p-5">
          <Video className="text-accent-cyan mb-3" size={20} />
          <div className="text-2xl font-bold">{jobs.length}</div>
          <div className="text-sm text-gray-400 mt-1">전체 작업</div>
        </div>
        <div className="bg-navy-800 rounded-xl border border-navy-700 p-5">
          <Video className="text-accent-green mb-3" size={20} />
          <div className="text-2xl font-bold">{completedJobs.length}</div>
          <div className="text-sm text-gray-400 mt-1">완료된 영상</div>
        </div>
        <div className="bg-navy-800 rounded-xl border border-navy-700 p-5">
          <DollarSign className="text-accent-gold mb-3" size={20} />
          <div className="text-2xl font-bold">${totalCost.toFixed(2)}</div>
          <div className="text-sm text-gray-400 mt-1">총 누적 비용</div>
        </div>
      </div>

      {/* 전체 작업 테이블 */}
      <div className="bg-navy-800 rounded-xl border border-navy-700">
        <div className="px-6 py-4 border-b border-navy-700">
          <h2 className="font-semibold">전체 작업 목록</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-navy-700">
                <th className="text-left px-6 py-3 text-gray-400 font-medium">ID</th>
                <th className="text-left px-6 py-3 text-gray-400 font-medium">제목</th>
                <th className="text-left px-6 py-3 text-gray-400 font-medium">카테고리</th>
                <th className="text-left px-6 py-3 text-gray-400 font-medium">모드</th>
                <th className="text-left px-6 py-3 text-gray-400 font-medium">상태</th>
                <th className="text-left px-6 py-3 text-gray-400 font-medium">비용</th>
                <th className="text-left px-6 py-3 text-gray-400 font-medium">작성자</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-navy-700">
              {jobs.map(job => (
                <tr key={job.id} className="hover:bg-navy-700/30">
                  <td className="px-6 py-3 text-gray-400">#{job.id}</td>
                  <td className="px-6 py-3">{job.title}</td>
                  <td className="px-6 py-3 text-gray-400">{job.category}</td>
                  <td className="px-6 py-3 text-gray-400">{job.autonomy}</td>
                  <td className="px-6 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded-full ${
                      job.status === 'READY' ? 'bg-accent-green/20 text-accent-green' :
                      job.status === 'FAILED' ? 'bg-accent-red/20 text-accent-red' :
                      'bg-navy-700 text-gray-400'
                    }`}>
                      {job.status}
                    </span>
                  </td>
                  <td className="px-6 py-3 text-gray-400">${parseFloat(job.costAccumulated || 0).toFixed(2)}</td>
                  <td className="px-6 py-3 text-gray-400">{job.createdBy}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Layout>
  )
}
