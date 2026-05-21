import { useState, useEffect, useRef, useCallback } from 'react'
import { Table, Tag, Space, Button, Input, Spin, Alert, Tooltip, Progress, Card, Row, Col, Statistic, InputNumber, message, Badge } from 'antd'
import { ReloadOutlined, SearchOutlined, ArrowLeftOutlined, ThunderboltOutlined, LoadingOutlined } from '@ant-design/icons'
import * as api from '../api'

const METRICS = [
  { key: 'pr_count', label: 'PR', color: '#1890ff', githubKey: 'github_pr_total' },
  { key: 'comments_count', label: '评论', color: '#faad14', githubKey: 'github_pr_comments_total' },
  { key: 'issues_count', label: 'Issues', color: '#eb2f96', githubKey: 'github_pure_issues_total' },
  { key: 'timeline_count', label: 'Timeline', color: '#722ed1', githubKey: null },
  { key: 'details_count', label: 'PR 详情', color: '#52c41a', githubKey: 'github_pr_total' },
  { key: 'reviews_count', label: 'Reviews', color: '#13c2c2', githubKey: 'github_pr_total' },
  { key: 'commits_count', label: 'Commits', color: '#fa541c', githubKey: 'github_pr_total' },
]

const TASK_ACTIONS = [
  { key: 'prs', label: '获取 PR', desc: '从 GitHub 拉取 PR 列表', apiFn: 'asyncFetchPrs', defaultParam: 100, paramName: 'max_count', icon: '📥' },
  { key: 'issues', label: '获取 Issues', desc: '从 GitHub 拉取 Issues 列表', apiFn: 'asyncFetchIssues', defaultParam: 50, paramName: 'max_count', icon: '📋' },
  { key: 'comments', label: '获取评论', desc: '对已有 PR 拉取评论数据', apiFn: 'asyncFetchComments', defaultParam: 30, paramName: 'limit', icon: '💬' },
  { key: 'timelines', label: '获取 Timeline', desc: '拉取 Issue/PR 的事件时间线', apiFn: 'asyncFetchTimelines', defaultParam: 20, paramName: 'limit', icon: '⏱️' },
  { key: 'profiles', label: '获取 Profile', desc: '从 Timeline/评论中提取用户并获取 Profile', apiFn: 'asyncFetchProfiles', defaultParam: 30, paramName: 'limit', icon: '👤' },
  { key: 'update_prs', label: '增量更新 PR', desc: '对比 updated_at 增量更新已有 PR', apiFn: 'updatePrs', icon: '🔄' },
  { key: 'update_issues', label: '增量更新 Issues', desc: '对比 updated_at 增量更新已有 Issues', apiFn: 'updateIssues', icon: '🔄' },
  { key: 'update_comments', label: '增量更新评论', desc: '对比 updated_at 增量更新已有评论', apiFn: 'updateComments', icon: '🔄' },
]

const STATUS_MAP = {
  pending: { color: 'default', text: '等待中' },
  running: { color: 'processing', text: '运行中' },
  completed: { color: 'success', text: '完成' },
  failed: { color: 'error', text: '失败' },
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

function MetricProgress({ label, fetched, total, color }) {
  const pct = total > 0 ? Math.min(Math.round((fetched / total) * 100), 100) : 0
  const hasTotal = total !== null && total !== undefined
  let status = 'exception'
  if (pct >= 100) status = 'success'
  else if (pct >= 70) status = 'normal'
  else if (pct > 0) status = 'active'

  return (
    <Card size="small">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 4 }}>
        <span style={{ fontSize: 13, fontWeight: 500 }}>{label}</span>
        <span style={{ fontSize: 12, color: '#999' }}>
          {fetched.toLocaleString()}{hasTotal ? ` / ${total.toLocaleString()}` : ''}
        </span>
      </div>
      {hasTotal ? (
        <Tooltip title={`已获取 ${fetched.toLocaleString()} / GitHub 总计 ${total.toLocaleString()}`}>
          <Progress
            percent={pct}
            size="small"
            status={status}
            strokeColor={color}
            format={() => `${pct}%`}
          />
        </Tooltip>
      ) : (
        <div style={{ fontSize: 20, fontWeight: 600, color, textAlign: 'center', padding: '4px 0' }}>
          {fetched.toLocaleString()}
        </div>
      )}
    </Card>
  )
}

