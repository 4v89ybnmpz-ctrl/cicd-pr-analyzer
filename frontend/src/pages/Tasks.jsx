import { useState, useEffect, useRef } from 'react'
import { Table, Tag, Space, Button, message, Popconfirm, Badge, Modal, Typography, Tooltip } from 'antd'
import { ReloadOutlined, DeleteOutlined, ClearOutlined, EyeOutlined, FileTextOutlined } from '@ant-design/icons'
import * as api from '../api'

const { Text } = Typography

const STATUS_MAP = {
  pending: { color: 'default', text: '等待中' },
  running: { color: 'processing', text: '运行中' },
  completed: { color: 'success', text: '已完成' },
  failed: { color: 'error', text: '失败' },
}

const TYPE_MAP = {
  fetch_prs: '获取 PR',
  fetch_issues: '获取 Issues',
  fetch_comments: '获取评论',
  fetch_timelines: '获取 Timeline',
  fetch_profiles: '获取 Profile',
}

const LOG_COLORS = { INFO: '#52c41a', WARN: '#faad14', ERROR: '#ff4d4f' }

export default function Tasks() {
  const [data, setData] = useState([])
  const [detailVisible, setDetailVisible] = useState(false)
  const [currentTask, setCurrentTask] = useState(null)
  const [logs, setLogs] = useState([])
  const [logLoading, setLogLoading] = useState(false)
  const timerRef = useRef(null)
  const logTimerRef = useRef(null)

  const [statusFilter, setStatusFilter] = useState(null)
  const [counts, setCounts] = useState({})

  const fetchTasks = async (status = null) => {
    try {
      const res = await api.getTaskList({ status, limit: 50 })
      setData((res.data.tasks || []).map(t => ({ key: t.task_id, ...t })))
      setCounts(res.data.counts || {})
    } catch {}
  }

  useEffect(() => {
    fetchTasks(statusFilter)
    timerRef.current = setInterval(() => fetchTasks(statusFilter), 3000)
    return () => { clearInterval(timerRef.current); clearInterval(logTimerRef.current) }
  }, [])

  const handleFilter = (status) => {
    setStatusFilter(status)
    clearInterval(timerRef.current)
    fetchTasks(status)
    timerRef.current = setInterval(() => fetchTasks(status), 3000)
  }

  const showDetail = async (task) => {
    setCurrentTask(task)
    setDetailVisible(true)
    setLogLoading(true)
    try {
      const res = await api.getTaskLogs(task.task_id)
      setLogs(res.data.logs || [])
    } catch { setLogs([]) }
    setLogLoading(false)
    clearInterval(logTimerRef.current)
    logTimerRef.current = setInterval(async () => {
      try {
        const res = await api.getTaskLogs(task.task_id)
        setLogs(res.data.logs || [])
        if (task.status === 'completed' || task.status === 'failed') clearInterval(logTimerRef.current)
      } catch {}
    }, 2000)
  }

  const handleDelete = async (taskId) => {
    try { await api.deleteTask(taskId); message.success('已删除'); fetchTasks() } catch { message.error('删除失败') }
  }

  const handleClearCompleted = async () => {
    const done = data.filter(t => t.status === 'completed' || t.status === 'failed')
    for (const t of done) { try { await api.deleteTask(t.task_id) } catch {} }
    message.success(`已清理 ${done.length} 个任务`)
    fetchTasks(statusFilter)
  }

  const runningCount = counts.running || 0

  const columns = [
    { title: '任务ID', dataIndex: 'task_id', key: 'task_id', width: 80, render: v => <code>{v}</code> },
    { title: '类型', dataIndex: 'task_type', key: 'task_type', width: 100, render: v => TYPE_MAP[v] || v },
    { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 90,
      render: v => { const s = STATUS_MAP[v] || { color: 'default', text: v }; return <Tag color={s.color}>{s.text}</Tag> },
    },
    {
      title: '进度', key: 'progress', width: 160,
      render: (_, r) => {
        if (r.status === 'pending') return <Tag>等待中</Tag>
        if (r.status === 'running') return <span>{r.progress || 0} / {r.total || '?'}</span>
        if (r.status === 'completed' && r.result) {
          const res = r.result
          const parts = []
          if (res.fetched !== undefined) parts.push(`获取 ${res.fetched}`)
          if (res.saved !== undefined) parts.push(`保存 ${res.saved}`)
          if (res.failed) parts.push(`失败 ${res.failed}`)
          if (res.error) return <Tooltip title={res.error}><Tag color="error" style={{ maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{res.error.length > 30 ? res.error.substring(0, 30) + '...' : res.error}</Tag></Tooltip>
          return <Tag color="success">{parts.join('，')}</Tag>
        }
        if (r.status === 'failed') return <Tooltip title={r.error}><Tag color="error" style={{ maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.error || '失败'}</Tag></Tooltip>
        return '-'
      },
    },
    {
      title: '耗时', key: 'duration', width: 80,
      render: (_, r) => {
        if (!r.started_at) return '-'
        const start = new Date(r.started_at).getTime()
        const end = r.finished_at ? new Date(r.finished_at).getTime() : Date.now()
        const sec = Math.round((end - start) / 1000)
        return sec > 60 ? `${Math.floor(sec / 60)}m${sec % 60}s` : `${sec}s`
      },
    },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 150, render: v => v ? v.substring(0, 19).replace('T', ' ') : '-' },
    {
      title: '操作', key: 'action', width: 120,
      render: (_, r) => (
        <Space size="small">
          <Button size="small" type="link" icon={<FileTextOutlined />} onClick={() => showDetail(r)}>
            日志
          </Button>
          {r.status !== 'running' && (
            <Popconfirm title="删除此任务？" onConfirm={() => handleDelete(r.task_id)}>
              <Button size="small" danger icon={<DeleteOutlined />} />
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  return (
    <div>
      <h2 style={{ marginBottom: 24 }}>
        任务监控
        {runningCount > 0 && <Badge count={runningCount} style={{ marginLeft: 12 }} />}
      </h2>
      <Space style={{ marginBottom: 16 }}>
        <Button onClick={() => handleFilter(null)} type={statusFilter === null ? 'primary' : 'default'}>全部 ({counts.total || 0})</Button>
        <Button onClick={() => handleFilter('running')} type={statusFilter === 'running' ? 'primary' : 'default'}>运行中 ({counts.running || 0})</Button>
        <Button onClick={() => handleFilter('pending')} type={statusFilter === 'pending' ? 'primary' : 'default'}>等待中 ({counts.pending || 0})</Button>
        <Button onClick={() => handleFilter('completed')} type={statusFilter === 'completed' ? 'primary' : 'default'}>已完成 ({counts.completed || 0})</Button>
        <Button onClick={() => handleFilter('failed')} danger={statusFilter === 'failed'} type={statusFilter === 'failed' ? 'primary' : 'default'}>失败 ({counts.failed || 0})</Button>
        <span style={{ color: '#ccc' }}>|</span>
        <Button icon={<ReloadOutlined />} onClick={() => fetchTasks(statusFilter)}>刷新</Button>
        <Popconfirm title="清理所有已完成/失败的任务？" onConfirm={handleClearCompleted}>
          <Button icon={<ClearOutlined />}>清理已完成</Button>
        </Popconfirm>
        <span style={{ color: '#999' }}>每 3 秒自动刷新</span>
      </Space>
      <Table columns={columns} dataSource={data} pagination={{ pageSize: 20, showTotal: (t) => `共 ${t} 个任务` }} />

      <Modal
        title={<Space><FileTextOutlined />任务详情 - {currentTask?.task_id}</Space>}
        open={detailVisible}
        onCancel={() => { setDetailVisible(false); clearInterval(logTimerRef.current) }}
        footer={null}
        width={800}
      >
        {currentTask && (
          <div>
            <Space size="large" style={{ marginBottom: 16 }}>
              <span><b>类型:</b> {TYPE_MAP[currentTask.task_type] || currentTask.task_type}</span>
              <span><b>状态:</b> {(() => { const s = STATUS_MAP[currentTask.status] || {}; return <Tag color={s.color}>{s.text}</Tag> })()}</span>
              <span><b>描述:</b> {currentTask.description}</span>
            </Space>
            {currentTask.result && (
              <div style={{ marginBottom: 12, padding: 8, background: '#f6ffed', borderRadius: 4, border: '1px solid #b7eb8f' }}>
                <b>结果:</b> 获取 {(currentTask.result.fetched || 0)} 条{currentTask.result.failed ? `，失败 ${currentTask.result.failed} 条` : ''}
                {currentTask.result.error && <span style={{ color: '#ff4d4f', marginLeft: 8 }}>错误: {currentTask.result.error}</span>}
              </div>
            )}
            {currentTask.error && (
              <div style={{ marginBottom: 12, padding: 8, background: '#fff2f0', borderRadius: 4, border: '1px solid #ffccc7' }}>
                <b>错误:</b> {currentTask.error}
              </div>
            )}
            <div style={{ marginBottom: 8 }}><b>日志</b> <Text type="secondary">({logs.length} 条)</Text></div>
            <div style={{
              background: '#1e1e1e', borderRadius: 6, padding: 12, maxHeight: 400, overflow: 'auto',
              fontFamily: 'Menlo, Monaco, "Courier New", monospace', fontSize: 12,
            }}>
              {logLoading ? <Text style={{ color: '#999' }}>加载中...</Text> : (
                logs.length === 0 ? <Text style={{ color: '#666' }}>暂无日志</Text> :
                logs.map((log, i) => (
                  <div key={i} style={{ lineHeight: '22px' }}>
                    <Text style={{ color: '#666' }}>[{log.time && log.time.includes('-') ? log.time.substring(0, 19) : log.time}]</Text>
                    <Text style={{ color: LOG_COLORS[log.level] || '#ccc', margin: '0 6px' }}>[{log.level}]</Text>
                    <Text style={{ color: '#d4d4d4' }}>{log.message}</Text>
                  </div>
                ))
              )}
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}
