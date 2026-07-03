import { useParams } from 'react-router-dom'
import Layout from '../components/Layout'

export default function JobDetail() {
  const { id } = useParams()
  return (
    <Layout>
      <h1 className="text-2xl font-bold mb-2">작업 상세 #{id}</h1>
      <p className="text-gray-400">Sprint 2 Day 3에서 구현 예정 — 파이프라인 스텝퍼, 게이트 승인 UI</p>
    </Layout>
  )
}
