import { useState } from 'react'
import { Table, Button, Input, Tag, Space, InputNumber, message } from 'antd'
import { SearchOutlined, ReloadOutlined, DownloadOutlined } from '@ant-design/icons'
import * as api from '../../api'

export default function PullComments() {
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(false)
  const [fetchLoading, setFetchLoading] = useState(false)
  const [owner, setOwner] = useState('')
  const [repo, setRepo] = useState('')
  const [pullNumber, setPullNumber] = useState('')
  const [fetchLimit, setFetchLimit] = useState(10)

  const fetchData = async () => {
    if (!owner || !repo || !pullNumber) { message.warning('请输入完整信息'); return }
    setLoading(true)
    try {
      const res = await api.getAtomGitPullComments(owner, repo, pullNumber)
      setData(res.data.comments || [])
    } catch (e) {
      if (e.response?.status === 503) message.error('AtomGit 服务未配置')
      else message.error(e._friendlyMsg || '请求失败')
    } finally { setLoading(false) }
  }

  // 批量获取评论并保存到数据库
  const handleBatchFetch = async () => {
    if (!owner || !repo) { message.warning('请输入 owner 和 repo'); return }
    setFetchLoading(true)
    try {
      const res = await api.getAtomGitBatchComments(owner, repo, { limit: fetchLimit })
      const d = res.data
      message.success(`获取完成: ${d.total_prs} 个 PR, ${d.total_comments} 条评论, 已存库 ${d.saved_to_db} 个`)
    } catch (e) {
      message.error(e._friendlyMsg || '获取失败')
    } finally { setFetchLoading(false) }
  }

  const columns = [
    { title: 'ID', dataIndex: 'id', width: 70 },
    { title: '作者', dataIndex: 'user', width: 120 },
    { title: 'Bot', dataIndex: 'is_bot', width: 50, render: v => v ? <Tag color="orange">Bot</Tag> : '-' },
    { title: '内容', dataIndex: 'body', ellipsis: true, render: v => v?.slice(0, 150) },
    { title: '创建时间', dataIndex: 'created_at', width: 170, render: v => v?.slice(0, 19) },
  ]

  return (
    <div>
      <h2 style={{ marginBottom: 16 }}>PR 评论 <Tag color="blue">AtomGit</Tag></h2>
      <Space style={{ marginBottom: 16 }} wrap>
        <Input placeholder="Owner" value={owner} onChange={e => setOwner(e.target.value)} style={{ width: 120 }} />
        <Input placeholder="Repo" value={repo} onChange={e => setRepo(e.target.value)} style={{ width: 120 }} />
        <Input placeholder="PR #" value={pullNumber} onChange={e => setPullNumber(e.target.value)} style={{ width: 80 }} onPressEnter={fetchData} />
        <Button type="primary" icon={<SearchOutlined />} onClick={fetchData} loading={loading}>查询</Button>
        <Button icon={<ReloadOutlined />} onClick={fetchData}>刷新</Button>
      </Space>
      <Space style={{ marginBottom: 16 }} wrap>
        <InputNumber min={1} max={500} value={fetchLimit} onChange={v => setFetchLimit(v)} style={{ width: 80 }} />
        <Button icon={<DownloadOutlined />} onClick={handleBatchFetch} loading={fetchLoading}>
          批量获取评论（存库）
        </Button>
      </Space>
      <Table columns={columns} dataSource={data} rowKey="id" loading={loading} size="small" />
    </div>
  )
}
