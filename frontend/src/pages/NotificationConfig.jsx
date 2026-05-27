import { useState, useEffect } from 'react'
import {
  Card, Form, Input, Switch, Select, Button, Space, message, Spin, Alert,
  Checkbox, InputNumber, Row, Col, Modal, Tag, Divider,
} from 'antd'
import {
  PlusOutlined, ReloadOutlined, DeleteOutlined, SendOutlined, BellOutlined, SettingOutlined,
} from '@ant-design/icons'
import * as api from '../api'

const CHANNEL_OPTIONS = [
  { label: '邮件', value: 'email' },
  { label: '飞书', value: 'feishu' },
  { label: '钉钉', value: 'dingtalk' },
  { label: 'Slack', value: 'slack' },
]

const METRIC_OPTIONS = [
  { value: 'health_score', label: '健康度分数' },
  { value: 'ci_failure_rate', label: 'CI 失败率' },
  { value: 'review_delay', label: 'Review 延迟(小时)' },
  { value: 'trend_alert', label: '趋势预警数量' },
]

const OPERATOR_OPTIONS = [
  { value: 'lt', label: '< 小于' },
  { value: 'lte', label: '<= 小于等于' },
  { value: 'gt', label: '> 大于' },
  { value: 'gte', label: '>= 大于等于' },
  { value: 'eq', label: '= 等于' },
]

const SEVERITY_OPTIONS = [
  { value: 'critical', label: '严重' },
  { value: 'warning', label: '警告' },
  { value: 'info', label: '信息' },
]

