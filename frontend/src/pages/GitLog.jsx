import { useState, useEffect, useCallback } from 'react'
import { Table, Input, Tag, Space, Button, Card, Row, Col, Statistic, message, Tooltip, Descriptions } from 'antd'
import { ReloadOutlined, SearchOutlined, BranchesOutlined, DeleteOutlined } from '@ant-design/icons'
import * as api from '../api'

export default function GitLog() {
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [authorFilter, setAuthorFilter] = useState('')
  const [queryOwner, setQueryOwner] = useState('')
  const [queryRepo, setQueryRepo] = useState('')
  const [summary, setSummary] = useState(null)
  const [expandedKeys, setExpandedKeys] = useState([])

  const fetchCommits = useCallback(async (p = 1, owner = queryOwner, repo = queryRepo) => {
    if (!owner || !repo) return
    setLoading(true)
    try {
      const params = { page: p, size: 20, sort_by: 'author_date', sort_order: 'desc' }
      if (authorFilter) params.author = authorFilter
      const res = await api.getGitLogCommits(owner, repo, params)
      setData((res.data.data || []).map((c, i) => ({ key: c.hash || i, ...c })))
      setTotal(res.data.total || 0)
      setPage(p)
    } catch (e) {
      if (e.response?.status !== 404) message.error('查询失败: ' + e.message)
    }
    setLoading(false)
  }, [queryOwner, queryRepo, authorFilter])

  const fetchSummary = useCallback(async (owner = queryOwner, repo = queryRepo) => {
    if (!owner || !repo) { setSummary(null); return }
    try {
      const res = await api.getGitLogSummary(owner, repo)
      setSummary(res.data.summary || null)
    } catch { setSummary(null) }
  }, [queryOwner, queryRepo])

  useEffect(() => { fetchCommits(1); fetchSummary() }, [fetchCommits, fetchSummary])

  const handleQuery = () => {
    const o = queryOwner.trim()
    const r = queryRepo.trim()
    if (!o || !r) { message.warning('请输入 owner 和 repo'); return }
    fetchCommits(1, o, r)
    fetchSummary(o, r)
  }

  const columns = [
    {
      title: 'Hash', dataIndex: 'abbrev_hash', width: 80,
      render: v => <Tooltip title="点击复制完整 hash"><code style={{ cursor: 'pointer' }} onClick={() => { navigator.clipboard?.writeText(data.find(d => d.abbrev_hash === v)?.hash || v) }}>{v}</code></Tooltip>,
    },
    { title: '提交信息', dataIndex: 'subject', ellipsis: true, render: v => <span style={{ fontWeight: 500 }}>{v}</span> },
    { title: '作者', dataIndex: 'author_name', width: 120, render: v => <Tag>{v}</Tag> },
    { title: '邮箱', dataIndex: 'author_email', width: 180, ellipsis: true, render: v => <span style={{ fontSize: 12, color: '#999' }}>{v}</span> },
    { title: '日期', dataIndex: 'author_date', width: 110, render: v => v?.substring(0, 10), sorter: (a, b) => (a.author_date || '').localeCompare(b.author_date || '') },
    {
      title: '文件数', dataIndex: 'files_changed', width: 70, align: 'center',
      sorter: (a, b) => (a.files_changed || 0) - (b.files_changed || 0),
    },
    {
      title: '+/-', width: 120,
      sorter: (a, b) => (a.total_additions || 0) - (b.total_additions || 0),
      render: (_, r) => (
        <Space size={4}>
          <span style={{ color: '#52c41a' }}>+{(r.total_additions || 0).toLocaleString()}</span>
          <span style={{ color: '#999' }}>/</span>
          <span style={{ color: '#ff4d4f' }}>-{(r.total_deletions || 0).toLocaleString()}</span>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <h2 style={{ marginBottom: 24 }}><BranchesOutlined style={{ marginRight: 8 }} />Git Log 数据</h2>

      <Space style={{ marginBottom: 16 }} wrap>
        <Input placeholder="Owner" value={queryOwner} onChange={e => setQueryOwner(e.target.value)} style={{ width: 150 }} />
        <Input placeholder="Repo" value={queryRepo} onChange={e => setQueryRepo(e.target.value)} style={{ width: 200 }} />
        <Button type="primary" icon={<SearchOutlined />} onClick={handleQuery} loading={loading}>查询</Button>
        <Input placeholder="按作者筛选" prefix={<SearchOutlined />} value={authorFilter}
          onChange={e => setAuthorFilter(e.target.value)}
          onPressEnter={() => fetchCommits(1)}
          style={{ width: 180 }} allowClear />
        <Button icon={<ReloadOutlined />} onClick={() => fetchCommits(page)}>刷新</Button>
      </Space>

      {summary && (
        <Row gutter={[16, 12]} style={{ marginBottom: 16 }}>
          <Col span={4}>
            <Card size="small"><Statistic title="总提交数" value={summary.commit_count || 0} valueStyle={{ color: '#1890ff' }} /></Card>
          </Col>
          <Col span={3}>
            <Card size="small"><Statistic title="分支" value={summary.branches?.length || 0} /></Card>
          </Col>
          <Col span={3}>
            <Card size="small"><Statistic title="标签" value={summary.tags?.length || 0} /></Card>
          </Col>
          <Col span={3}>
            <Card size="small"><Statistic title="贡献者" value={summary.contributors?.length || 0} /></Card>
          </Col>
          <Col span={11}>
            <Card size="small">
              <div style={{ fontSize: 12, color: '#999', marginBottom: 4 }}>Top 贡献者</div>
              <Space wrap size={4}>
                {summary.contributors?.slice(0, 6).map((c, i) => (
                  <Tag key={i} color={i < 3 ? 'blue' : 'default'}>{c.name} ({c.commits})</Tag>
                ))}
              </Space>
            </Card>
          </Col>
        </Row>
      )}

      <Table
        columns={columns}
        dataSource={data}
        loading={loading}
        size="middle"
        scroll={{ x: 900 }}
        expandedRowKeys={expandedKeys}
        onExpandedRowsChange={setExpandedKeys}
        expandable={{
          expandedRowRender: (r) => (
            <div style={{ margin: 0 }}>
              {r.files?.length > 0 ? (
                <Table size="small" dataSource={r.files.map((f, i) => ({ key: i, ...f }))} pagination={false}
                  columns={[
                    { title: '文件', dataIndex: 'file', key: 'file', ellipsis: true, width: '60%' },
                    { title: '增加', dataIndex: 'additions', width: 100, render: v => <Tag color="green">+{v}</Tag> },
                    { title: '删除', dataIndex: 'deletions', width: 100, render: v => <Tag color="red">-{v}</Tag> },
                  ]}
                />
              ) : <span style={{ color: '#999', padding: 8, display: 'inline-block' }}>无文件变更（merge commit）</span>}
            </div>
          ),
        }}
        pagination={{
          current: page, total, pageSize: 20,
          onChange: (p) => fetchCommits(p),
          showTotal: (t) => `共 ${t} 条提交`,
          showSizeChanger: false,
        }}
      />
    </div>
  )
}
