import { useState, useEffect } from 'react'
import { Table, Input, Tag, Space, Button, message } from 'antd'
import { ReloadOutlined, SearchOutlined, ArrowLeftOutlined } from '@ant-design/icons'
import * as api from '../api'

export default function PrData({ filter, onBack }) {
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [owner, setOwner] = useState(filter?.owner || '')
  const [repo, setRepo] = useState(filter?.repo || '')
  const pageSize = 20

  const fetchData = async (p = page) => {
    setLoading(true)
    try {
      const o = owner || filter?.owner
      const r = repo || filter?.repo
      if (!o || !r) {
        setLoading(false)
        return
      }
      const res = await api.getPrData(o, r)
      const prs = res.data?.data?.prs || []
      setTotal(prs.length)
      const start = (p - 1) * pageSize
      const pageData = prs.slice(start, start + pageSize).map((pr, i) => ({
        key: pr.number || i,
        ...pr,
        owner: o,
        repo: r,
      }))
      setData(pageData)
    } catch (e) {
      message.error('获取数据失败: ' + e.message)
    }
    setLoading(false)
  }

  useEffect(() => {
    if (owner || filter?.owner) fetchData(1)
  }, [filter])

  const columns = [
    {
      title: 'PR#', dataIndex: 'number', key: 'number',
      render: (v, r) => <a href={`https://github.com/${r.owner}/${r.repo}/pull/${v}`} target="_blank" rel="noreferrer">#{v}</a>,
    },
    { title: '标题', dataIndex: 'title', key: 'title', ellipsis: true },
    { title: '作者', dataIndex: 'user', key: 'user' },
    {
      title: '状态', dataIndex: 'state', key: 'state',
      render: v => <Tag color={v === 'open' ? 'green' : v === 'closed' ? 'red' : 'default'}>{v}</Tag>,
    },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 170 },
    { title: '更新时间', dataIndex: 'updated_at', key: 'updated_at', width: 170 },
  ]

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        {onBack && (
          <Button icon={<ArrowLeftOutlined />} onClick={onBack}>返回列表</Button>
        )}
        <h2 style={{ margin: 0 }}>
          {owner || filter?.owner}/{repo || filter?.repo} 的 PR 数据
        </h2>
      </Space>

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
        pagination={{
          current: page,
          total,
          pageSize,
          onChange: (p) => { setPage(p); fetchData(p) },
          showTotal: (t) => `共 ${t} 条`,
        }}
        scroll={{ x: 800 }}
      />
    </div>
  )
}
