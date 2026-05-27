import { useState } from 'react'
import { Table, Button, Input, Tag, Space, InputNumber, message } from 'antd'
import { SearchOutlined, ReloadOutlined } from '@ant-design/icons'
import * as api from '../../api'

const STATE_COLORS = { opened: 'green', closed: 'red', merged: 'purple', locked: 'default' }

export default function MrDetails() {
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(false)
  const [owner, setOwner] = useState('')
  const [repo, setRepo] = useState('')
  const [limit, setLimit] = useState(50)

  const fetchData = async () => {
    if (!owner || !repo) { message.warning('请输入 owner 和 repo'); return }
    setLoading(true)
    try {
      const res = await api.getGitCodeBatchDetails(owner, repo, { limit })
      const details = (res.data.results || []).map((d, i) => ({ key: d.iid || i, ...d }))
      setData(details)
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
      title: '合并状态', dataIndex: 'merge_status', width: 100,
      render: v => v ? <Tag color={v === 'can_be_merged' ? 'green' : 'orange'}>{v}</Tag> : '-',
    },
    {
      title: 'Pipeline', dataIndex: 'pipeline_status', width: 100,
      render: v => v ? <Tag color={v === 'success' ? 'green' : v === 'failed' ? 'red' : 'blue'}>{v}</Tag> : '-',
    },
    { title: '更新时间', dataIndex: 'updated_at', width: 170 },
  ]

  return (
    <div>
      <h2 style={{ marginBottom: 24 }}>
        MR 详情 <Tag color="purple">GitCode</Tag>
      </h2>
      <Space style={{ marginBottom: 16 }} wrap>
        <Input placeholder="Owner" value={owner} onChange={e => setOwner(e.target.value)} style={{ width: 180 }} />
        <Input placeholder="Repo" value={repo} onChange={e => setRepo(e.target.value)} style={{ width: 180 }}
          onPressEnter={fetchData} />
        <InputNumber min={1} max={500} value={limit} onChange={v => setLimit(v)} addonBefore="数量" style={{ width: 140 }} />
        <Button type="primary" icon={<SearchOutlined />} onClick={fetchData} loading={loading}>查询</Button>
        <Button icon={<ReloadOutlined />} onClick={fetchData}>刷新</Button>
      </Space>
      <Table
        columns={columns}
        dataSource={data}
        loading={loading}
        scroll={{ x: 1000 }}
        pagination={{ pageSize: 20, showTotal: (t) => `共 ${t} 条` }}
      />
    </div>
  )
}
