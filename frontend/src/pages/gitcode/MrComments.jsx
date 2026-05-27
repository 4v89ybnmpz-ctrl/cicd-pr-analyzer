import { useState } from 'react'
import { Table, Button, Input, Tag, Space, message } from 'antd'
import { SearchOutlined, ReloadOutlined } from '@ant-design/icons'
import * as api from '../../api'

export default function MrComments() {
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(false)
  const [owner, setOwner] = useState('')
  const [repo, setRepo] = useState('')
  const [mrIid, setMrIid] = useState('')

  const fetchData = async () => {
    if (!owner || !repo || !mrIid) { message.warning('请输入 owner、repo 和 MR IID'); return }
    setLoading(true)
    try {
      const res = await api.getGitCodeMrComments(owner, repo, mrIid)
      const comments = (res.data.comments || []).map((c, i) => ({ key: c.id || i, ...c }))
      setData(comments)
    } catch (e) {
      const msg = e.response?.status === 503 ? 'GitCode 服务未配置' : '查询失败: ' + e.message
      message.error(msg)
      setData([])
    }
    setLoading(false)
  }

  const columns = [
    {
      title: '作者', dataIndex: 'author', width: 130,
      render: v => v?.name || v?.username || '-',
    },
    {
      title: 'Bot', width: 60,
      render: (_, r) => r.system ? <Tag color="blue">系统</Tag> : <Tag>User</Tag>,
    },
    {
      title: '内容', dataIndex: 'body', ellipsis: true,
      render: v => (v || '').substring(0, 150),
    },
    { title: '创建时间', dataIndex: 'created_at', width: 170 },
  ]

  return (
    <div>
      <h2 style={{ marginBottom: 24 }}>
        MR 评论 <Tag color="purple">GitCode</Tag>
      </h2>
      <Space style={{ marginBottom: 16 }} wrap>
        <Input placeholder="Owner" value={owner} onChange={e => setOwner(e.target.value)} style={{ width: 150 }} />
        <Input placeholder="Repo" value={repo} onChange={e => setRepo(e.target.value)} style={{ width: 150 }} />
        <Input placeholder="MR IID (如 123)" value={mrIid} onChange={e => setMrIid(e.target.value)} style={{ width: 140 }}
          onPressEnter={fetchData} />
        <Button type="primary" icon={<SearchOutlined />} onClick={fetchData} loading={loading}>查询</Button>
        <Button icon={<ReloadOutlined />} onClick={fetchData}>刷新</Button>
      </Space>
      <Table
        columns={columns}
        dataSource={data}
        loading={loading}
        scroll={{ x: 700 }}
        pagination={{ pageSize: 20, showTotal: (t) => `共 ${t} 条评论` }}
      />
    </div>
  )
}
