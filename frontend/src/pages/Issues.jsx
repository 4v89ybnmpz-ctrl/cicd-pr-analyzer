import { useState, useEffect } from 'react'
import { Table, Input, Tag, Space, Button, message } from 'antd'
import { ReloadOutlined, SearchOutlined, DownloadOutlined, SyncOutlined } from '@ant-design/icons'
import * as api from '../api'

export default function Issues({ onNavigate }) {
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [owner, setOwner] = useState('')
  const [repo, setRepo] = useState('')
  const [stateFilter, setStateFilter] = useState('')
  const [fetchOwner, setFetchOwner] = useState('rust-lang')
  const [fetchRepo, setFetchRepo] = useState('rust')
  const [fetchCount, setFetchCount] = useState(50)

  const fetchFromDB = async (p = page) => {
    setLoading(true)
    try {
      const params = { page: p, size: 20, sort_by: 'created_at', sort_order: 'desc' }
      if (owner) params.owner = owner
      if (repo) params.repo = repo
      if (stateFilter) params.state = stateFilter
      const res = await api.getIssues(params)
      const items = (res.data.data || []).map((item, i) => ({ key: item.number || i, ...item }))
      setData(items)
      setTotal(res.data.total || 0)
    } catch (e) {
      message.error('获取数据失败: ' + e.message)
    }
    setLoading(false)
  }

  useEffect(() => { fetchFromDB(1) }, [])

  const fetchFromGithub = async () => {
    if (!fetchOwner || !fetchRepo) {
      message.warning('请输入 owner 和 repo')
      return
    }
    try {
      const res = await api.asyncFetchIssues(fetchOwner, fetchRepo, { max_count: fetchCount })
      const task = res.data.task
      if (task.status === 'running' || task.status === 'pending') {
        message.success('任务已创建，正在跳转到任务监控...')
        if (onNavigate) onNavigate('tasks')
      } else {
        message.warning(res.data.message || '任务已存在')
        if (onNavigate) onNavigate('tasks')
      }
    } catch (e) {
      message.error('创建任务失败: ' + e.message)
    }
  }

  const handleUpdate = async () => {
    if (!owner || !repo) {
      message.warning('请先筛选指定仓库')
      return
    }
    setLoading(true)
    try {
      const res = await api.updateIssues(owner, repo)
      message.success(`更新完成: 更新=${res.data.updated}, 新增=${res.data.added}, 未变=${res.data.unchanged}`)
      fetchFromDB(1)
    } catch (e) {
      message.error('更新失败: ' + e.message)
    }
    setLoading(false)
  }

  const columns = [
    {
      title: 'Issue#', dataIndex: 'number', key: 'number', width: 80,
      render: (v, r) => <a href={r.url} target="_blank" rel="noreferrer">#{v}</a>,
    },
    { title: '标题', dataIndex: 'title', key: 'title', ellipsis: true },
    {
      title: '状态', dataIndex: 'state', key: 'state', width: 70,
      render: v => <Tag color={v === 'open' ? 'green' : 'red'}>{v}</Tag>,
    },
    { title: '作者', dataIndex: 'user', key: 'user', width: 120 },
    {
      title: '标签', dataIndex: 'labels', key: 'labels', width: 200,
      render: v => (v || []).slice(0, 3).map((l, i) => <Tag key={i}>{l}</Tag>),
    },
    {
      title: '评论', dataIndex: 'comments_count', key: 'comments_count', width: 60,
      render: v => v || 0,
    },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 170 },
  ]

  return (
    <div>
      <h2 style={{ marginBottom: 24 }}>Issues</h2>

      <Space style={{ marginBottom: 12 }} wrap>
        <Input placeholder="Owner (获取)" value={fetchOwner} onChange={e => setFetchOwner(e.target.value)} style={{ width: 130 }} />
        <Input placeholder="Repo (获取)" value={fetchRepo} onChange={e => setFetchRepo(e.target.value)} style={{ width: 130 }} />
        <Input placeholder="数量" type="number" value={fetchCount} onChange={e => setFetchCount(Number(e.target.value))} style={{ width: 70 }} />
        <Button type="primary" icon={<DownloadOutlined />} onClick={fetchFromGithub} loading={loading}>
          从 GitHub 获取
        </Button>
      </Space>

      <Space style={{ marginBottom: 16 }} wrap>
        <Input placeholder="Owner (筛选)" value={owner} onChange={e => setOwner(e.target.value)} style={{ width: 130 }} />
        <Input placeholder="Repo (筛选)" value={repo} onChange={e => setRepo(e.target.value)} style={{ width: 130 }} />
        <Input placeholder="状态 (open/closed)" value={stateFilter} onChange={e => setStateFilter(e.target.value)} style={{ width: 120 }} />
        <Button type="primary" icon={<SearchOutlined />} onClick={() => { setPage(1); fetchFromDB(1) }}>搜索</Button>
        <Button icon={<SyncOutlined />} onClick={handleUpdate} loading={loading}>更新数据</Button>
        <Button icon={<ReloadOutlined />} onClick={() => fetchFromDB()}>刷新</Button>
      </Space>

      <Table
        columns={columns}
        dataSource={data}
        loading={loading}
        pagination={{
          current: page, total, pageSize: 20,
          onChange: (p) => { setPage(p); fetchFromDB(p) },
          showTotal: (t) => `共 ${t} 条`,
        }}
        scroll={{ x: 900 }}
      />
    </div>
  )
}
