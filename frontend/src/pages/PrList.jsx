import { useState, useEffect } from 'react'
import { Table, Button, Input, Modal, Tag, Space, message, Popconfirm } from 'antd'
import { ReloadOutlined, DeleteOutlined, SearchOutlined, DownloadOutlined, EyeOutlined, SyncOutlined } from '@ant-design/icons'
import * as api from '../api'

export default function PrList({ onNavigate, setFilter }) {
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(false)
  const [owner, setOwner] = useState('')
  const [repo, setRepo] = useState('')

  const fetchData = async () => {
    setLoading(true)
    try {
      const res = await api.getPrList({ limit: 200 })
      const projects = res.data.data || []
      const rows = []
      for (const p of projects) {
        rows.push({
          key: `${p.owner}/${p.repo}`,
          owner: p.owner,
          repo: p.repo,
          total: p.total,
        })
      }
      setData(rows)
    } catch (e) {
      message.error('获取数据失败: ' + e.message)
    }
    setLoading(false)
  }

  useEffect(() => { fetchData() }, [])

  const handleDelete = (record) => {
    Modal.confirm({
      title: '确认删除',
      content: `确定要删除 ${record.owner}/${record.repo} 的所有 PR 数据吗？此操作不可恢复。`,
      okText: '确认删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          await api.deletePrData(record.owner, record.repo)
          message.success('删除成功')
          fetchData()
        } catch (e) {
          message.error('删除失败')
        }
      },
    })
  }

  const handleViewDetails = (record) => {
    if (setFilter) setFilter({ owner: record.owner, repo: record.repo })
    if (onNavigate) onNavigate('prdata')
  }

  const handleUpdate = async (record) => {
    setLoading(true)
    try {
      const res = await api.updatePrs(record.owner, record.repo)
      message.success(`更新完成: 更新=${res.data.updated}, 新增=${res.data.added}, 未变=${res.data.unchanged}`)
      fetchData()
    } catch (e) {
      message.error('更新失败: ' + e.message)
    }
    setLoading(false)
  }

  const handleFetch = async () => {
    if (!owner || !repo) {
      message.warning('请输入 owner 和 repo')
      return
    }
    try {
      const res = await api.asyncFetchPrs(owner, repo, { max_count: 50 })
      const task = res.data.task
      if (task.status === 'running' || task.status === 'pending') {
        message.success('任务已创建，正在跳转到任务监控...')
        if (onNavigate) onNavigate('tasks')
      } else {
        message.warning(res.data.message || '任务已存在')
        if (onNavigate) onNavigate('tasks')
      }
    } catch (e) {
      message.error('创建任务失败: ' + e.message)
    }
  }

  const columns = [
    { title: 'Owner', dataIndex: 'owner', key: 'owner' },
    { title: 'Repo', dataIndex: 'repo', key: 'repo' },
    { title: 'PR 数量', dataIndex: 'total', key: 'total', render: v => <Tag color="blue">{v}</Tag> },
    {
      title: '操作', key: 'action',
      render: (_, record) => (
        <Space>
          <Button size="small" type="link" icon={<EyeOutlined />} onClick={() => handleViewDetails(record)}>
            查看数据
          </Button>
          <Button size="small" icon={<SyncOutlined />} onClick={() => handleUpdate(record)} loading={loading}>
            更新
          </Button>
          <Popconfirm
            title="删除确认"
            description={`确定删除 ${record.owner}/${record.repo} 的所有 PR 数据？`}
            okText="确认删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
            onConfirm={() => handleDelete(record)}
          >
            <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <h2 style={{ marginBottom: 24 }}>PR 数据列表</h2>
      <Space style={{ marginBottom: 16 }} wrap>
        <Input placeholder="Owner" value={owner} onChange={e => setOwner(e.target.value)} style={{ width: 150 }} />
        <Input placeholder="Repo" value={repo} onChange={e => setRepo(e.target.value)} style={{ width: 150 }} />
        <Button type="primary" icon={<DownloadOutlined />} onClick={handleFetch} loading={loading}>
          获取 PR
        </Button>
        <Button icon={<ReloadOutlined />} onClick={fetchData}>刷新</Button>
      </Space>
      <Table
        columns={columns}
        dataSource={data}
        loading={loading}
        pagination={{ pageSize: 20 }}
      />
    </div>
  )
}
