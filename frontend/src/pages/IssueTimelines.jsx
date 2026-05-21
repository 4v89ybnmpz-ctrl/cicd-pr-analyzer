import { useState, useEffect } from 'react'
import { Table, Input, Tag, Space, Button, message, Tooltip } from 'antd'
import { ReloadOutlined, SearchOutlined, DownloadOutlined } from '@ant-design/icons'
import * as api from '../api'

const EVENT_COLORS = {
  labeled: 'blue', unlabeled: 'default', commented: 'green',
  closed: 'red', reopened: 'orange', merged: 'purple',
  assigned: 'cyan', unassigned: 'default', referenced: 'geekblue',
  subscribed: 'default', mentioned: 'gold', milestoned: 'lime',
  demilestoned: 'volcano', renamed: 'blue', cross_referenced: 'geekblue',
  head_ref_deleted: 'red', head_ref_restored: 'green',
}

export default function IssueTimelines({ onNavigate }) {
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [owner, setOwner] = useState('')
  const [repo, setRepo] = useState('')
  const [issueNumber, setIssueNumber] = useState('')
  const [fetchOwner, setFetchOwner] = useState('rust-lang')
  const [fetchRepo, setFetchRepo] = useState('rust')
  const [fetchLimit, setFetchLimit] = useState(5)

  const fetchFromDB = async (p = page) => {
    setLoading(true)
    try {
      const params = { page: p, size: 20, sort_by: 'created_at', sort_order: 'desc' }
      if (owner) params.owner = owner
      if (repo) params.repo = repo
      if (issueNumber) params.issue_number = issueNumber
      const res = await api.getIssueTimelines(params)
      const items = (res.data.data || []).map((item, i) => ({ key: item.event_id || i, ...item }))
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
      const res = await api.asyncFetchTimelines(fetchOwner, fetchRepo, { limit: fetchLimit })
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

  const columns = [
    { title: 'Issue#', dataIndex: 'issue_number', key: 'issue_number', width: 70, fixed: 'left' },
    {
      title: '类型', dataIndex: 'is_pr', key: 'is_pr', width: 65,
      render: v => v ? <Tag color="purple">PR</Tag> : <Tag color="blue">Issue</Tag>,
    },
    {
      title: '事件类型', dataIndex: 'event_type', key: 'event_type', width: 110,
      render: v => <Tag color={EVENT_COLORS[v] || 'default'}>{v}</Tag>,
    },
    {
      title: '触发者', dataIndex: 'actor', key: 'actor', width: 120,
      render: v => v ? <a href={`https://github.com/${v}`} target="_blank" rel="noreferrer">{v}</a> : '-',
    },
    {
      title: '标签', dataIndex: 'label', key: 'label', width: 130,
      render: (v, r) => v ? <Tag color={`#${r.label_color || '1677ff'}`}>{v}</Tag> : '-',
    },
    {
      title: '指派给', dataIndex: 'assignee', key: 'assignee', width: 110,
      render: v => v || '-',
    },
    {
      title: '里程碑', dataIndex: 'milestone', key: 'milestone', width: 110,
      render: v => v || '-',
    },
    {
      title: '内容/评论', dataIndex: 'body', key: 'body', width: 200, ellipsis: true,
      render: v => v ? <Tooltip title={v}><span>{v.substring(0, 80)}</span></Tooltip> : '-',
    },
    {
      title: '状态', dataIndex: 'state', key: 'state', width: 70,
      render: v => v ? <Tag color={v === 'open' ? 'green' : 'red'}>{v}</Tag> : '-',
    },
    {
      title: '来源', dataIndex: 'source_issue_url', key: 'source', width: 100,
      render: v => v ? <a href={v} target="_blank" rel="noreferrer">链接</a> : '-',
    },
    {
      title: 'Commit', dataIndex: 'commit_id', key: 'commit_id', width: 80,
      render: v => v ? <Tooltip title={v}><code style={{ fontSize: 12 }}>{v.substring(0, 7)}</code></Tooltip> : '-',
    },
    { title: '时间', dataIndex: 'created_at', key: 'created_at', width: 170 },
  ]

  return (
    <div>
      <h2 style={{ marginBottom: 24 }}>Issue Timelines</h2>

      <Space style={{ marginBottom: 12 }} wrap>
        <Input placeholder="Owner (获取)" value={fetchOwner} onChange={e => setFetchOwner(e.target.value)} style={{ width: 130 }} />
        <Input placeholder="Repo (获取)" value={fetchRepo} onChange={e => setFetchRepo(e.target.value)} style={{ width: 130 }} />
        <Input placeholder="Issue数量" type="number" value={fetchLimit} onChange={e => setFetchLimit(Number(e.target.value))} style={{ width: 80 }} />
        <Button type="primary" icon={<DownloadOutlined />} onClick={fetchFromGithub} loading={loading}>
          从 GitHub 获取
        </Button>
      </Space>

      <Space style={{ marginBottom: 16 }} wrap>
        <Input placeholder="Owner (筛选)" value={owner} onChange={e => setOwner(e.target.value)} style={{ width: 130 }} />
        <Input placeholder="Repo (筛选)" value={repo} onChange={e => setRepo(e.target.value)} style={{ width: 130 }} />
        <Input placeholder="Issue# (筛选)" value={issueNumber} onChange={e => setIssueNumber(e.target.value)} style={{ width: 80 }} />
        <Button type="primary" icon={<SearchOutlined />} onClick={() => { setPage(1); fetchFromDB(1) }}>搜索</Button>
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
        scroll={{ x: 1200 }}
      />
    </div>
  )
}
