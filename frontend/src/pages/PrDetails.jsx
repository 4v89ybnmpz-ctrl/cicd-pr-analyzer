import { useState, useEffect } from 'react'
import { Table, Input, Tag, Space, Button } from 'antd'
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import * as api from '../api'

export default function PrDetails() {
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(false)
  const [owner, setOwner] = useState('')
  const [repo, setRepo] = useState('')
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)

  const fetchData = async (p = page) => {
    setLoading(true)
    try {
      const params = { page: p, size: 20, sort_by: 'updated_at', sort_order: 'desc' }
      if (owner) params.owner = owner
      if (repo) params.repo = repo
      const res = await api.getDetails(params)
      const items = (res.data.items || []).map((item, i) => ({
        key: item.pr_number || i,
        ...item,
      }))
      setData(items)
      setTotal(res.data.total || 0)
    } catch (e) {
      setData([])
    }
    setLoading(false)
  }

  useEffect(() => { fetchData(1) }, [])

  const columns = [
    {
      title: 'PR', dataIndex: 'pr_number', key: 'pr_number',
      render: (v, r) => <a href={r.url || `https://github.com/${r.owner}/${r.repo}/pull/${v}`} target="_blank" rel="noreferrer">#{v}</a>,
    },
    { title: '标题', dataIndex: 'title', key: 'title', ellipsis: true },
    {
      title: '状态', dataIndex: 'state', key: 'state',
      render: v => <Tag color={v === 'open' ? 'green' : v === 'closed' ? 'red' : 'default'}>{v}</Tag>,
    },
    { title: '作者', dataIndex: 'user', key: 'user', ellipsis: true },
    { title: 'Owner', dataIndex: 'owner', key: 'owner' },
    { title: 'Repo', dataIndex: 'repo', key: 'repo' },
    { title: '更新时间', dataIndex: 'updated_at', key: 'updated_at', width: 170 },
  ]

  return (
    <div>
      <h2 style={{ marginBottom: 24 }}>PR 详情</h2>
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
        pagination={{ current: page, total, pageSize: 20, onChange: (p) => { setPage(p); fetchData(p) } }}
        scroll={{ x: 900 }}
      />
    </div>
  )
}
