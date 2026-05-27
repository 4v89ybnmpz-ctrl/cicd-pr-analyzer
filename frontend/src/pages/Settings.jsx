import { useState, useEffect } from 'react'
import { Tabs, Card, Input, Button, Space, message, Descriptions, Alert } from 'antd'
import { SettingOutlined, RobotOutlined, BellOutlined, ApiOutlined, GlobalOutlined, CheckCircleOutlined } from '@ant-design/icons'
import LlmConfig from './LlmConfig'
import NotificationConfig from './NotificationConfig'
import WebhookManager from './WebhookManager'
import * as api from '../api'

function ProxyConfig() {
  const [proxy, setProxy] = useState('')
  const [envProxy, setEnvProxy] = useState('')
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  const fetchProxy = async () => {
    setLoading(true)
    try {
      const res = await api.getProxyConfig()
      setProxy(res.data.proxy || '')
      setEnvProxy(res.data.env_proxy || '')
    } catch (e) {
      message.error('加载代理配置失败')
    }
    setLoading(false)
  }

  useEffect(() => { fetchProxy() }, [])

  const handleSave = async () => {
    setSaving(true)
    setSaved(false)
    try {
      const res = await api.updateProxyConfig(proxy.trim())
      message.success(res.data.message)
      setSaved(true)
    } catch (e) {
      message.error(`保存失败: ${e.message}`)
    }
    setSaving(false)
  }

  return (
    <div>
      <Card title={<span><GlobalOutlined style={{ marginRight: 8 }} />代理配置</span>} size="small" style={{ maxWidth: 600 }}>
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="配置 HTTP/HTTPS 代理后，Git clone/fetch 操作将通过代理访问 GitHub"
        />
        <div style={{ marginBottom: 16 }}>
          <div style={{ marginBottom: 4, fontWeight: 500 }}>代理地址</div>
          <Space.Compact style={{ width: '100%' }}>
            <Input
              placeholder="例如: http://127.0.0.1:7890 或 socks5://127.0.0.1:1080"
              value={proxy}
              onChange={e => { setProxy(e.target.value); setSaved(false) }}
              onPressEnter={handleSave}
            />
            <Button type="primary" onClick={handleSave} loading={saving} icon={saved ? <CheckCircleOutlined /> : null}>
              {saving ? '保存中' : '保存'}
            </Button>
          </Space.Compact>
        </div>
        {envProxy && (
          <Descriptions size="small" bordered column={1}>
            <Descriptions.Item label="环境变量 HTTPS_PROXY">
              <code>{envProxy}</code>
            </Descriptions.Item>
          </Descriptions>
        )}
      </Card>
    </div>
  )
}

const TAB_ITEMS = [
  {
    key: 'proxy',
    label: <span><GlobalOutlined /> 代理配置</span>,
    children: <ProxyConfig />,
  },
  {
    key: 'llm',
    label: <span><RobotOutlined /> AI 模型</span>,
    children: <LlmConfig />,
  },
  {
    key: 'notification',
    label: <span><BellOutlined /> 通知配置</span>,
    children: <NotificationConfig />,
  },
  {
    key: 'webhook',
    label: <span><ApiOutlined /> Webhook</span>,
    children: <WebhookManager />,
  },
]

export default function Settings() {
  return (
    <div>
      <h2 style={{ marginBottom: 20 }}><SettingOutlined style={{ marginRight: 8 }} />系统设置</h2>
      <Tabs items={TAB_ITEMS} size="small" />
    </div>
  )
}
