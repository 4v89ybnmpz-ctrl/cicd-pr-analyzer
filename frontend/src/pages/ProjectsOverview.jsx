import { useState, useEffect } from 'react'
import { Table, Tag, Space, Button, Input, Spin, Alert, Tooltip, Progress, Card, Row, Col, Statistic } from 'antd'
import { ReloadOutlined, SearchOutlined, FolderOutlined, CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons'
import * as api from '../api'

const METRICS = [
  { key: 'pr_count', label: 'PR', color: '#1890ff' },
  { key: 'comments_count', label: '评论', color: '#faad14' },
  { key: 'issues_count', label: 'Issues', color: '#eb2f96' },
  { key: 'timeline_count', label: 'Timeline', color: '#722ed1' },
  { key: 'details_count', label: 'PR 详情', color: '#52c41a' },
  { key: 'reviews_count', label: 'Reviews', color: '#13c2c2' },
  { key: 'commits_count', label: 'Commits', color: '#fa541c' },
]

function DataTag({ count, label, color }) {
  if (!count) return <Tag style={{ opacity: 0.4 }}>{label}: 0</Tag>
  return (
    <Tooltip title={`${label}: ${count} 条`}>
      <Tag color={color} style={{ margin: 2 }}>{label}: {count}</Tag>
    </Tooltip>
  )
}

function Completeness({ project }) {
  const filled = METRICS.filter(m => project[m.key] > 0).length
  const pct = Math.round((filled / METRICS.length) * 100)
  let status = 'exception'
  if (pct >= 70) status = 'success'
  else if (pct >= 40) status = 'normal'
  else if (pct > 0) status = 'active'
  return (
    <Tooltip title={`已获取 ${filled}/${METRICS.length} 类数据`}>
      <Progress percent={pct} size="small" status={status} style={{ width: 80 }} />
    </Tooltip>
  )
}

export default function ProjectsOverview({ onNavigate }) {
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [search, setSearch] = useState('')

  const fetchData = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.getProjectsOverview()
      setData(res.data.projects || [])
    } catch (e) {
      setError(e.message)
    }
    setLoading(false)
  }

  useEffect(() => { fetchData() }, [])

  const filtered = search
    ? data.filter(p => `${p.owner}/${p.repo}`.toLowerCase().includes(search.toLowerCase()))
    : data

  const totals = METRICS.reduce((acc, m) => {
    acc[m.key] = data.reduce((s, p) => s + (p[m.key] || 0), 0)
    return acc
  }, {})

  const columns = [
    {
      title: '项目', key: 'project', fixed: 'left', width: 220,
      render: (_, r) => (
        <Space>
          <a href={`https://github.com/${r.owner}/${r.repo}`} target="_blank" rel="noopener noreferrer" style={{ fontWeight: 500 }}>
            {r.owner}/{r.repo}
          </a>
        </Space>
      ),
      sorter: (a, b) => `${a.owner}/${a.repo}`.localeCompare(`${b.owner}/${b.repo}`),
    },
    {
      title: '完整度', key: 'completeness', width: 110,
      render: (_, r) => <Completeness project={r} />,
      sorter: (a, b) => {
        const fa = METRICS.filter(m => a[m.key] > 0).length
        const fb = METRICS.filter(m => b[m.key] > 0).length
        return fb - fa
      },
    },
    ...METRICS.map(m => ({
      title: m.label,
      dataIndex: m.key,
      key: m.key,
      width: 80,
      align: 'center',
      render: v => {
        if (!v) return <span style={{ color: '#d9d9d9' }}>-</span>
        return <Tag color={m.color}>{v.toLocaleString()}</Tag>
      },
      sorter: (a, b) => (a[m.key] || 0) - (b[m.key] || 0),
    })),
    {
      title: '最后更新', dataIndex: 'last_updated', key: 'last_updated', width: 100,
      render: v => v ? <span style={{ fontSize: 12, color: '#999' }}>{v.substring(0, 16).replace('T', ' ')}</span> : <span style={{ color: '#d9d9d9' }}>-</span>,
      sorter: (a, b) => (a.last_updated || '').localeCompare(b.last_updated || ''),
    },
    {
      title: '操作', key: 'action', width: 80, fixed: 'right',
      render: (_, r) => (
        <Button size="small" type="link" icon={<FolderOutlined />}
          onClick={() => { if (onNavigate) onNavigate('prs', null, { owner: r.owner, repo: r.repo }) }}>
          查看
        </Button>
      ),
    },
  ]

  if (loading && data.length === 0) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />
  if (error) return <Alert type="error" message={error} />

  return (
    <div>
      <h2 style={{ marginBottom: 24 }}>项目数据总览</h2>

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col span={4}>
          <Card size="small"><Statistic title="项目总数" value={data.length} /></Card>
        </Col>
        {METRICS.map(m => (
          <Col span={2.5} key={m.key} style={{ minWidth: 120 }}>
            <Card size="small">
              <Statistic title={m.label} value={totals[m.key] || 0} valueStyle={{ fontSize: 18, color: m.color }} />
            </Card>
          </Col>
        ))}
      </Row>

      <Space style={{ marginBottom: 16 }} wrap>
        <Input
          placeholder="搜索项目 (owner/repo)"
          prefix={<SearchOutlined />}
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ width: 280 }}
          allowClear
        />
        <Button icon={<ReloadOutlined />} onClick={fetchData} loading={loading}>刷新</Button>
        <span style={{ color: '#999', fontSize: 12 }}>
          {filtered.length === data.length ? `共 ${data.length} 个项目` : `筛选: ${filtered.length} / ${data.length}`}
        </span>
      </Space>

      <Table
        columns={columns}
        dataSource={filtered.map((p, i) => ({ key: `${p.owner}/${p.repo}`, ...p }))}
        loading={loading}
        pagination={{ pageSize: 20, showTotal: t => `共 ${t} 个项目` }}
        scroll={{ x: 1100 }}
        size="middle"
      />
    </div>
  )
}
