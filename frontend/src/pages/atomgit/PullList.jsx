import { useState } from 'react'
import { Table, Button, Input, Tag, Space, Select, InputNumber, message, Modal } from 'antd'
import { SearchOutlined, ReloadOutlined, DownloadOutlined, CloudDownloadOutlined } from '@ant-design/icons'
import * as api from '../../api'

const STATE_OPTIONS = [
  { value: 'all', label: '全部' },
  { value: 'open', label: '打开' },
  { value: 'closed', label: '关闭' },
]
const STATE_COLORS = { open: 'green', closed: 'red' }

export default function PullList() {
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(false)
  const [fetchLoading, setFetchLoading] = useState(false)
  const [owner, setOwner] = useState('')
  const [repo, setRepo] = useState('')
  const [state, setState] = useState('all')
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)

  const fetchData = async (p = page) => {
    if (!owner || !repo) { message.warning('请输入 owner 和 repo'); return }
    setLoading(true)
    try {
      const res = await api.getAtomGitPulls(owner, repo, { state, page: p, size: 20 })
      setData(res.data.pulls || [])
      setTotal(res.data.total || 0)
      setPage(p)
    } catch (e) {
      if (e.response?.status === 503) message.error('AtomGit 服务未配置')
      else message.error(e._friendlyMsg || '请求失败')
    } finally { setLoading(false) }
  }

  // 批量获取 PR 评论并保存到数据库
  const handleFetchComments = async () => {
    if (!owner || !repo) { message.warning('请输入 owner 和 repo'); return }
    setFetchLoading(true)
    try {
      const res = await api.getAtomGitBatchComments(owner, repo, { limit: 10, state })
      const d = res.data
      message.success(`获取完成: ${d.total_prs} 个 PR, ${d.total_comments} 条评论, 已存库 ${d.saved_to_db} 个`)
    } catch (e) {
      message.error(e._friendlyMsg || '获取失败')
    } finally { setFetchLoading(false) }
  }

  // 全量获取整个项目的 PR 评论
  const handleFetchAllComments = () => {
    if (!owner || !repo) { message.warning('请输入 owner 和 repo'); return }
    Modal.confirm({
      title: '全量获取 PR 评论',
      content: `将获取 ${owner}/${repo} 所有 PR 的评论并保存到数据库，可能耗时较长，确认继续？`,
      okText: '确认获取',
      onOk: async () => {
        setFetchLoading(true)
        try {
          const res = await api.getAtomGitAllComments(owner, repo, { state, skip_no_comments: true })
          const d = res.data
          message.success(`全量获取完成: ${d.total_prs} 个 PR, ${d.total_comments} 条评论, 已存库 ${d.saved_to_db} 个`)
        } catch (e) {
          message.error(e._friendlyMsg || '获取失败')
        } finally { setFetchLoading(false) }
      },
    })
  }

  const columns = [
    { title: '#', dataIndex: 'number', width: 70, render: v => <a href={`https://atomgit.com/${owner}/${repo}/pulls/${v}`} target="_blank" rel="noreferrer">{v}</a> },
    { title: '标题', dataIndex: 'title', ellipsis: true },
    { title: '状态', dataIndex: 'state', width: 80, render: v => <Tag color={STATE_COLORS[v] || 'default'}>{v}</Tag> },
    { title: '作者', dataIndex: 'user', width: 120 },
    { title: 'Bot', dataIndex: 'is_bot', width: 50, render: v => v ? <Tag color="orange">Bot</Tag> : '-' },
    { title: '评论', dataIndex: 'comments_count', width: 60 },
    { title: '创建时间', dataIndex: 'created_at', width: 170, render: v => v?.slice(0, 19) },
  ]

  return (
    <div>
      <h2 style={{ marginBottom: 16 }}>PR 列表 <Tag color="blue">AtomGit</Tag></h2>
      <Space style={{ marginBottom: 16 }} wrap>
        <Input placeholder="Owner" value={owner} onChange={e => setOwner(e.target.value)} style={{ width: 150 }} />
        <Input placeholder="Repo" value={repo} onChange={e => setRepo(e.target.value)} style={{ width: 150 }} onPressEnter={() => fetchData(1)} />
        <Select value={state} onChange={setState} options={STATE_OPTIONS} style={{ width: 100 }} />
        <Button type="primary" icon={<SearchOutlined />} onClick={() => fetchData(1)} loading={loading}>查询</Button>
        <Button icon={<ReloadOutlined />} onClick={() => fetchData()}>刷新</Button>
      </Space>
      <Space style={{ marginBottom: 16 }} wrap>
        <Button icon={<DownloadOutlined />} onClick={handleFetchComments} loading={fetchLoading}>
          批量获取评论（存库）
        </Button>
        <Button icon={<CloudDownloadOutlined />} onClick={handleFetchAllComments} loading={fetchLoading}>
          全量获取评论（存库）
        </Button>
      </Space>
      <Table
        columns={columns} dataSource={data} rowKey="number" loading={loading}
        pagination={{ current: page, pageSize: 20, total, showTotal: t => `共 ${t} 条`, onChange: fetchData }}
        size="small"
      />
    </div>
  )
}
