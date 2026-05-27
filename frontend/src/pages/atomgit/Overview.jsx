import { useState, useEffect, useCallback } from 'react'
import { Table, Tag, Space, Button, Input, Spin, Tooltip, Progress, Card, Row, Col, Statistic, InputNumber, message, Modal, Select } from 'antd'
import { ReloadOutlined, SearchOutlined, ArrowLeftOutlined, ThunderboltOutlined, LoadingOutlined, PlusOutlined, CloudDownloadOutlined, CommentOutlined, AuditOutlined, CodeOutlined, FileTextOutlined, ClockCircleOutlined, AlertOutlined, ProfileOutlined, DownloadOutlined, DeleteOutlined } from '@ant-design/icons'
import * as api from '../../api'

const STORAGE_KEY = 'atomgit_projects'

const METRICS = [
  { key: 'pr_count', label: 'PR', color: '#1890ff' },
  { key: 'comments_count', label: '评论', color: '#faad14' },
  { key: 'issues_count', label: 'Issues', color: '#eb2f96' },
  { key: 'reviews_count', label: 'Reviews', color: '#13c2c2' },
  { key: 'commits_count', label: 'Commits', color: '#fa541c' },
  { key: 'files_count', label: '文件', color: '#52c41a' },
  { key: 'timeline_count', label: '时间线', color: '#722ed1' },
]

const TASK_ACTIONS = [
  { key: 'batch-comments', label: '批量获取评论', desc: '获取最近 N 个 PR 的评论并保存到数据库', icon: '💬', defaultParam: 10, paramName: 'limit', fn: async (owner, repo, param, state) => { const res = await api.getAtomGitBatchComments(owner, repo, { limit: param, state }); return res.data } },
  { key: 'all-comments', label: '全量获取评论', desc: '获取整个项目所有 PR 的评论（可能耗时较长）', icon: '☁️', fn: async (owner, repo, _param, state) => { const res = await api.getAtomGitAllComments(owner, repo, { state, skip_no_comments: true }); return res.data } },
  { key: 'batch-details', label: '批量获取 PR 详情', desc: '获取最近 N 个 PR 的详细信息并保存', icon: '📋', defaultParam: 20, paramName: 'limit', needPulls: true, batchFn: 'getAtomGitBatchDetails' },
  { key: 'batch-reviews', label: '批量获取 Reviews', desc: '获取最近 N 个 PR 的 Review 记录', icon: '👀', defaultParam: 20, paramName: 'limit', needPulls: true, batchFn: 'getAtomGitBatchReviews' },
  { key: 'batch-commits', label: '批量获取 Commits', desc: '获取最近 N 个 PR 的提交记录', icon: '📝', defaultParam: 20, paramName: 'limit', needPulls: true, batchFn: 'getAtomGitBatchCommits' },
  { key: 'batch-files', label: '批量获取变更文件', desc: '获取最近 N 个 PR 的变更文件列表', icon: '📄', defaultParam: 20, paramName: 'limit', needPulls: true, batchFn: 'getAtomGitBatchFiles' },
  { key: 'batch-timelines', label: '批量获取时间线', desc: '获取最近 N 个 PR 的时间线事件', icon: '⏱️', defaultParam: 20, paramName: 'limit', needPulls: true, batchFn: 'getAtomGitBatchTimelines' },
  { key: 'issues', label: '获取 Issues', desc: '获取仓库的 Issue 列表', icon: '📌', defaultParam: 0, paramName: 'limit', fn: async (owner, repo, param, state) => { const res = await api.getAtomGitIssues(owner, repo, { state, max_count: param || 0, size: 100 }); return res.data } },
]

function loadProjects() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]') } catch { return [] }
}
function saveProjects(projects) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(projects))
}

