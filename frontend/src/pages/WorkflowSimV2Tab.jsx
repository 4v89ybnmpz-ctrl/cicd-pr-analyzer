/**
 * WorkflowSimV2Tab — 工作流仿真 2.0
 * 驱动真实 Claude Code CLI 执行算子开发全流程
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import {
  Card, Tag, Row, Col, Button, Spin, Empty, Input, Select, Steps,
  message, Progress, Alert, Space, Tooltip, Typography, Collapse, Modal, Tabs,
} from 'antd'
import {
  ExperimentOutlined, PlayCircleOutlined, StopOutlined,
  CheckCircleOutlined, CloseCircleOutlined, LoadingOutlined,
  WarningOutlined, CodeOutlined, ClockCircleOutlined,
  ReloadOutlined, HistoryOutlined, ApiOutlined,
  RightOutlined, DownOutlined, GithubOutlined,
  DownloadOutlined, ToolOutlined, BranchesOutlined, PlusOutlined, SwapOutlined,
} from '@ant-design/icons'
import {
  getWorkflowV2Plugins, createWorkflowSimV2Session,
  getWorkflowSimV2Sessions, getWorkflowSimV2Session,
  startWorkflowSimV2Session, stopWorkflowSimV2Session,
  getActiveWorkflowSimV2Session,
  streamWorkflowSimV2, cloneWorkflowV2Repo, checkWorkflowV2Repo,
  forkWorkflowV2Repo,
  listWorkflowV2Branches, createWorkflowV2Branch, switchWorkflowV2Branch,
  installCannbotScenario, checkCannbotInstall,
  exportWorkflowV2Session,
} from '../api'

const STATUS_ICON = {
  pending: null,
  running: <LoadingOutlined />,
  completed: <CheckCircleOutlined style={{ color: '#52c41a' }} />,
  failed: <CloseCircleOutlined style={{ color: '#ff4d4f' }} />,
}

const STATUS_COLOR = {
  pending: '#d9d9d9',
  running: '#1677ff',
  completed: '#52c41a',
  failed: '#ff4d4f',
}

const STORAGE_KEY = 'workflow-sim-v2-config'

function loadPersistedConfig() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch { return null }
}

function persistConfig(data) {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(data))
  } catch { /* ignore */ }
}

