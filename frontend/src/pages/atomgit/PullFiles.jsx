import { useState } from 'react'
import { Table, Button, Input, Tag, Space, message } from 'antd'
import { SearchOutlined, ReloadOutlined, DownloadOutlined } from '@ant-design/icons'
import * as api from '../../api'

const STATUS_COLORS = { added: 'green', modified: 'blue', removed: 'red', renamed: 'orange' }

export default function PullFiles() {
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
      const res = await api.getAtomGitPullFiles(owner, repo, pullNumber)
      setData(res.data.files || [])
    } catch (e) {
      if (e.response?.status === 503) message.error('AtomGit 服务未配置')
      else message.error(e._friendlyMsg || '请求失败')
    } finally { setLoading(false) }
  }

  const handleBatchFetch = async () => {
    if (!owner || !repo || !batchPrs) { message.warning('请输入 owner、repo 和 PR 编号列表'); return }
    setFetchLoading(true)
    try {
      const res = await api.getAtomGitBatchFiles(owner, repo, batchPrs)
      const d = res.data
      message.success(`批量获取完成: ${d.success_count} 成功, ${d.failed_count} 失败, 已存库 ${d.saved_to_db || 0}`)
    } catch (e) {
      message.error(e._friendlyMsg || '获取失败')
    } finally { setFetchLoading(false) }
  }

  const columns = [
    { title: '文件', dataIndex: 'filename', ellipsis: true },
    { title: '状态', dataIndex: 'status', width: 90, render: v => <Tag color={STATUS_COLORS[v] || 'default'}>{v}</Tag> },
    { title: '+', dataIndex: 'additions', width: 60, render: v => <span style={{ color: '#52c41a' }}>+{v}</span> },
    { title: '-', dataIndex: 'deletions', width: 60, render: v => <span style={{ color: '#ff4d4f' }}>-{v}</span> },
    { title: '变更', dataIndex: 'changes', width: 60 },
  ]

  return (
    <div>
      <h2 style={{ marginBottom: 16 }}>PR 变更文件 <Tag color="blue">AtomGit</Tag></h2>
      <Space style={{ marginBottom: 16 }} wrap>
        <Input placeholder="Owner" value={owner} onChange={e => setOwner(e.target.value)} style={{ width: 120 }} />
        <Input placeholder="Repo" value={repo} onChange={e => setRepo(e.target.value)} style={{ width: 120 }} />
        <Input placeholder="PR #" value={pullNumber} onChange={e => setPullNumber(e.target.value)} style={{ width: 80 }} onPressEnter={fetchData} />
        <Button type="primary" icon={<SearchOutlined />} onClick={fetchData} loading={loading}>查询</Button>
        <Button icon={<ReloadOutlined />} onClick={fetchData}>刷新</Button>
      </Space>
      <Space style={{ marginBottom: 16 }} wrap>
        <Input placeholder="批量 PR 编号 (如 1,2,3)" value={batchPrs} onChange={e => setBatchPrs(e.target.value)} style={{ width: 220 }} />
        <Button icon={<DownloadOutlined />} onClick={handleBatchFetch} loading={fetchLoading}>批量获取变更文件（存库）</Button>
      </Space>
      <Table columns={columns} dataSource={data} rowKey="filename" loading={loading} size="small" />
    </div>
  )
}
