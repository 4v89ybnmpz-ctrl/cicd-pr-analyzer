import { useState, useEffect, useCallback, useRef } from 'react'
import {
  Card, Button, Input, Select, Tag, Space, Tabs, message, Spin, Empty,
  Typography, Row, Col, Tooltip, Popconfirm, List, Dropdown, Progress,
} from 'antd'
import {
  CloudDownloadOutlined, CloudUploadOutlined, SafetyCertificateOutlined,
  PlayCircleOutlined, CheckCircleFilled, CloseCircleFilled, LoadingOutlined,
  StopOutlined, DeleteOutlined, HistoryOutlined, ThunderboltOutlined,
  CodeOutlined, BulbOutlined, ToolOutlined, FileTextOutlined,
  DownloadOutlined, FileMarkdownOutlined, DownOutlined,
  EyeOutlined, AlertOutlined, CheckOutlined, WarningOutlined,
} from '@ant-design/icons'
import {
  createOpsDevSession, getOpsDevSessions, getOpsDevSession,
  deleteOpsDevSession, executeOpsDevStep, stopOpsDevStep,
  exportOpsDevSession, superviseOpsDevSession, streamOpsDevSession,
} from '../api'

const { TextArea } = Input
const { Text, Title } = Typography

const STEPS = [
  { id: 'clone', name: '克隆仓库', icon: <CloudDownloadOutlined /> },
  { id: 'install', name: '安装插件', icon: <CloudUploadOutlined /> },
  { id: 'verify', name: '验证安装', icon: <SafetyCertificateOutlined /> },
  { id: 'execute', name: '执行开发', icon: <PlayCircleOutlined /> },
]

const STEP_ORDER = ['clone', 'install', 'verify', 'execute']

const SCENARIOS = [
  { value: 'ops-direct-invoke', label: 'ops-direct-invoke (Kernel 直调)' },
  { value: 'ops-registry-invoke', label: 'ops-registry-invoke (算子上库)' },
  { value: 'ops-code-reviewer', label: 'ops-code-reviewer (算子代码检视)' },
  { value: 'catlass-op-generator', label: 'catlass-op-generator (Catlass 算子)' },
  { value: 'triton-op-generator', label: 'triton-op-generator (Triton 算子)' },
  { value: 'pypto-op-orchestrator', label: 'pypto-op-orchestrator (PyPTO 算子)' },
  { value: 'model-infer-optimize', label: 'model-infer-optimize (模型推理优化)' },
  { value: 'torch-compile', label: 'torch-compile (图模式编译)' },
]

const TOOLS = [
  { value: 'claude', label: 'Claude Code' },
  { value: 'cursor', label: 'Cursor' },
  { value: 'copilot', label: 'Copilot' },
]

function getStepState(step, steps) {
  const idx = STEP_ORDER.indexOf(step.id)
  const prev = idx > 0 ? steps[idx - 1] : null
  if (step.status === 'running') return 'running'
  if (step.status === 'completed') return 'completed'
  if (step.status === 'failed') return 'failed'
  if (!prev || prev.status === 'completed') return 'idle'
  return 'disabled'
}

function StepButton({ stepDef, state, onExecute, onStop }) {
  const btnProps = {
    completed: { type: 'default', icon: <CheckCircleFilled style={{ color: '#52c41a' }} />, disabled: true, style: { borderColor: '#b7eb8f', color: '#52c41a' } },
    running: { type: 'default', icon: <LoadingOutlined />, loading: true, style: { borderColor: '#1890ff', color: '#1890ff' } },
    failed: { type: 'default', danger: true, icon: <CloseCircleFilled /> },
    idle: { type: 'default', icon: stepDef.icon, style: { borderColor: '#91d5ff', color: '#1890ff' } },
    disabled: { type: 'default', disabled: true, icon: stepDef.icon },
  }[state]

  const label = {
    completed: stepDef.name,
    running: `${stepDef.name}...`,
    failed: `${stepDef.name} (失败)`,
    idle: stepDef.name,
    disabled: stepDef.name,
  }[state]

  return state === 'running' ? (
    <Space>
      <Button {...btnProps}>{label}</Button>
      <Tooltip title="停止">
        <Button size="small" danger icon={<StopOutlined />} onClick={onStop} />
      </Tooltip>
    </Space>
  ) : (
    <Button {...btnProps} onClick={state === 'failed' || state === 'idle' ? onExecute : undefined}>
      {label}
    </Button>
  )
}

