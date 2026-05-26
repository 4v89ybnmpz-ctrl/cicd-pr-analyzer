import { useState, useEffect } from 'react'
import { Card, Form, Input, InputNumber, Button, message, Space, Tag, Spin, Descriptions, Alert, Select } from 'antd'
import { RobotOutlined, CheckCircleOutlined, CloseCircleOutlined, ReloadOutlined, ThunderboltOutlined } from '@ant-design/icons'
import * as api from '../api'

const PROVIDER_OPTIONS = [
  { value: 'openai', label: 'OpenAI 兼容', desc: '适用于 OpenAI、GLM、DeepSeek、Qwen 等兼容接口' },
  { value: 'anthropic', label: 'Anthropic', desc: '适用于 Claude 系列模型' },
]

export default function LlmConfig() {
  const [config, setConfig] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState(null)
  const [provider, setProvider] = useState('openai')
  const [form] = Form.useForm()

  const fetchConfig = async () => {
    setLoading(true)
    try {
      const res = await api.getLlmConfig()
      setConfig(res.data)
      setProvider(res.data.provider || 'openai')
      form.setFieldsValue({
        provider: res.data.provider || 'openai',
        model: res.data.model || '',
        base_url: res.data.base_url || '',
        api_key: res.data.api_key_set ? '••••••••' : '',
        max_tokens: res.data.max_tokens || 4096,
        temperature: res.data.temperature ?? 0.3,
      })
    } catch (e) {
      message.error('获取配置失败')
    }
    setLoading(false)
  }

  useEffect(() => { fetchConfig() }, [])

  const handleSave = async () => {
    const values = form.getFieldsValue()
    setSaving(true)
    try {
      const params = {}
      if (values.provider) params.provider = values.provider
      if (values.model) params.model = values.model
      if (values.base_url) params.base_url = values.base_url
      if (values.api_key && values.api_key !== '••••••••') params.api_key = values.api_key
      if (values.max_tokens) params.max_tokens = values.max_tokens
      if (values.temperature !== undefined) params.temperature = values.temperature
      await api.updateLlmConfig(params)
      message.success('配置已保存并生效')
      setTestResult(null)
      fetchConfig()
    } catch (e) {
      message.error(`保存失败: ${e.message}`)
    }
    setSaving(false)
  }

  const handleTest = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      const res = await api.testLlmConnection()
      setTestResult(res.data)
    } catch (e) {
      setTestResult({ ok: false, error: e.message })
    }
    setTesting(false)
  }

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '60px auto' }} />

  return (
    <div>
      <Card
        title={<span><RobotOutlined style={{ marginRight: 8, color: '#722ed1' }} />AI 模型配置</span>}
        extra={<Button icon={<ReloadOutlined />} onClick={fetchConfig}>刷新</Button>}
      >
        <Alert
          type={config?.ai_ready ? 'success' : 'warning'}
          message={config?.ai_ready ? 'LLM 已就绪' : 'LLM 未就绪'}
          description={config?.ai_ready
            ? `当前模型: ${config.model}，点击下方"测试连接"验证端到端可用性`
            : '请配置有效的 API Key 和 Base URL，保存后自动生效'}
          showIcon
          icon={config?.ai_ready ? <CheckCircleOutlined /> : <CloseCircleOutlined />}
          style={{ marginBottom: 24 }}
        />

        <Form form={form} layout="vertical" onFinish={handleSave}>
          <Form.Item label="接口类型" name="provider" tooltip="选择 LLM API 的兼容协议">
            <Select
              options={PROVIDER_OPTIONS.map(p => ({ value: p.value, label: `${p.label} — ${p.desc}` }))}
              onChange={v => setProvider(v)}
            />
          </Form.Item>
          <Form.Item label="模型名称" name="model" tooltip="LLM 模型标识，如 glm-5.1、claude-3-sonnet、deepseek-chat 等">
            <Input placeholder={provider === 'openai' ? 'glm-5.1 / deepseek-chat / qwen-plus' : 'claude-3-sonnet'} />
          </Form.Item>
          <Form.Item label="API Base URL" name="base_url" tooltip="LLM API 的基础地址">
            <Input placeholder={provider === 'openai' ? 'https://api.openai.com/v1' : 'https://api.anthropic.com'} />
          </Form.Item>
          <Form.Item label="API Key" name="api_key" tooltip="API 认证密钥，已配置时显示掩码">
            <Input.Password placeholder="sk-..." />
          </Form.Item>
          <Form.Item label="最大 Tokens" name="max_tokens" tooltip="单次请求最大生成 token 数">
            <InputNumber min={256} max={128000} step={1024} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="Temperature" name="temperature" tooltip="生成温度，越低越确定，越高越随机">
            <InputNumber min={0} max={1} step={0.1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit" loading={saving} icon={<RobotOutlined />}>
                保存并生效
              </Button>
              <Button loading={testing} onClick={handleTest} icon={<ThunderboltOutlined />}
                style={{ background: '#faad14', borderColor: '#faad14', color: '#fff' }}>
                测试连接
              </Button>
            </Space>
          </Form.Item>
        </Form>

        {/* 测试结果 */}
        {testResult && (
          <Alert
            type={testResult.ok ? 'success' : 'error'}
            message={testResult.ok ? '连接测试通过' : '连接测试失败'}
            description={
              testResult.ok
                ? <div>
                    <div>模型: {testResult.model} · 延迟: {testResult.latency_ms}ms</div>
                    <div style={{ color: '#666', fontSize: 12, marginTop: 4 }}>响应: {testResult.response}</div>
                  </div>
                : <div style={{ wordBreak: 'break-all', fontSize: 12 }}>{testResult.error}</div>
            }
            showIcon
            icon={testResult.ok ? <CheckCircleOutlined /> : <CloseCircleOutlined />}
            style={{ marginBottom: 16 }}
          />
        )}

        {config && (
          <Descriptions title="当前状态" bordered size="small" column={2} style={{ marginTop: 16 }}>
            <Descriptions.Item label="接口类型">
              <Tag color={config.provider === 'openai' ? 'blue' : 'purple'}>{PROVIDER_OPTIONS.find(p => p.value === config.provider)?.label || config.provider}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="模型">{config.model}</Descriptions.Item>
            <Descriptions.Item label="就绪状态">
              {config.ai_ready
                ? <Tag color="green" icon={<CheckCircleOutlined />}>已就绪</Tag>
                : <Tag color="red" icon={<CloseCircleOutlined />}>未就绪</Tag>}
            </Descriptions.Item>
            <Descriptions.Item label="API Key">{config.api_key_set ? '已设置' : '未设置'}</Descriptions.Item>
            <Descriptions.Item label="Base URL">{config.base_url || '-'}</Descriptions.Item>
            <Descriptions.Item label="Max Tokens">{config.max_tokens}</Descriptions.Item>
            <Descriptions.Item label="Temperature">{config.temperature}</Descriptions.Item>
          </Descriptions>
        )}
      </Card>
    </div>
  )
}