function TaskButton({ action, owner, repo, onTaskCreated }) {
  const [loading, setLoading] = useState(false)
  const [param, setParam] = useState(action.defaultParam || 10)

  const handleClick = async () => {
    setLoading(true)
    try {
      let res
      if (action.paramName) {
        res = await api[action.apiFn](owner, repo, { [action.paramName]: param })
      } else {
        res = await api[action.apiFn](owner, repo)
      }
      if (res.data.task) {
        message.success(`${action.label} 任务已创建`)
      } else if (res.data.updated !== undefined) {
        message.success(`${action.label} 完成: 更新=${res.data.updated}, 新增=${res.data.added}, 未变=${res.data.unchanged}`)
      } else {
        message.success(`${action.label} 已完成`)
      }
      if (onTaskCreated) onTaskCreated()
    } catch (e) {
      message.error(`${action.label} 失败: ${e.message}`)
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
            <InputNumber
              size="small"
              min={1}
              max={500}
              value={param}
              onChange={v => setParam(v || 10)}
              style={{ width: 70 }}
              addonAfter="条"
            />
          )}
          <Button
            type="primary"
            size="small"
            icon={loading ? <LoadingOutlined /> : <ThunderboltOutlined />}
            onClick={handleClick}
            loading={loading}
          >
            执行
          </Button>
        </Space>
      </div>
    </Card>
  )
}

