import { useState, useEffect } from 'react'
import { Tabs, Card, Input, Button, Space, message, Descriptions, Alert, Tag, Popconfirm, Progress, Tooltip } from 'antd'
import { SettingOutlined, RobotOutlined, BellOutlined, ApiOutlined, GlobalOutlined, CheckCircleOutlined, KeyOutlined, PlusOutlined, DeleteOutlined, EyeInvisibleOutlined, EyeOutlined, SyncOutlined, ClockCircleOutlined } from '@ant-design/icons'
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

function formatReset(seconds) {
  if (!seconds || seconds <= 0) return '-'
  if (seconds < 60) return `${Math.ceil(seconds)}秒`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}分${Math.ceil(seconds % 60)}秒`
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  return `${h}时${m}分`
}

function RateLimitBar({ remaining, limit, resetInSeconds }) {
  if (remaining == null || limit == null || limit === 0) return <span style={{ color: '#999' }}>未知</span>
  const pct = Math.round((remaining / limit) * 100)
  const color = pct > 50 ? '#52c41a' : pct > 20 ? '#faad14' : '#ff4d4f'
  return (
    <Tooltip title={`剩余 ${remaining}/${limit}，${resetInSeconds > 0 ? formatReset(resetInSeconds) + '后重置' : '已可重置'}`}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <Progress percent={pct} size="small" strokeColor={color} style={{ width: 80, margin: 0 }} showInfo={false} />
        <span style={{ fontSize: 12, color }}>{remaining}/{limit}</span>
        {resetInSeconds > 0 && (
          <span style={{ fontSize: 11, color: '#999' }}><ClockCircleOutlined /> {formatReset(resetInSeconds)}</span>
        )}
      </div>
    </Tooltip>
  )
}

function TokenPoolConfig({ platform, label, color, getFn, updateFn, checkFn }) {
  const [maskedTokens, setMaskedTokens] = useState([])
  const [totalCount, setTotalCount] = useState(0)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [checking, setChecking] = useState(false)
  const [newToken, setNewToken] = useState('')
  const [checkResults, setCheckResults] = useState(null)
  const [lastCheckTime, setLastCheckTime] = useState(null)

  const fetchTokens = async () => {
    setLoading(true)
    try {
      const res = await getFn()
      setMaskedTokens(res.data.tokens || [])
      setTotalCount(res.data.total || 0)
    } catch (e) {
      message.error('加载 Token 失败: ' + (e._friendlyMsg || e.message))
    }
    setLoading(false)
  }

  useEffect(() => { fetchTokens() }, [])

  const handleAdd = async () => {
    const trimmed = newToken.trim()
    if (!trimmed) { message.warning('请输入 Token'); return }
    setSaving(true)
    try {
      const res = await updateFn({ action: 'add', token: trimmed })
      message.success(res.data.message)
      setNewToken('')
      fetchTokens()
    } catch (e) {
      message.error('添加失败: ' + (e._friendlyMsg || e.message))
    }
    setSaving(false)
  }

  const handleRemove = async (index) => {
    setSaving(true)
    try {
      const res = await updateFn({ action: 'remove', index })
      message.success(res.data.message)
      setCheckResults(null)
      fetchTokens()
    } catch (e) {
      message.error('删除失败: ' + (e._friendlyMsg || e.message))
    }
    setSaving(false)
  }

  const handleCheck = async () => {
    if (!checkFn) return
    setChecking(true)
    try {
      const res = await checkFn()
      setCheckResults(res.data.tokens || [])
      setLastCheckTime(res.data.timestamp)
      message.success(`检测完成: ${res.data.total} 个 Token`)
    } catch (e) {
      message.error('检测失败: ' + (e._friendlyMsg || e.message))
    }
    setChecking(false)
  }

  return (
    <Card title={<span><KeyOutlined style={{ marginRight: 8 }} />{label} Token 池</span>} size="small" style={{ maxWidth: 750 }}>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message={`配置 ${label} API 访问令牌，支持多个 Token 轮换使用以避免速率限制。Token 仅脱敏显示，不会明文暴露。`}
      />
      <div style={{ marginBottom: 16 }}>
        <Space style={{ marginBottom: 8 }} wrap>
          <Input.Password
            placeholder={`输入新的 ${label} Token`}
            value={newToken}
            onChange={e => setNewToken(e.target.value)}
            onPressEnter={handleAdd}
            style={{ width: 350 }}
            iconRender={visible => visible ? <EyeOutlined /> : <EyeInvisibleOutlined />}
          />
          <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd} loading={saving}>添加</Button>
        </Space>
      </div>
      {maskedTokens.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <div style={{ marginBottom: 8, fontWeight: 500, display: 'flex', alignItems: 'center', gap: 8 }}>
            已配置 <Tag color={color}>{totalCount}</Tag> 个 Token
            {checkFn && (
              <Button size="small" icon={<SyncOutlined />} onClick={handleCheck} loading={checking}>
                检测额度
              </Button>
            )}
            {lastCheckTime && (
              <span style={{ fontSize: 11, color: '#999' }}>上次检测: {lastCheckTime?.slice(11, 19)}</span>
            )}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {maskedTokens.map((t, i) => {
              const check = checkResults?.[i]
              return (
                <div key={i} style={{ padding: '8px 12px', background: check?.valid === false ? '#fff2f0' : '#fafafa', borderRadius: 4, border: `1px solid ${check?.valid === false ? '#ffccc7' : '#f0f0f0'}` }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Tag color={color} style={{ minWidth: 24, textAlign: 'center' }}>#{i + 1}</Tag>
                    <code style={{ flex: 1, fontSize: 13, userSelect: 'none' }}>{t}</code>
                    {check?.valid === true && <Tag color="green">有效</Tag>}
                    {check?.valid === false && <Tag color="red">无效</Tag>}
                    {check?.valid === null && check?.error && <Tag color="orange">检测失败</Tag>}
                    <Popconfirm
                      title="确认删除此 Token？"
                      okText="删除"
                      okButtonProps={{ danger: true }}
                      onConfirm={() => handleRemove(i)}
                    >
                      <Button type="text" size="small" danger icon={<DeleteOutlined />} />
                    </Popconfirm>
                  </div>
                  {/* GitHub 额度详情 */}
                  {check?.valid && platform === 'github' && check.core && (
                    <div style={{ marginTop: 6, paddingLeft: 32, fontSize: 12 }}>
                      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
                        <span>Core: <RateLimitBar remaining={check.core.remaining} limit={check.core.limit} resetInSeconds={check.core.reset_in_seconds} /></span>
                        <span>Search: <RateLimitBar remaining={check.search?.remaining} limit={check.search?.limit} resetInSeconds={check.search?.reset_in_seconds} /></span>
                        <span>GraphQL: <RateLimitBar remaining={check.graphql?.remaining} limit={check.graphql?.limit} resetInSeconds={check.graphql?.reset_in_seconds} /></span>
                      </div>
                    </div>
                  )}
                  {/* AtomGit 额度详情 */}
                  {check?.valid && platform === 'atomgit' && check.rate_limit && (
                    <div style={{ marginTop: 6, paddingLeft: 32, fontSize: 12 }}>
                      <span>API: <RateLimitBar remaining={check.rate_limit.remaining} limit={check.rate_limit.limit} resetInSeconds={check.rate_limit.reset_in_seconds} /></span>
                      {check.user && <span style={{ marginLeft: 12 }}>用户: {check.user}</span>}
                    </div>
                  )}
                  {/* 错误信息 */}
                  {check?.error && (
                    <div style={{ marginTop: 4, paddingLeft: 32, fontSize: 11, color: '#ff4d4f' }}>{check.error}</div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}
      {maskedTokens.length === 0 && !loading && (
        <Alert type="warning" showIcon message="未配置任何 Token" style={{ marginBottom: 16 }} />
      )}
    </Card>
  )
}

const TAB_ITEMS = [
  {
    key: 'tokens',
    label: <span><KeyOutlined /> Token 配置</span>,
    children: (
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <TokenPoolConfig
          platform="github"
          label="GitHub"
          color="black"
          getFn={api.getGithubTokens}
          updateFn={api.updateGithubTokens}
          checkFn={api.checkGithubTokens}
        />
        <TokenPoolConfig
          platform="atomgit"
          label="AtomGit"
          color="blue"
          getFn={api.getAtomgitTokens}
          updateFn={api.updateAtomgitTokens}
          checkFn={api.checkAtomgitTokens}
        />
      </Space>
    ),
  },
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