function _buildAccumulatedOutput(steps, upToStepId) {
  const lines = []
  let stopped = false
  for (const step of steps || []) {
    if (stopped) break
    if (upToStepId && step.step_id === upToStepId) stopped = true
    if (!step.output && step.status === 'pending') continue
    if (step.step_id !== 'clone' || step.output) {
      lines.push('', `─── ${step.step_name} ───`, '')
    }
    if (step.output) {
      lines.push(...step.output.split('\n'))
    }
  }
  return lines
}

function EventCard({ event }) {
  if (event.type === 'thinking') {
    return (
      <div style={{ background: '#e6f7ff', border: '1px solid #91d5ff', borderRadius: 6, padding: '8px 12px', marginBottom: 6 }}>
        <Space><BulbOutlined style={{ color: '#1890ff' }} /><Text type="secondary" style={{ fontSize: 12 }}>思考</Text></Space>
        <div style={{ marginTop: 4, whiteSpace: 'pre-wrap', fontSize: 13 }}>{event.content}</div>
      </div>
    )
  }
  if (event.type === 'tool_use') {
    return (
      <div style={{ background: '#f9f0ff', border: '1px solid #d3adf7', borderRadius: 6, padding: '8px 12px', marginBottom: 6 }}>
        <Space><ToolOutlined style={{ color: '#722ed1' }} /><Text type="secondary" style={{ fontSize: 12 }}>工具: {event.name || '调用'}</Text></Space>
        {event.input && typeof event.input === 'object' && (
          <div style={{ marginTop: 4, fontSize: 12, color: '#595959' }}>
            {JSON.stringify(event.input, null, 2).slice(0, 500)}
          </div>
        )}
        {typeof event.input === 'string' && event.input && (
          <div style={{ marginTop: 4, fontSize: 12, color: '#595959' }}>{event.input.slice(0, 300)}</div>
        )}
      </div>
    )
  }
  if (event.type === 'result') {
    return (
      <div style={{ background: '#f6ffed', border: '1px solid #b7eb8f', borderRadius: 6, padding: '8px 12px', marginBottom: 6 }}>
        <Space><ThunderboltOutlined style={{ color: '#52c41a' }} /><Text type="secondary" style={{ fontSize: 12 }}>结果</Text></Space>
        <div style={{ marginTop: 4, whiteSpace: 'pre-wrap', fontSize: 13 }}>{event.content?.slice(0, 2000)}</div>
      </div>
    )
  }
  // text
  return (
    <div style={{ background: '#fafafa', border: '1px solid #d9d9d9', borderRadius: 6, padding: '8px 12px', marginBottom: 6 }}>
      <Space><FileTextOutlined style={{ color: '#8c8c8c' }} /><Text type="secondary" style={{ fontSize: 12 }}>文本</Text></Space>
      <div style={{ marginTop: 4, whiteSpace: 'pre-wrap', fontSize: 13 }}>{event.content}</div>
    </div>
  )
}

