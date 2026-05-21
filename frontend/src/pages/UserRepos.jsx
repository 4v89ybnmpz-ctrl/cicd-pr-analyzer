import { useState, useEffect } from 'react'
import { Table, Tag, Space, Button, message } from 'antd'
import { ArrowLeftOutlined, ReloadOutlined } from '@ant-design/icons'
import * as api from '../api'

const EVENT_LABELS = {
  PushEvent: { label: 'Push', color: 'green' },
  PullRequestEvent: { label: 'PR', color: 'blue' },
  IssuesEvent: { label: 'Issue', color: 'orange' },
  IssueCommentEvent: { label: '评论', color: 'cyan' },
  CreateEvent: { label: '创建', color: 'default' },
  DeleteEvent: { label: '删除', color: 'default' },
  WatchEvent: { label: 'Star', color: 'gold' },
  ForkEvent: { label: 'Fork', color: 'purple' },
  ReleaseEvent: { label: 'Release', color: 'geekblue' },
}

export default function UserRepos({ username, onBack }) {
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)

  const fetchFromDB = async (p = page) => {
    setLoading(true)
    try {
      const res = await api.getUserReposFromDB({ username, page: p, size: 20, sort_by: 'total_events', sort_order: 'desc' })
      const items = (res.data.data || []).map((item, i) => ({ key: item.repo || i, ...item }))
      setData(items)
      setTotal(res.data.total || 0)
    } catch {
      setData([])
    }
    setLoading(false)
  }

  const fetchFromGithub = async () => {
    setLoading(true)
    try {
      await api.getUserRepos(username, { max_pages: 3 })
      message.success(`已获取 ${username} 的参与项目`)
      fetchFromDB(1)
    } catch (e) {
      message.error('获取失败: ' + e.message)
    }
    setLoading(false)
  }

  useEffect(() => { fetchFromDB(1) }, [username])

  const columns = [
    {
      title: '项目', dataIndex: 'repo', key: 'repo', ellipsis: true,
      render: v => <a href={`https://github.com/${v}`} target="_blank" rel="noreferrer">{v}</a>,
    },
    { title: '事件总数', dataIndex: 'total_events', key: 'total_events', width: 90, render: v => v || 0 },
    {
      title: '参与方式', dataIndex: 'event_types', key: 'event_types', width: 300,
      render: v => {
        if (!v) return '-'
        return Object.entries(v).sort((a, b) => b[1] - a[1]).map(([type, count]) => {
          const info = EVENT_LABELS[type] || { label: type.replace('Event', ''), color: 'default' }
          return <Tag key={type} color={info.color}>{info.label} ×{count}</Tag>
        })
      },
    },
  ]

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        {onBack && <Button icon={<ArrowLeftOutlined />} onClick={onBack}>返回</Button>}
        <h2 style={{ margin: 0 }}>{username} 参与的项目</h2>
      </Space>
      <Space style={{ marginBottom: 16 }}>
        <Button type="primary" onClick={fetchFromGithub} loading={loading}>从 GitHub 获取</Button>
        <Button icon={<ReloadOutlined />} onClick={() => fetchFromDB()}>刷新</Button>
      </Space>
      <Table
        columns={columns}
        dataSource={data}
        loading={loading}
        pagination={{
          current: page, total, pageSize: 20,
          onChange: (p) => { setPage(p); fetchFromDB(p) },
          showTotal: (t) => `共 ${t} 个项目`,
        }}
      />
    </div>
  )
}
