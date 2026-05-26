import { useState, useEffect, useRef, useCallback } from 'react'
import { Card, Row, Col, Statistic, Tag, Space, Button, AutoComplete, Select, Spin, message, Collapse, Drawer, Timeline, Descriptions, Badge, Input, InputNumber, Modal } from 'antd'
import {
  RobotOutlined, ThunderboltOutlined, PlayCircleOutlined, ReloadOutlined,
  CheckCircleOutlined, ClockCircleOutlined, ExclamationCircleOutlined,
  DatabaseOutlined, TeamOutlined, DollarOutlined, EyeOutlined, SendOutlined,
  SettingOutlined, SaveOutlined,
} from '@ant-design/icons'
import * as api from '../api'

const AGENT_META = {
  orchestrator: { label: 'Orchestrator', desc: '总调度，理解意图并分配任务', icon: '🎯', color: '#1890ff', llm: 'glm-5.1' },
  planner: { label: 'Planner', desc: '分析项目画像，生成 DAG 执行计划', icon: '📋', color: '#722ed1', llm: 'glm-5.1' },
  collector: { label: 'Collector', desc: '从 GitHub 采集 PR/评论/Review 数据', icon: '📥', color: '#52c41a', llm: 'glm-5.1' },
  analyst: { label: 'Analyst', desc: 'CI/CD 工程效能深度分析', icon: '🔬', color: '#eb2f96', llm: 'glm-5.1' },
  validator: { label: 'Validator', desc: '数据完整性和分析质量验证', icon: '✅', color: '#faad14', llm: 'glm-5.1' },
  reporter: { label: 'Reporter', desc: '生成洞察报告和改进建议', icon: '📊', color: '#13c2c2', llm: 'glm-5.1' },
}

const MODE_OPTIONS = [
  { value: 'smart', label: 'Smart（推荐）', desc: '规则规划 + DAG 引擎，Token 最少' },
  { value: 'sequential', label: 'Sequential', desc: '固定 5 步顺序执行，适中消耗' },
  { value: 'orchestrator', label: 'Orchestrator', desc: 'LLM 自主调度，最灵活但消耗最高' },
]

function AgentCard({ name, info }) {
  const meta = AGENT_META[name] || { label: name, desc: '', icon: '🤖', color: '#999', llm: '' }
  const statusMap = { idle: 'default', running: 'processing', error: 'error', created: 'warning' }
  return (
    <Card size="small" style={{ borderLeft: `3px solid ${meta.color}` }} bodyStyle={{ padding: '10px 14px' }}>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 6 }}>
        <span style={{ fontSize: 20, marginRight: 8 }}>{meta.icon}</span>
        <span style={{ fontWeight: 600, flex: 1 }}>{meta.label}</span>
        <Badge status={statusMap[info?.status] || 'default'} text={
          <Tag color={info?.status === 'running' ? 'blue' : info?.status === 'error' ? 'red' : 'default'} style={{ fontSize: 11 }}>
            {info?.status || 'unknown'}
          </Tag>
        } />
      </div>
      <div style={{ fontSize: 12, color: '#666', marginBottom: 4 }}>{meta.desc}</div>
      <Space size={8} style={{ fontSize: 11, color: '#999' }}>
        <span>LLM: <Tag style={{ fontSize: 10 }}>{meta.llm}</Tag></span>
        {info?.total_invocations > 0 && <span>调用: {info.total_invocations}次</span>}
        {info?.total_errors > 0 && <span style={{ color: '#ff4d4f' }}>错误: {info.total_errors}</span>}
      </Space>
    </Card>
  )
}

