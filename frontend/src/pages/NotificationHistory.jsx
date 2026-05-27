import { useState, useEffect } from 'react'
import { Table, Tag, Space, Button, Select, Spin, Row, Col, Tooltip, message } from 'antd'
import { ReloadOutlined, HistoryOutlined, DeleteOutlined } from '@ant-design/icons'
import * as api from '../api'

const STATUS_MAP = {
  success: { color: 'green', label: '成功' },
  failed: { color: 'red', label: '失败' },
}

const CHANNEL_COLORS = {
  email: 'blue',
  feishu: 'purple',
  dingtalk: 'cyan',
  slack: 'geekblue',
}

export default function NotificationHistory() {
  const [data, setData] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [statusFilter, setStatusFilter] = useState(null)
  const [configs, setConfigs] = useState([])
  const [configFilter, setConfigFilter] = useState(null)

  const fetchData = async (p = page) => {
    setLoading(true)
    try {
      const params = { page: p, size: 20 }
      if (statusFilter) params.status = statusFilter
      if (configFilter) params.config_id = configFilter
      const res = await api.getNotificationHistory(params)
      setData(res.data.data || [])
      setTotal(res.data.total || 0)
    } catch (e) {
      message.error('加载历史记录失败')
    }
    setLoading(false)
  }

  // 加载配置列表（用于筛选）
  const fetchConfigs = async () => {
    try {
      const res = await api.getNotificationConfigs()
      setConfigs(res.data.data || [])
    } catch (e) { /* 静默 */ }
  }

  useEffect(() => { fetchConfigs() }, [])

  useEffect(() => { fetchData(1) }, [statusFilter, configFilter])

  const columns = [
    {
      title: '配置名称',
      dataIndex: 'config_name',
      key: 'config_name',
      width: 180,
      ellipsis: true,
    },
    {
      title: '渠道',
      dataIndex: 'channel',
      key: 'channel',
      width: 100,
      render: (ch) => <Tag color={CHANNEL_COLORS[ch] || 'default'}>{ch}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 80,
      render: (status) => {
        const cfg = STATUS_MAP[status] || { color: 'default', label: status }
        return <Tag color={cfg.color}>{cfg.label}</Tag>
      },
    },
    {
      title: '主题',
      dataIndex: 'subject',
      key: 'subject',
      ellipsis: true,
      render: (text) => (
        <Tooltip title={text} placement="topLeft">
          <span>{text || '-'}</span>
        </Tooltip>
      ),
    },
    {
      title: '触发类型',
      dataIndex: 'trigger_type',
      key: 'trigger_type',
      width: 120,
      render: (t) => {
        const labels = { analysis_complete: '分析完成', test: '手动测试', scheduled: '定时触发' }
        return <Tag>{labels[t] || t}</Tag>
      },
    },
    {
      title: '错误信息',
      dataIndex: 'error',
      key: 'error',
      width: 200,
      ellipsis: true,
      render: (err) => err ? (
        <Tooltip title={err}><span style={{ color: '#ff4d4f' }}>{err}</span></Tooltip>
      ) : '-',
    },
    {
      title: '发送时间',
      dataIndex: 'sent_at',
      key: 'sent_at',
      width: 170,
      render: (t) => t ? new Date(t).toLocaleString('zh-CN') : '-',
    },
  ]

  return (
    <div>
      <Row gutter={[16, 16]} align="middle" style={{ marginBottom: 24 }}>
        <Col><h2 style={{ margin: 0 }}><HistoryOutlined style={{ marginRight: 8, color: '#1890ff' }} />通知历史</h2></Col>
      </Row>

      <Space style={{ marginBottom: 16 }} wrap>
        <Select
          value={statusFilter}
          onChange={v => { setStatusFilter(v); setPage(1) }}
          allowClear
          placeholder="状态筛选"
          style={{ width: 120 }}
          options={[
            { value: null, label: '全部状态' },
            { value: 'success', label: '成功' },
            { value: 'failed', label: '失败' },
          ]}
        />
        <Select
          value={configFilter}
          onChange={v => { setConfigFilter(v); setPage(1) }}
          allowClear
          placeholder="配置筛选"
          style={{ width: 200 }}
          options={configs.map(c => ({ value: c.config_id, label: c.name }))}
        />
        <Button icon={<ReloadOutlined />} onClick={() => fetchData(page)}>刷新</Button>
      </Space>

      <Table
        columns={columns}
        dataSource={data}
        loading={loading}
        rowKey={(r) => r.history_id || r._id || Math.random()}
        pagination={{
          current: page,
          total,
          pageSize: 20,
          onChange: (p) => { setPage(p); fetchData(p) },
          showTotal: (t) => `共 ${t} 条`,
        }}
        scroll={{ x: 1000 }}
        size="middle"
      />
    </div>
  )
}