function SupervisionPanel({ data }) {
  const coverage = data.skill_coverage || 0
  const statusColor = { used: '#52c41a', partially_used: '#faad14', unused: '#ff4d4f', unknown: '#d9d9d9' }
  const agentStatusColor = { invoked: '#52c41a', not_invoked: '#ff4d4f', unknown: '#d9d9d9' }
  const sourceColor = { skill: '#1890ff', claude_extra: '#722ed1', unknown: '#8c8c8c' }
  const qualityColor = { good: '#52c41a', acceptable: '#faad14', questionable: '#ff4d4f' }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {data.overview && (
        <Card size="small" title={<span><EyeOutlined /> 执行概览</span>}>
          <Text>{data.overview}</Text>
        </Card>
      )}

      {data.conclusion && (
        <Card size="small" title="总体结论">
          <Text>{data.conclusion}</Text>
          {coverage > 0 && (
            <div style={{ marginTop: 8 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>Skill 覆盖率</Text>
              <Progress percent={coverage} size="small" strokeColor={coverage >= 80 ? '#52c41a' : coverage >= 50 ? '#faad14' : '#ff4d4f'} />
            </div>
          )}
        </Card>
      )}

      {data.skills_usage?.length > 0 && (
        <Card size="small" title={`Skills 使用情况 (${data.skills_usage.length} 个)`}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {data.skills_usage.map((s, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 0' }}>
                <Tag color={statusColor[s.status] || '#d9d9d9'} style={{ width: 90, textAlign: 'center', fontSize: 11 }}>
                  {s.status === 'used' ? '✓ 已使用' : s.status === 'partially_used' ? '◐ 部分' : s.status === 'unused' ? '✗ 未使用' : '？未知'}
                </Tag>
                <Text strong style={{ fontSize: 13 }}>{s.skill}</Text>
                {s.detail && <Text type="secondary" style={{ fontSize: 12 }}>{s.detail}</Text>}
              </div>
            ))}
          </div>
        </Card>
      )}

      {data.agents_usage?.length > 0 && (
        <Card size="small" title={`Agents 调用情况 (${data.agents_usage.length} 个)`}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {data.agents_usage.map((a, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 0' }}>
                <Tag color={agentStatusColor[a.status] || '#d9d9d9'} style={{ width: 90, textAlign: 'center', fontSize: 11 }}>
                  {a.status === 'invoked' ? '✓ 已调用' : a.status === 'not_invoked' ? '✗ 未调用' : '？未知'}
                </Tag>
                <Text strong style={{ fontSize: 13 }}>{a.agent}</Text>
                {a.detail && <Text type="secondary" style={{ fontSize: 12 }}>{a.detail}</Text>}
              </div>
            ))}
          </div>
        </Card>
      )}

      {data.decisions?.length > 0 && (
        <Card size="small" title={`关键决策分析 (${data.decisions.length} 个)`}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {data.decisions.map((d, i) => (
              <div key={i} style={{
                background: d.source === 'skill' ? '#e6f7ff' : d.source === 'claude_extra' ? '#f9f0ff' : '#fafafa',
                border: `1px solid ${d.source === 'skill' ? '#91d5ff' : d.source === 'claude_extra' ? '#d3adf7' : '#d9d9d9'}`,
                borderRadius: 6, padding: '8px 12px',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <Text strong style={{ fontSize: 13 }}>{d.step}</Text>
                  <Tag color={sourceColor[d.source]} style={{ fontSize: 11 }}>
                    {d.source === 'skill' ? 'Skill 定义' : d.source === 'claude_extra' ? 'Claude 额外' : '未知来源'}
                  </Tag>
                  <Tag color={qualityColor[d.quality]} style={{ fontSize: 11 }}>
                    {d.quality === 'good' ? '✓ 合理' : d.quality === 'acceptable' ? '△ 可接受' : '✗ 存疑'}
                  </Tag>
                </div>
                {d.detail && <Text type="secondary" style={{ fontSize: 12 }}>{d.detail}</Text>}
              </div>
            ))}
          </div>
        </Card>
      )}

      {data.warnings?.length > 0 && (
        <Card size="small" title={<span style={{ color: '#faad14' }}><AlertOutlined /> 警告</span>}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {data.warnings.map((w, i) => (
              <div key={i} style={{ color: '#d48806', fontSize: 13 }}>⚠ {w}</div>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}

export default function OpsDevSession() {
  const [sessions, setSessions] = useState([])
  const [current, setCurrent] = useState(null)
  const [outputLines, setOutputLines] = useState([])
  const [events, setEvents] = useState([])
  const [activeTab, setActiveTab] = useState('terminal')
  const [executing, setExecuting] = useState(false)
  const [loading, setLoading] = useState(false)

  // 配置
  const [scenario, setScenario] = useState('ops-direct-invoke')
  const [tool, setTool] = useState('claude')
  const [opName, setOpName] = useState('')
  const [opSpec, setOpSpec] = useState('')

  const esRef = useRef(null)
  const outputEndRef = useRef(null)

  const loadSessions = useCallback(async () => {
    try {
      const res = await getOpsDevSessions()
      setSessions(res.data?.sessions || [])
    } catch { /* ignore */ }
  }, [])

  useEffect(() => { loadSessions() }, [loadSessions])

  // 自动滚动
  useEffect(() => {
    outputEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [outputLines, events])

  // 清理 SSE
  useEffect(() => {
    return () => { esRef.current?.close() }
  }, [])

  const loadSession = useCallback(async (id) => {
    try {
      setLoading(true)
      const res = await getOpsDevSession(id)
      const s = res.data
      setCurrent(s)
      // 恢复输出
      const runningStep = s.steps?.find(st => st.status === 'running')
      if (runningStep) {
        // 累积所有已完成步骤的输出
        const allLines = _buildAccumulatedOutput(s.steps, runningStep.step_id)
        setOutputLines(allLines)
        setEvents(runningStep.events || [])
        startStream(id)
      } else {
        // 累积所有步骤输出
        const allLines = _buildAccumulatedOutput(s.steps)
        setOutputLines(allLines)
        const lastExecuted = [...(s.steps || [])].reverse().find(st => st.output || st.events?.length)
        setEvents(lastExecuted?.events || [])
      }
    } catch (e) {
      message.error('加载会话失败')
    } finally {
      setLoading(false)
    }
  }, [])

  const startStream = useCallback((id) => {
    esRef.current?.close()
    setExecuting(true)

    const es = streamOpsDevSession(id)
    esRef.current = es

    es.addEventListener('output', (e) => {
      try {
        const data = JSON.parse(e.data)
        setOutputLines(prev => [...prev, data.line])
      } catch { /* ignore */ }
    })

    es.addEventListener('claude_event', (e) => {
      try {
        const evt = JSON.parse(e.data)
        setEvents(prev => [...prev, evt])
      } catch { /* ignore */ }
    })

    es.addEventListener('step_complete', () => {
      es.close()
      esRef.current = null
      setExecuting(false)
      loadSession(id)
    })

    es.addEventListener('error', () => {
      es.close()
      esRef.current = null
      setExecuting(false)
    })

    es.onerror = () => {
      es.close()
      esRef.current = null
      setExecuting(false)
    }
  }, [loadSession])

  const handleCreate = async () => {
    try {
      const res = await createOpsDevSession({ scenario, tool, op_name: opName, op_spec: opSpec })
      const s = res.data
      setCurrent(s)
      setOutputLines([])
      setEvents([])
      setSupervision(null)
      setSupervisionLogs([])
      setActiveTab('terminal')
      loadSessions()
      message.success('会话已创建')
    } catch (e) {
      message.error('创建会话失败: ' + (e.response?.data?.detail || e.message))
    }
  }

  const handleExecuteStep = async (stepId) => {
    if (!current) return
    try {
      setExecuting(true)
      // 追加步骤分隔符，不清空之前的输出
      const stepName = STEPS.find(s => s.id === stepId)?.name || stepId
      setOutputLines(prev => [...prev, '', `─── ${stepName} ───`, ''])
      setEvents([])
      setActiveTab('terminal')
      await executeOpsDevStep(current.session_id, stepId)
      startStream(current.session_id)
    } catch (e) {
      setExecuting(false)
      message.error(`执行失败: ${e.response?.data?.detail || e.message}`)
    }
  }

  const handleStop = async () => {
    if (!current) return
    const running = current.steps?.find(s => s.status === 'running')
    if (!running) return
    try {
      await stopOpsDevStep(current.session_id, running.step_id)
      esRef.current?.close()
      esRef.current = null
      setExecuting(false)
      loadSession(current.session_id)
    } catch {
      message.error('停止失败')
    }
  }

  const handleDelete = async (id) => {
    try {
      await deleteOpsDevSession(id)
      if (current?.session_id === id) {
        setCurrent(null)
        setOutputLines([])
        setEvents([])
        setSupervision(null)
        setSupervisionLogs([])
      }
      loadSessions()
      message.success('已删除')
    } catch {
      message.error('删除失败')
    }
  }

  const loadHistory = async (id) => {
    await loadSession(id)
  }

  const [exporting, setExporting] = useState(false)
  const [supervising, setSupervising] = useState(false)
  const [supervision, setSupervision] = useState(null)
  const [supervisionLogs, setSupervisionLogs] = useState([])

  const handleExport = async (format) => {
    if (!current) {
      message.warning('请先选择会话')
      return
    }
    setExporting(true)
    try {
      const res = await exportOpsDevSession(current.session_id, format)
      const ext = format === 'markdown' ? 'md' : 'txt'
      const filename = `ops-dev-${current.op_name || current.scenario}-${current.session_id}.${ext}`
      const url = URL.createObjectURL(res.data)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      message.success('导出成功')
    } catch (e) {
      message.error(`导出失败: ${e._friendlyMsg || e.message}`)
    } finally {
      setExporting(false)
    }
  }

  const handleSupervise = async () => {
    if (!current) {
      message.warning('请先选择会话')
      return
    }
    setSupervising(true)
    setSupervision(null)
    setSupervisionLogs(['─── 监督分析启动 ───', '正在调用 LLM 分析执行过程...', ''])
    setActiveTab('supervision')
    try {
      const res = await superviseOpsDevSession(current.session_id)
      setSupervision(res.data)
      const d = res.data
      const logLines = [
        `[分析完成] Skill 覆盖率: ${d.skill_coverage || 0}% | Skills: ${d.skill_count || 0} | Agents: ${d.agent_count || 0} | 事件: ${d.total_events || 0}`,
        `概览: ${d.overview || ''}`,
        `结论: ${d.conclusion || ''}`,
      ]
      if (d.warnings?.length) {
        logLines.push(`警告 (${d.warnings.length}):`)
        d.warnings.forEach(w => logLines.push(`  ⚠ ${w}`))
      }
      setSupervisionLogs(prev => [...prev, ...logLines])
    } catch (e) {
      setSupervisionLogs(prev => [...prev, `[分析失败] ${e._friendlyMsg || e.message}`])
      message.error(`监督分析失败: ${e._friendlyMsg || e.message}`)
    } finally {
      setSupervising(false)
    }
  }

  const handleExportSupervision = () => {
    if (!supervision) {
      message.warning('请先执行监督分析')
      return
    }
    const d = supervision
    const lines = [
      `# 监督分析报告`,
      ``,
      `## 概览`,
      d.overview || '',
      ``,
      `## 结论`,
      d.conclusion || '',
      ``,
      `## Skill 覆盖率: ${d.skill_coverage || 0}%`,
      ``,
    ]
    if (d.skills_usage?.length) {
      lines.push('## Skills 使用情况')
      lines.push('| Skill | 状态 | 详情 |')
      lines.push('|-------|------|------|')
      d.skills_usage.forEach(s => lines.push(`| ${s.skill} | ${s.status} | ${s.detail || ''} |`))
      lines.push('')
    }
    if (d.agents_usage?.length) {
      lines.push('## Agents 调用情况')
      lines.push('| Agent | 状态 | 详情 |')
      lines.push('|-------|------|------|')
      d.agents_usage.forEach(a => lines.push(`| ${a.agent} | ${a.status} | ${a.detail || ''} |`))
      lines.push('')
    }
    if (d.decisions?.length) {
      lines.push('## 关键决策分析')
      d.decisions.forEach(dec => {
        lines.push(`### ${dec.step}`)
        lines.push(`- 来源: ${dec.source === 'skill' ? 'Skill 定义' : dec.source === 'claude_extra' ? 'Claude 额外' : '未知'}`)
        lines.push(`- 质量: ${dec.quality}`)
        lines.push(`- 详情: ${dec.detail || ''}`)
        lines.push('')
      })
    }
    if (d.warnings?.length) {
      lines.push('## 警告')
      d.warnings.forEach(w => lines.push(`- ⚠ ${w}`))
      lines.push('')
    }
    const content = lines.join('\n')
    const filename = `supervision-${current?.op_name || 'report'}-${current?.session_id || 'unknown'}.md`
    const blob = new Blob([content], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    message.success('监督报告已导出')
  }

  const steps = current?.steps || STEPS.map(s => ({ ...s, status: 'pending' }))
  const executeStep = steps.find(s => s.step_id === 'execute')
  const showStructuredLog = executeStep?.status === 'running' || (executeStep?.events?.length > 0)

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <Row gutter={16} style={{ flex: 1, minHeight: 0 }}>
        {/* 左栏：配置 + 历史 */}
        <Col span={6} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <Card title="配置" size="small">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <div>
                <Text type="secondary" style={{ fontSize: 12 }}>安装场景</Text>
                <Select value={scenario} onChange={setScenario} options={SCENARIOS} style={{ width: '100%' }} size="small" />
              </div>
              <div>
                <Text type="secondary" style={{ fontSize: 12 }}>AI 工具</Text>
                <Select value={tool} onChange={setTool} options={TOOLS} style={{ width: '100%' }} size="small" />
              </div>
              <div>
                <Text type="secondary" style={{ fontSize: 12 }}>算子名称</Text>
                <Input value={opName} onChange={e => setOpName(e.target.value)} placeholder="如: Abs" size="small" />
              </div>
              <div>
                <Text type="secondary" style={{ fontSize: 12 }}>算子规格（可选）</Text>
                <TextArea value={opSpec} onChange={e => setOpSpec(e.target.value)} placeholder="如: 帮我开发一个 Abs 算子，输入 float16" rows={2} size="small" />
              </div>
              <Button type="primary" icon={<CodeOutlined />} onClick={handleCreate} block disabled={executing}>
                创建会话
              </Button>
            </div>
          </Card>

          <Card title={<span><HistoryOutlined /> 历史会话</span>} size="small" style={{ flex: 1, overflow: 'auto' }} bodyStyle={{ padding: 0 }}>
            <List
              size="small"
              dataSource={sessions}
              renderItem={s => (
                <List.Item
                  style={{ cursor: 'pointer', background: current?.session_id === s.session_id ? '#e6f7ff' : undefined, padding: '6px 12px' }}
                  onClick={() => loadHistory(s.session_id)}
                  actions={[
                    <Popconfirm title="确认删除?" onConfirm={(e) => { e?.stopPropagation(); handleDelete(s.session_id) }} onCancel={(e) => e?.stopPropagation()}>
                      <Button size="small" type="text" danger icon={<DeleteOutlined />} onClick={(e) => e.stopPropagation()} />
                    </Popconfirm>,
                  ]}
                >
                  <List.Item.Meta
                    title={<Text style={{ fontSize: 13 }}>{s.op_name || s.scenario}</Text>}
                    description={
                      <Space size={4}>
                        <Text type="secondary" style={{ fontSize: 11 }}>{s.created_at?.slice(0, 16)}</Text>
                        <Tag color={s.status === 'completed' ? 'green' : s.status === 'failed' ? 'red' : 'blue'} style={{ fontSize: 11 }}>
                          {s.status}
                        </Tag>
                      </Space>
                    }
                  />
                </List.Item>
              )}
              locale={{ emptyText: <Empty description="暂无会话" image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
            />
          </Card>
        </Col>

        {/* 右栏：步骤 + 输出 */}
        <Col span={18} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {/* 步骤按钮 */}
          <Card size="small">
            <Space size="middle" wrap>
              {STEPS.map((stepDef, i) => {
                const stepData = steps[i] || { ...stepDef, status: 'pending' }
                const state = current ? getStepState(stepData, steps) : 'disabled'
                return (
                  <StepButton
                    key={stepDef.id}
                    stepDef={stepDef}
                    state={state}
                    onExecute={() => handleExecuteStep(stepDef.id)}
                    onStop={handleStop}
                  />
                )
              })}
              {current && (
                <Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }}>
                  会话: {current.session_id} | {current.scenario}
                </Text>
              )}
              {current && (
                <Dropdown menu={{
                  items: [
                    { key: 'markdown', label: '导出 Markdown', icon: <FileMarkdownOutlined /> },
                    { key: 'text', label: '导出文本', icon: <FileTextOutlined /> },
                  ],
                  onClick: ({ key }) => handleExport(key),
                }}>
                  <Button icon={<DownloadOutlined />} size="small" loading={exporting}>
                    导出 <DownOutlined />
                  </Button>
                </Dropdown>
              )}
              {current && (
                <Button icon={<EyeOutlined />} size="small" loading={supervising} onClick={handleSupervise}>
                  监督分析
                </Button>
              )}
            </Space>
          </Card>

          {/* 输出区域 */}
          <Card
            size="small"
            style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}
            bodyStyle={{ flex: 1, overflow: 'auto', padding: 0 }}
          >
            <Tabs
              activeKey={activeTab}
              onChange={setActiveTab}
              size="small"
              style={{ height: '100%', display: 'flex', flexDirection: 'column' }}
              items={[
                {
                  key: 'terminal',
                  label: '终端输出',
                  children: (
                    <div style={{
                      background: '#1e1e1e', color: '#d4d4d4', padding: 12,
                      fontFamily: 'Menlo, Monaco, Consolas, monospace', fontSize: 13,
                      height: '100%', overflow: 'auto', whiteSpace: 'pre-wrap',
                      minHeight: 300,
                    }}>
                      {outputLines.length === 0 && !executing && (
                        <Text type="secondary" style={{ color: '#666' }}>
                          {current ? '点击步骤按钮开始执行...' : '创建会话后开始操作...'}
                        </Text>
                      )}
                      {outputLines.map((line, i) => (
                        <div key={i}>{line}</div>
                      ))}
                      {executing && <span className="cursor-blink">▌</span>}
                      <div ref={outputEndRef} />
                    </div>
                  ),
                },
                ...(showStructuredLog ? [{
                  key: 'events',
                  label: <span><BulbOutlined /> 结构化日志</span>,
                  children: (
                    <div style={{ padding: 12, overflow: 'auto', height: '100%', minHeight: 300 }}>
                      {events.length === 0 ? (
                        <Empty description="等待 Claude 输出..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
                      ) : (
                        events.map((evt, i) => <EventCard key={i} event={evt} />)
                      )}
                    </div>
                  ),
                }] : []),
                {
                  key: 'supervision',
                  label: <span><EyeOutlined /> 监督分析</span>,
                  children: (
                    <div style={{ padding: 12, overflow: 'auto', height: '100%', minHeight: 300 }}>
                      {!supervision && !supervising && supervisionLogs.length === 0 && (
                        <Empty description="点击「监督分析」按钮启动 AI 监督" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                      )}
                      {supervisionLogs.length > 0 && (
                        <div style={{
                          background: '#0d1117', color: '#c9d1d9', padding: 12,
                          fontFamily: 'Menlo, Monaco, Consolas, monospace', fontSize: 13,
                          borderRadius: 6, marginBottom: 12, whiteSpace: 'pre-wrap',
                        }}>
                          {supervisionLogs.map((line, i) => (
                            <div key={i}>{line}</div>
                          ))}
                          {supervising && <span className="cursor-blink">▌</span>}
                        </div>
                      )}
                      {supervision && !supervising && (
                        <div>
                          <div style={{ marginBottom: 8, textAlign: 'right' }}>
                            <Button icon={<FileMarkdownOutlined />} size="small" onClick={handleExportSupervision}>
                              导出监督报告
                            </Button>
                          </div>
                          <SupervisionPanel data={supervision} />
                        </div>
                      )}
                    </div>
                  ),
                },
              ]}
            />
          </Card>
        </Col>
      </Row>

      <style>{`
        .cursor-blink {
          animation: blink 1s step-end infinite;
        }
        @keyframes blink {
          50% { opacity: 0; }
        }
      `}</style>
    </div>
  )
}