function PipelineFlow({ spans }) {
  if (!spans || spans.length === 0) return <div style={{ color: '#999', textAlign: 'center', padding: 20 }}>暂无执行追踪数据</div>
  return (
    <Timeline
      items={spans.map((s, i) => ({
        color: s.status === 'completed' ? 'green' : s.status === 'failed' ? 'red' : 'blue',
        children: (
          <div>
            <Space>
              <Tag color={AGENT_META[s.agent_name]?.color || 'default'}>{AGENT_META[s.agent_name]?.label || s.agent_name}</Tag>
              <span style={{ fontWeight: 500 }}>{s.action}</span>
              {s.duration_ms && <span style={{ color: '#999', fontSize: 12 }}>{(s.duration_ms / 1000).toFixed(1)}s</span>}
            </Space>
            {(s.input_tokens || s.output_tokens) && (
              <div style={{ fontSize: 11, color: '#999', marginTop: 2 }}>
                Token: {s.input_tokens || 0}in / {s.output_tokens || 0}out
                {s.tool_calls > 0 && ` · 工具调用: ${s.tool_calls}`}
              </div>
            )}
          </div>
        ),
      }))}
    />
  )
}

export default function AgentStudio({ onNavigate }) {
  const [health, setHealth] = useState(null)
  const [agentsStatus, setAgentsStatus] = useState(null)
  const [cost, setCost] = useState(null)
  const [traces, setTraces] = useState([])
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(false)
  const [selectedTrace, setSelectedTrace] = useState(null)
  const [searchText, setSearchText] = useState('')
  const [analyzeOwner, setAnalyzeOwner] = useState('')
  const [analyzeRepo, setAnalyzeRepo] = useState('')
  const [mode, setMode] = useState('smart')
  const [maxPrs, setMaxPrs] = useState(100)
  const [analyzing, setAnalyzing] = useState(false)
  const [taskPolling, setTaskPolling] = useState(null)
  const [taskResult, setTaskResult] = useState(null)
  const [sseEvents, setSseEvents] = useState([])
  const [taskLogs, setTaskLogs] = useState([])
  const [llmConfig, setLlmConfig] = useState(null)
  const [llmModalOpen, setLlmModalOpen] = useState(false)
  const [llmForm, setLlmForm] = useState({})
  const eventSourceRef = useRef(null)

  const refreshAll = useCallback(async () => {
    setLoading(true)
    try {
      const [h, a, c, at, p, l] = await Promise.all([
        api.getAgentHealth().then(r => r.data).catch(() => null),
        api.getAgentsStatus().then(r => r.data).catch(() => null),
        api.getAgentCost().then(r => r.data).catch(() => null),
        api.getAgentTasks().then(r => (r.data.tasks || [])).catch(() => []),
        api.getProjectsOverview().then(r => r.data.projects || []).catch(() => []),
        api.getLlmConfig().then(r => r.data).catch(() => null),
      ])
      setHealth(h)
      setAgentsStatus(a)
      setCost(c)
      setTraces(Array.isArray(at) ? at : (at?.tasks || []))
      setProjects(p)
      setLlmConfig(l)
    } catch {}
    setLoading(false)
  }, [])

  useEffect(() => { refreshAll() }, [refreshAll])

  const projectOptions = projects.map(p => ({
    value: `${p.owner}/${p.repo}`,
    label: `${p.owner}/${p.repo}`,
  }))

  const openLlmConfig = () => {
    setLlmForm({
      model: llmConfig?.model || 'glm-5.1',
      base_url: llmConfig?.base_url || '',
      api_key: '',
      max_tokens: llmConfig?.max_tokens || 4096,
      temperature: llmConfig?.temperature ?? 0.3,
    })
    setLlmModalOpen(true)
  }

  const saveLlmConfig = async () => {
    try {
      const params = {}
      if (llmForm.model) params.model = llmForm.model
      if (llmForm.base_url) params.base_url = llmForm.base_url
      if (llmForm.api_key) params.api_key = llmForm.api_key
      if (llmForm.max_tokens) params.max_tokens = llmForm.max_tokens
      if (llmForm.temperature !== undefined) params.temperature = llmForm.temperature
      const res = await api.updateLlmConfig(params)
      message.success(res.data.message || '配置已更新')
      setLlmModalOpen(false)
      refreshAll()
    } catch (e) {
      message.error('保存失败: ' + e.message)
    }
  }

  const handleAnalyze = async () => {
    if (!analyzeOwner || !analyzeRepo) { message.warning('请选择项目'); return }
    setAnalyzing(true)
    setTaskResult(null)
    setSseEvents([])
    try {
      const res = await api.agentAnalyzeAsync({ owner: analyzeOwner, repo: analyzeRepo, max_prs: maxPrs, mode })
      const task = res.data
      setTaskPolling(task.task_id)
      message.success(`任务已创建: ${task.task_id}`)
      // SSE stream
      if (eventSourceRef.current) eventSourceRef.current.close()
      const es = new EventSource(`/api/agent/stream/${task.task_id}`)
      eventSourceRef.current = es
      es.onmessage = (e) => {
        try {
          const evt = JSON.parse(e.data)
          setSseEvents(prev => [...prev.slice(-50), evt])
          if (evt.event_type === 'completed' || evt.event_type === 'failed') {
            es.close()
            setAnalyzing(false)
            if (evt.event_type === 'completed') {
              message.success('分析完成')
            } else {
              message.error('分析失败: ' + (evt.data?.error || ''))
            }
            fetchTaskLogs(task.task_id)
            refreshAll()
          }
        } catch {}
      }
      es.onerror = () => {
        es.close()
        pollTask(task.task_id)
      }
    } catch (e) {
      message.error('启动分析失败: ' + e.message)
      setAnalyzing(false)
    }
  }

  const fetchTaskLogs = async (taskId) => {
    try {
      const res = await api.getAgentStatus(taskId)
      const t = res.data
      setTaskLogs(t.logs || [])
      setTaskResult(t)
    } catch {}
  }

  const pollTask = async (taskId) => {
    const poll = async () => {
      try {
        const res = await api.getAgentStatus(taskId)
        const t = res.data
        setTaskLogs(t.logs || [])
        if (t.status === 'completed') {
          setTaskResult(t)
          setAnalyzing(false)
          message.success('分析完成')
          refreshAll()
          return
        }
        if (t.status === 'failed') {
          setTaskResult(t)
          setAnalyzing(false)
          message.error('分析失败: ' + (t.error || ''))
          return
        }
        setTimeout(poll, 3000)
      } catch {
        setAnalyzing(false)
      }
    }
    poll()
  }

  const handleSelectTrace = async (trace) => {
    setSelectedTrace(trace)
    setTaskLogs(trace.logs || [])
    setTaskResult(trace)
    if (trace.task_id) {
      try {
        const res = await api.getAgentStatus(trace.task_id)
        const full = res.data
        setTaskLogs(full.logs || [])
        setTaskResult(full)
      } catch {}
    }
  }

  useEffect(() => {
    return () => { if (eventSourceRef.current) eventSourceRef.current.close() }
  }, [])

  const agents = agentsStatus?.agents || {}
  const agentNames = Object.keys(AGENT_META)
  const wfOk = health?.workflow === 'ok'
  const llmOk = health?.llm === 'ok'

  return (
    <div>
      <h2 style={{ marginBottom: 24 }}><RobotOutlined style={{ marginRight: 8 }} />Agent 工作室</h2>

      <Row gutter={[16, 12]} style={{ marginBottom: 16 }}>
        <Col span={4}>
          <Card size="small" bodyStyle={{ padding: '12px 16px' }}>
            <Statistic title="工作流引擎" valueStyle={{ color: wfOk ? '#52c41a' : '#ff4d4f', fontSize: 16 }}
              value={wfOk ? '就绪' : '不可用'} prefix={<ThunderboltOutlined />} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small" bodyStyle={{ padding: '12px 16px' }}
            extra={<Button size="small" type="text" icon={<SettingOutlined />} onClick={openLlmConfig} />}
            title={null}
            actions={undefined}
          >
            <Statistic title="LLM" valueStyle={{ color: llmOk ? '#52c41a' : '#ff4d4f', fontSize: 16 }}
              value={llmConfig?.model || (llmOk ? '就绪' : '不可用')} prefix={<RobotOutlined />} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small" bodyStyle={{ padding: '12px 16px' }}>
            <Statistic title="总 Token 消耗" value={cost?.total_tokens?.toLocaleString() || 0}
              valueStyle={{ color: '#1890ff', fontSize: 16 }} prefix={<DatabaseOutlined />} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small" bodyStyle={{ padding: '12px 16px' }}>
            <Statistic title="总费用 (USD)" value={`$${(cost?.total_cost || 0).toFixed(4)}`}
              valueStyle={{ color: '#faad14', fontSize: 16 }} prefix={<DollarOutlined />} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small" bodyStyle={{ padding: '12px 16px' }}>
            <Statistic title="执行追踪" value={traces.length}
              valueStyle={{ color: '#722ed1', fontSize: 16 }} prefix={<EyeOutlined />} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small" bodyStyle={{ padding: '12px 16px' }}>
            <Statistic title="Agent 数" value={agentNames.length}
              valueStyle={{ color: '#13c2c2', fontSize: 16 }} prefix={<TeamOutlined />} />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={16}>
          <Card title={<span><RobotOutlined style={{ marginRight: 8 }} />Agent 团队</span>}
            extra={<Button size="small" icon={<ReloadOutlined />} onClick={refreshAll}>刷新</Button>}
          >
            <Row gutter={[12, 12]}>
              {agentNames.map(name => (
                <Col xs={24} sm={12} md={8} key={name}>
                  <AgentCard name={name} info={agents[name]} />
                </Col>
              ))}
            </Row>
          </Card>

          <Card title={<span><PlayCircleOutlined style={{ marginRight: 8 }} />启动分析</span>} style={{ marginTop: 16 }}>
            <Space wrap style={{ marginBottom: 16 }}>
              <AutoComplete
                options={projectOptions}
                value={searchText}
                onChange={(v) => {
                  setSearchText(v || '')
                  if (!v) { setAnalyzeOwner(''); setAnalyzeRepo(''); return }
                  const idx = v.indexOf('/')
                  if (idx >= 0) { setAnalyzeOwner(v.substring(0, idx)); setAnalyzeRepo(v.substring(idx + 1)) }
                  else { setAnalyzeOwner(v); setAnalyzeRepo('') }
                }}
                onSelect={(v) => {
                  const [o, r] = v.split('/')
                  setAnalyzeOwner(o); setAnalyzeRepo(r); setSearchText(v)
                }}
                placeholder="选择项目 (owner/repo)"
                style={{ width: 280 }}
                filterOption={(input, option) => option.label.toLowerCase().includes(input.toLowerCase())}
                allowClear
              />
              <Select value={mode} onChange={setMode} style={{ width: 200 }} options={MODE_OPTIONS.map(m => ({ value: m.value, label: m.label }))} />
              <Select value={maxPrs} onChange={setMaxPrs} style={{ width: 120 }}
                options={[50, 100, 200, 500].map(n => ({ value: n, label: `最多 ${n} PR` }))} />
              <Button type="primary" icon={<ThunderboltOutlined />} onClick={handleAnalyze} loading={analyzing} disabled={!analyzeOwner || !analyzeRepo}>
                开始分析
              </Button>
            </Space>
          </Card>

          <Card title={<span><ClockCircleOutlined style={{ marginRight: 8 }} />执行日志</span>}
            style={{ marginTop: 16 }}
            extra={taskPolling && <Button size="small" icon={<ReloadOutlined />} onClick={() => fetchTaskLogs(taskPolling)}>刷新日志</Button>}
          >
            {analyzing && <div style={{ marginBottom: 8 }}><Spin size="small" /> <span style={{ color: '#52c41a' }}>分析进行中...</span></div>}
            <div style={{ maxHeight: 500, overflow: 'auto', fontSize: 12, background: '#fafafa', borderRadius: 6, padding: 8 }}>
              {(taskLogs.length > 0 ? taskLogs : sseEvents).length > 0 ? (taskLogs.length > 0 ? taskLogs : sseEvents).map((evt, i) => {
                const et = evt.event_type || ''
                const data = evt.data || {}
                const agent = data.agent
                const meta = agent ? AGENT_META[agent] : null
                const time = evt.time_str || (evt.timestamp ? new Date(evt.timestamp * 1000).toLocaleTimeString() : '')
                
                let color = 'processing'
                let icon = '⏳'
                let text = ''
                if (et === 'started') { color = 'blue'; icon = '🚀'; text = `开始分析 ${data.owner}/${data.repo}` }
                else if (et === 'completed') { color = 'success'; icon = '✅'; text = '分析完成' }
                else if (et === 'failed') { color = 'error'; icon = '❌'; text = `失败: ${data.error || ''}` }
                else if (et === 'agent_started') { color = 'blue'; icon = meta?.icon || '🤖'; text = `${meta?.label || agent} 开始执行` }
                else if (et === 'agent_completed') { color = 'green'; icon = '✅'; text = `${meta?.label || agent} 完成` + (data.duration ? ` (${data.duration?.toFixed?.(1) || data.duration}s)` : '') }
                else if (et === 'agent_failed') { color = 'red'; icon = '❌'; text = `${meta?.label || agent} 失败: ${data.error || ''}` }
                else if (et === 'agent_tool_call') { color = 'cyan'; icon = '🔧'; text = `${meta?.label || agent} 调用工具: ${data.tool || data.name || ''}` }
                else if (et === 'agent_tool_result') { color = 'default'; icon = '📋'; text = `${meta?.label || agent} 获取结果` }
                else if (et === 'agent_delegate') { color = 'purple'; icon = '🎯'; text = `${meta?.label || agent} → ${data.target || ''}` }
                else if (et === 'agent_retry') { color = 'orange'; icon = '🔄'; text = `${meta?.label || agent} 重试 #${data.attempt || '?'}` }
                else if (et === 'batch_started') { color = 'blue'; icon = '📦'; text = `批量分析开始 (${data.total} 个项目)` }
                else if (et === 'batch_progress') { color = 'processing'; icon = '📊'; text = `批量进度: ${data.completed}/${data.total}` }
                else if (et === 'batch_completed') { color = 'success'; icon = '🎉'; text = `批量分析完成` }
                else { text = data.message || data.action || JSON.stringify(data).substring(0, 80) }
                
                return (
                  <div key={i} style={{ padding: '4px 0', borderBottom: '1px solid #f0f0f0', display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ color: '#999', fontFamily: 'monospace', fontSize: 11, flexShrink: 0 }}>{time}</span>
                    <span style={{ fontSize: 13 }}>{icon}</span>
                    <Tag color={color} style={{ fontSize: 10, margin: 0, flexShrink: 0 }}>
                      {et.replace('agent_', '')}
                    </Tag>
                    <span style={{ color: '#333' }}>{text}</span>
                  </div>
                )
              }) : (
                <div style={{ textAlign: 'center', color: '#bbb', padding: 40 }}>
                  {analyzing ? '等待事件...' : '点击「开始分析」后，执行日志将在此展示'}
                </div>
              )}
            </div>

            {taskResult && !analyzing && (
              <Card size="small" title="分析结果" style={{ marginTop: 12 }}>
                {taskResult.error && <div style={{ color: '#ff4d4f', marginBottom: 8 }}>错误: {taskResult.error}</div>}
                {taskResult.report ? (
                  <>
                    {taskResult.report.ai_analysis && (
                      <div style={{ marginTop: 8 }}>
                        <h4>AI 分析</h4>
                        <pre style={{ whiteSpace: 'pre-wrap', fontSize: 13, background: '#f6f8fa', padding: 12, borderRadius: 6, maxHeight: 400, overflow: 'auto' }}>{taskResult.report.ai_analysis}</pre>
                      </div>
                    )}
                    {taskResult.report.dag_execution && (
                      <div style={{ marginTop: 8 }}>
                        <h4>DAG 执行状态</h4>
                        <Tag color={taskResult.report.dag_execution.status === 'completed' ? 'success' : taskResult.report.dag_execution.status === 'partial' ? 'warning' : 'error'}>
                          {taskResult.report.dag_execution.status}
                        </Tag>
                        {taskResult.report.dag_execution.stages?.map((s, i) => (
                          <div key={i} style={{ padding: '4px 0', borderBottom: '1px solid #f5f5f5' }}>
                            <Space>
                              <Tag color={s.status === 'completed' ? 'green' : s.status === 'error' ? 'red' : 'blue'}>{s.stage}</Tag>
                              <span style={{ color: '#666' }}>
                                {s.agent && <span>Agent: {s.agent}</span>}
                                {s.error && <span style={{ color: '#ff4d4f' }}> 错误: {s.error}</span>}
                                {s.duration_ms > 0 && <span> ({s.duration_ms}ms)</span>}
                              </span>
                            </Space>
                          </div>
                        ))}
                      </div>
                    )}
                    {taskResult.report.stats_report && (
                      <div style={{ marginTop: 8 }}>
                        <h4>统计报告</h4>
                        <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12, background: '#f6f8fa', padding: 12, borderRadius: 6, maxHeight: 400, overflow: 'auto' }}>
                          {typeof taskResult.report.stats_report === 'string' ? taskResult.report.stats_report : JSON.stringify(taskResult.report.stats_report, null, 2)}
                        </pre>
                      </div>
                    )}
                    {!taskResult.report.ai_analysis && !taskResult.report.dag_execution?.stages?.length && (
                      <div style={{ color: '#999' }}>暂无分析结果</div>
                    )}
                  </>
                ) : (
                  <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12, maxHeight: 400, overflow: 'auto' }}>
                    {JSON.stringify(taskResult, null, 2).substring(0, 2000)}
                  </pre>
                )}
              </Card>
            )}
          </Card>
        </Col>

        <Col xs={24} lg={8}>
          <Card title={<span><EyeOutlined style={{ marginRight: 8 }} />历史任务</span>}
            extra={<Button size="small" icon={<ReloadOutlined />} onClick={refreshAll}>刷新</Button>}
            bodyStyle={{ padding: '8px 12px', maxHeight: 600, overflow: 'auto' }}
          >
            {traces.length > 0 ? traces.map((t, i) => (
              <div
                key={i}
                onClick={() => handleSelectTrace(t)}
                style={{
                  padding: '8px 6px', borderBottom: '1px solid #f5f5f5', cursor: 'pointer',
                  background: selectedTrace?.task_id === t.task_id ? '#f0f5ff' : 'transparent',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ fontWeight: 500, fontSize: 13 }}>{t.owner}/{t.repo}</span>
                  <Tag color={t.status === 'completed' ? 'success' : t.status === 'failed' ? 'error' : 'processing'} style={{ fontSize: 10 }}>
                    {t.status}
                  </Tag>
                </div>
                <div style={{ fontSize: 11, color: '#999', marginTop: 2 }}>
                  {t.mode && <span>{t.mode} · </span>}
                  {t.type && <span>{t.type} · </span>}
                  {t.started_at && <span>{t.started_at.substring(5, 19)}</span>}
                </div>
              </div>
            )) : <div style={{ color: '#999', textAlign: 'center', padding: 20 }}>暂无历史任务</div>}
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col span={24}>
          <Card title={<span><TeamOutlined style={{ marginRight: 8 }} />Agent 协作流程说明</span>} size="small">
            <Row gutter={24}>
              <Col span={16}>
                <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
                  {['planner', 'collector', 'analyst', 'validator', 'reporter'].map((name, i) => {
                    const m = AGENT_META[name]
                    return (
                      <span key={name} style={{ display: 'inline-flex', alignItems: 'center' }}>
                        {i > 0 && <span style={{ color: '#ccc', margin: '0 4px' }}>→</span>}
                        <span style={{
                          padding: '4px 12px', borderRadius: 6, border: `1px solid ${m.color}`,
                          background: `${m.color}11`, fontSize: 13,
                        }}>
                          {m.icon} {m.label}
                        </span>
                      </span>
                    )
                  })}
                </div>
                <div style={{ marginTop: 12, fontSize: 13, color: '#666', lineHeight: 2 }}>
                  <div><b>Planner</b> 分析项目规模、缓存状态，生成 DAG 执行计划（哪些数据需要采集、哪些可跳过）</div>
                  <div><b>Collector</b> 按计划从 GitHub 采集 PR 列表、评论、详情、Review，自动入库 MongoDB</div>
                  <div><b>Analyst</b> 从 PR 评论中提取 CI/CD 构建结果，分析成功率/耗时/趋势/失败原因</div>
                  <div><b>Validator</b> 检查数据完整性（PR、评论、CI/CD 结果是否齐全），不足则触发补充采集</div>
                  <div><b>Reporter</b> 规则引擎 A-F 评级 + AI 生成改进建议 + 风险评估，输出最终报告</div>
                </div>
              </Col>
              <Col span={8}>
                <Card size="small" title="编排模式" type="inner">
                  {MODE_OPTIONS.map(m => (
                    <div key={m.value} style={{ marginBottom: 8, fontSize: 12 }}>
                      <b style={{ color: m.value === mode ? '#1890ff' : '#333' }}>{m.label}</b>
                      <div style={{ color: '#999' }}>{m.desc}</div>
                    </div>
                  ))}
                </Card>
              </Col>
            </Row>
          </Card>
        </Col>
      </Row>

      <Modal
        title={<span><SettingOutlined style={{ marginRight: 8 }} />LLM 配置 {onNavigate && <a onClick={() => { setLlmModalOpen(false); onNavigate('llm-config') }} style={{ fontSize: 12, color: '#722ed1', marginLeft: 8, cursor: 'pointer', fontWeight: 400 }}>→ 前往完整配置页</a>}</span>}
        open={llmModalOpen}
        onOk={saveLlmConfig}
        onCancel={() => setLlmModalOpen(false)}
        okText="保存并热更新"
        width={520}
      >
        <div style={{ marginBottom: 12 }}>
          <div style={{ marginBottom: 4, fontWeight: 500 }}>模型名称</div>
          <Input
            value={llmForm.model}
            onChange={e => setLlmForm({ ...llmForm, model: e.target.value })}
            placeholder="glm-5.1"
          />
          <div style={{ fontSize: 11, color: '#999', marginTop: 2 }}>兼容 Anthropic 接口的模型名称</div>
        </div>
        <div style={{ marginBottom: 12 }}>
          <div style={{ marginBottom: 4, fontWeight: 500 }}>API Base URL</div>
          <Input
            value={llmForm.base_url}
            onChange={e => setLlmForm({ ...llmForm, base_url: e.target.value })}
            placeholder="https://open.bigmodel.cn/api/paas/v4"
          />
          <div style={{ fontSize: 11, color: '#999', marginTop: 2 }}>留空则使用默认地址</div>
        </div>
        <div style={{ marginBottom: 12 }}>
          <div style={{ marginBottom: 4, fontWeight: 500 }}>API Key</div>
          <Input.Password
            value={llmForm.api_key}
            onChange={e => setLlmForm({ ...llmForm, api_key: e.target.value })}
            placeholder={llmConfig?.api_key_set ? '已设置，留空不修改' : '未设置'}
          />
        </div>
        <Row gutter={16}>
          <Col span={12}>
            <div style={{ marginBottom: 4, fontWeight: 500 }}>Max Tokens</div>
            <InputNumber
              value={llmForm.max_tokens}
              onChange={v => setLlmForm({ ...llmForm, max_tokens: v })}
              min={256} max={32768} style={{ width: '100%' }}
            />
          </Col>
          <Col span={12}>
            <div style={{ marginBottom: 4, fontWeight: 500 }}>Temperature</div>
            <InputNumber
              value={llmForm.temperature}
              onChange={v => setLlmForm({ ...llmForm, temperature: v })}
              min={0} max={2} step={0.1} style={{ width: '100%' }}
            />
          </Col>
        </Row>
      </Modal>
    </div>
  )
}
