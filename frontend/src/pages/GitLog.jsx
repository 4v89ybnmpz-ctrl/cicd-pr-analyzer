import { useState, useEffect, useCallback, useMemo } from 'react'
import { Table, Input, Tag, Space, Button, Card, Row, Col, Statistic, message, Tooltip, AutoComplete, Modal, Select } from 'antd'
import { ReloadOutlined, SearchOutlined, BranchesOutlined, FileTextOutlined } from '@ant-design/icons'
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
  const [projects, setProjects] = useState([])
  const [searchText, setSearchText] = useState('')
  const [filesModal, setFilesModal] = useState({ open: false, commit: null })
  // 分支相关状态
  const [branches, setBranches] = useState([])
  const [selectedBranch, setSelectedBranch] = useState(null)

  useEffect(() => {
    api.getGitProjects().then(res => {
      setProjects(res.data.projects || [])
    }).catch(() => {})
  }, [])

  const projectOptions = useMemo(() => {
    const q = searchText.toLowerCase().trim()
    return projects
      .filter(p => {
        if (!q) return true
        return p.owner.toLowerCase().startsWith(q) ||
               p.repo.toLowerCase().startsWith(q) ||
               `${p.owner}/${p.repo}`.toLowerCase().includes(q)
      })
      .slice(0, 15)
      .map(p => ({
        value: `${p.owner}/${p.repo}`,
        label: (
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span><b>{p.owner}</b>/{p.repo}</span>
            <Tag>{p.commit_count} commits</Tag>
          </div>
        ),
      }))
  }, [projects, searchText])

  const fetchCommits = useCallback(async (p = 1, owner = queryOwner, repo = queryRepo, branch = selectedBranch) => {
    if (!owner || !repo) return
    setLoading(true)
    try {
      const params = { page: p, size: 20, sort_by: 'author_date', sort_order: 'desc' }
      if (authorFilter) params.author = authorFilter
      if (branch) params.branch = branch
      const res = await api.getGitLogCommits(owner, repo, params)
      setData((res.data.data || []).map((c, i) => ({ key: c.hash || i, ...c })))
      setTotal(res.data.total || 0)
      setPage(p)
    } catch (e) {
      if (e.response?.status !== 404) message.error('查询失败: ' + e.message)
    }
    setLoading(false)
  }, [queryOwner, queryRepo, authorFilter, selectedBranch])

  const fetchSummary = useCallback(async (owner = queryOwner, repo = queryRepo) => {
    if (!owner || !repo) { setSummary(null); return }
    try {
      const res = await api.getGitLogSummary(owner, repo)
      setSummary(res.data.summary || null)
    } catch { setSummary(null) }
  }, [queryOwner, queryRepo])

  const fetchBranches = useCallback(async (owner = queryOwner, repo = queryRepo) => {
    if (!owner || !repo) { setBranches([]); return }
    try {
      const res = await api.getGitBranches(owner, repo)
      const raw = res.data.branches || []
      // 转为短名称（去掉 origin/ 前缀）
      const shortNames = [...new Set(raw.map(b => b.replace(/^origin\//, '')))]
      setBranches(shortNames)
    } catch { setBranches([]) }
  }, [queryOwner, queryRepo])

  useEffect(() => { fetchCommits(1); fetchSummary(); fetchBranches() }, [fetchCommits, fetchSummary, fetchBranches])

  const handleQuery = (owner, repo) => {
    const o = (owner || queryOwner).trim()
    const r = (repo || queryRepo).trim()
    if (!o || !r) { message.warning('请输入 owner 和 repo'); return }
    setSelectedBranch(null)
    setQueryOwner(o)
    setQueryRepo(r)
    setSearchText(`${o}/${r}`)
  }

  const handleSelect = (value) => {
    const [o, r] = value.split('/')
    setSelectedBranch(null)
    setQueryOwner(o)
    setQueryRepo(r)
    setSearchText(value)
  }

  // 切换分支时触发查询
  const handleBranchChange = (branch) => {
    setSelectedBranch(branch)
  }

  // selectedBranch 变化时自动查询
  useEffect(() => {
    if (queryOwner && queryRepo) {
      fetchCommits(1, queryOwner, queryRepo, selectedBranch)
    }
  }, [selectedBranch])

  const columns = [
    {
      title: 'Hash', dataIndex: 'abbrev_hash', width: 80,
      render: v => <Tooltip title="点击复制完整 hash"><code style={{ cursor: 'pointer' }} onClick={() => { navigator.clipboard?.writeText(data.find(d => d.abbrev_hash === v)?.hash || v) }}>{v}</code></Tooltip>,
    },
    { title: '提交信息', dataIndex: 'subject', ellipsis: true, render: v => <span style={{ fontWeight: 500 }}>{v}</span> },
    {
      title: '分支', dataIndex: 'branches', width: 140,
      render: (v) => {
        if (!v || v.length === 0) return <span style={{ color: '#d9d9d9' }}>-</span>
        const display = v.slice(0, 2)
        const rest = v.length - 2
        return (
          <Space size={2} wrap>
            {display.map((b, i) => <Tag key={i} color="blue" style={{ fontSize: 11 }}>{b}</Tag>)}
            {rest > 0 && <Tag style={{ fontSize: 11 }}>+{rest}</Tag>}
          </Space>
        )
      },
      filters: branches.map(b => ({ text: b, value: b })),
      onFilter: (value, record) => (record.branches || []).includes(value),
    },
    { title: '作者', dataIndex: 'author_name', width: 120, render: v => <Tag>{v}</Tag> },
    {
      title: '作者时间(UTC)', dataIndex: 'author_date_utc', width: 120,
      sorter: (a, b) => (a.author_date_utc || '').localeCompare(b.author_date_utc || ''),
      render: (v, r) => v || r.author_date?.substring(0, 16),
    },
    { title: '作者时区', dataIndex: 'author_tz', width: 80, render: v => v ? <Tag color="orange">{v}</Tag> : <span style={{ color: '#d9d9d9' }}>-</span> },
    { title: '提交者', dataIndex: 'committer_name', width: 120, render: v => <Tag color="geekblue">{v}</Tag> },
    {
      title: '提交时间(UTC)', dataIndex: 'committer_date_utc', width: 120,
      render: (v, r) => v || r.committer_date?.substring(0, 16),
    },
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
    {
      title: '文件详情', key: 'files_detail', width: 90, align: 'center',
      render: (_, r) => (
        r.files?.length > 0 ? (
          <Button type="link" size="small" icon={<FileTextOutlined />}
            onClick={() => setFilesModal({ open: true, commit: r })}>
            {r.files.length} 个文件
          </Button>
        ) : (
          <span style={{ color: '#d9d9d9' }}>-</span>
        )
      ),
    },
  ]

  return (
    <div>
      <h2 style={{ marginBottom: 24 }}><BranchesOutlined style={{ marginRight: 8 }} />Git Log 数据</h2>

      <Space style={{ marginBottom: 16 }} wrap>
        <AutoComplete
          options={projectOptions}
          onSelect={handleSelect}
          value={searchText}
          onChange={(v) => {
            setSearchText(v || '')
            if (!v) { setQueryOwner(''); setQueryRepo(''); return }
            const idx = v.indexOf('/')
            if (idx >= 0) { setQueryOwner(v.substring(0, idx)); setQueryRepo(v.substring(idx + 1)) }
            else { setQueryOwner(v); setQueryRepo('') }
          }}
          style={{ width: 300 }}
          placeholder="输入项目名称 (owner/repo)，如 oc→octocat"
          filterOption={false}
          allowClear
        />
        <Button type="primary" icon={<SearchOutlined />} onClick={() => handleQuery()} loading={loading}>查询</Button>
        <Input placeholder="按作者筛选" prefix={<SearchOutlined />} value={authorFilter}
          onChange={e => setAuthorFilter(e.target.value)}
          onPressEnter={() => fetchCommits(1)}
          style={{ width: 180 }} allowClear />
        {branches.length > 0 && (
          <Select
            style={{ width: 200 }}
            placeholder="按分支筛选"
            value={selectedBranch}
            onChange={handleBranchChange}
            allowClear
            showSearch
            options={[
              { value: null, label: '全部分支' },
              ...branches.map(b => ({ value: b, label: b })),
            ]}
          />
        )}
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
        scroll={{ x: 1300 }}
        pagination={{
          current: page, total, pageSize: 20,
          onChange: (p) => fetchCommits(p),
          showTotal: (t) => `共 ${t} 条提交`,
          showSizeChanger: false,
        }}
      />

      <Modal
        title={
          filesModal.commit
            ? <span><FileTextOutlined style={{ marginRight: 8 }} />文件变更详情 — <code>{filesModal.commit.abbrev_hash}</code> {filesModal.commit.subject}</span>
            : '文件变更详情'
        }
        open={filesModal.open}
        onCancel={() => setFilesModal({ open: false, commit: null })}
        footer={null}
        width={800}
      >
        {filesModal.commit?.files?.length > 0 ? (
          <Table
            size="small"
            dataSource={filesModal.commit.files.map((f, i) => ({ key: i, ...f }))}
            pagination={filesModal.commit.files.length > 20 ? { pageSize: 20 } : false}
            columns={[
              { title: '文件', dataIndex: 'file', key: 'file', ellipsis: true },
              {
                title: '增加', dataIndex: 'additions', width: 100,
                render: v => <Tag color="green">+{v}</Tag>,
                sorter: (a, b) => (a.additions || 0) - (b.additions || 0),
              },
              {
                title: '删除', dataIndex: 'deletions', width: 100,
                render: v => <Tag color="red">-{v}</Tag>,
                sorter: (a, b) => (a.deletions || 0) - (b.deletions || 0),
              },
            ]}
          />
        ) : (
          <div style={{ textAlign: 'center', color: '#999', padding: 24 }}>无文件变更（merge commit）</div>
        )}
      </Modal>
    </div>
  )
}