export default function WorkflowSimV2Tab() {
  const _saved = loadPersistedConfig()

  const [plugins, setPlugins] = useState([])
  const [selectedPlugin, setSelectedPlugin] = useState(_saved?.selectedPlugin || null)
  const [opName, setOpName] = useState(_saved?.opName || '')
  const [opSpec, setOpSpec] = useState(_saved?.opSpec || '')
  const [workDir, setWorkDir] = useState(_saved?.workDir || '')
  const [pluginsLoading, setPluginsLoading] = useState(false)

  // Step 1: 算子库
  const [repoUrl, setRepoUrl] = useState(_saved?.repoUrl || 'https://atomgit.com/cann/ops-math')
  const [gitcodeToken, setGitcodeToken] = useState(_saved?.gitcodeToken || '')
  const [forkStatus, setForkStatus] = useState('idle') // idle | forking | forked | error
  const [forkInfo, setForkInfo] = useState(null) // {fork_url, fork_path}
  const [cloneStatus, setCloneStatus] = useState('idle') // idle | checking | cloning | cloned | error
  const [cloneInfo, setCloneInfo] = useState(null) // {branch, path}

  // Step 2: 插件安装
  const [selectedTool, setSelectedTool] = useState(_saved?.selectedTool || 'claude')
  const [installStatus, setInstallStatus] = useState('idle') // idle | checking | installing | installed | error
  const [installInfo, setInstallInfo] = useState(null)

  // 分支管理
  const [branches, setBranches] = useState([])
  const [currentBranch, setCurrentBranch] = useState('')
  const [branchesLoading, setBranchesLoading] = useState(false)
  const [newBranchName, setNewBranchName] = useState('')
  const [baseBranch, setBaseBranch] = useState('')
  const [branchCreating, setBranchCreating] = useState(false)
  const [branchSwitching, setBranchSwitching] = useState(false)
  const [selectedBranchToSwitch, setSelectedBranchToSwitch] = useState(null)

  const [stepTimeout, setStepTimeout] = useState(_saved?.stepTimeout || 1800)

  const [session, setSession] = useState(null)
  const [steps, setSteps] = useState([])
  const [alerts, setAlerts] = useState([])
  const [terminalLines, setTerminalLines] = useState([])
  const [logs, setLogs] = useState([])
  const [simulating, setSimulating] = useState(false)
  const [summary, setSummary] = useState(null)
  const [selectedStepIndex, setSelectedStepIndex] = useState(-1)

  const [historyList, setHistoryList] = useState([])
  const [historyLoading, setHistoryLoading] = useState(false)

  const [pipeline, setPipeline] = useState(null)
  const [fixRounds, setFixRounds] = useState([])

  // 历史回看：null 表示查看当前仿真，有值表示查看历史记录
  const [viewingHistoryId, setViewingHistoryId] = useState(null)

  // 日志预览 modal
  const [previewModal, setPreviewModal] = useState(null) // { session_id, op_name, terminal_log, simulation_log, tab: 'terminal'|'simlog' }

  const esRef = useRef(null)
  const termEndRef = useRef(null)

  // 配置字段变化时自动持久化到 sessionStorage
  useEffect(() => {
    persistConfig({ repoUrl, gitcodeToken, workDir, selectedPlugin, selectedTool, opName, opSpec, stepTimeout })
  }, [repoUrl, gitcodeToken, workDir, selectedPlugin, selectedTool, opName, opSpec, stepTimeout])

  // 加载插件列表
  useEffect(() => {
    setPluginsLoading(true)
    getWorkflowV2Plugins()
      .then(res => setPlugins(res.data?.plugins || []))
      .catch(() => message.warning('插件列表加载失败，请检查后端服务'))
      .finally(() => setPluginsLoading(false))
  }, [])

  // 加载历史
  const loadHistory = useCallback(() => {
    setHistoryLoading(true)
    getWorkflowSimV2Sessions({ limit: 20 })
      .then(res => setHistoryList(res.data?.sessions || []))
      .catch(() => {})
      .finally(() => setHistoryLoading(false))
  }, [])

  useEffect(() => { loadHistory() }, [loadHistory])

  // 页面加载时检测运行中的会话（刷新恢复）
  useEffect(() => {
    getActiveWorkflowSimV2Session()
      .then(res => {
        const active = res.data?.active
        if (!active) return
        // 有运行中的会话，恢复展示
        setSession(active)
        setSteps(active.steps || [])
        setAlerts(active.breakpoint_alerts || [])
        setSummary(active.summary || null)
        setPipeline(active.pipeline || null)
        if (active.pipeline?.fix_rounds) setFixRounds(active.pipeline.fix_rounds)
        setTerminalLines(active.terminal_log || [])
        setLogs(active.simulation_log || [])
        setSimulating(false) // 进程已不在，不显示运行态
      })
      .catch(() => {})
  }, [])

  // 工作目录变化时自动检查仓库状态
  useEffect(() => {
    if (!workDir.trim()) { setCloneStatus('idle'); setCloneInfo(null); return }
    setCloneStatus('checking')
    checkWorkflowV2Repo(workDir.trim())
      .then(res => {
        if (res.data?.is_git) {
          setCloneStatus('cloned')
          setCloneInfo({ branch: res.data.branch, path: res.data.path })
        } else if (res.data?.exists) {
          setCloneStatus('error')
          setCloneInfo(null)
        } else {
          setCloneStatus('idle')
          setCloneInfo(null)
        }
      })
      .catch(() => setCloneStatus('idle'))
  }, [workDir])

  // Fork 算子库到用户 GitCode 账号
  const handleFork = useCallback(async () => {
    if (!repoUrl.trim()) { message.warning('请输入算子库地址'); return }
    if (!gitcodeToken.trim()) { message.warning('请输入 GitCode Token'); return }
    setForkStatus('forking')
    try {
      const res = await forkWorkflowV2Repo({ repo_url: repoUrl.trim(), token: gitcodeToken.trim() })
      if (res.data.error) {
        setForkStatus('error')
        message.error(res.data.error)
        return
      }
      setForkStatus('forked')
      setForkInfo(res.data)
      message.success(res.data.status === 'already_forked' ? '仓库已存在于您的账号' : 'Fork 成功')
    } catch (e) {
      setForkStatus('error')
      message.error(e._friendlyMsg || 'Fork 失败')
    }
  }, [repoUrl, gitcodeToken])

  // Clone 算子库（从 fork 后的仓库 clone）
  const handleClone = useCallback(async () => {
    // clone URL 优先使用 fork 后的地址
    const cloneUrl = forkInfo?.fork_url || repoUrl.trim()
    if (!cloneUrl) { message.warning('请先 Fork 或输入仓库地址'); return }
    if (!workDir.trim()) { message.warning('请输入工作目录'); return }
    setCloneStatus('cloning')
    try {
      const res = await cloneWorkflowV2Repo({ repo_url: cloneUrl, target_dir: workDir.trim() })
      if (res.data.error) {
        setCloneStatus('error')
        message.error(res.data.error)
        return
      }
      setCloneStatus('cloned')
      setCloneInfo({ branch: res.data.branch, path: res.data.path })
      message.success(res.data.status === 'already_exists' ? '仓库已存在' : 'Clone 成功')
    } catch (e) {
      setCloneStatus('error')
      message.error(e._friendlyMsg || 'Clone 失败')
    }
  }, [repoUrl, workDir, forkInfo])

  // 安装插件
  const handleInstall = useCallback(async () => {
    if (!selectedPlugin) { message.warning('请先选择插件'); return }
    if (!workDir.trim()) { message.warning('请先设置工作目录'); return }
    setInstallStatus('installing')
    try {
      // 找到选中插件的 scenario_path
      const plugin = plugins.find(p => p.plugin_id === selectedPlugin)
      const scenarioPath = plugin?.plugin_id
        ? `plugins-official/${plugin.plugin_id}`
        : ''
      if (!scenarioPath) { message.error('无法确定插件路径'); setInstallStatus('error'); return }

      const res = await installCannbotScenario({
        scenario_path: scenarioPath,
        tool: selectedTool,
        level: 'project',
        install_path: workDir.trim(),
      })
      if (res.data?.success) {
        setInstallStatus('installed')
        setInstallInfo(res.data)
        message.success('插件安装成功')
      } else {
        setInstallStatus('error')
        message.error(res.data?.errors || '安装失败')
      }
    } catch (e) {
      setInstallStatus('error')
      message.error(e._friendlyMsg || '安装失败')
    }
  }, [selectedPlugin, selectedTool, workDir, plugins])

  // 加载分支列表
  const loadBranches = useCallback(async () => {
    if (!workDir.trim()) return
    setBranchesLoading(true)
    try {
      const res = await listWorkflowV2Branches(workDir.trim())
      if (res.data.error) {
        message.error(res.data.error)
        return
      }
      setBranches(res.data.branches || [])
      setCurrentBranch(res.data.current_branch || '')
    } catch (e) {
      message.error(e._friendlyMsg || '获取分支失败')
    } finally {
      setBranchesLoading(false)
    }
  }, [workDir])

  // clone 完成后自动加载分支
  useEffect(() => {
    if (cloneStatus === 'cloned') loadBranches()
  }, [cloneStatus, loadBranches])

  // 创建新分支
  const handleCreateBranch = useCallback(async () => {
    if (!newBranchName.trim()) { message.warning('请输入分支名称'); return }
    if (!workDir.trim()) { message.warning('请先设置工作目录'); return }
    setBranchCreating(true)
    try {
      const res = await createWorkflowV2Branch({ work_dir: workDir.trim(), branch_name: newBranchName.trim(), base_branch: baseBranch || '' })
      if (res.data.error) { message.error(res.data.error); return }
      message.success(res.data.message)
      setNewBranchName('')
      setCurrentBranch(newBranchName.trim())
      // 更新 cloneInfo 中的分支信息
      setCloneInfo(prev => prev ? { ...prev, branch: newBranchName.trim() } : null)
      loadBranches()
    } catch (e) {
      message.error(e._friendlyMsg || '创建分支失败')
    } finally {
      setBranchCreating(false)
    }
  }, [workDir, newBranchName, loadBranches])

  // 切换分支
  const handleSwitchBranch = useCallback(async (branchName) => {
    if (!branchName || !workDir.trim()) return
    setBranchSwitching(true)
    try {
      const res = await switchWorkflowV2Branch({ work_dir: workDir.trim(), branch_name: branchName })
      if (res.data.error) { message.error(res.data.error); return }
      message.success(res.data.message)
      setCurrentBranch(branchName)
      setCloneInfo(prev => prev ? { ...prev, branch: branchName } : null)
      loadBranches()
    } catch (e) {
      message.error(e._friendlyMsg || '切换分支失败')
    } finally {
      setBranchSwitching(false)
    }
  }, [workDir, loadBranches])

  // 自动滚动终端
  useEffect(() => {
    termEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [terminalLines])

  // 清理 SSE
  useEffect(() => {
    return () => { if (esRef.current) esRef.current.close() }
  }, [])

  const addLog = useCallback((type, text) => {
    setLogs(prev => [...prev, { time: new Date().toLocaleTimeString(), type, text }])
  }, [])

  // 启动仿真
  const handleStart = useCallback(async () => {
    if (!selectedPlugin) { message.warning('请选择插件'); return }
    if (!opName.trim()) { message.warning('请输入算子名称'); return }

    // 重置状态
    setSteps([])
    setAlerts([])
    setTerminalLines([])
    setLogs([])
    setSummary(null)
    setSelectedStepIndex(-1)
    setSimulating(true)
    setPipeline(null)
    setFixRounds([])
    setViewingHistoryId(null)

    try {
      // 创建会话
      const createRes = await createWorkflowSimV2Session({
        plugin_id: selectedPlugin,
        op_name: opName.trim(),
        op_spec: opSpec.trim(),
        work_dir: workDir.trim(),
        step_timeout: stepTimeout,
      })
      const sid = createRes.data.session_id
      if (!sid) {
        message.error(createRes.data.error || '创建会话失败')
        setSimulating(false)
        return
      }
      setSession(createRes.data)
      setSteps(createRes.data.steps || [])
      if (createRes.data.pipeline) setPipeline(createRes.data.pipeline)
      addLog('info', `会话已创建: ${sid}`)

      // 启动执行
      await startWorkflowSimV2Session(sid)
      addLog('info', '仿真已启动，等待 SSE 流...')

      // 连接 SSE
      if (esRef.current) esRef.current.close()
      const es = streamWorkflowSimV2(sid)
      esRef.current = es

      es.addEventListener('start', (e) => {
        const data = JSON.parse(e.data)
        addLog('info', `开始仿真: ${data.op_name} (${data.total_steps} 步)`)
      })

      es.addEventListener('step_start', (e) => {
        const data = JSON.parse(e.data)
        setSelectedStepIndex(data.step_index)
        addLog('info', `[${data.step_index + 1}/${data.total}] ${data.step_name}`)
      })

      es.addEventListener('claude_output', (e) => {
        const data = JSON.parse(e.data)
        // 过滤掉空内容和噪音事件
        const content = data.content || ''
        if (!content.trim() && data.type !== 'tool_use') return
        setTerminalLines(prev => [...prev, {
          type: data.type,
          content: content,
          toolName: data.tool_name || '',
          stepId: data.step_id,
          time: new Date().toLocaleTimeString(),
        }])
      })

      es.addEventListener('gate_check', (e) => {
        const data = JSON.parse(e.data)
        setSteps(prev => prev.map((s, i) => {
          if (s.step_id === data.step_id) {
            return { ...s, gate_passed: data.passed, gate_artifacts: data.artifacts }
          }
          return s
        }))
        if (!data.passed) {
          addLog('warn', `门禁未通过: ${data.artifacts.filter(a => !a.exists).map(a => a.name).join(', ')}`)
        }
      })

      es.addEventListener('skill_compliance', (e) => {
        const data = JSON.parse(e.data)
        setSteps(prev => prev.map(s => {
          if (s.step_id === data.step_id) {
            return { ...s, skill_compliance: { score: data.score, skills_referenced: data.skills_referenced, skills_missing: data.skills_missing, violations: data.violations } }
          }
          return s
        }))
      })

      es.addEventListener('breakpoint_alert', (e) => {
        const data = JSON.parse(e.data)
        setAlerts(prev => [...prev, data])
        addLog('warn', `[${data.severity}] ${data.message}`)
      })

      es.addEventListener('step_done', (e) => {
        const data = JSON.parse(e.data)
        setSteps(prev => prev.map(s => {
          if (s.step_id === data.step_id) {
            return {
              ...s, status: 'completed', duration_ms: data.duration_ms,
              token_usage: data.token_usage, skill_compliance_score: data.skill_compliance_score,
              gate_passed: data.gate_passed,
              ...(data.error_detail ? { error_detail: data.error_detail } : {}),
            }
          }
          return s
        }))
        const logType = data.error_detail ? 'warn' : 'success'
        const errInfo = data.error_detail ? ` [${data.error_detail.category}]` : ''
        addLog(logType, `${data.step_id} 完成 (${data.duration_ms}ms, 门禁: ${data.gate_passed ? '通过' : '未通过'})${errInfo}`)
      })

      // --- Pipeline SSE 事件 ---
      es.addEventListener('pipeline_status', (e) => {
        const data = JSON.parse(e.data)
        setPipeline(data)
      })

      es.addEventListener('pipeline_start', (e) => {
        const data = JSON.parse(e.data)
        setPipeline(prev => ({
          ...(prev || {}),
          status: 'running',
          mr_url: data.mr_url,
          mr_iid: data.mr_iid,
          stages: data.stages || prev?.stages || [],
          triggered_at: data.triggered_at,
        }))
        addLog('info', `流水线已触发${data.mr_url ? ` — MR: ${data.mr_url}` : ''}`)
      })

      es.addEventListener('pipeline_stage_update', (e) => {
        const data = JSON.parse(e.data)
        setPipeline(prev => {
          if (!prev) return prev
          const stages = (prev.stages || []).map(s =>
            s.key === data.stage_key ? { ...s, ...data.stage } : s
          )
          return { ...prev, stages }
        })
        addLog(data.stage?.status === 'success' ? 'success' : data.stage?.status === 'failed' ? 'error' : 'info',
          `流水线阶段 ${data.stage_key}: ${data.stage?.status || '更新'}`)
      })

      es.addEventListener('pipeline_done', (e) => {
        const data = JSON.parse(e.data)
        setPipeline(prev => ({
          ...(prev || {}),
          status: data.status,
          stages: data.stages || prev?.stages || [],
          completed_at: data.completed_at,
        }))
        addLog(data.status === 'success' ? 'success' : 'warn',
          `流水线${data.status === 'success' ? '全部通过' : '存在失败阶段'}`)
      })

      es.addEventListener('pipeline_fix_round', (e) => {
        const data = JSON.parse(e.data)
        setFixRounds(prev => [...prev, data])
        addLog('info', `修复轮次 ${data.round_number}: ${data.error_type}`)
      })

      es.addEventListener('summary', (e) => {
        const data = JSON.parse(e.data)
        setSummary(data)
        setSimulating(false)
        addLog('info', `仿真完成 — ${data.verdict}, ${data.passed_steps}/${data.total_steps} 步通过`)
        message.success('仿真完成')
        loadHistory()
        // 不立即关闭 SSE，等后续 pipeline 事件到达后再关
        setTimeout(() => { if (esRef.current === es) es.close() }, 3000)
      })

      es.addEventListener('error', (e) => {
        if (e.data) {
          try {
            const data = JSON.parse(e.data)
            addLog('error', `错误: ${data.error}`)
            message.error(data.error)
          } catch { /* ignore */ }
        }
        setSimulating(false)
        es.close()
      })

      es.onerror = () => {
        setSimulating(false)
        addLog('error', 'SSE 连接断开')
        es.close()
      }
    } catch (e) {
      message.error(e.response?.data?.detail || e._friendlyMsg || '启动失败')
      setSimulating(false)
    }
  }, [selectedPlugin, opName, workDir, addLog, loadHistory])

  // 停止仿真
  const handleStop = useCallback(async () => {
    if (session?.session_id) {
      await stopWorkflowSimV2Session(session.session_id)
      addLog('info', '仿真已停止')
    }
    setSimulating(false)
    if (esRef.current) esRef.current.close()
    // 刷新 session 状态
    if (session?.session_id) {
      const res = await getWorkflowSimV2Session(session.session_id)
      if (res.data && !res.data.error) {
        setSession(res.data)
        setSteps(res.data.steps || [])
        setSimulating(false)
      }
    }
    loadHistory()
  }, [session, addLog, loadHistory])

  // 加载历史详情
  const loadHistoryDetail = useCallback(async (sid) => {
    try {
      const res = await getWorkflowSimV2Session(sid)
      const data = res.data
      if (data.error) { message.error(data.error); return }

      // 检测不一致：session 已停止/完成但步骤还在 running → 自动调 stop 修复
      const hasRunningStep = (data.steps || []).some(s => s.status === 'running')
      if (hasRunningStep && data.status !== 'running') {
        await stopWorkflowSimV2Session(sid)
        const res2 = await getWorkflowSimV2Session(sid)
        if (!res2.data.error) Object.assign(data, res2.data)
      }

      if (data.steps) setSteps(data.steps)
      if (data.breakpoint_alerts) setAlerts(data.breakpoint_alerts)
      if (data.summary) setSummary(data.summary)
      if (data.pipeline) setPipeline(data.pipeline)
      if (data.pipeline?.fix_rounds) setFixRounds(data.pipeline.fix_rounds)
      setSession(data)
      setSelectedStepIndex(-1)
      // 恢复终端日志和仿真日志
      setTerminalLines(data.terminal_log || [])
      setLogs(data.simulation_log || [])
      setSimulating(false)
      setViewingHistoryId(sid)
      message.success('历史记录加载成功')
      loadHistory()
    } catch (e) {
      message.error('加载失败')
    }
  }, [loadHistory])

  // 返回当前仿真视图
  const backToCurrent = useCallback(() => {
    setViewingHistoryId(null)
    if (session && !viewingHistoryId) return
    // 清空回看数据，让页面回到空状态或当前仿真
    setSteps([])
    setAlerts([])
    setSummary(null)
    setPipeline(null)
    setFixRounds([])
    setSession(null)
    setSelectedStepIndex(-1)
    setTerminalLines([])
    setLogs([])
  }, [session, viewingHistoryId])

  // 当前选中步骤
  const selectedStep = selectedStepIndex >= 0 ? steps[selectedStepIndex] : null
  const criticalAlerts = alerts.filter(a => a.severity === 'CRITICAL' || a.severity === 'HIGH')

  return (
    <div style={{ display: 'flex', gap: 12, minHeight: 600 }}>
      {/* 左侧：历史记录侧边栏 */}
      <div style={{ width: 260, flexShrink: 0 }}>
        <Card
          size="small"
          title={
            <Space>
              <HistoryOutlined />
              <span>仿真记录</span>
              <Button type="link" size="small" onClick={loadHistory} loading={historyLoading} style={{ padding: 0 }}>刷新</Button>
            </Space>
          }
          bodyStyle={{ padding: '8px 0' }}
          style={{ position: 'sticky', top: 16 }}
        >
          {viewingHistoryId && (
            <div style={{ padding: '0 12px 8px' }}>
              <Button size="small" block onClick={backToCurrent}>
                返回当前仿真
              </Button>
            </div>
          )}
          <div style={{ maxHeight: 500, overflowY: 'auto' }}>
            {historyList.length === 0 && !historyLoading && (
              <div style={{ padding: '16px 12px', textAlign: 'center' }}>
                <Text type="secondary" style={{ fontSize: 12 }}>暂无仿真记录</Text>
              </div>
            )}
            {historyList.map(h => (
              <div
                key={h.session_id}
                onClick={() => loadHistoryDetail(h.session_id)}
                style={{
                  padding: '8px 12px',
                  marginBottom: 2,
                  cursor: 'pointer',
                  background: viewingHistoryId === h.session_id ? '#e6f7ff'
                    : session?.session_id === h.session_id && !viewingHistoryId ? '#f0f5ff' : 'transparent',
                  borderLeft: viewingHistoryId === h.session_id
                    ? '3px solid #1677ff'
                    : `3px solid ${STATUS_COLOR[h.status] || '#d9d9d9'}`,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <Text strong ellipsis style={{ fontSize: 12, flex: 1 }}>{h.op_name || '-'}</Text>
                  <Tag color={STATUS_COLOR[h.status]} style={{ fontSize: 9, lineHeight: '16px', padding: '0 4px', margin: 0 }}>
                    {h.status}
                  </Tag>
                </div>
                <div style={{ fontSize: 10, color: '#999', marginTop: 2 }}>
                  {h.plugin_name || '-'}
                </div>
                <div style={{ fontSize: 10, color: '#bbb', marginTop: 1 }}>
                  {h.created_at ? new Date(h.created_at).toLocaleString() : ''}
                </div>
                {h.status === 'running' && (
                  <div style={{ marginTop: 4 }} onClick={e => e.stopPropagation()}>
                    <Button
                      size="small"
                      danger
                      type="link"
                      style={{ fontSize: 10, padding: 0, height: 'auto' }}
                      onClick={async () => {
                        await stopWorkflowSimV2Session(h.session_id)
                        message.success('仿真已终止')
                        loadHistory()
                        if (session?.session_id === h.session_id) {
                          handleStop()
                        }
                      }}
                    >
                      终止仿真
                    </Button>
                  </div>
                )}
                {h.status !== 'running' && (
                  <div style={{ marginTop: 4 }} onClick={e => e.stopPropagation()}>
                    <Button
                      size="small"
                      type="link"
                      icon={<DownloadOutlined />}
                      style={{ fontSize: 10, padding: 0, height: 'auto', marginRight: 8 }}
                      onClick={async () => {
                        try {
                          const res = await exportWorkflowV2Session(h.session_id)
                          const url = URL.createObjectURL(res.data)
                          const a = document.createElement('a')
                          a.href = url
                          a.download = `sim-${h.session_id}-${h.op_name || 'report'}.md`
                          a.click()
                          URL.revokeObjectURL(url)
                        } catch { message.error('导出失败') }
                      }}
                    >
                      导出
                    </Button>
                    <Button
                      size="small"
                      type="link"
                      style={{ fontSize: 10, padding: 0, height: 'auto' }}
                      onClick={async () => {
                        try {
                          const res = await getWorkflowSimV2Session(h.session_id)
                          const data = res.data
                          if (data.error) { message.error(data.error); return }
                          setPreviewModal({
                            session_id: h.session_id,
                            op_name: h.op_name || data.op_name || '-',
                            terminal_log: data.terminal_log || [],
                            simulation_log: data.simulation_log || [],
                            tab: 'terminal',
                          })
                        } catch { message.error('加载失败') }
                      }}
                    >
                      预览日志
                    </Button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* 右侧：主内容区 */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 16, minWidth: 0 }}>
      {/* 查看历史时显示提示横幅 */}
      {viewingHistoryId && (
        <Alert
          type="info"
          showIcon
          message="正在查看历史仿真记录"
          description={
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span>Session: {viewingHistoryId} · {session?.plugin_name} · {session?.op_name}</span>
              <Space>
                <Button size="small" icon={<DownloadOutlined />} onClick={async () => {
                  try {
                    const res = await exportWorkflowV2Session(viewingHistoryId)
                    const url = URL.createObjectURL(res.data)
                    const a = document.createElement('a')
                    a.href = url
                    a.download = `sim-${viewingHistoryId}-${session?.op_name || 'report'}.md`
                    a.click()
                    URL.revokeObjectURL(url)
                  } catch { message.error('导出失败') }
                }}>导出报告</Button>
                <Button size="small" onClick={backToCurrent}>返回当前仿真</Button>
              </Space>
            </div>
          }
          style={{ marginBottom: 0 }}
        />
      )}

      {/* 运行中会话中断提示（刷新后检测到 running 但实际进程已不在） */}
      {session && session.status === 'running' && !simulating && (
        <Alert
          type="warning"
          showIcon
          icon={<WarningOutlined />}
          message="会话中断 — 仿真进程已丢失"
          description={
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span>Session: {session.session_id} · {session.op_name} — 后端进程已不存在（可能因页面刷新或后端重启）</span>
              <Space>
                <Button size="small" onClick={() => loadHistoryDetail(session.session_id)}>
                  查看详情
                </Button>
                <Button size="small" danger onClick={handleStop}>
                  终止并标记为已停止
                </Button>
              </Space>
            </div>
          }
          style={{ marginBottom: 0 }}
        />
      )}

      {/* Step 1: 算子库 */}
      <Card size="small" title={
        <Space>
          <GithubOutlined />
          <span>Step 1: 算子库</span>
          {forkStatus === 'forked' && <Tag color="cyan" style={{ fontSize: 10 }}>已 Fork</Tag>}
          {cloneStatus === 'cloned' && <Tag color="green" style={{ fontSize: 10 }}>已克隆</Tag>}
          {cloneStatus === 'cloning' && <Tag color="blue" style={{ fontSize: 10 }}><LoadingOutlined /> 克隆中</Tag>}
          {forkStatus === 'forking' && <Tag color="blue" style={{ fontSize: 10 }}><LoadingOutlined /> Fork 中</Tag>}
          {cloneStatus === 'checking' && <Tag style={{ fontSize: 10 }}><LoadingOutlined /> 检查中</Tag>}
        </Space>
      }>
        <Space direction="vertical" size={6} style={{ width: '100%' }}>
          {/* 上游仓库地址 */}
          <Row gutter={8} align="middle">
            <Col><Text strong style={{ fontSize: 12 }}>上游仓库:</Text></Col>
            <Col flex="auto">
              <Input
                placeholder="如 https://atomgit.com/cann/ops-math"
                value={repoUrl}
                onChange={e => { setRepoUrl(e.target.value); setForkStatus('idle'); setForkInfo(null) }}
                style={{ width: '100%' }}
              />
            </Col>
          </Row>
          {/* GitCode Token */}
          <Row gutter={8} align="middle">
            <Col><Text strong style={{ fontSize: 12 }}>GitCode Token:</Text></Col>
            <Col flex="auto">
              <Input.Password
                placeholder="输入 GitCode API Token（用于 Fork 操作）"
                value={gitcodeToken}
                onChange={e => setGitcodeToken(e.target.value)}
                style={{ width: '100%' }}
              />
            </Col>
            <Col>
              <Button
                icon={<GithubOutlined />}
                onClick={handleFork}
                loading={forkStatus === 'forking'}
                disabled={!repoUrl.trim() || !gitcodeToken.trim() || forkStatus === 'forking' || forkStatus === 'forked'}
                type={forkStatus === 'forked' ? 'default' : 'primary'}
              >
                {forkStatus === 'forked' ? '已 Fork' : forkStatus === 'forking' ? 'Fork 中...' : 'Fork 到我的账号'}
              </Button>
            </Col>
          </Row>
          {/* Fork 结果 */}
          {forkInfo && (
            <div style={{ padding: '4px 0' }}>
              <Space size={8}>
                <Tag color="cyan" style={{ fontSize: 10 }}>Fork: {forkInfo.fork_path || ''}</Tag>
                {forkInfo.fork_url && <a href={forkInfo.fork_url.replace('.git', '')} target="_blank" rel="noopener noreferrer" style={{ fontSize: 11 }}>查看仓库</a>}
              </Space>
            </div>
          )}
          {/* 工作目录 + Clone */}
          <Row gutter={8} align="middle">
            <Col><Text strong style={{ fontSize: 12 }}>工作目录:</Text></Col>
            <Col flex="auto">
              <Input
                placeholder="Clone 目标目录，如 /tmp/ops-math"
                value={workDir}
                onChange={e => setWorkDir(e.target.value)}
                style={{ width: '100%' }}
              />
            </Col>
            <Col>
              <Button
                icon={<DownloadOutlined />}
                onClick={handleClone}
                loading={cloneStatus === 'cloning'}
                disabled={(!forkInfo?.fork_url && !repoUrl.trim()) || !workDir.trim() || cloneStatus === 'cloning' || cloneStatus === 'cloned'}
                type={cloneStatus === 'cloned' ? 'default' : 'primary'}
              >
                {cloneStatus === 'cloned' ? '已克隆' : cloneStatus === 'cloning' ? '克隆中...' : 'Clone 到本地'}
              </Button>
            </Col>
          </Row>
          {/* Clone 结果 */}
          {cloneInfo && (
            <div>
              <Space size={8}>
                <Text type="secondary" style={{ fontSize: 11 }}>路径: {cloneInfo.path}</Text>
                {currentBranch && <Tag color="blue" style={{ fontSize: 10 }}>当前分支: {currentBranch}</Tag>}
              </Space>
            </div>
          )}
          {/* 分支管理：clone 完成后显示 */}
          {cloneStatus === 'cloned' && (
            <div style={{ borderTop: '1px dashed #e8e8e8', paddingTop: 8, marginTop: 4 }}>
              <Row gutter={8} align="middle" style={{ marginBottom: 6 }}>
                <Col><BranchesOutlined style={{ color: '#1677ff' }} /> <Text strong style={{ fontSize: 12 }}>分支:</Text></Col>
                <Col flex="auto">
                  <Select
                    style={{ width: '100%' }}
                    placeholder="选择分支切换"
                    value={currentBranch || undefined}
                    loading={branchesLoading}
                    onChange={(val) => { setSelectedBranchToSwitch(val); handleSwitchBranch(val) }}
                    options={branches.map(b => ({
                      value: b.name,
                      label: (
                        <span>
                          {b.is_current ? <Tag color="blue" style={{ fontSize: 9, lineHeight: '14px', padding: '0 3px', marginRight: 4 }}>当前</Tag> : null}
                          {b.name}
                          {b.is_remote && !b.is_current && <Tag style={{ fontSize: 9, lineHeight: '14px', padding: '0 3px', marginLeft: 4 }}>远程</Tag>}
                        </span>
                      ),
                    }))}
                    popupMatchSelectWidth={false}
                  />
                </Col>
                <Col>
                  <Button
                    size="small"
                    icon={<ReloadOutlined />}
                    onClick={loadBranches}
                    loading={branchesLoading}
                  />
                </Col>
              </Row>
              <Row gutter={8} align="middle">
                <Col><Text strong style={{ fontSize: 12 }}>基于:</Text></Col>
                <Col>
                  <Select
                    style={{ width: 200 }}
                    placeholder="自动检测主分支"
                    value={baseBranch || undefined}
                    onChange={setBaseBranch}
                    allowClear
                    options={[
                      { value: '', label: '自动检测 (origin/main 或 master)' },
                      ...branches.map(b => ({
                        value: b.name,
                        label: `${b.is_current ? '★ ' : ''}${b.name}${b.is_remote ? ' (远程)' : ''}`,
                      })),
                    ]}
                  />
                </Col>
              </Row>
              <Row gutter={8} align="middle">
                <Col><Text strong style={{ fontSize: 12 }}>新分支:</Text></Col>
                <Col flex="auto">
                  <Input
                    placeholder="输入新分支名称，如 feature/add-op"
                    value={newBranchName}
                    onChange={e => setNewBranchName(e.target.value)}
                    onPressEnter={handleCreateBranch}
                    style={{ width: '100%' }}
                    suffix={
                      <Button
                        type="link"
                        size="small"
                        icon={<PlusOutlined />}
                        onClick={handleCreateBranch}
                        loading={branchCreating}
                        disabled={!newBranchName.trim()}
                        style={{ padding: 0 }}
                      >
                        创建并切换
                      </Button>
                    }
                  />
                </Col>
              </Row>
            </div>
          )}
        </Space>
      </Card>

      {/* Step 2: 安装插件 */}
      <Card size="small" title={
        <Space>
          <ToolOutlined />
          <span>Step 2: 安装插件</span>
          {installStatus === 'installed' && <Tag color="green" style={{ fontSize: 10 }}>已安装</Tag>}
          {installStatus === 'installing' && <Tag color="blue" style={{ fontSize: 10 }}><LoadingOutlined /> 安装中</Tag>}
        </Space>
      }>
        <Row gutter={12} align="middle">
          <Col>
            <Space>
              <Text strong style={{ fontSize: 12 }}>插件:</Text>
              <Select
                style={{ width: 260 }}
                placeholder="选择插件"
                loading={pluginsLoading}
                value={selectedPlugin}
                onChange={setSelectedPlugin}
                options={plugins.map(p => ({
                  value: p.plugin_id,
                  label: `${p.plugin_name}${p.agents_count ? ` (${p.agents_count} agents)` : ''}`,
                }))}
              />
            </Space>
          </Col>
          <Col>
            <Space>
              <Text strong style={{ fontSize: 12 }}>工具:</Text>
              <Select
                style={{ width: 120 }}
                value={selectedTool}
                onChange={setSelectedTool}
                options={[
                  { value: 'claude', label: 'Claude' },
                  { value: 'cursor', label: 'Cursor' },
                  { value: 'trae', label: 'Trae' },
                  { value: 'opencode', label: 'OpenCode' },
                ]}
              />
            </Space>
          </Col>
          <Col>
            <Button
              icon={<ToolOutlined />}
              onClick={handleInstall}
              loading={installStatus === 'installing'}
              disabled={!selectedPlugin || !workDir.trim() || installStatus === 'installing' || installStatus === 'installed'}
              type={installStatus === 'installed' ? 'default' : 'primary'}
            >
              {installStatus === 'installed' ? '已安装' : installStatus === 'installing' ? '安装中...' : '安装到工作目录'}
            </Button>
          </Col>
        </Row>
        {installInfo && (
          <div style={{ marginTop: 6 }}>
            <Space size={8}>
              <Tag style={{ fontSize: 10 }}>工具: {selectedTool}</Tag>
              {installInfo.skills?.length > 0 && <Tag color="green" style={{ fontSize: 10 }}>Skills: {installInfo.skills.length}</Tag>}
              {installInfo.agents?.length > 0 && <Tag color="blue" style={{ fontSize: 10 }}>Agents: {installInfo.agents.length}</Tag>}
            </Space>
          </div>
        )}
      </Card>

      {/* Step 3: 开始仿真 */}
      <Card size="small" title={
        <Space>
          <ExperimentOutlined />
          <span>Step 3: 开始仿真</span>
        </Space>
      }>
        <Space direction="vertical" size={6} style={{ width: '100%' }}>
          <Row gutter={8} align="middle">
            <Col><Text strong style={{ fontSize: 12 }}>算子名:</Text></Col>
            <Col>
              <Input
                style={{ width: 160 }}
                placeholder="如 Abs, Add, ScaledBesselI1"
                value={opName}
                onChange={e => setOpName(e.target.value)}
              />
            </Col>
          </Row>
          <Row gutter={8} align="middle">
            <Col><Text strong style={{ fontSize: 12 }}>需求描述:</Text></Col>
            <Col flex="auto">
              <Input.TextArea
                placeholder="描述算子开发需求，如：指数缩放第一类修正贝塞尔函数 I₁(x)·exp(-|x|) 的 AscendC 实现，支持 float16/float32 数据类型"
                value={opSpec}
                onChange={e => setOpSpec(e.target.value)}
                autoSize={{ minRows: 2, maxRows: 4 }}
                style={{ width: '100%' }}
              />
            </Col>
          </Row>
          <Row gutter={8} align="middle">
            <Col><Text strong style={{ fontSize: 12 }}>步骤超时:</Text></Col>
            <Col>
              <Select
                style={{ width: 160 }}
                value={stepTimeout}
                onChange={setStepTimeout}
                options={[
                  { value: 600, label: '10 分钟' },
                  { value: 1200, label: '20 分钟' },
                  { value: 1800, label: '30 分钟 (默认)' },
                  { value: 3600, label: '60 分钟' },
                  { value: 7200, label: '120 分钟' },
                  { value: 0, label: '不限制' },
                ]}
              />
            </Col>
            <Col>
              <Tooltip title="每个工作流步骤的最大执行时间。超时后步骤标记为超时但会继续完成。">
                <WarningOutlined style={{ color: '#faad14' }} />
              </Tooltip>
            </Col>
          </Row>
          <Row>
            <Col>
              {simulating ? (
                <Button danger icon={<StopOutlined />} onClick={handleStop}>
                  停止仿真
                </Button>
              ) : (
                <Button
                  type="primary"
                  icon={<PlayCircleOutlined />}
                  onClick={handleStart}
                  disabled={!selectedPlugin || !opName.trim()}
                >
                  开始仿真
                </Button>
              )}
            </Col>
          </Row>
        </Space>
        {session && (
          <div style={{ marginTop: 8 }}>
            <Space size={8} wrap>
              <Tag>Session: {session.session_id}</Tag>
              <Tag color="blue">{session.plugin_name}</Tag>
              <Tag color="green">{session.op_name}</Tag>
              <Tag color={session.status === 'running' ? 'blue' : session.status === 'completed' ? 'green' : session.status === 'stopped' ? 'orange' : 'default'}>
                {session.status}
              </Tag>
              <Text type="secondary" style={{ fontSize: 12 }}>{session.work_dir}</Text>
            </Space>
            {/* 各步骤进程信息 */}
            {steps.filter(s => s.process).length > 0 && (
              <div style={{ marginTop: 6, padding: '6px 8px', background: '#fafafa', borderRadius: 4, fontSize: 11 }}>
                <Text type="secondary" style={{ fontSize: 11 }}>进程记录:</Text>
                <div style={{ marginTop: 4, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  {steps.map(s => s.process ? (
                    <Tag key={s.step_id} color={s.process.alive ? 'green' : 'default'} style={{ fontSize: 10, lineHeight: '16px', padding: '2px 6px' }}>
                      {s.step_name} — PID {s.process.pid} {s.process.alive ? '运行中' : `退出(${s.process.exit_code ?? '-'})`} {s.process.elapsed_sec}s
                      {s.process.killed ? ' [终止]' : ''}
                    </Tag>
                  ) : null)}
                </div>
              </div>
            )}
          </div>
        )}
      </Card>

      {/* 断点告警横幅 */}
      {criticalAlerts.length > 0 && (
        <Alert
          type="error"
          showIcon
          icon={<WarningOutlined />}
          message={`${criticalAlerts.length} 个严重告警`}
          description={
            <div>
              {criticalAlerts.slice(0, 3).map((a, i) => (
                <div key={i} style={{ fontSize: 12 }}>
                  <Tag color={a.severity === 'CRITICAL' ? 'error' : 'warning'} style={{ fontSize: 10 }}>{a.severity}</Tag>
                  <span>[{a.step_id}] {a.message}</span>
                </div>
              ))}
              {criticalAlerts.length > 3 && <Text type="secondary" style={{ fontSize: 11 }}>... 还有 {criticalAlerts.length - 3} 个</Text>}
            </div>
          }
        />
      )}

      {/* 步骤进度 */}
      {steps.length > 0 && (
        <Card size="small" title={<Space><CodeOutlined /> 工作流步骤 ({steps.length})</Space>}>
          <Steps
            size="small"
            current={steps.findIndex(s => s.status === 'running')}
            items={steps.map((s, i) => {
              const compliance = s.skill_compliance
              const complianceTag = compliance ? (
                <Tag color={compliance.score >= 0.8 ? 'green' : compliance.score >= 0.5 ? 'orange' : 'red'} style={{ fontSize: 10, marginLeft: 4 }}>
                  {Math.round(compliance.score * 100)}%
                </Tag>
              ) : null
              return {
                title: (
                  <span style={{ cursor: 'pointer' }} onClick={() => setSelectedStepIndex(i)}>
                    {s.step_name}
                    {complianceTag}
                  </span>
                ),
                status: s.status === 'running' ? 'process' : s.status === 'completed' ? 'finish' : 'wait',
                icon: s.status === 'completed'
                  ? <CheckCircleOutlined style={{ color: s.gate_passed === false ? '#ff4d4f' : '#52c41a' }} />
                  : s.status === 'running'
                    ? <LoadingOutlined />
                    : null,
              }
            })}
          />
        </Card>
      )}

      {/* 选中步骤详情 */}
      {selectedStep && (
        <Card size="small" title={
          <Space>
            <span>{selectedStep.step_name}</span>
            <Tag color={STATUS_COLOR[selectedStep.status]}>{selectedStep.status}</Tag>
            {selectedStep.gate_passed !== null && (
              <Tag color={selectedStep.gate_passed ? 'green' : 'red'}>
                门禁{selectedStep.gate_passed ? '通过' : '未通过'}
              </Tag>
            )}
            {selectedStep.duration_ms > 0 && (
              <Tag>{selectedStep.duration_ms}ms</Tag>
            )}
            {selectedStep.process && (
              <Tag color={selectedStep.process.alive ? 'green' : 'default'} style={{ fontSize: 10 }}>
                PID {selectedStep.process.pid} {selectedStep.process.alive ? '运行中' : `已退出(${selectedStep.process.exit_code ?? '-'})`} {selectedStep.process.elapsed_sec}s
                {selectedStep.process.killed ? ' [终止]' : ''}
              </Tag>
            )}
          </Space>
        }>
        {/* 进程详情 */}
        {selectedStep.process && (
          <div style={{ marginBottom: 8, padding: '6px 8px', background: '#f5f5f5', borderRadius: 4, fontSize: 11 }}>
            <Space size={16} wrap>
              <span><Text type="secondary">PID:</Text> {selectedStep.process.pid}</span>
              <span>
                <Text type="secondary">状态:</Text>{' '}
                {selectedStep.process.alive
                  ? <Text style={{ color: '#52c41a' }}>运行中</Text>
                  : <Text type="secondary">已退出 (exit code: {selectedStep.process.exit_code ?? '-'})</Text>
                }
              </span>
              <span><Text type="secondary">耗时:</Text> {selectedStep.process.elapsed_sec}s</span>
              {selectedStep.process.killed && <Tag color="orange" style={{ fontSize: 9 }}>手动终止</Tag>}
              {selectedStep.process.error && <span><Text type="danger">{selectedStep.process.error}</Text></span>}
            </Space>
          </div>
        )
        }
          {/* 错误详情 */}
          {selectedStep.error_detail && (
            <div style={{
              marginBottom: 8, padding: 8, borderRadius: 6,
              background: selectedStep.error_detail.category === 'ENV' ? '#fff7e6' :
                          selectedStep.error_detail.category === 'CLI' ? '#fff1f0' :
                          selectedStep.error_detail.category === 'NETWORK' ? '#e6f7ff' :
                          selectedStep.error_detail.category === 'TIMEOUT' ? '#fff7e6' :
                          selectedStep.error_detail.category === 'SKILL' ? '#f6ffed' :
                          selectedStep.error_detail.category === 'PERMISSION' ? '#fff1f0' :
                          '#f5f5f5',
              borderLeft: `3px solid ${
                selectedStep.error_detail.category === 'ENV' ? '#fa8c16' :
                selectedStep.error_detail.category === 'CLI' ? '#ff4d4f' :
                selectedStep.error_detail.category === 'NETWORK' ? '#1677ff' :
                selectedStep.error_detail.category === 'TIMEOUT' ? '#faad14' :
                selectedStep.error_detail.category === 'SKILL' ? '#52c41a' :
                selectedStep.error_detail.category === 'PERMISSION' ? '#ff4d4f' :
                '#999'
              }`,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                <Tag color={
                  selectedStep.error_detail.category === 'ENV' ? 'orange' :
                  selectedStep.error_detail.category === 'CLI' ? 'red' :
                  selectedStep.error_detail.category === 'NETWORK' ? 'blue' :
                  selectedStep.error_detail.category === 'TIMEOUT' ? 'gold' :
                  selectedStep.error_detail.category === 'SKILL' ? 'green' :
                  selectedStep.error_detail.category === 'PERMISSION' ? 'red' :
                  'default'
                } style={{ fontSize: 11 }}>
                  {selectedStep.error_detail.category}
                </Tag>
                <Text strong style={{ fontSize: 12 }}>错误详情</Text>
              </div>
              <div style={{ fontSize: 11, lineHeight: 1.8 }}>
                <div><Text type="secondary">根因分析：</Text><Text type="danger">{selectedStep.error_detail.root_cause}</Text></div>
                <div><Text type="secondary">原始错误：</Text><Text code style={{ fontSize: 10 }}>{selectedStep.error_detail.original_error}</Text></div>
                {selectedStep.error_detail.exit_code != null && (
                  <div><Text type="secondary">进程退出码：</Text><Text code>{selectedStep.error_detail.exit_code}</Text></div>
                )}
                <div style={{ marginTop: 4, padding: '4px 8px', background: '#ffffff', borderRadius: 4 }}>
                  <Text type="secondary">处理建议：</Text><Text style={{ color: '#1677ff' }}>{selectedStep.error_detail.suggestion}</Text>
                </div>
              </div>
            </div>
          )}
          {/* 该步骤的告警详情 */}
          {alerts.filter(a => a.step_id === selectedStep.step_id).length > 0 && (
            <div style={{ marginBottom: 8 }}>
              <Text strong style={{ fontSize: 12 }}>步骤告警：</Text>
              <div style={{ marginTop: 4 }}>
                {alerts.filter(a => a.step_id === selectedStep.step_id).map((a, idx) => (
                  <div key={idx} style={{
                    padding: '4px 8px', marginBottom: 4, borderRadius: 4, fontSize: 11,
                    background: a.severity === 'CRITICAL' ? '#fff1f0' : a.severity === 'HIGH' ? '#fff7e6' : '#f6ffed',
                    borderLeft: `2px solid ${a.severity === 'CRITICAL' ? '#ff4d4f' : a.severity === 'HIGH' ? '#fa8c16' : '#52c41a'}`,
                  }}>
                    <Space size={4}>
                      <Tag color={a.severity === 'CRITICAL' ? 'error' : a.severity === 'HIGH' ? 'warning' : 'success'} style={{ fontSize: 9, lineHeight: '14px', padding: '0 4px' }}>
                        {a.severity}
                      </Tag>
                      {a.error_category && (
                        <Tag style={{ fontSize: 9, lineHeight: '14px', padding: '0 4px' }}>{a.error_category}</Tag>
                      )}
                      <Text style={{ fontSize: 11 }}>{a.message}</Text>
                    </Space>
                    {a.root_cause && (
                      <div style={{ marginTop: 2, marginLeft: 4 }}>
                        <Text type="secondary" style={{ fontSize: 10 }}>原因: {a.root_cause}</Text>
                      </div>
                    )}
                    {a.suggestion && (
                      <div style={{ marginTop: 1, marginLeft: 4 }}>
                        <Text style={{ fontSize: 10, color: '#1677ff' }}>建议: {a.suggestion}</Text>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
          {/* 门禁产物 */}
          {selectedStep.gate_artifacts?.length > 0 && (
            <div style={{ marginBottom: 8 }}>
              <Tooltip title={`门禁 = 步骤完成后检查预期的产出物文件是否已生成（如 DESIGN.md、op_kernel 代码等）。通过表示所有预期文件都已创建。`}>
                <Text strong style={{ fontSize: 12 }}>
                  门禁检查: {selectedStep.gate_passed ? '✓ 通过' : '✗ 未通过'}
                  <span style={{ color: '#999', fontWeight: 400, marginLeft: 4, fontSize: 10 }}>(检查步骤产出物文件是否存在)</span>
                </Text>
              </Tooltip>
              <div style={{ marginTop: 4, display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                {selectedStep.gate_artifacts.map(a => (
                  <Tag key={a.name} color={a.exists ? 'green' : 'red'} style={{ fontSize: 11 }}>
                    {a.exists ? '✓' : '✗'} {a.name}
                  </Tag>
                ))}
              </div>
            </div>
          )}
          {selectedStep.gate_passed !== null && (!selectedStep.gate_artifacts || selectedStep.gate_artifacts.length === 0) && (
            <div style={{ marginBottom: 8 }}>
              <Tooltip title={`门禁 = 步骤完成后检查预期的产出物文件是否已生成。此步骤未定义产出物，默认通过。`}>
                <Text strong style={{ fontSize: 12 }}>
                  门禁检查: {selectedStep.gate_passed ? '✓ 通过' : '✗ 未通过'}
                  <span style={{ color: '#999', fontWeight: 400, marginLeft: 4, fontSize: 10 }}>(未定义产出物，默认通过)</span>
                </Text>
              </Tooltip>
            </div>
          )}
          {/* Skill 遵从度 */}
          {selectedStep.skill_compliance && (
            <div style={{ marginBottom: 8 }}>
              <Tooltip title={`计算方式: Claude 执行期间通过 Read/Glob/Grep 引用的 Skill 文件数 / 步骤要求的 Skill 总数。检测 Claude 是否读取了安装的 Skills 指南。`}>
                <Text strong style={{ fontSize: 12 }}>
                  Skill 遵从度: {Math.round((selectedStep.skill_compliance.score || 0) * 100)}%
                  <span style={{ color: '#999', fontWeight: 400, marginLeft: 4, fontSize: 10 }}>(引用 Skill 数 / 要求总数)</span>
                </Text>
              </Tooltip>
              <div style={{ marginTop: 4 }}>
                {selectedStep.skill_compliance.skills_expected?.length > 0 && (
                  <div>
                    <Text type="secondary" style={{ fontSize: 11 }}>步骤要求: </Text>
                    {selectedStep.skill_compliance.skills_expected.map(s => (
                      <Tag key={s} style={{ fontSize: 10 }}>{s}</Tag>
                    ))}
                  </div>
                )}
                {selectedStep.skill_compliance.skills_referenced?.length > 0 && (
                  <div style={{ marginTop: 2 }}>
                    <Text type="secondary" style={{ fontSize: 11 }}>已引用: </Text>
                    {selectedStep.skill_compliance.skills_referenced.map(s => (
                      <Tag key={s} color="green" style={{ fontSize: 10 }}>{s}</Tag>
                    ))}
                  </div>
                )}
                {selectedStep.skill_compliance.skills_missing?.length > 0 && (
                  <div style={{ marginTop: 2 }}>
                    <Text type="secondary" style={{ fontSize: 11 }}>缺失: </Text>
                    {selectedStep.skill_compliance.skills_missing.map(s => (
                      <Tag key={s} color="red" style={{ fontSize: 10 }}>{s}</Tag>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
          {/* 步骤输出 */}
          {selectedStep.output && (
            <div>
              <Text strong style={{ fontSize: 12 }}>输出:</Text>
              <pre style={{
                background: '#f6f8fa', padding: 8, borderRadius: 4,
                maxHeight: 200, overflow: 'auto', fontSize: 11, lineHeight: 1.5,
                marginTop: 4,
              }}>
                {selectedStep.output.slice(0, 2000)}
              </pre>
            </div>
          )}
        </Card>
      )}

      {/* 流水线状态面板 */}
      {pipeline && (
        <PipelinePanel pipeline={pipeline} fixRounds={fixRounds} />
      )}

      {/* 终端面板 */}
      {(simulating || terminalLines.length > 0) && (
        <Card
          size="small"
          title={
            <Space>
              <CodeOutlined />
              <span>终端输出</span>
              {simulating && <Spin size="small" />}
              <Tag style={{ fontSize: 10 }}>{terminalLines.length} 行</Tag>
            </Space>
          }
          extra={!simulating && terminalLines.length > 0 && (
            <Button size="small" icon={<DownloadOutlined />} onClick={() => {
              const content = terminalLines.map(l => `[${l.time}] [${l.type}] ${l.content}`).join('\n')
              const blob = new Blob([content], { type: 'text/plain' })
              const url = URL.createObjectURL(blob)
              const a = document.createElement('a')
              a.href = url
              a.download = `terminal-${session?.session_id || 'log'}.txt`
              a.click()
              URL.revokeObjectURL(url)
            }}>下载</Button>
          )}
        >
          <div style={{
            background: '#1e1e1e', borderRadius: 6, padding: 8,
            maxHeight: 400, overflowY: 'auto', fontFamily: 'Menlo, Monaco, monospace', fontSize: 12,
          }}>
            {terminalLines.map((line, i) => {
              const isTool = line.type === 'tool_use'
              const isThinking = line.type === 'thinking'
              const isResult = line.type === 'tool_result'
              const color = isTool ? '#569cd6' : isThinking ? '#6a9955' : isResult ? '#dcdcaa' : '#d4d4d4'
              return (
                <div key={i} style={{ marginBottom: 1 }}>
                  <span style={{ color: '#555' }}>[{line.time}]</span>{' '}
                  <span style={{ color }}>{line.content}</span>
                </div>
              )
            })}
            {simulating && (
              <div style={{ color: '#888' }}>
                <Spin size="small" style={{ marginRight: 4 }} />等待输出...
              </div>
            )}
            <div ref={termEndRef} />
          </div>
        </Card>
      )}

      {/* 日志面板 */}
      {logs.length > 0 && (
        <Card
          size="small"
          title="仿真日志"
          extra={!simulating && logs.length > 0 && (
            <Button size="small" icon={<DownloadOutlined />} onClick={() => {
              const content = logs.map(l => `[${l.time}] [${l.type.toUpperCase()}] ${l.text}`).join('\n')
              const blob = new Blob([content], { type: 'text/plain' })
              const url = URL.createObjectURL(blob)
              const a = document.createElement('a')
              a.href = url
              a.download = `simlog-${session?.session_id || 'log'}.txt`
              a.click()
              URL.revokeObjectURL(url)
            }}>下载</Button>
          )}
        >
          <div style={{
            maxHeight: 200, overflowY: 'auto', background: '#fafafa', borderRadius: 6,
            padding: 8, fontSize: 12,
          }}>
            {logs.map((log, i) => (
              <div key={i} style={{ marginBottom: 2 }}>
                <span style={{ color: '#888' }}>[{log.time}]</span>{' '}
                <span style={{ color: log.type === 'error' ? '#ff4d4f' : log.type === 'warn' ? '#faad14' : log.type === 'success' ? '#52c41a' : '#1890ff' }}>
                  {log.text}
                </span>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* 仿真结果统计 */}
      {summary && (
        <Row gutter={12}>
          <Col span={6}>
            <Card size="small">
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 24, fontWeight: 700, color: summary.verdict === 'PASS' ? '#52c41a' : summary.verdict === 'FAIL' ? '#ff4d4f' : '#faad14' }}>
                  {summary.verdict}
                </div>
                <div style={{ fontSize: 12, color: '#999' }}>总评</div>
              </div>
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 24, fontWeight: 700 }}>{summary.passed_steps}/{summary.total_steps}</div>
                <div style={{ fontSize: 12, color: '#999' }}>步骤通过</div>
              </div>
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 24, fontWeight: 700, color: summary.total_alerts > 0 ? '#fa541c' : '#52c41a' }}>
                  {summary.total_alerts}
                </div>
                <div style={{ fontSize: 12, color: '#999' }}>告警 ({summary.critical_alerts} CRITICAL)</div>
              </div>
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 16, fontWeight: 600 }}>
                  {summary.total_tokens?.input?.toLocaleString() || 0} / {summary.total_tokens?.output?.toLocaleString() || 0}
                </div>
                <div style={{ fontSize: 12, color: '#999' }}>Token (input/output)</div>
              </div>
            </Card>
          </Col>
        </Row>
      )}

      {/* 导出报告按钮（仿真完成或历史回看时显示） */}
      {summary && session && !viewingHistoryId && (
        <div style={{ marginTop: 8, textAlign: 'right' }}>
          <Button icon={<DownloadOutlined />} size="small" onClick={async () => {
            try {
              const res = await exportWorkflowV2Session(session.session_id)
              const url = URL.createObjectURL(res.data)
              const a = document.createElement('a')
              a.href = url
              a.download = `sim-${session.session_id}-${session.op_name || 'report'}.md`
              a.click()
              URL.revokeObjectURL(url)
            } catch { message.error('导出失败') }
          }}>导出完整报告 (Markdown)</Button>
        </div>
      )}

      {/* 空状态 */}
      {!simulating && steps.length === 0 && (
        <Card>
          <Empty
            description="选择插件和算子名称后点击「开始仿真」，驱动 Claude Code CLI 执行真实的算子开发全流程"
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        </Card>
      )}
      </div>{/* 右侧主内容区结束 */}

      {/* 日志预览 Modal */}
      {previewModal && (
        <Modal
          open
          width={900}
          title={`日志预览 — ${previewModal.op_name} (${previewModal.session_id})`}
          onCancel={() => setPreviewModal(null)}
          footer={[
            <Button key="dl-terminal" size="small" icon={<DownloadOutlined />} onClick={() => {
              const content = (previewModal.terminal_log || []).map(l => `[${l.time}] [${l.type}] ${l.content}`).join('\n')
              const blob = new Blob([content], { type: 'text/plain' })
              const url = URL.createObjectURL(blob)
              const a = document.createElement('a')
              a.href = url
              a.download = `terminal-${previewModal.session_id}.txt`
              a.click()
              URL.revokeObjectURL(url)
            }}>下载终端日志</Button>,
            <Button key="dl-simlog" size="small" icon={<DownloadOutlined />} onClick={() => {
              const content = (previewModal.simulation_log || []).map(l => `[${l.time}] [${l.type.toUpperCase()}] ${l.text}`).join('\n')
              const blob = new Blob([content], { type: 'text/plain' })
              const url = URL.createObjectURL(blob)
              const a = document.createElement('a')
              a.href = url
              a.download = `simlog-${previewModal.session_id}.txt`
              a.click()
              URL.revokeObjectURL(url)
            }}>下载仿真日志</Button>,
            <Button key="close" size="small" onClick={() => setPreviewModal(null)}>关闭</Button>,
          ]}
        >
          <Tabs
            activeKey={previewModal.tab || 'terminal'}
            onChange={key => setPreviewModal({ ...previewModal, tab: key })}
            items={[
              {
                key: 'terminal',
                label: `终端输出 (${(previewModal.terminal_log || []).length} 行)`,
                children: (
                  <div style={{
                    background: '#1e1e1e', borderRadius: 6, padding: 10,
                    maxHeight: 500, overflowY: 'auto',
                    fontFamily: 'Menlo, Monaco, monospace', fontSize: 12,
                  }}>
                    {(previewModal.terminal_log || []).length === 0 && (
                      <div style={{ color: '#888', textAlign: 'center', padding: 20 }}>无终端输出</div>
                    )}
                    {(previewModal.terminal_log || []).map((line, i) => {
                      const isTool = line.type === 'tool_use'
                      const isThinking = line.type === 'thinking'
                      const isResult = line.type === 'tool_result'
                      const color = isTool ? '#569cd6' : isThinking ? '#6a9955' : isResult ? '#dcdcaa' : '#d4d4d4'
                      return (
                        <div key={i} style={{ marginBottom: 1, wordBreak: 'break-all' }}>
                          <span style={{ color: '#555' }}>[{line.time}]</span>{' '}
                          <span style={{ color }}>{line.content}</span>
                        </div>
                      )
                    })}
                  </div>
                ),
              },
              {
                key: 'simlog',
                label: `仿真日志 (${(previewModal.simulation_log || []).length} 条)`,
                children: (
                  <div style={{
                    maxHeight: 500, overflowY: 'auto', background: '#fafafa', borderRadius: 6,
                    padding: 10, fontSize: 12,
                  }}>
                    {(previewModal.simulation_log || []).length === 0 && (
                      <div style={{ color: '#999', textAlign: 'center', padding: 20 }}>无仿真日志</div>
                    )}
                    {(previewModal.simulation_log || []).map((log, i) => (
                      <div key={i} style={{ marginBottom: 2 }}>
                        <span style={{ color: '#888' }}>[{log.time}]</span>{' '}
                        <span style={{ color: log.type === 'error' ? '#ff4d4f' : log.type === 'warn' ? '#faad14' : log.type === 'success' ? '#52c41a' : '#1890ff' }}>
                          {log.text}
                        </span>
                      </div>
                    ))}
                  </div>
                ),
              },
            ]}
          />
        </Modal>
      )}
    </div>
  )
}

const { Text } = Typography

// ==================== 流水线状态展示面板 ====================

const PIPELINE_STAGE_ICON = {
  success: <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 18 }} />,
  failed: <CloseCircleOutlined style={{ color: '#ff4d4f', fontSize: 18 }} />,
  running: <LoadingOutlined style={{ color: '#1677ff', fontSize: 18 }} />,
  pending: <ClockCircleOutlined style={{ color: '#d9d9d9', fontSize: 18 }} />,
}

const PIPELINE_STAGE_BG = {
  success: '#f6ffed',
  failed: '#fff2f0',
  running: '#e6f7ff',
  pending: '#fafafa',
}

const PIPELINE_STAGE_BORDER = {
  success: '#b7eb8f',
  failed: '#ffccc7',
  running: '#91caff',
  pending: '#d9d9d9',
}

/**
 * PipelinePanel — CI/CD 流水线状态展示
 *
 * 接收 pipeline 数据，实时展示各阶段状态。
 * 失败阶段可点击展开查看错误日志。
 *
 * SSE 事件驱动：
 *   pipeline_start  — PR 已创建，流水线已触发
 *   pipeline_stage_update — 某阶段状态变化
 *   pipeline_done — 流水线完成（success/failed）
 *   pipeline_fix_round — 修复循环记录
 *   pipeline_status — 初始/中间状态同步
 *
 * 当 pipeline.status === 'pending' 时显示待集成提示。
 */
function PipelinePanel({ pipeline, fixRounds }) {
  if (!pipeline) return null

  const { status, mr_url, stages = [] } = pipeline

  // 待集成提示
  if (status === 'pending' && stages.every(s => s.status === 'pending')) {
    return (
      <Card
        size="small"
        title={
          <Space>
            <ApiOutlined />
            <span>CI/CD 流水线</span>
          </Space>
        }
      >
        <div style={{ textAlign: 'center', padding: '16px 0', color: '#999' }}>
          <ApiOutlined style={{ fontSize: 24, marginBottom: 8, display: 'block' }} />
          <Text type="secondary">CI/CD 流水线集成待实现（需求 3.2）</Text>
          <br />
          <Text type="secondary" style={{ fontSize: 11 }}>
            工作流步骤全部完成后，将自动提交 PR → 触发流水线 → 实时展示各阶段状态
          </Text>
        </div>
      </Card>
    )
  }

  // 计算进度
  const completedStages = stages.filter(s => s.status === 'success' || s.status === 'failed').length
  const progressPercent = stages.length > 0 ? Math.round((completedStages / stages.length) * 100) : 0

  // 流水线整体状态
  const overallIcon = status === 'success'
    ? <CheckCircleOutlined style={{ color: '#52c41a' }} />
    : status === 'failed'
      ? <CloseCircleOutlined style={{ color: '#ff4d4f' }} />
      : status === 'running'
        ? <LoadingOutlined style={{ color: '#1677ff' }} />
        : <ClockCircleOutlined />

  return (
    <Card
      size="small"
      title={
        <Space>
          <ApiOutlined />
          <span>CI/CD 流水线</span>
          {overallIcon}
          {mr_url && (
            <a href={mr_url} target="_blank" rel="noopener noreferrer" style={{ fontSize: 12 }}>
              查看 MR
            </a>
          )}
        </Space>
      }
    >
      {/* 整体进度条 */}
      <Progress
        percent={progressPercent}
        status={status === 'failed' ? 'exception' : status === 'success' ? 'success' : 'active'}
        size="small"
        style={{ marginBottom: 12 }}
      />

      {/* 阶段流水线可视化 */}
      <div style={{ display: 'flex', alignItems: 'stretch', gap: 0, overflowX: 'auto' }}>
        {stages.map((stage, idx) => {
          const icon = PIPELINE_STAGE_ICON[stage.status] || PIPELINE_STAGE_ICON.pending
          const isFailed = stage.status === 'failed'
          const isLast = idx === stages.length - 1

          return (
            <div key={stage.key || idx} style={{ display: 'flex', alignItems: 'center' }}>
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  padding: '8px 12px',
                  minWidth: 90,
                  borderRadius: 6,
                  background: PIPELINE_STAGE_BG[stage.status] || PIPELINE_STAGE_BG.pending,
                  border: `1px solid ${PIPELINE_STAGE_BORDER[stage.status] || PIPELINE_STAGE_BORDER.pending}`,
                  cursor: isFailed ? 'pointer' : 'default',
                  transition: 'all 0.3s',
                }}
              >
                <div style={{ marginBottom: 4 }}>{icon}</div>
                <div style={{ fontSize: 12, fontWeight: 500, whiteSpace: 'nowrap' }}>
                  {stage.name}
                </div>
                {stage.duration_ms > 0 && (
                  <div style={{ fontSize: 10, color: '#999', marginTop: 2 }}>
                    {(stage.duration_ms / 1000).toFixed(1)}s
                  </div>
                )}
              </div>
              {!isLast && (
                <div style={{
                  width: 24, display: 'flex', alignItems: 'center', justifyContent: 'center',
                  color: stage.status === 'success' ? '#52c41a' : '#d9d9d9',
                }}>
                  →
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* 失败阶段错误日志（可展开） */}
      {stages.some(s => s.status === 'failed') && (
        <Collapse
          size="small"
          style={{ marginTop: 12 }}
          items={stages
            .filter(s => s.status === 'failed' && s.log)
            .map(s => ({
              key: s.key,
              label: (
                <Space>
                  <CloseCircleOutlined style={{ color: '#ff4d4f' }} />
                  <span>{s.name} — 失败日志</span>
                </Space>
              ),
              children: (
                <pre style={{
                  background: '#1e1e1e', color: '#d4d4d4', padding: 12,
                  borderRadius: 4, fontSize: 11, lineHeight: 1.6,
                  maxHeight: 300, overflow: 'auto', whiteSpace: 'pre-wrap',
                }}>
                  {s.log || '暂无日志'}
                </pre>
              ),
            }))}
        />
      )}

      {/* 修复轮次 */}
      {fixRounds && fixRounds.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <Text strong style={{ fontSize: 12 }}>修复轮次:</Text>
          <div style={{ marginTop: 4 }}>
            {fixRounds.map((round, idx) => (
              <div key={idx} style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '4px 8px', marginBottom: 4, borderRadius: 4,
                background: round.pipeline_after_fix?.status === 'success' ? '#f6ffed' : '#fff7e6',
              }}>
                <Tag style={{ fontSize: 10 }}>轮次 {round.round_number}</Tag>
                <Tag color={round.error_type === 'compile_error' ? 'red' : 'orange'} style={{ fontSize: 10 }}>
                  {round.error_type}
                </Tag>
                <Text style={{ fontSize: 11, flex: 1 }}>{round.error_log?.slice(0, 80) || '修复中...'}</Text>
                {round.pipeline_after_fix && (
                  <Tag color={round.pipeline_after_fix.status === 'success' ? 'green' : 'red'} style={{ fontSize: 10 }}>
                    {round.pipeline_after_fix.status === 'success' ? '通过' : '未通过'}
                  </Tag>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </Card>
  )
}
