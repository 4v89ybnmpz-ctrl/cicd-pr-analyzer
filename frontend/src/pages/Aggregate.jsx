import { useState, useEffect } from 'react'
import { Card, Row, Col, Statistic, Spin, Alert, Tag } from 'antd'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts'
import * as api from '../api'

const COLORS = ['#1890ff', '#52c41a', '#faad14', '#ff4d4f', '#722ed1', '#13c2c2']

export default function Aggregate() {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.getAggregate()
      .then(res => setStats(res.data.stats))
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />
  if (error) return <Alert type="error" message={error} />

  const byRepo = stats?.by_repo || []
  const byState = stats?.by_state || []

  const total = byRepo.reduce((s, r) => s + r.count, 0)

  return (
    <div>
      <h2 style={{ marginBottom: 24 }}>聚合统计</h2>

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col span={8}>
          <Card><Statistic title="总仓库数" value={byRepo.length} /></Card>
        </Col>
        <Col span={8}>
          <Card><Statistic title="总 PR 数" value={total} /></Card>
        </Col>
        <Col span={8}>
          <Card><Statistic title="状态类型" value={byState.length} /></Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={14}>
          <Card title="各仓库 PR 数量">
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={byRepo}>
                <XAxis dataKey="_id" tick={{ fontSize: 12 }} />
                <YAxis />
                <Tooltip />
                <Bar dataKey="count" fill="#1890ff" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card title="PR 状态分布">
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie data={byState} dataKey="count" nameKey="_id" cx="50%" cy="50%" outerRadius={100} label>
                  {byState.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </Card>
        </Col>
      </Row>

      <Card title="仓库详情" style={{ marginTop: 16 }}>
        <Row gutter={[16, 16]}>
          {byRepo.map((r, i) => (
            <Col xs={12} sm={8} md={6} key={i}>
              <Card size="small">
                <Statistic title={r._id} value={r.count} suffix="PR" />
              </Card>
            </Col>
          ))}
        </Row>
      </Card>

      <Card title="状态详情" style={{ marginTop: 16 }}>
        {byState.map((s, i) => (
          <Tag key={i} color={COLORS[i % COLORS.length]} style={{ fontSize: 14, padding: '4px 12px', margin: 4 }}>
            {s._id}: {s.count}
          </Tag>
        ))}
      </Card>
    </div>
  )
}
