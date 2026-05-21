import { useState, useEffect } from 'react'
import { Table, Input, Tag, Space, Button, message } from 'antd'
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import * as api from '../api'

export default function Comments() {
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(false)
  const [owner, setOwner] = useState('')
  const [repo, setRepo] = useState('')
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)

  const fetchData = async (p = page) => {
    setLoading(true)
    try {
      const params = { page: p, size: 20, sort_by: 'created_at', sort_order: 'desc' }
      if (owner) params.owner = owner
      if (repo) params.repo = repo
      const res = await api.getComments(params)
      const items = (res.data.data || []).map((item, i) => ({ key: item.comment_id || i, ...item }))
      setData(items)
      setTotal(res.data.total || 0)
    } catch (e) {
      setData([])
    }
    setLoading(false)
  }

  useEffect(() => { fetchData(1) }, [])

  const columns = [
    { title: 'Owner', dataIndex: 'owner', key: 'owner' },
    { title: 'Repo', dataIndex: 'repo', key: 'repo' },
    {
      title: 'PR#', dataIndex: 'pr_number', key: 'pr_number',
      render: (v, r) => <a href={`https://github.com/${r.owner}/${r.repo}/pull/${v}`} target="_blank" rel="noreferrer">#{v}</a>,
    },
    { title: '用户', dataIndex: 'user', key: 'user' },
    {
      title: 'Bot', dataIndex: 'is_bot', key: 'is_bot',
      render: v => v ? <Tag color="orange">Bot</Tag> : <Tag>Human</Tag>,
    },
    {
      title: '内容', dataIndex: 'body', key: 'body', ellipsis: true,
      render: v => (v || '').substring(0, 100),
    },
    { title: '时间', dataIndex: 'created_at', key: 'created_at', width: 170 },
  ]

  return (
    <div>
      <h2 style={{ marginBottom: 24 }}>PR 评论</h2>
      <Space style={{ marginBottom: 16 }} wrap>
        <Input placeholder="Owner" value={owner} onChange={e => setOwner(e.target.value)} style={{ width: 150 }} />
        <Input placeholder="Repo" value={repo} onChange={e => setRepo(e.target.value)} style={{ width: 150 }} />
        <Button type="primary" icon={<SearchOutlined />} onClick={() => { setPage(1); fetchData(1) }}>搜索</Button>
        <Button icon={<ReloadOutlined />} onClick={() => fetchData()}>刷新</Button>
      </Space>
      <Table
        columns={columns}
        dataSource={data}
        loading={loading}
        pagination={{ current: page, total, pageSize: 20, onChange: (p) => { setPage(p); fetchData(p) }, showTotal: (t) => `共 ${t} 条` }}
        scroll={{ x: 900 }}
      />
    </div>
  )
}
