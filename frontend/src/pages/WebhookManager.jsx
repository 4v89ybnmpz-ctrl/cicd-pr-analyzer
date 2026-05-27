import { useState, useEffect } from 'react'
import {
  Card, Form, Input, Switch, Button, Space, Table, Tag, Select, Row, Col, message, Spin, Alert, Divider,
} from 'antd'
import {
  ApiOutlined, ReloadOutlined, SaveOutlined, CopyOutlined, CheckCircleOutlined, InfoCircleOutlined,
} from '@ant-design/icons'
import * as api from '../api'

export default function WebhookManager() {
  const [config, setConfig] = useState(null)
  const [events, setEvents] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [sourceFilter, setSourceFilter] = useState(null)
  const [form] = Form.useForm()

  const fetchConfig = async () => {
    try {
      const res = await api.getWebhookConfig()
      setConfig(res.data.data || {})
      form.setFieldsValue({
        github_secret: '',
        gitcode_token: '',
        auto_sync: res.data.data?.auto_sync !== false,
      })
    } catch (e) { /* 静默 */ }
  }

  const fetchEvents = async (p = page) => {
    try {
      const params = { page: p, size: 20 }
      if (sourceFilter) params.source = sourceFilter
      const res = await api.getWebhookEvents(params)
      setEvents(res.data.data || [])
      setTotal(res.data.total || 0)
    } catch (e) { /* 静默 */ }
  }

  useEffect(() => {
    Promise.all([fetchConfig(), fetchEvents(1)]).finally(() => setLoading(false))
  }, [])

  useEffect(() => { fetchEvents(1) }, [sourceFilter])

  const handleSave = async () => {
    try {
      const values = await form.validateFields()
      setSaving(true)
      await api.updateWebhookConfig({
        github_secret: values.github_secret || undefined,
        gitcode_token: values.gitcode_token || undefined,
        auto_sync: values.auto_sync,
      })
      message.success('配置已保存')
      fetchConfig()
    } catch (e) {
      if (e.errorFields) return
      message.error(`保存失败: ${e.message}`)
    } finally {
      setSaving(false)
    }
  }

  const copyUrl = (path) => {
    const base = window.location.origin + '/api'
    navigator.clipboard.writeText(base + path)
    message.success('已复制到剪贴板')
  }

  const columns = [
    {
      title: '来源', dataIndex: 'source', width: 90,
      render: (s) => <Tag color={s === 'github' ? 'blue' : 'orange'}>{s === 'github' ? 'GitHub' : 'GitCode'}</Tag>,
    },
    { title: '事件类型', dataIndex: 'event_type', width: 130, render: (t) => <Tag>{t}</Tag> },
    { title: 'Action', dataIndex: 'action', width: 100, ellipsis: true },
    {
      title: '项目', width: 180,
      render: (_, r) => r.owner && r.repo ? `${r.owner}/${r.repo}` : '-',
    },
    {
      title: '状态', dataIndex: 'processed', width: 80,
      render: (p) => <Tag color={p ? 'green' : 'default'} icon={p ? <CheckCircleOutlined /> : null}>
        {p ? '已处理' : '待处理'}
      </Tag>,
    },
    {
      title: '摘要', dataIndex: 'payload_summary', ellipsis: true,
      render: (s) => {
        if (!s) return '-'
        const parts = Object.entries(s).map(([k, v]) => `${k}=${v}`).join(', ')
        return parts
      },
    },
    {
      title: '时间', dataIndex: 'created_at', width: 170,
      render: (t) => t ? new Date(t).toLocaleString('zh-CN') : '-',
    },
  ]

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />

  return (
    <div>
      <Row gutter={[16, 16]} align="middle" style={{ marginBottom: 24 }}>
        <Col><h2 style={{ margin: 0 }}><ApiOutlined style={{ marginRight: 8, color: '#1890ff' }} />Webhook 管理</h2></Col>
      </Row>

      {/* 配置区 */}
      <Card title="Webhook 配置" style={{ marginBottom: 16 }}>
        <Alert
          type="info" showIcon icon={<InfoCircleOutlined />}
          message="配置指引"
          description={
            <div style={{ fontSize: 13 }}>
              <p style={{ margin: '4px 0' }}>
                <strong>GitHub:</strong> 在仓库 Settings → Webhooks → Add webhook，Payload URL 填入下方地址，Content type 选 JSON，Secret 填入下方配置的密钥。
              </p>
              <p style={{ margin: '4px 0' }}>
                <strong>GitCode:</strong> 在仓库 Settings → Webhooks，URL 填入下方地址，Token 填入下方配置的令牌。
              </p>
              <Space style={{ marginTop: 8 }}>
                <Tag color="blue" style={{ cursor: 'pointer' }} onClick={() => copyUrl('/webhooks/github')}>
                  <CopyOutlined /> GitHub: /api/webhooks/github
                </Tag>
                <Tag color="orange" style={{ cursor: 'pointer' }} onClick={() => copyUrl('/webhooks/gitcode')}>
                  <CopyOutlined /> GitCode: /api/webhooks/gitcode
                </Tag>
              </Space>
            </div>
          }
          style={{ marginBottom: 16 }}
        />

        <Form form={form} layout="vertical">
          <Row gutter={16}>
            <Col xs={24} md={8}>
              <Form.Item name="github_secret" label="GitHub Webhook Secret">
                <Input.Password placeholder="输入 GitHub Webhook Secret" />
              </Form.Item>
            </Col>
            <Col xs={24} md={8}>
              <Form.Item name="gitcode_token" label="GitCode Webhook Token">
                <Input.Password placeholder="输入 GitCode Webhook Token" />
              </Form.Item>
            </Col>
            <Col xs={24} md={4}>
              <Form.Item name="auto_sync" label="自动同步" valuePropName="checked">
                <Switch />
              </Form.Item>
            </Col>
            <Col xs={24} md={4}>
              <Form.Item label=" ">
                <Button type="primary" icon={<SaveOutlined />} onClick={handleSave} loading={saving}>保存</Button>
              </Form.Item>
            </Col>
          </Row>
        </Form>

        {config && (
          <div style={{ color: '#666', fontSize: 12 }}>
            当前状态: GitHub Secret {config.github_secret_set ? '已配置' : '未配置'} | GitCode Token {config.gitcode_token_set ? '已配置' : '未配置'} | 自动同步: {config.auto_sync ? '开启' : '关闭'}
          </div>
        )}
      </Card>

      {/* 事件日志 */}
      <Card
        title="事件日志"
        extra={
          <Space>
            <Select
              value={sourceFilter}
              onChange={v => { setSourceFilter(v); setPage(1) }}
              allowClear
              placeholder="来源"
              style={{ width: 120 }}
              options={[
                { value: null, label: '全部' },
                { value: 'github', label: 'GitHub' },
                { value: 'gitcode', label: 'GitCode' },
              ]}
            />
            <Button icon={<ReloadOutlined />} onClick={() => fetchEvents(page)}>刷新</Button>
          </Space>
        }
      >
        <Table
          columns={columns}
          dataSource={events}
          rowKey={(r) => r.event_id || r._id || Math.random()}
          pagination={{
            current: page, total, pageSize: 20,
            onChange: (p) => { setPage(p); fetchEvents(p) },
            showTotal: (t) => `共 ${t} 条`,
          }}
          scroll={{ x: 900 }}
          size="middle"
        />
      </Card>
    </div>
  )
}