function TaskButton({ action, owner, repo, state, onDone }) {
  const [loading, setLoading] = useState(false)
  const [param, setParam] = useState(action.defaultParam || 10)

  const handleClick = async () => {
    setLoading(true)
    try {
      let result
      if (action.needPulls) {
        const pullsRes = await api.getAtomGitPulls(owner, repo, { state, page: 1, size: param })
        const pulls = pullsRes.data.pulls || []
        if (!pulls.length) { message.warning('未获取到 PR'); setLoading(false); return }
        const prNumbers = pulls.map(p => p.number).join(',')
        const res = await api[action.batchFn](owner, repo, prNumbers)
        result = res.data
      } else {
        result = await action.fn(owner, repo, param, state)
      }

      const summary = result.total_prs !== undefined
        ? `${result.total_prs} PR, ${result.total_comments} 评论, 存库 ${result.saved_to_db || 0}`
        : result.success_count !== undefined
        ? `${result.success_count} 成功, ${result.failed_count} 失败, 存库 ${result.saved_to_db || 0}`
        : result.total !== undefined
        ? `${result.total} 条`
        : '完成'
      message.success(`${action.label} 完成: ${summary}`)
      if (onDone) onDone(summary)
    } catch (e) {
      message.error(`${action.label} 失败: ${e._friendlyMsg || e.message}`)
    }
    setLoading(false)
  }

  return (
    <Card size="small" style={{ marginBottom: 8 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 500, fontSize: 14 }}>
            <span style={{ marginRight: 6 }}>{action.icon}</span>
            {action.label}
          </div>
          <div style={{ fontSize: 12, color: '#999', marginTop: 2 }}>{action.desc}</div>
        </div>
        <Space size="small">
          {action.paramName && (
            <InputNumber size="small" min={0} max={500} value={param} onChange={v => setParam(v ?? (action.defaultParam || 10))} style={{ width: 70 }} addonAfter="条" />
          )}
          <Button type="primary" size="small" icon={loading ? <LoadingOutlined /> : <ThunderboltOutlined />} onClick={handleClick} loading={loading}>执行</Button>
        </Space>
      </div>
    </Card>
  )
}