export default function NotificationConfig() {
  const [configs, setConfigs] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [showModal, setShowModal] = useState(false)
  const [form] = Form.useForm()

  const fetchConfigs = async () => {
    setLoading(true)
    try {
      const res = await api.getNotificationConfigs()
      setConfigs(res.data.data || [])
    } catch (e) {
      message.error('加载配置失败')
    }
    setLoading(false)
  }

  useEffect(() => { fetchConfigs() }, [])

  // 新建配置
  const handleCreate = () => {
    setEditingId(null)
    form.resetFields()
    form.setFieldsValue({
      name: '', enabled: true, channels: [],
      channel_settings: {}, rules: [], schedule: 'on_complete',
    })
    setShowModal(true)
  }

  // 编辑配置
  const handleEdit = (config) => {
    setEditingId(config.config_id)
    form.setFieldsValue({
      name: config.name,
      enabled: config.enabled,
      channels: config.channels || [],
      channel_settings: config.channel_settings || {},
      rules: (config.rules || []).map(r => ({ ...r })),
      schedule: config.schedule || 'on_complete',
    })
    setShowModal(true)
  }

  // 保存配置
  const handleSave = async () => {
    try {
      const values = await form.validateFields()
      setSaving(true)

      const data = {
        name: values.name,
        enabled: values.enabled,
        channels: values.channels || [],
        channel_settings: values.channel_settings || {},
        rules: (values.rules || []).filter(r => r && r.metric),
        schedule: values.schedule || 'on_complete',
      }

      if (editingId) {
        data.config_id = editingId
      }

      const res = editingId
        ? await api.updateNotificationConfig(editingId, data)
        : await api.createNotificationConfig(data)

      if (res.data.data) {
        message.success(editingId ? '配置已更新' : '配置已创建')
        setShowModal(false)
        fetchConfigs()
      }
    } catch (e) {
      if (e.errorFields) return
      message.error(`保存失败: ${e.message}`)
    } finally {
      setSaving(false)
    }
  }

  // 删除配置
  const handleDelete = (configId) => {
    Modal.confirm({
      title: '确认删除',
      content: '删除后不可恢复，确认要删除此通知配置吗？',
      okType: 'danger',
      onOk: async () => {
        try {
          await api.deleteNotificationConfig(configId)
          message.success('已删除')
          fetchConfigs()
        } catch (e) {
          message.error(`删除失败: ${e.message}`)
        }
      },
    })
  }

  // 测试发送
  const handleTest = async (configId) => {
    try {
      message.loading({ content: '正在发送测试通知...', key: 'test', duration: 0 })
      const res = await api.testNotificationConfig(configId)
      if (res.data.sent) {
        message.success({ content: '测试通知发送成功', key: 'test' })
      } else {
        message.warning({ content: `测试发送失败: ${res.data.message}`, key: 'test' })
      }
    } catch (e) {
      message.error({ content: `测试失败: ${e.message}`, key: 'test' })
    }
  }

  // 监听渠道变化
  const selectedChannels = Form.useWatch('channels', form) || []

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />

  return (
    <div>
      <Row gutter={[16, 16]} align="middle" style={{ marginBottom: 24 }}>
        <Col><h2 style={{ margin: 0 }}><BellOutlined style={{ marginRight: 8, color: '#1890ff' }} />通知配置</h2></Col>
        <Col flex="auto" />
        <Col>
          <Space>
            <Button icon={<PlusOutlined />} type="primary" onClick={handleCreate}>新建配置</Button>
            <Button icon={<ReloadOutlined />} onClick={fetchConfigs}>刷新</Button>
          </Space>
        </Col>
      </Row>

      {configs.length === 0 ? (
        <Card>
          <div style={{ textAlign: 'center', padding: 40, color: '#999' }}>
            <BellOutlined style={{ fontSize: 40, marginBottom: 16 }} />
            <div style={{ fontSize: 16, marginBottom: 8 }}>暂无通知配置</div>
            <div>点击"新建配置"创建你的第一条通知规则</div>
          </div>
        </Card>
      ) : (
        <Row gutter={[16, 16]}>
          {configs.map(config => (
            <Col xs={24} key={config.config_id}>
              <Card
                title={
                  <Space>
                    <Tag color={config.enabled ? 'green' : 'default'}>{config.enabled ? '已启用' : '已禁用'}</Tag>
                    <span style={{ fontWeight: 600 }}>{config.name}</span>
                  </Space>
                }
                extra={
                  <Space>
                    <Button size="small" icon={<SendOutlined />} onClick={() => handleTest(config.config_id)}>测试</Button>
                    <Button size="small" icon={<SettingOutlined />} onClick={() => handleEdit(config)}>编辑</Button>
                    <Button size="small" danger icon={<DeleteOutlined />} onClick={() => handleDelete(config.config_id)}>删除</Button>
                  </Space>
                }
              >
                <Row gutter={[16, 8]}>
                  <Col xs={24} md={8}>
                    <span style={{ color: '#666' }}>通知渠道：</span>
                    {(config.channels || []).map((ch, i) => (
                      <Tag key={i} color="blue">{ch}</Tag>
                    ))}
                  </Col>
                  <Col xs={24} md={8}>
                    <span style={{ color: '#666' }}>触发方式：</span>
                    <Tag>{config.schedule === 'on_complete' ? '分析完成后' : config.schedule}</Tag>
                  </Col>
                  <Col xs={24} md={8}>
                    <span style={{ color: '#666' }}>规则数：</span>
                    <Tag>{(config.rules || []).length} 条</Tag>
                  </Col>
                </Row>
                {(config.rules || []).length > 0 && (
                  <div style={{ marginTop: 8 }}>
                    {config.rules.map((rule, i) => (
                      <Tag key={i} style={{ marginBottom: 4 }}>
                        {rule.project_pattern || '*'} · {rule.metric} {rule.operator} {rule.threshold} ({rule.severity})
                      </Tag>
                    ))}
                  </div>
                )}
              </Card>
            </Col>
          ))}
        </Row>
      )}

      {/* 新建/编辑弹窗 */}
      <Modal
        title={editingId ? '编辑通知配置' : '新建通知配置'}
        open={showModal}
        onCancel={() => setShowModal(false)}
        onOk={handleSave}
        confirmLoading={saving}
        width={700}
        okText="保存"
      >
        <Form form={form} layout="vertical">
          <Row gutter={16}>
            <Col span={18}>
              <Form.Item name="name" label="配置名称" rules={[{ required: true, message: '请输入配置名称' }]}>
                <Input placeholder="例如：CI 失败告警" />
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item name="enabled" label="启用" valuePropName="checked">
                <Switch />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item name="channels" label="通知渠道" rules={[{ required: true, message: '请选择至少一个渠道' }]}>
            <Checkbox.Group options={CHANNEL_OPTIONS} />
          </Form.Item>

          {/* 渠道参数 */}
          {selectedChannels.includes('email') && (
            <Card size="small" title="邮件配置" style={{ marginBottom: 16 }}>
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item name={['channel_settings', 'email', 'smtp_host']} label="SMTP 服务器">
                    <Input placeholder="smtp.example.com" />
                  </Form.Item>
                </Col>
                <Col span={6}>
                  <Form.Item name={['channel_settings', 'email', 'smtp_port']} label="端口">
                    <InputNumber style={{ width: '100%' }} placeholder={587} />
                  </Form.Item>
                </Col>
                <Col span={6}>
                  <Form.Item name={['channel_settings', 'email', 'use_tls']} label="TLS" valuePropName="checked">
                    <Switch defaultChecked />
                  </Form.Item>
                </Col>
              </Row>
              <Row gutter={16}>
                <Col span={8}>
                  <Form.Item name={['channel_settings', 'email', 'sender']} label="发件人">
                    <Input placeholder="noreply@example.com" />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item name={['channel_settings', 'email', 'username']} label="用户名">
                    <Input />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item name={['channel_settings', 'email', 'password']} label="密码">
                    <Input.Password />
                  </Form.Item>
                </Col>
              </Row>
              <Form.Item name={['channel_settings', 'email', 'recipients']} label="收件人（逗号分隔）">
                <Input placeholder="user1@example.com, user2@example.com" />
              </Form.Item>
            </Card>
          )}

          {selectedChannels.includes('feishu') && (
            <Card size="small" title="飞书配置" style={{ marginBottom: 16 }}>
              <Form.Item name={['channel_settings', 'feishu', 'webhook_url']} label="Webhook URL">
                <Input placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/xxx" />
              </Form.Item>
            </Card>
          )}

          {selectedChannels.includes('dingtalk') && (
            <Card size="small" title="钉钉配置" style={{ marginBottom: 16 }}>
              <Form.Item name={['channel_settings', 'dingtalk', 'webhook_url']} label="Webhook URL">
                <Input placeholder="https://oapi.dingtalk.com/robot/send?access_token=xxx" />
              </Form.Item>
              <Form.Item name={['channel_settings', 'dingtalk', 'secret']} label="签名密钥（可选）">
                <Input.Password placeholder="SEC..." />
              </Form.Item>
            </Card>
          )}

          {selectedChannels.includes('slack') && (
            <Card size="small" title="Slack 配置" style={{ marginBottom: 16 }}>
              <Form.Item name={['channel_settings', 'slack', 'webhook_url']} label="Webhook URL">
                <Input placeholder="https://hooks.slack.com/services/xxx" />
              </Form.Item>
            </Card>
          )}

          <Form.Item name="schedule" label="触发方式">
            <Select options={[
              { value: 'on_complete', label: '分析完成后自动发送' },
            ]} />
          </Form.Item>

          <Divider>通知规则</Divider>

          <Form.List name="rules">
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name, ...restField }) => (
                  <Row key={key} gutter={8} align="middle" style={{ marginBottom: 8 }}>
                    <Col span={5}>
                      <Form.Item {...restField} name={[name, 'project_pattern']} style={{ marginBottom: 0 }}>
                        <Input placeholder="项目 (*/owner/repo)" />
                      </Form.Item>
                    </Col>
                    <Col span={6}>
                      <Form.Item {...restField} name={[name, 'metric']} style={{ marginBottom: 0 }}>
                        <Select options={METRIC_OPTIONS} placeholder="指标" allowClear />
                      </Form.Item>
                    </Col>
                    <Col span={4}>
                      <Form.Item {...restField} name={[name, 'operator']} style={{ marginBottom: 0 }}>
                        <Select options={OPERATOR_OPTIONS} placeholder="操作符" />
                      </Form.Item>
                    </Col>
                    <Col span={4}>
                      <Form.Item {...restField} name={[name, 'threshold']} style={{ marginBottom: 0 }}>
                        <InputNumber style={{ width: '100%' }} placeholder="阈值" />
                      </Form.Item>
                    </Col>
                    <Col span={3}>
                      <Form.Item {...restField} name={[name, 'severity']} style={{ marginBottom: 0 }}>
                        <Select options={SEVERITY_OPTIONS} placeholder="级别" />
                      </Form.Item>
                    </Col>
                    <Col span={2}>
                      <Button type="text" danger onClick={() => remove(name)}>删除</Button>
                    </Col>
                  </Row>
                ))}
                <Button type="dashed" onClick={() => add({ project_pattern: '*', operator: 'gt', severity: 'warning' })} block icon={<PlusOutlined />}>
                  添加规则
                </Button>
              </>
            )}
          </Form.List>
        </Form>
      </Modal>
    </div>
  )
}
