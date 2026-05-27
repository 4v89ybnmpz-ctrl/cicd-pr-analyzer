import { useState } from 'react'
import { Table, Button, Input, Tag, Space, Select, message } from 'antd'
import { SearchOutlined, ReloadOutlined } from '@ant-design/icons'
import * as api from '../../api'

const STATE_OPTIONS = [
  { value: 'all', label: '全部' },
  { value: 'opened', label: '打开' },
  { value: 'closed', label: '关闭' },
  { value: 'merged', label: '已合并' },
]

const STATE_COLORS = { opened: 'green', closed: 'red', merged: 'purple', locked: 'default' }

export default function MrList() {
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(false)
  const [owner, setOwner] = useState('')
  const [repo, setRepo] = useState('')
  const [state, setState] = useState('all')
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)

  const fetchData = async (p = page) => {
    if (!owner || !repo) { message.warning('请输入 owner 和 repo'); return }
    setLoading(true)
    try {
      const res = await api.getGitCodeMrs(owner, repo, { state, page: p, per_page: 20 })
      const mrs = (res.data.results || []).map((mr, i) => ({ key: mr.iid || i, ...mr }))
      setData(mrs)
      setTotal(res.data.total_mrs || mrs.length)
      setPage(p)
    } catch (e) {
      const msg = e.response?.status === 503 ? 'GitCode 服务未配置' : '查询失败: ' + e.message
      message.error(msg)
      setData([])
    }
    setLoading(false)
  }

  const columns = [
    {
      title: 'IID', dataIndex: 'iid', width: 70,
      render: v => <a href={`https://gitcode.net/${owner}/${repo}/-/merge_requests/${v}`} target="_blank" rel="noreferrer">!{v}</a>,
    },
    { title: '标题', dataIndex: 'title', ellipsis: true },
    {
      title: '状态', dataIndex: 'state', width: 80,
      render: v => <Tag color={STATE_COLORS[v] || 'default'}>{v}</Tag>,
    },
    { title: '作者', dataIndex: 'author', width: 120, render: v => v?.name || v?.username || '-' },
    {
      title: '标签', dataIndex: 'labels', width: 200,
      render: v => v?.length > 0
        ? v.slice(0, 3).map((l, i) => <Tag key={i}>{l}</Tag>)
        : <span style={{ color: '#d9d9d9' }}>-</span>,
    },
    { title: '创建时间', dataIndex: 'created_at', width: 170 },
  ]

  return (
    <div>
      <h2 style={{ marginBottom: 24 }}>
        MR 列表 <Tag color="purple">GitCode</Tag>
      </h2>
      <Space style={{ marginBottom: 16 }} wrap>
        <Input placeholder="Owner (如 openeuler)" value={owner} onChange={e => setOwner(e.target.value)} style={{ width: 180 }} />
        <Input placeholder="Repo (如 kernel)" value={repo} onChange={e => setRepo(e.target.value)} style={{ width: 180 }}
          onPressEnter={() => fetchData(1)} />
        <Select value={state} onChange={setState} options={STATE_OPTIONS} style={{ width: 100 }} />
        <Button type="primary" icon={<SearchOutlined />} onClick={() => fetchData(1)} loading={loading}>查询</Button>
        <Button icon={<ReloadOutlined />} onClick={() => fetchData()}>刷新</Button>
      </Space>
      <Table
        columns={columns}
        dataSource={data}
        loading={loading}
        scroll={{ x: 900 }}
        pagination={{
          current: page, total, pageSize: 20,
          onChange: (p) => fetchData(p),
          showTotal: (t) => `共 ${t} 条`,
        }}
      />
    </div>
  )
}