function ProjectDetail({ owner, repo, onBack }) {
  const [prTotal, setPrTotal] = useState(0)
  const [issueTotal, setIssueTotal] = useState(0)
  const [state, setState] = useState('all')
  const [loading, setLoading] = useState(true)
  const [actionResults, setActionResults] = useState([])

  const refreshStats = useCallback(async () => {
    try {
      const [prRes, issueRes] = await Promise.all([
        api.getAtomGitPulls(owner, repo, { state, page: 1, size: 1 }).catch(() => ({ data: { total: 0 } })),
        api.getAtomGitIssues(owner, repo, { state, page: 1, size: 1 }).catch(() => ({ data: { total: 0 } })),
      ])
      setPrTotal(prRes.data.total || 0)
      setIssueTotal(issueRes.data.total || 0)
    } catch {}
    setLoading(false)
  }, [owner, repo, state])

  useEffect(() => { refreshStats() }, [refreshStats])

  const handleActionDone = (summary) => {
    setActionResults(prev => [{
      key: `${Date.now()}`,
      summary,
      time: new Date().toLocaleTimeString(),
    }, ...prev].slice(0, 30))
    refreshStats()
  }

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />

  return (
    <div>
      <Space style={{ marginBottom: 20 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={onBack}>返回列表</Button>
        <h2 style={{ margin: 0 }}>
          <a href={`https://atomgit.com/${owner}/${repo}`} target="_blank" rel="noopener noreferrer">{owner}/{repo}</a>
        </h2>
        <Tag color="blue">AtomGit</Tag>
        <Select value={state} onChange={setState} size="small" style={{ width: 90 }}
          options={[{ value: 'all', label: '全部' }, { value: 'open', label: '打开' }, { value: 'closed', label: '关闭' }]}
        />
      </Space>

      <Row gutter={[16, 12]} style={{ marginBottom: 16 }}>
        <Col span={6}><Card size="small"><Statistic title="PR 总数" value={prTotal} valueStyle={{ color: '#1890ff', fontSize: 20 }} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="Issue 总数" value={issueTotal} valueStyle={{ color: '#eb2f96', fontSize: 20 }} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="状态筛选" value={state === 'all' ? '全部' : state} valueStyle={{ color: '#52c41a', fontSize: 20 }} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="已执行操作" value={actionResults.length} valueStyle={{ color: '#722ed1', fontSize: 20 }} /></Card></Col>
      </Row>

      <Row gutter={[24, 0]}>
        <Col xs={24} lg={14}>
          <Card title={<span><ThunderboltOutlined style={{ marginRight: 8 }} />数据获取操作</span>} size="small">
            {TASK_ACTIONS.map(action => (
              <TaskButton key={action.key} action={action} owner={owner} repo={repo} state={state} onDone={handleActionDone} />
            ))}
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card title={<span><ClockCircleOutlined style={{ marginRight: 8 }} />执行历史</span>} size="small">
            {actionResults.length === 0 ? (
              <div style={{ textAlign: 'center', color: '#ccc', padding: 20 }}>暂无执行记录</div>
            ) : (
              <div style={{ maxHeight: 500, overflow: 'auto' }}>
                {actionResults.map(r => (
                  <div key={r.key} style={{ padding: '8px 0', borderBottom: '1px solid #f0f0f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: 13, color: '#52c41a' }}>{r.summary}</span>
                    <span style={{ fontSize: 12, color: '#999' }}>{r.time}</span>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </Col>
      </Row>
    </div>
  )
}

export default function AtomGitOverview() {
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState(null)
  const [addModalOpen, setAddModalOpen] = useState(false)
  const [addOwner, setAddOwner] = useState('')
  const [addRepo, setAddRepo] = useState('')
  const [refreshing, setRefreshing] = useState(false)

  const fetchData = useCallback(async () => {
    setLoading(true)
    const list = loadProjects()
    // 补充每个项目的 AtomGit PR 总数
    for (let i = 0; i < list.length; i++) {
      if (list[i].pr_total === undefined) {
        try {
          const res = await api.getAtomGitPulls(list[i].owner, list[i].repo, { state: 'all', page: 1, size: 1 })
          list[i].pr_total = res.data.total || 0
        } catch { list[i].pr_total = 0 }
      }
    }
    setProjects(list)
    saveProjects(list)
    setLoading(false)
  }, [])

  const handleRefresh = async () => {
    setRefreshing(true)
    const list = loadProjects()
    for (let i = 0; i < list.length; i++) {
      try {
        const res = await api.getAtomGitPulls(list[i].owner, list[i].repo, { state: 'all', page: 1, size: 1 })
        list[i].pr_total = res.data.total || 0
        list[i].last_updated = new Date().toISOString()
      } catch {}
    }
    setProjects(list)
    saveProjects(list)
    setRefreshing(false)
    message.success('刷新完成')
  }

  const handleAdd = () => {
    const o = addOwner.trim(), r = addRepo.trim()
    if (!o || !r) { message.warning('请输入 owner 和 repo'); return }
    const list = loadProjects()
    if (list.some(p => p.owner === o && p.repo === r)) { message.warning('项目已存在'); return }
    const newProject = { owner: o, repo: r, pr_total: 0, created_at: new Date().toISOString(), last_updated: new Date().toISOString() }
    list.push(newProject)
    saveProjects(list)
    setProjects(list)
    setAddModalOpen(false)
    setAddOwner('')
    setAddRepo('')
    setSelected(newProject)
    message.success(`已添加 ${o}/${r}`)
  }

  const handleRemove = (owner, repo) => {
    const list = loadProjects().filter(p => !(p.owner === owner && p.repo === repo))
    saveProjects(list)
    setProjects(list)
    message.success('已删除')
  }

  useEffect(() => { fetchData() }, [fetchData])

  if (selected) {
    return <ProjectDetail owner={selected.owner} repo={selected.repo} onBack={() => { setSelected(null); fetchData() }} />
  }

  const filtered = search
    ? projects.filter(p => `${p.owner}/${p.repo}`.toLowerCase().includes(search.toLowerCase()))
    : projects

  const columns = [
    {
      title: '项目', key: 'project', fixed: 'left', width: 220,
      render: (_, r) => (
        <a href={`https://atomgit.com/${r.owner}/${r.repo}`} target="_blank" rel="noopener noreferrer" style={{ fontWeight: 500 }}>
          {r.owner}/{r.repo}
        </a>
      ),
      sorter: (a, b) => `${a.owner}/${a.repo}`.localeCompare(`${b.owner}/${b.repo}`),
    },
    {
      title: 'PR 总数', key: 'pr_total', width: 100, align: 'center',
      render: (_, r) => r.pr_total ? <span style={{ color: '#1890ff', fontWeight: 500 }}>{r.pr_total.toLocaleString()}</span> : <span style={{ color: '#d9d9d9' }}>-</span>,
      sorter: (a, b) => (a.pr_total || 0) - (b.pr_total || 0),
    },
    {
      title: '添加时间', dataIndex: 'created_at', key: 'created_at', width: 100,
      render: v => v ? <span style={{ fontSize: 12, color: '#999' }}>{v.substring(0, 16).replace('T', ' ')}</span> : '-',
    },
    {
      title: '最后更新', dataIndex: 'last_updated', key: 'last_updated', width: 100,
      render: v => v ? <span style={{ fontSize: 12, color: '#999' }}>{v.substring(0, 16).replace('T', ' ')}</span> : '-',
    },
    {
      title: '操作', key: 'action', width: 130, fixed: 'right',
      render: (_, r) => (
        <Space size="small">
          <Button size="small" type="primary" icon={<ThunderboltOutlined />} onClick={() => setSelected(r)}>管理</Button>
          <Popconfirm title={`删除 ${r.owner}/${r.repo}？`} onConfirm={() => handleRemove(r.owner, r)} okButtonProps={{ danger: true }}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  if (loading && projects.length === 0) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />

  return (
    <div>
      <h2 style={{ marginBottom: 24 }}>项目数据总览 <Tag color="blue">AtomGit</Tag></h2>

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col span={8}>
          <Card size="small"><Statistic title="项目总数" value={projects.length} valueStyle={{ color: '#1677ff' }} /></Card>
        </Col>
        <Col span={8}>
          <Card size="small"><Statistic title="PR 总数" value={projects.reduce((s, p) => s + (p.pr_total || 0), 0)} valueStyle={{ color: '#1890ff' }} /></Card>
        </Col>
        <Col span={8}>
          <Card size="small"><Statistic title="平均 PR" value={projects.length ? Math.round(projects.reduce((s, p) => s + (p.pr_total || 0), 0) / projects.length) : 0} valueStyle={{ color: '#52c41a' }} /></Card>
        </Col>
      </Row>

      <Space style={{ marginBottom: 16 }} wrap>
        <Input placeholder="搜索项目 (owner/repo)" prefix={<SearchOutlined />} value={search} onChange={e => setSearch(e.target.value)} style={{ width: 280 }} allowClear />
        <Button icon={<ReloadOutlined />} onClick={fetchData} loading={loading}>刷新</Button>
        <Button icon={<CloudDownloadOutlined />} onClick={handleRefresh} loading={refreshing}>刷新 PR 统计</Button>
        <Button type="dashed" icon={<PlusOutlined />} onClick={() => setAddModalOpen(true)}>添加项目</Button>
        <span style={{ color: '#999', fontSize: 12 }}>
          {filtered.length === projects.length ? `共 ${projects.length} 个项目` : `筛选: ${filtered.length} / ${projects.length}`}
        </span>
      </Space>

      <Table
        columns={columns}
        dataSource={filtered.map(p => ({ key: `${p.owner}/${p.repo}`, ...p }))}
        loading={loading}
        pagination={{ pageSize: 20, showTotal: t => `共 ${t} 个项目` }}
        scroll={{ x: 800 }}
        size="middle"
      />

      <Modal
        title="添加 AtomGit 项目"
        open={addModalOpen}
        onCancel={() => { setAddModalOpen(false); setAddOwner(''); setAddRepo('') }}
        onOk={handleAdd}
        okText="添加并进入管理"
      >
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <div>
            <div style={{ marginBottom: 4, fontWeight: 500 }}>AtomGit 仓库地址</div>
            <Space>
              <Input placeholder="Owner (如 openeuler)" value={addOwner} onChange={e => setAddOwner(e.target.value)} style={{ width: 200 }} />
              <span style={{ fontSize: 18, color: '#999' }}>/</span>
              <Input placeholder="Repo (如 kernel)" value={addRepo} onChange={e => setAddRepo(e.target.value)} style={{ width: 250 }} />
            </Space>
          </div>
          {addOwner && addRepo && (
            <div style={{ padding: '8px 12px', background: '#f6f8fa', borderRadius: 6, fontSize: 13 }}>
              <a href={`https://atomgit.com/${addOwner}/${addRepo}`} target="_blank" rel="noopener noreferrer">
                https://atomgit.com/{addOwner}/{addRepo}
              </a>
            </div>
          )}
          <div style={{ color: '#999', fontSize: 12 }}>添加后进入项目管理页，可手动触发 PR / Issues / 评论 / Reviews 等数据获取</div>
        </Space>
      </Modal>
    </div>
  )
}
