import { useState } from 'react'
import { Table, Button, Input, Tag, Space, message } from 'antd'
import { SearchOutlined, ReloadOutlined, DownloadOutlined } from '@ant-design/icons'
import * as api from '../../api'

export default function PullCommits() {
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(false)
  const [fetchLoading, setFetchLoading] = useState(false)
  const [owner, setOwner] = useState('')
  const [repo, setRepo] = useState('')
  const [pullNumber, setPullNumber] = useState('')
  const [batchPrs, setBatchPrs] = useState('')

  const fetchData = async () => {
    if (!owner || !repo || !pullNumber) { message.warning('请输入完整信息'); return }
    setLoading(true)
    try {
      const res = await api.getAtomGitPullCommits(owner, repo, pullNumber)
      setData(res.data.commits || [])
    } catch (e) {
      if (e.response?.status === 503) message.error('AtomGit 服务未配置')
      else message.error(e._friendlyMsg || '请求失败')
    } finally { setLoading(false) }
  }

  const handleBatchFetch = async () => {
    if (!owner || !repo || !batchPrs) { message.warning('请输入 owner、repo 和 PR 编号列表'); return }
    setFetchLoading(true)
    try {
      const res = await api.getAtomGitBatchCommits(owner, repo, batchPrs)
      const d = res.data
      message.success(`批量获取完成: ${d.success_count} 成功, ${d.failed_count} 失败, 已存库 ${d.saved_to_db || 0}`)
    } catch (e) {
      message.error(e._friendlyMsg || '获取失败')
    } finally { setFetchLoading(false) }
  }

  const columns = [
    { title: 'SHA', dataIndex: 'sha', width: 100, render: v => <code>{v?.slice(0, 8)}</code> },
    { title: '消息', dataIndex: 'message', ellipsis: true },
    { title: '作者', dataIndex: 'author_name', width: 120 },
    { title: '验证', dataIndex: 'verified', width: 60, render: v => v ? <Tag color="green">已验证</Tag> : <Tag>未验证</Tag> },
    { title: '日期', dataIndex: 'author_date', width: 170, render: v => v?.slice(0, 19) },
  ]

  return (
    <div>
      <h2 style={{ marginBottom: 16 }}>PR Commits <Tag color="blue">AtomGit</Tag></h2>
      <Space style={{ marginBottom: 16 }} wrap>
        <Input placeholder="Owner" value={owner} onChange={e => setOwner(e.target.value)} style={{ width: 120 }} />
        <Input placeholder="Repo" value={repo} onChange={e => setRepo(e.target.value)} style={{ width: 120 }} />
        <Input placeholder="PR #" value={pullNumber} onChange={e => setPullNumber(e.target.value)} style={{ width: 80 }} onPressEnter={fetchData} />
        <Button type="primary" icon={<SearchOutlined />} onClick={fetchData} loading={loading}>查询</Button>
        <Button icon={<ReloadOutlined />} onClick={fetchData}>刷新</Button>
      </Space>
      <Space style={{ marginBottom: 16 }} wrap>
        <Input placeholder="批量 PR 编号 (如 1,2,3)" value={batchPrs} onChange={e => setBatchPrs(e.target.value)} style={{ width: 220 }} />
        <Button icon={<DownloadOutlined />} onClick={handleBatchFetch} loading={fetchLoading}>批量获取 Commits（存库）</Button>
      </Space>
      <Table columns={columns} dataSource={data} rowKey="sha" loading={loading} size="small" />
    </div>
  )
}