function ProjectDetail({ owner, repo, onBack }) {
  const [project, setProject] = useState(null)
  const [githubStats, setGithubStats] = useState(null)
  const [recentTasks, setRecentTasks] = useState([])
  const [loadingProject, setLoadingProject] = useState(true)
  const timerRef = useRef(null)

  const refreshAll = useCallback(async () => {
    try {
      const [overviewRes, tasksRes] = await Promise.all([
        api.getProjectsOverview(),
        api.getTaskList({ limit: 50 }),
      ])
      const projects = overviewRes.data.projects || []
      const current = projects.find(p => p.owner === owner && p.repo === repo)
      if (current) setProject(current)

      const allTasks = tasksRes.data.tasks || []
      const related = allTasks.filter(t => {
        const d = (t.description || '') + ' ' + (t.task_type || '')
        return d.includes(owner) && d.includes(repo)
      })
      setRecentTasks(related)
    } catch {}
    setLoadingProject(false)
  }, [owner, repo])

  const fetchGithubStats = useCallback(async () => {
    try {
      const res = await api.getRepoStats(owner, repo)
      setGithubStats(res.data.stats || null)
    } catch {}
  }, [owner, repo])

  useEffect(() => {
    refreshAll()
    fetchGithubStats()
    timerRef.current = setInterval(refreshAll, 3000)
    return () => clearInterval(timerRef.current)
  }, [refreshAll, fetchGithubStats])

  if (loadingProject && !project) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />

  const runningCount = recentTasks.filter(t => t.status === 'running').length

  const overallPct = (() => {
    if (!githubStats) return null
    const comparisons = [
      { fetched: project?.pr_count || 0, total: githubStats.github_pr_total },
      { fetched: project?.comments_count || 0, total: githubStats.github_pr_comments_total },
      { fetched: project?.issues_count || 0, total: githubStats.github_pure_issues_total },
    ].filter(c => c.total !== null && c.total !== undefined && c.total > 0)
    if (comparisons.length === 0) return null
    return Math.round(comparisons.reduce((s, c) => s + Math.min(c.fetched / c.total, 1), 0) / comparisons.length * 100)
  })()

  return (
    <div>
      <Space style={{ marginBottom: 20 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={onBack}>返回列表</Button>
        <h2 style={{ margin: 0 }}>
          <a href={`https://github.com/${owner}/${repo}`} target="_blank" rel="noopener noreferrer">
            {owner}/{repo}
          </a>
        </h2>
        {project?.last_updated && (
          <span style={{ color: '#999', fontSize: 12 }}>最后更新: {project.last_updated.substring(0, 16).replace('T', ' ')}</span>
        )}
      </Space>

      {githubStats && !githubStats.error && (
        <Row gutter={[16, 12]} style={{ marginBottom: 16 }}>
          <Col span={6}>
            <Card size="small">
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 12, color: '#999', marginBottom: 4 }}>整体完成度</div>
                {overallPct !== null ? (
                  <Progress type="circle" percent={overallPct} size={64} strokeColor={overallPct >= 80 ? '#52c41a' : overallPct >= 50 ? '#1890ff' : '#faad14'} />
                ) : (
                  <span style={{ color: '#999' }}>--</span>
                )}
              </div>
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small"><Statistic title="Stars" value={githubStats.stargazers_count || 0} valueStyle={{ color: '#faad14', fontSize: 20 }} /></Card>
          </Col>
          <Col span={6}>
            <Card size="small"><Statistic title="Forks" value={githubStats.forks_count || 0} valueStyle={{ color: '#1890ff', fontSize: 20 }} /></Card>
          </Col>
          <Col span={6}>
            <Card size="small"><Statistic title="Open Issues" value={githubStats.open_issues_count || 0} valueStyle={{ color: '#eb2f96', fontSize: 20 }} /></Card>
          </Col>
        </Row>
      )}

      <Row gutter={[12, 12]} style={{ marginBottom: 24 }}>
        {METRICS.map(m => (
          <Col key={m.key} span={3} style={{ minWidth: 130 }}>
            <MetricProgress
              label={m.label}
              fetched={project?.[m.key] || 0}
              total={githubStats?.[m.githubKey]}
              color={m.color}
            />
          </Col>
        ))}
      </Row>

      <Row gutter={[24, 0]}>
        <Col xs={24} lg={14}>
          <Card title={<span><ThunderboltOutlined style={{ marginRight: 8 }} />数据获取操作</span>} size="small">
            {TASK_ACTIONS.map(action => (
              <TaskButton key={action.key} action={action} owner={owner} repo={repo} onTaskCreated={refreshAll} />
            ))}
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card
            title={
              <span>
                <Badge count={runningCount} offset={[8, 0]}>
                  <span>最近任务</span>
                </Badge>
                <span style={{ color: '#999', fontSize: 12, marginLeft: 12 }}>每 3s 刷新</span>
              </span>
            }
            size="small"
          >
            {recentTasks.length === 0 ? (
              <div style={{ textAlign: 'center', color: '#ccc', padding: 20 }}>暂无相关任务</div>
            ) : (
              <div style={{ maxHeight: 440, overflow: 'auto' }}>
                {recentTasks.map(t => {
                  const s = STATUS_MAP[t.status] || { color: 'default', text: t.status }
                  return (
                    <div key={t.task_id} style={{ padding: '8px 0', borderBottom: '1px solid #f0f0f0' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <Space size="small">
                          <Tag color={s.color}>{s.text}</Tag>
                          <span style={{ fontSize: 13 }}>{t.description}</span>
                        </Space>
                        <span style={{ fontSize: 12, color: '#999' }}>
                          {t.created_at ? t.created_at.substring(11, 19) : ''}
                        </span>
                      </div>
                      {t.status === 'running' && (
                        <div style={{ marginTop: 4 }}>
                          <Progress percent={t.total ? Math.round((t.progress || 0) / t.total * 100) : 0} size="small" />
                        </div>
                      )}
                      {t.status === 'completed' && t.result && (
                        <div style={{ marginTop: 4, fontSize: 12, color: '#52c41a' }}>
                          获取 {t.result.fetched || 0} 条{t.result.failed ? `，失败 ${t.result.failed} 条` : ''}
                        </div>
                      )}
                      {t.status === 'failed' && (
                        <div style={{ marginTop: 4, fontSize: 12, color: '#ff4d4f' }}>{t.error || '执行失败'}</div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </Card>
        </Col>
      </Row>
    </div>
  )
}

export default function ProjectsOverview() {
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState(null)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.getProjectsOverview()
      setData(res.data.projects || [])
    } catch (e) {
      setError(e.message)
    }
    setLoading(false)
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  if (selected) {
    return <ProjectDetail owner={selected.owner} repo={selected.repo} onBack={() => setSelected(null)} />
  }

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
        <a href={`https://github.com/${r.owner}/${r.repo}`} target="_blank" rel="noopener noreferrer" style={{ fontWeight: 500 }}>
          {r.owner}/{r.repo}
        </a>
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
      title: m.label, dataIndex: m.key, key: m.key, width: 80, align: 'center',
      render: v => v ? <Tag color={m.color}>{v.toLocaleString()}</Tag> : <span style={{ color: '#d9d9d9' }}>-</span>,
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
        <Button size="small" type="primary" icon={<ThunderboltOutlined />}
          onClick={() => setSelected(r)}>
          管理
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
        dataSource={filtered.map(p => ({ key: `${p.owner}/${p.repo}`, ...p }))}
        loading={loading}
        pagination={{ pageSize: 20, showTotal: t => `共 ${t} 个项目` }}
        scroll={{ x: 1100 }}
        size="middle"
      />
    </div>
  )
}
