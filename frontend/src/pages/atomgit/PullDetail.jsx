import { useState } from 'react'
import { Descriptions, Button, Input, Tag, Space, message, Spin, InputNumber } from 'antd'
import { SearchOutlined, DownloadOutlined } from '@ant-design/icons'
import * as api from '../../api'

export default function PullDetail() {
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(false)
  const [fetchLoading, setFetchLoading] = useState(false)
  const [owner, setOwner] = useState('')
  const [repo, setRepo] = useState('')
  const [pullNumber, setPullNumber] = useState('')

  const fetchData = async () => {
    if (!owner || !repo || !pullNumber) { message.warning('请输入完整信息'); return }
    setLoading(true)
    try {
      const res = await api.getAtomGitPullDetail(owner, repo, pullNumber)
      setDetail(res.data.detail || null)
    } catch (e) {
      if (e.response?.status === 503) message.error('AtomGit 服务未配置')
      else message.error(e._friendlyMsg || '请求失败')
      setDetail(null)
    } finally { setLoading(false) }
  }

  // 批量获取多个 PR 详情并保存
  const [batchPrs, setBatchPrs] = useState('')
  const handleBatchFetch = async () => {
    if (!owner || !repo || !batchPrs) { message.warning('请输入 owner、repo 和 PR 编号列表'); return }
    setFetchLoading(true)
    try {
      const res = await api.getAtomGitBatchDetails(owner, repo, batchPrs)
      const d = res.data
      message.success(`批量获取完成: ${d.success_count} 成功, ${d.failed_count} 失败, 已存库 ${d.saved_to_db || 0}`)
    } catch (e) {
      message.error(e._friendlyMsg || '获取失败')
    } finally { setFetchLoading(false) }
  }

  const STATE_COLORS = { open: 'green', closed: 'red' }

  return (
    <div>
      <h2 style={{ marginBottom: 16 }}>PR 详情 <Tag color="blue">AtomGit</Tag></h2>
      <Space style={{ marginBottom: 16 }} wrap>
        <Input placeholder="Owner" value={owner} onChange={e => setOwner(e.target.value)} style={{ width: 120 }} />
        <Input placeholder="Repo" value={repo} onChange={e => setRepo(e.target.value)} style={{ width: 120 }} />
        <Input placeholder="PR #" value={pullNumber} onChange={e => setPullNumber(e.target.value)} style={{ width: 80 }} onPressEnter={fetchData} />
        <Button type="primary" icon={<SearchOutlined />} onClick={fetchData} loading={loading}>查询</Button>
      </Space>
      <Space style={{ marginBottom: 16 }} wrap>
        <Input placeholder="批量 PR 编号 (如 1,2,3)" value={batchPrs} onChange={e => setBatchPrs(e.target.value)} style={{ width: 220 }} />
        <Button icon={<DownloadOutlined />} onClick={handleBatchFetch} loading={fetchLoading}>批量获取详情（存库）</Button>
      </Space>
      {loading && <Spin style={{ display: 'block', margin: '40px auto' }} />}
      {detail && !loading && (
        <Descriptions bordered column={2} size="small">
          <Descriptions.Item label="编号">{detail.number}</Descriptions.Item>
          <Descriptions.Item label="状态"><Tag color={STATE_COLORS[detail.state] || 'default'}>{detail.state}</Tag></Descriptions.Item>
          <Descriptions.Item label="标题" span={2}>{detail.title}</Descriptions.Item>
          <Descriptions.Item label="作者">{detail.user?.login}</Descriptions.Item>
          <Descriptions.Item label="草稿">{detail.draft ? '是' : '否'}</Descriptions.Item>
          <Descriptions.Item label="源分支">{detail.head?.ref}</Descriptions.Item>
          <Descriptions.Item label="目标分支">{detail.base?.ref}</Descriptions.Item>
          <Descriptions.Item label="标签">{(detail.labels || []).map(l => <Tag key={l.name}>{l.name}</Tag>)}</Descriptions.Item>
          <Descriptions.Item label="指派人">{(detail.assignees || []).map(a => a.login).join(', ') || '-'}</Descriptions.Item>
          <Descriptions.Item label="评审人">{(detail.requested_reviewers || []).map(r => r.login).join(', ') || '-'}</Descriptions.Item>
          <Descriptions.Item label="里程碑">{detail.milestone?.title || '-'}</Descriptions.Item>
          <Descriptions.Item label="变更">+{detail.additions} / -{detail.deletions}</Descriptions.Item>
          <Descriptions.Item label="变更文件">{detail.changed_files}</Descriptions.Item>
          <Descriptions.Item label="可合并">{detail.mergeable === true ? '是' : detail.mergeable === false ? '否' : '未知'}</Descriptions.Item>
          <Descriptions.Item label="已合并">{detail.merged ? '是' : '否'}</Descriptions.Item>
          <Descriptions.Item label="评论">{detail.comments}</Descriptions.Item>
          <Descriptions.Item label="Review 评论">{detail.review_comments}</Descriptions.Item>
          <Descriptions.Item label="创建时间">{detail.created_at}</Descriptions.Item>
          <Descriptions.Item label="更新时间">{detail.updated_at}</Descriptions.Item>
          {detail.body && <Descriptions.Item label="描述" span={2}><pre style={{ maxHeight: 200, overflow: 'auto', margin: 0, whiteSpace: 'pre-wrap' }}>{detail.body}</pre></Descriptions.Item>}
        </Descriptions>
      )}
    </div>
  )
}
