/**
 * WorkflowSimV2Tab — 工作流仿真 2.0
 * 驱动真实 Claude Code CLI 执行算子开发全流程
 */
import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import {
  Card, Tag, Row, Col, Button, Spin, Empty, Input, Select, Steps, Table,
  message, Progress, Alert, Space, Tooltip, Typography, Collapse, Modal, Tabs, Switch, Drawer,
} from 'antd'
import {
  ExperimentOutlined, PlayCircleOutlined, StopOutlined,
  CheckCircleOutlined, CloseCircleOutlined, LoadingOutlined,
  WarningOutlined, CodeOutlined, ClockCircleOutlined,
  ReloadOutlined, HistoryOutlined, ApiOutlined,
  RightOutlined, DownOutlined, UpOutlined, GithubOutlined,
  DownloadOutlined, ToolOutlined, BranchesOutlined, PlusOutlined, SwapOutlined,
  ApartmentOutlined, RobotOutlined, FileTextOutlined, ThunderboltOutlined, SafetyCertificateOutlined,
  RocketOutlined, NodeIndexOutlined, DeploymentUnitOutlined,
} from '@ant-design/icons'
import {
  getWorkflowV2Plugins, createWorkflowSimV2Session,
  getWorkflowSimV2Sessions, getWorkflowSimV2Session,
  startWorkflowSimV2Session, stopWorkflowSimV2Session,
  getActiveWorkflowSimV2Session,
  streamWorkflowSimV2, cloneWorkflowV2Repo, checkWorkflowV2Repo,
  forkWorkflowV2Repo, checkWorkflowV2Fork,
  listWorkflowV2Branches, createWorkflowV2Branch, switchWorkflowV2Branch,
  installCannbotScenario, checkCannbotInstall, checkCannbotInstallWorkdir,
  exportWorkflowV2Session, triggerPipelineSSE,
  cancelPipeline,
  streamWorkflowJsonl,
  getWorkflowJsonlHistory,
  getWorkflowDefinition,
  getNpuHosts, streamNpuTestSSE, cancelNpuTest, streamNpuTestClaudeSSE,
  getBreakpointDiagnosis, exportBreakpointDiagnosis,
} from '../api'
import {
  ReactFlow, Controls, Background, MarkerType, Handle, Position,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import PipelinePanel from '../components/workflowSimV2/PipelinePanel'
import NpuTestPanel from '../components/workflowSimV2/NpuTestPanel'
import PluginArchGraph from '../components/workflowSimV2/PluginArchGraph'
import BreakpointDiagnosisGraph from '../components/workflowSimV2/BreakpointDiagnosisGraph'
import { PieChart, Pie, Cell, Tooltip as RTooltip, BarChart, Bar, XAxis, YAxis, ResponsiveContainer } from 'recharts'

const { Text } = Typography

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

  const [stepTimeout, setStepTimeout] = useState(_saved?.stepTimeout ?? 0)

  const [session, setSession] = useState(null)
  const [steps, setSteps] = useState([])
  const [alerts, setAlerts] = useState([])
  const [monitorInsights, setMonitorInsights] = useState({})
  // skill 运行时实时状态：Map<skillName, Map<stepId, status>>
  // status ∈ pending/expected/running/passed/failed，由 SSE 事件推导，供 Skill 流程图实时点亮
  const [runtimeSkillStatus, setRuntimeSkillStatus] = useState({})
  const [terminalLines, setTerminalLines] = useState([])
  // 实时调用链：步骤 → Agent → Skill 树
  const [journeyData, setJourneyData] = useState([])
  const journeyRef = useRef([])
  useEffect(() => { journeyRef.current = journeyData }, [journeyData])
  // Claude 工作流水（jsonl 实时镜像）：claude 原生存档的 thinking/tool_use/tool_result 流水
  const [jsonlLines, setJsonlLines] = useState([])
  const [jsonlActiveFile, setJsonlActiveFile] = useState('')
  const [jsonlWaiting, setJsonlWaiting] = useState(false)
  const [showTerminal, setShowTerminal] = useState(true)
  const [showJsonl, setShowJsonl] = useState(true)
  const [fixLog, setFixLog] = useState([])
  const [showFixLog, setShowFixLog] = useState(true)
  const [logs, setLogs] = useState([])
  const [progLogs, setProgLogs] = useState([])
  const [showProgLog, setShowProgLog] = useState(true)
  const progLogEndRef = useRef(null)
  const progLogBoxRef = useRef(null)
  const [progLogPinned, setProgLogPinned] = useState(true)
  const [npuClaudeLogs, setNpuClaudeLogs] = useState([])
  const [npuClaudeRunning, setNpuClaudeRunning] = useState(false)
  const [showNpuClaude, setShowNpuClaude] = useState(true)
  const npuClaudeEsRef = useRef(null)
  const npuClaudeEndRef = useRef(null)
  const [simulating, setSimulating] = useState(false)
  const [summary, setSummary] = useState(null)
  const [selectedStepIndex, setSelectedStepIndex] = useState(-1)
  const [autoPipeline, setAutoPipeline] = useState(false)

  const [historyList, setHistoryList] = useState([])
  const [historyLoading, setHistoryLoading] = useState(false)

  const [pipeline, setPipeline] = useState(null)
  const [fixRounds, setFixRounds] = useState([])

  // 多并发后台运行：所有 running 会话列表 + 当前正查看的 session
  const [runningSessions, setRunningSessions] = useState([])
  const [viewingSessionId, setViewingSessionId] = useState(null)

  // 真机 NPU 远程测试
  const [npuTest, setNpuTest] = useState(null)       // session.npu_test 镜像
  const [npuLogs, setNpuLogs] = useState([])          // 远程 stdout/stderr 实时流
  const npuEsRef = useRef(null)                       // npu-test SSE
  const npuLogEndRef = useRef(null)                   // npu 日志面板自动滚动锚点
  // 历史回看：null 表示查看当前仿真，有值表示查看历史记录
  const [viewingHistoryId, setViewingHistoryId] = useState(null)

  // 日志预览 modal
  const [previewModal, setPreviewModal] = useState(null) // { session_id, op_name, terminal_log, simulation_log, tab: 'terminal'|'simlog' }

  // 插件架构图
  const [pluginDrawerOpen, setPluginDrawerOpen] = useState(false)
  const [pluginDef, setPluginDef] = useState(null)
  const [pluginDefLoading, setPluginDefLoading] = useState(false)

  // 插件断点诊断（跨 session 病灶聚合）
  const [diagnosis, setDiagnosis] = useState(null)
  const [diagnosisLoading, setDiagnosisLoading] = useState(false)
  const [diagnosisLimit, setDiagnosisLimit] = useState(50)
  const [diagnosisOpen, setDiagnosisOpen] = useState(false)

  const esRef = useRef(null)
  const termEndRef = useRef(null)
  const termBoxRef = useRef(null)   // terminal 滚动容器
  const jsonlEsRef = useRef(null)   // jsonl tail 的独立 EventSource
  const jsonlEndRef = useRef(null)  // jsonl 面板自动滚动锚点
  const jsonlBoxRef = useRef(null)  // jsonl 滚动容器
  const npuBoxRef = useRef(null)    // npu 日志滚动容器
  // 自动滚动守卫：仅当用户已在底部时才跟随滚动
  const [termPinned, setTermPinned] = useState(true)
  const [jsonlPinned, setJsonlPinned] = useState(true)
  const [npuPinned, setNpuPinned] = useState(true)
  const stepsRef = useRef([])  // 供 SSE 回调读取最新 steps（避免闭包陈旧值）
  useEffect(() => { stepsRef.current = steps }, [steps])
  const pluginDefRef = useRef(null)  // 供 SSE 回调读取最新 pluginDef（反查 agent 声明的 skills）
  useEffect(() => { pluginDefRef.current = pluginDef }, [pluginDef])

  // skill 运行时状态优先级（聚合多 step 状态时取最强）：failed > running > passed > expected > pending
  const SKILL_STATUS_RANK = { failed: 4, running: 3, passed: 2, expected: 1, pending: 0 }

  // 更新某 skill 在某 step 的运行时状态。onlyUpgrade=true 时仅在更高优先级时覆盖（避免回退）。
  const setSkillStatus = useCallback((skill, stepId, status, onlyUpgrade = false) => {
    if (!skill) return
    setRuntimeSkillStatus(prev => {
      const perStep = { ...(prev[skill] || {}) }
      const cur = perStep[stepId]
      if (onlyUpgrade && cur && SKILL_STATUS_RANK[cur] > SKILL_STATUS_RANK[status]) return prev
      if (perStep[stepId] === status) return prev
      perStep[stepId] = status
      return { ...prev, [skill]: perStep }
    })
  }, [])

  // 连接 jsonl tail SSE（独立第二条 EventSource，只读镜像 claude 原生工作流水）
  const connectJsonlStream = useCallback((sid) => {
    if (jsonlEsRef.current) jsonlEsRef.current.close()
    let intentionallyClosed = false
    const jes = streamWorkflowJsonl(sid)
    jsonlEsRef.current = jes
    jes.addEventListener('jsonl_switch', (e) => {
      const data = JSON.parse(e.data)
      setJsonlActiveFile(data.file || '')
      const isSub = data.kind === 'subagent'
      const label = isSub
        ? `── 🤖 进入子 Agent 流水：${data.file || ''}${data.skipped_history ? '（仅显示后续实时输出）' : ''} ──`
        : `── 会话切换到 ${data.file || ''} ──`
      setJsonlLines(prev => [...prev, { kind: isSub ? 'subagent_switch' : 'switch', summary: label, ts: '' }])
    })
    jes.addEventListener('jsonl_line', (e) => {
      const data = JSON.parse(e.data)
      setJsonlWaiting(false)
      setJsonlLines(prev => [...prev, { kind: data.kind, summary: data.summary, ts: data.ts, type: data.type }])
    })
    jes.addEventListener('no_active', () => {
      setJsonlWaiting(true)
    })
    jes.addEventListener('jsonl_done', () => {
      if (intentionallyClosed) return
      intentionallyClosed = true
      setJsonlLines(prev => prev.length > 0 && prev[prev.length - 1]?.summary === '── claude 会话已结束 ──'
        ? prev
        : [...prev, { kind: 'switch', summary: '── claude 会话已结束 ──', ts: '' }])
      jes.close()
      jsonlEsRef.current = null
    })
    jes.onerror = () => {
      if (intentionallyClosed) {
        jes.close()
        return
      }
    }
  }, [])

  const disconnectJsonlStream = useCallback(() => {
    if (jsonlEsRef.current) { jsonlEsRef.current.close(); jsonlEsRef.current = null }
  }, [])

  // 配置字段变化时自动持久化到 sessionStorage
  useEffect(() => {
    persistConfig({ repoUrl, gitcodeToken, workDir, selectedPlugin, selectedTool, opName, opSpec, stepTimeout })
  }, [repoUrl, gitcodeToken, workDir, selectedPlugin, selectedTool, opName, opSpec, stepTimeout])

  // 加载插件列表
  useEffect(() => {
    setPluginsLoading(true)
    getWorkflowV2Plugins()
      .then(res => {
        const list = res.data?.plugins || []
        setPlugins(list)
        // 若用户未选过插件，默认选中第一个，驱动 Skill 实时流程图渲染
        if (!selectedPlugin && list.length > 0) setSelectedPlugin(list[0].plugin_id)
      })
      .catch(() => message.warning('插件列表加载失败，请检查后端服务'))
      .finally(() => setPluginsLoading(false))
  }, [])

  // 选中插件时自动加载其架构定义（驱动 Skill 实时流程图渲染，无需手动点"查看插件架构"）
  useEffect(() => {
    if (!selectedPlugin) { setPluginDef(null); return }
    if (pluginDef && pluginDef.plugin_id === selectedPlugin) return
    setPluginDefLoading(true)
    getWorkflowDefinition(selectedPlugin)
      .then(res => setPluginDef(res.data))
      .catch(() => { setPluginDef(null) })
      .finally(() => setPluginDefLoading(false))
  }, [selectedPlugin])

  // 加载历史
  const loadHistory = useCallback(() => {
    setHistoryLoading(true)
    getWorkflowSimV2Sessions({ limit: 20 })
      .then(res => setHistoryList(res.data?.sessions || []))
      .catch(() => {})
      .finally(() => setHistoryLoading(false))
  }, [])

  useEffect(() => { loadHistory() }, [loadHistory])

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

  // 工作目录或插件变化时自动检测安装状态
  useEffect(() => {
    if (!workDir.trim() || !selectedPlugin) {
      if (installStatus !== 'installing') setInstallStatus('idle')
      return
    }
    setInstallStatus('checking')
    checkCannbotInstallWorkdir(workDir.trim(), selectedPlugin, selectedTool)
      .then(res => {
        if (res.data?.installed) {
          setInstallStatus('installed')
          setInstallInfo(res.data)
        } else {
          setInstallStatus('idle')
          setInstallInfo(null)
        }
      })
      .catch(() => setInstallStatus('idle'))
  }, [workDir, selectedPlugin, selectedTool])

  // repoUrl + gitcodeToken 变化时自动检测是否已 fork
  useEffect(() => {
    if (!repoUrl.trim() || !gitcodeToken.trim()) { return }
    setForkStatus('checking')
    checkWorkflowV2Fork(repoUrl.trim(), gitcodeToken.trim())
      .then(res => {
        if (res.data?.forked) {
          setForkStatus('forked')
          setForkInfo({
            fork_url: res.data.fork_url,
            fork_ssh: res.data.fork_ssh,
            fork_path: res.data.fork_path,
          })
        } else {
          setForkStatus('idle')
          setForkInfo(null)
        }
      })
      .catch(() => setForkStatus('idle'))
  }, [repoUrl, gitcodeToken])

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

  // 自动滚动终端（仅当用户已在底部时）
  useEffect(() => {
    if (termPinned) termEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [terminalLines, termPinned])

  // 自动滚动 jsonl 面板（仅当用户已在底部时）
  useEffect(() => {
    if (jsonlPinned) jsonlEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [jsonlLines, jsonlPinned])

  // 清理 SSE
  useEffect(() => {
    return () => {
      if (esRef.current) esRef.current.close()
      if (jsonlEsRef.current) jsonlEsRef.current.close()
      if (npuEsRef.current) npuEsRef.current.close()
      if (npuClaudeEsRef.current) npuClaudeEsRef.current.close()
    }
  }, [])

  // npu 日志面板自动滚动（仅当用户已在底部时）
  useEffect(() => {
    if (npuPinned) npuLogEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [npuLogs, npuPinned])

  // 程序日志面板自动滚动
  useEffect(() => {
    if (progLogPinned) progLogEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [progLogs, progLogPinned])

  const addLog = useCallback((type, text) => {
    setLogs(prev => [...prev, { time: new Date().toLocaleTimeString(), type, text }])
  }, [])

  // 绑定仿真 SSE 事件（handleStart 与 restoreSession 共用）。
  // 后端改为执行与 SSE 解耦：SSE 断开不影响后台进程，故 onerror 不再判定仿真失败。
  const attachSseHandlers = useCallback((es, sid, { autoPipeline: ap } = {}) => {
    // session_snapshot：后端在 SSE 连接建立时发 DB 全量快照，统一首次/重连/重启后重连三条路径。
    // 收到后整体重置状态（用 DB 真相覆盖内存），再处理后续实时事件。
    es.addEventListener('session_snapshot', (e) => {
      const snap = JSON.parse(e.data)
      if (!snap || !snap.session_id) return
      setSteps(snap.steps || [])
      setAlerts(snap.breakpoint_alerts || [])
      setTerminalLines(snap.terminal_log || [])
      setLogs(snap.simulation_log || [])
      setProgLogs(snap.program_log || [])
      // jsonl_log 仅在仿真已结束时从 DB 加载（历史回看）；运行中由 /tail-jsonl SSE 实时提供，避免重复
      if (snap.jsonl_log && (snap.status === 'completed' || snap.status === 'stopped' || snap.status === 'failed')) {
        setJsonlLines(snap.jsonl_log)
      }
      if (snap.fix_log) setFixLog(snap.fix_log)
      setSummary(snap.summary || null)
      if (snap.install_result) setSession(prev => ({ ...prev, install_result: snap.install_result }))
      // 从 steps 重建 journey
      setJourneyData((snap.steps || []).map((s, i) => ({
        step_id: s.step_id, step_name: s.step_name, step_index: i,
        status: s.status === 'running' ? 'running' : 'completed',
        gate_passed: s.gate_passed ?? null,
        calls: [], skills_expected: s.required_skills || [],
        skills_referenced: s.skill_compliance?.skills_referenced || [],
        skills_from_subagents: s.skill_compliance?.skills_from_subagents || [],
        skills_missing: s.skill_compliance?.skills_missing || [],
      })))
      setPipeline(snap.pipeline || null)
      if (snap.npu_test) { setNpuTest(snap.npu_test); setNpuLogs(snap.npu_test.logs || []) }
    })

    es.addEventListener('start', (e) => {
      const data = JSON.parse(e.data)
      addLog('info', `开始仿真: ${data.op_name} (${data.total_steps} 步)`)
    })

    es.addEventListener('step_start', (e) => {
      const data = JSON.parse(e.data)
      setSelectedStepIndex(data.step_index)
      addLog('info', `[${data.step_index + 1}/${data.total}] ${data.step_name}`)
      const step = stepsRef.current?.find(s => s.step_id === data.step_id)
      for (const sk of step?.required_skills || []) {
        setSkillStatus(sk, data.step_id, 'expected', true)
      }
      setJourneyData(prev => {
        const next = [...prev]
        if (!next.find(j => j.step_id === data.step_id)) {
          next.push({ step_id: data.step_id, step_name: data.step_name, step_index: data.step_index, status: 'running', gate_passed: null, calls: [], skills_expected: step?.required_skills || [] })
        }
        return next
      })
    })

    es.addEventListener('claude_output', (e) => {
      const data = JSON.parse(e.data)
      const content = data.content || ''
      if (!content.trim() && data.type !== 'tool_use') return
      setTerminalLines(prev => [...prev, {
        type: data.type, content,
        toolName: data.tool_name || '', stepId: data.step_id,
        time: new Date().toLocaleTimeString(),
      }])
      if (data.skill_invoked) {
        setSkillStatus(data.skill_invoked, data.step_id, 'running', true)
        setJourneyData(prev => prev.map(j => j.step_id === data.step_id
          ? { ...j, calls: [...j.calls, { type: 'skill', name: data.skill_invoked, ts: new Date().toLocaleTimeString(), from: 'top' }] }
          : j))
      }
      if (data.tool_name === 'Agent' && data.tool_input) {
        const subType = data.tool_input.subagent_type || ''
        const agentName = subType.split(':').pop()
        const agentDef = (pluginDefRef.current?.agent_defs || []).find(
          a => a.name === agentName || subType.includes(a.name)
        )
        if (agentDef && agentDef.skills?.length) {
          for (const sk of agentDef.skills) setSkillStatus(sk, data.step_id, 'passed')
        }
        setJourneyData(prev => prev.map(j => j.step_id === data.step_id
          ? { ...j, calls: [...j.calls, { type: 'agent', name: agentName, sub_type: subType, desc: data.tool_input.description || '', skills: agentDef?.skills || [], ts: new Date().toLocaleTimeString() }] }
          : j))
      }
    })

    es.addEventListener('gate_check', (e) => {
      const data = JSON.parse(e.data)
      setSteps(prev => prev.map(s => s.step_id === data.step_id
        ? { ...s, gate_passed: data.passed, gate_artifacts: data.artifacts } : s))
      if (data.passed === false) addLog('warn', `门禁未通过: ${data.artifacts.filter(a => !a.exists).map(a => a.name).join(', ')}`)
    })

    es.addEventListener('skill_compliance', (e) => {
      const data = JSON.parse(e.data)
      setSteps(prev => prev.map(s => s.step_id === data.step_id
        ? { ...s, skill_compliance: { score: data.score, skills_referenced: data.skills_referenced, skills_from_subagents: data.skills_from_subagents, skills_missing: data.skills_missing, violations: data.violations } } : s))
      for (const sk of data.skills_referenced || []) setSkillStatus(sk, data.step_id, 'passed')
      for (const sk of data.skills_missing || []) setSkillStatus(sk, data.step_id, 'failed')
      setJourneyData(prev => prev.map(j => j.step_id === data.step_id
        ? { ...j, skills_referenced: data.skills_referenced || [], skills_from_subagents: data.skills_from_subagents || [], skills_missing: data.skills_missing || [] }
        : j))
    })

    es.addEventListener('monitor_insight', (e) => {
      const data = JSON.parse(e.data)
      setMonitorInsights(prev => ({ ...prev, [data.step_id]: data }))
      const MON_TO_RT = { compliant: 'passed', partial: 'passed', violation: 'failed' }
      for (const sa of data.skills_analysis || []) {
        const target = MON_TO_RT[sa.status]
        if (!target || !sa.skill) continue
        setRuntimeSkillStatus(prev => {
          const perStep = prev[sa.skill]
          const cur = perStep?.[data.step_id]
          if (cur === 'passed' || cur === 'running') return { ...prev, [sa.skill]: { ...perStep, [data.step_id]: target } }
          return prev
        })
      }
    })

    es.addEventListener('breakpoint_alert', (e) => {
      const data = JSON.parse(e.data)
      setAlerts(prev => [...prev, data])
      addLog('warn', `[${data.severity}] ${data.message}`)
    })

    es.addEventListener('program_log', (e) => {
      const data = JSON.parse(e.data)
      setProgLogs(prev => [...prev.slice(-999), data])
    })

    es.addEventListener('ai_gate', (e) => {
      const data = JSON.parse(e.data)
      setSteps(prev => prev.map(s => s.step_id === data.step_id
        ? { ...s, ai_gate: { verdict: data.verdict, reasoning: data.reasoning, found_files: data.found_files, missing_core: data.missing_core } }
        : s))
    })

    es.addEventListener('fix_start', (e) => {
      const data = JSON.parse(e.data)
      setFixLog(prev => [...prev, { time: new Date().toLocaleTimeString(), step_id: data.step_id, type: 'start', content: `🔧 开始补齐缺失产出物: ${(data.missing || []).join(', ')}` }])
    })

    es.addEventListener('fix_output', (e) => {
      const data = JSON.parse(e.data)
      setFixLog(prev => [...prev, data])
    })

    es.addEventListener('fix_done', (e) => {
      const data = JSON.parse(e.data)
      setFixLog(prev => [...prev, { time: new Date().toLocaleTimeString(), step_id: data.step_id, type: 'done', content: data.passed ? '✅ 补齐成功，门禁通过' : `❌ 仍缺失: ${(data.missing || []).join(', ')}` }])
    })

    es.addEventListener('step_done', (e) => {
      const data = JSON.parse(e.data)
      const stepFailed = !!data.error_detail || data.gate_passed === false
      setSteps(prev => prev.map(s => s.step_id === data.step_id
        ? { ...s, status: 'completed', duration_ms: data.duration_ms, token_usage: data.token_usage, skill_compliance_score: data.skill_compliance_score, gate_passed: data.gate_passed, ...(data.error_detail ? { error_detail: data.error_detail } : {}) }
        : s))
      setJourneyData(prev => prev.map(j => j.step_id === data.step_id
        ? { ...j, status: 'completed', gate_passed: data.gate_passed }
        : j))
      if (stepFailed) {
        const step = stepsRef.current?.find(s => s.step_id === data.step_id)
        const expected = step?.required_skills || []
        if (expected.length) {
          setRuntimeSkillStatus(prev => {
            const next = { ...prev }
            for (const sk of expected) {
              const perStep = { ...(next[sk] || {}) }
              const cur = perStep[data.step_id]
              if (!cur || cur === 'expected' || cur === 'pending' || cur === 'running') { perStep[data.step_id] = 'failed'; next[sk] = perStep }
            }
            return next
          })
        }
      }
      const logType = data.error_detail ? 'warn' : 'success'
      const errInfo = data.error_detail ? ` [${data.error_detail.category}]` : ''
      addLog(logType, `${data.step_id} 完成 (${data.duration_ms}ms, 门禁: ${data.gate_passed === true ? '通过' : data.gate_passed === null ? '跳过' : '未通过'})${errInfo}`)
    })

    // --- Pipeline SSE 事件 ---
    es.addEventListener('pipeline_status', (e) => {
      const data = JSON.parse(e.data)
      setPipeline(prev => ({ ...(prev || {}), ...data }))
      if (data.message) addLog('info', `[Pipeline] ${data.message}`)
    })
    es.addEventListener('pipeline_start', (e) => {
      const data = JSON.parse(e.data)
      setPipeline(prev => ({ ...(prev || {}), status: 'running', mr_url: data.mr_url, mr_iid: data.mr_iid, steps: data.steps || prev?.steps || [], triggered_at: data.triggered_at }))
      addLog('info', `流水线已触发${data.mr_url ? ` — MR: ${data.mr_url}` : ''}`)
    })
    es.addEventListener('pipeline_step_update', (e) => {
      const data = JSON.parse(e.data)
      setPipeline(prev => ({ ...(prev || {}), steps: data.steps || prev?.steps || [], mr_url: data.mr_url || prev?.mr_url, mr_iid: data.mr_iid || prev?.mr_iid }))
      const stepStatus = data.step?.status || '更新'
      const stepName = data.step?.name || data.step_key
      const logType = stepStatus === 'success' ? 'success' : stepStatus === 'failed' ? 'error' : 'info'
      addLog(logType, `[Pipeline] ${stepName}: ${stepStatus}${data.message ? ' — ' + data.message : ''}`)
    })
    es.addEventListener('pipeline_done', (e) => {
      const data = JSON.parse(e.data)
      setPipeline(prev => ({ ...(prev || {}), status: data.status, steps: data.steps || prev?.steps || [], completed_at: data.completed_at, fix_rounds: data.fix_rounds }))
      if (data.status === 'success') addLog('success', '流水线全部通过')
      else { const f = (data.steps || []).filter(s => s.status === 'failed'); addLog('error', `流水线失败: ${f.map(s => s.name || s.key).join(', ') || '未知'}${data.error ? ' — ' + data.error : ''}`) }
      message.info(data.status === 'success' ? 'CI/CD 流水线全部通过' : 'CI/CD 流水线存在失败')
    })
    es.addEventListener('pipeline_fix_round', (e) => {
      const data = JSON.parse(e.data)
      setFixRounds(prev => [...prev, data])
      addLog('warn', `修复轮次 ${data.round_number}: ${data.error_type}${data.error_log ? ' — ' + data.error_log.slice(0, 100) : ''}`)
    })

    es.addEventListener('summary', (e) => {
      const data = JSON.parse(e.data)
      setSummary(data)
      setSimulating(false)
      addLog('info', `仿真完成 — ${data.verdict}, ${data.passed_steps}/${data.total_steps} 步通过`)
      message.success('仿真完成')
      loadHistory()
      // 从 runningSessions 移除已完成的
      setRunningSessions(prev => prev.filter(s => s.session_id !== sid))
      if (!ap) setTimeout(() => { if (esRef.current === es) es.close() }, 3000)
    })

    es.addEventListener('error', (e) => {
      if (e.data) {
        try { const data = JSON.parse(e.data); addLog('error', `错误: ${data.error}`); message.error(data.error) } catch { /* ignore */ }
      }
    })

    // SSE 断开：后端执行已解耦，仿真仍在后台运行，不判定失败，等用户重连或刷新。
    es.onerror = () => {
      addLog('warn', 'SSE 连接断开，仿真仍在后台运行（刷新页面可恢复）')
      es.close()
    }
  }, [addLog, loadHistory])

  // 恢复/切换查看某个 session：加载其 DB 快照并重连 SSE 看实时。
  // 用于刷新恢复 running 会话、侧边栏切换查看后台跑着的会话。
  const restoreSession = useCallback((sess) => {
    if (!sess || !sess.session_id) return
    setSession(sess)
    setSteps(sess.steps || [])
    setAlerts(sess.breakpoint_alerts || [])
    setSummary(sess.summary || null)
    setPipeline(sess.pipeline || null)
    if (sess.pipeline?.fix_rounds) setFixRounds(sess.pipeline.fix_rounds)
    setNpuTest(sess.npu_test || null)
    setNpuLogs(sess.npu_test?.logs || [])
    setTerminalLines(sess.terminal_log || [])
    setLogs(sess.simulation_log || [])
    setViewingSessionId(sess.session_id)
    setSelectedStepIndex(-1)
    setRuntimeSkillStatus({})

    const isRunning = sess.status === 'running'
    setSimulating(isRunning)

    // 重连仿真 SSE（后端会发 session_snapshot 全量快照 + 后续实时事件）
    if (esRef.current) esRef.current.close()
    const token = sess.auto_pipeline ? (gitcodeToken.trim() || '') : ''
    const es = streamWorkflowSimV2(sess.session_id, token)
    esRef.current = es
    attachSseHandlers(es, sess.session_id, { autoPipeline: sess.auto_pipeline })
    // 重连 jsonl tail
    connectJsonlStream(sess.session_id)
  }, [attachSseHandlers, connectJsonlStream, gitcodeToken])

  // 页面加载时检测运行中的会话（刷新恢复）。
  // 后端执行与 SSE 解耦后，刷新不杀进程；这里恢复 running 列表并重连 SSE 看实时。
  // 注意：必须放在 restoreSession 声明之后，否则依赖数组 [restoreSession] 在渲染期
  // 访问会触发 TDZ（Cannot access 'restoreSession' before initialization）。
  useEffect(() => {
    getActiveWorkflowSimV2Session()
      .then(res => {
        const running = res.data?.sessions || (res.data?.active ? [res.data.active] : [])
        setRunningSessions(running)
        if (running.length === 0) return
        // 恢复第一个 running 会话：重连 SSE（后端会发 session_snapshot 全量 + 实时事件）
        restoreSession(running[0])
      })
      .catch(() => {})
  }, [restoreSession])

  // 启动仿真
  const handleStart = useCallback(async () => {
    if (!selectedPlugin) { message.warning('请选择插件'); return }
    if (!opName.trim()) { message.warning('请输入算子名称'); return }

    // 重置状态
    setSteps([])
    setAlerts([])
    setMonitorInsights({})
    setRuntimeSkillStatus({})
    setTerminalLines([])
    setJsonlLines([])
    setJsonlActiveFile('')
    setJsonlWaiting(false)
    setLogs([])
    setProgLogs([])
    setSummary(null)
    setSelectedStepIndex(-1)
    setSimulating(true)
    setJourneyData([])
    setFixLog([])
    setPipeline(null)
    setFixRounds([])
    setNpuTest(null)
    setNpuLogs([])
    setViewingHistoryId(null)

    try {
      // 创建会话
      const createRes = await createWorkflowSimV2Session({
        plugin_id: selectedPlugin,
        op_name: opName.trim(),
        op_spec: opSpec.trim(),
        work_dir: workDir.trim(),
        step_timeout: stepTimeout,
        gitcode_token: autoPipeline ? gitcodeToken.trim() : '',
        auto_pipeline: autoPipeline,
        repo_url: repoUrl.trim(),
        fork_info: forkInfo,
        clone_status: cloneStatus === 'cloned' ? 'cloned'
          : cloneStatus === 'error' ? 'failed'
          : 'pending',
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
      setNpuTest(createRes.data.npu_test || null)
      setNpuLogs(createRes.data.npu_test?.logs || [])
      setViewingSessionId(sid)
      addLog('info', `会话已创建: ${sid}`)

      // 启动执行（fire-and-forget 后台 Task，与 SSE 解耦）
      const token = autoPipeline ? gitcodeToken.trim() : ''
      await startWorkflowSimV2Session(sid, token)
      addLog('info', '仿真已启动（后台执行），等待 SSE 流...')
      // 加入后台 running 列表
      setRunningSessions(prev => {
        if (prev.some(s => s.session_id === sid)) return prev
        return [{ ...createRes.data, status: 'running' }, ...prev]
      })

      // 连接 SSE（只读订阅）
      if (esRef.current) esRef.current.close()
      const es = streamWorkflowSimV2(sid, token)
      esRef.current = es

      // 连接 jsonl tail SSE（独立第二条连接，只读镜像 claude 原生工作流水）
      connectJsonlStream(sid)

      attachSseHandlers(es, sid, { autoPipeline })
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
      setNpuTest(data.npu_test || null)
      setNpuLogs(data.npu_test?.logs || [])
      setSession(data)
      setSelectedStepIndex(-1)
      // 同步选中插件为该历史会话的插件，驱动 Skill 实时流程图加载对应 pluginDef
      if (data.plugin_id && data.plugin_id !== selectedPlugin) {
        setSelectedPlugin(data.plugin_id)
      }
      // 恢复终端日志和仿真日志
      setTerminalLines(data.terminal_log || [])
      setLogs(data.simulation_log || [])
      // 恢复 monitor insights（从 steps 中提取持久化的 monitor_insight）
      const restoredMonitor = {}
      for (const s of (data.steps || [])) {
        if (s.monitor_insight) restoredMonitor[s.step_id] = { step_id: s.step_id, ...s.monitor_insight }
      }
      setMonitorInsights(restoredMonitor)
      // 重置 live-only 状态
      setRuntimeSkillStatus({})
      setJsonlActiveFile(null)
      setFixLog(data.fix_log || [])
      // 历史回看不触发自动滚动到底（避免页面被 scrollIntoView 带到终端/jsonl 面板）
      setTermPinned(false)
      setJsonlPinned(false)
      // 恢复 jsonl 工作流水：优先从 DB jsonl_log（实时执行时持久化），降级从磁盘回读
      if (data.jsonl_log?.length > 0) {
        setJsonlLines(data.jsonl_log)
      } else {
        setJsonlLines([])
        try {
          const jsonlRes = await getWorkflowJsonlHistory(sid)
          if (jsonlRes.data?.lines?.length > 0) setJsonlLines(jsonlRes.data.lines)
        } catch { /* 老会话 jsonl 文件可能已清理 */ }
      }
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
    setNpuTest(null)
    setNpuLogs([])
    setSession(null)
    setSelectedStepIndex(-1)
    setTerminalLines([])
    setLogs([])
  }, [session, viewingHistoryId])

  // 发起真机 NPU 远程测试
  const triggerNpuTest = useCallback((cfg) => {
    if (!session?.session_id) return
    if (npuEsRef.current) npuEsRef.current.close()
    const es = streamNpuTestSSE(session.session_id, cfg)
    npuEsRef.current = es
    setNpuTest(prev => ({
      ...(prev || {}),
      status: 'running', host: cfg.host, remote_dir: cfg.remote_dir,
      build_cmd: cfg.build_cmd, test_cmd: cfg.test_cmd,
      steps: [], summary: null, error: null,
    }))
    setNpuLogs([])
    addLog('info', `[NPU] 发起真机测试 → ${cfg.host}`)

    es.addEventListener('npu_start', (e) => {
      const d = JSON.parse(e.data)
      setNpuTest(prev => ({ ...(prev || {}), status: 'running', steps: d.steps, triggered_at: d.started_at }))
      if (d.message) addLog('info', `[NPU] ${d.message}`)
    })
    es.addEventListener('npu_step_update', (e) => {
      const d = JSON.parse(e.data)
      setNpuTest(prev => ({ ...(prev || {}), steps: d.steps }))
      const st = d.step?.status || '更新'
      const t = st === 'success' ? 'success' : st === 'failed' ? 'error' : 'info'
      addLog(t, `[NPU] ${d.step_key}: ${st}${d.message ? ' — ' + String(d.message).split('\n')[0] : ''}`)
    })
    es.addEventListener('npu_log', (e) => {
      const d = JSON.parse(e.data)
      setNpuLogs(prev => [...prev.slice(-1999), { step: d.step, stream: d.stream, line: d.line }])
    })
    es.addEventListener('npu_result', (e) => {
      const d = JSON.parse(e.data)
      setNpuTest(prev => ({ ...(prev || {}), summary: d.summary }))
    })
    es.addEventListener('npu_done', (e) => {
      const d = JSON.parse(e.data)
      setNpuTest(prev => ({
        ...(prev || {}),
        status: d.status, steps: d.steps, summary: d.summary || prev?.summary,
        completed_at: d.completed_at, error: d.error, error_detail: d.error_detail,
      }))
      const ok = d.status === 'success'
      addLog(ok ? 'success' : 'error', `[NPU] ${ok ? '真机测试通过' : '真机测试失败'}${d.error ? ' — ' + d.error : ''}`)
      message.info(ok ? '真机 NPU 测试通过' : '真机 NPU 测试存在失败')
      es.close()
    })
    es.onerror = () => {
      setNpuTest(prev => ({ ...(prev || {}), status: prev?.status === 'running' ? 'failed' : prev?.status }))
      addLog('error', '[NPU] SSE 连接断开')
      es.close()
    }
  }, [session, addLog])

  // 取消真机测试
  const cancelNpuTestRun = useCallback(async () => {
    if (!session?.session_id) return
    try {
      await cancelNpuTest(session.session_id)
      setNpuTest(prev => ({ ...(prev || {}), status: 'cancelled' }))
      addLog('warn', '真机测试已取消')
      if (npuEsRef.current) npuEsRef.current.close()
    } catch {
      message.error('取消失败')
    }
  }, [session, addLog])

  // Claude 驱动的真机测试（共享同一 Claude 会话上下文）
  const triggerNpuTestClaude = useCallback(async (cfg) => {
    if (!session?.session_id) return
    if (npuClaudeEsRef.current) npuClaudeEsRef.current.close()
    setNpuClaudeLogs([])
    setNpuClaudeRunning(true)
    setShowNpuClaude(true)

    const es = streamNpuTestClaudeSSE(session.session_id, cfg)
    npuClaudeEsRef.current = es

    es.addEventListener('npu_claude_start', (e) => {
      const data = JSON.parse(e.data)
      setNpuClaudeLogs(prev => [...prev, { time: new Date().toLocaleTimeString(), type: 'start', content: `Claude 真机测试启动 (session: ${data.claude_session_id || '?'}...)` }])
    })
    es.addEventListener('npu_claude_log', (e) => {
      const data = JSON.parse(e.data)
      setNpuClaudeLogs(prev => [...prev.slice(-1999), data])
    })
    es.addEventListener('npu_claude_done', (e) => {
      const data = JSON.parse(e.data)
      setNpuClaudeLogs(prev => [...prev, { time: new Date().toLocaleTimeString(), type: 'done', content: '── Claude 真机测试结束 ──' }])
      setNpuClaudeRunning(false)
      es.close()
    })
    es.onerror = () => {
      setNpuClaudeRunning(false)
      es.close()
    }
  }, [session])

  // 生成插件断点诊断（跨 session 聚合病灶）
  const runDiagnosis = useCallback(async () => {
    if (!selectedPlugin) { message.warning('请先选择插件'); return }
    setDiagnosisLoading(true)
    try {
      const res = await getBreakpointDiagnosis(selectedPlugin, diagnosisLimit)
      setDiagnosis(res.data)
      setDiagnosisOpen(true)
      const n = res.data?.meta?.session_count || 0
      if (n === 0) message.info('该插件暂无已完成的仿真样本')
    } catch (e) {
      message.error('生成诊断失败')
    } finally {
      setDiagnosisLoading(false)
    }
  }, [selectedPlugin, diagnosisLimit])

  const handleExportDiagnosis = useCallback(async () => {
    if (!selectedPlugin) { message.warning('请先选择插件'); return }
    try {
      const res = await exportBreakpointDiagnosis(selectedPlugin, diagnosisLimit)
      const url = URL.createObjectURL(res.data)
      const a = document.createElement('a')
      a.href = url
      a.download = `diagnosis-${selectedPlugin}.md`
      a.click()
      URL.revokeObjectURL(url)
    } catch { message.error('导出诊断失败') }
  }, [selectedPlugin, diagnosisLimit])

  // 当前选中步骤
  const selectedStep = selectedStepIndex >= 0 ? steps[selectedStepIndex] : null

  // 外部步骤图标
  const EXT_ICON = {
    clone: <GithubOutlined />,
    npu: <ApiOutlined />,
    cicd: <DeploymentUnitOutlined />,
  }

  // 后端枚举(status) → Ant Steps status 的统一映射
  const mapToStepsStatus = (raw) => {
    if (raw === 'running') return 'process'
    if (['completed', 'success', 'cloned'].includes(raw)) return 'finish'
    if (['failed', 'cancelled', 'timeout', 'error'].includes(raw)) return 'error'
    return 'wait' // pending / idle / unknown
  }

  // 生命周期视图：合并后端 steps（含 ext_* 壳）与 pipeline/npu/clone 实时状态
  const lifecycleSteps = useMemo(() => {
    if (!steps.length) return []
    const cloneRaw = session?.clone_status || 'pending'
    const npuRaw = npuTest?.status || 'pending'
    const cicdRaw = pipeline?.status || 'pending'
    return steps.map(s => {
      if (s.step_type !== 'external') return s
      let liveStatus = s.status
      if (s.step_category === 'clone') liveStatus = cloneRaw
      else if (s.step_category === 'npu') liveStatus = npuRaw
      else if (s.step_category === 'cicd') liveStatus = cicdRaw
      return { ...s, status: liveStatus }
    })
  }, [steps, session, npuTest, pipeline])
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
                  <div style={{ marginTop: 4, display: 'flex', gap: 8 }} onClick={e => e.stopPropagation()}>
                    <Button
                      size="small"
                      type="link"
                      style={{ fontSize: 10, padding: 0, height: 'auto', color: '#1677ff' }}
                      onClick={async () => {
                        // 切换查看这个后台运行中的会话：加载快照 + 重连 SSE 看实时
                        try {
                          const res = await getWorkflowSimV2Session(h.session_id)
                          if (res.data && !res.data.error) restoreSession(res.data)
                          else message.error('加载失败')
                        } catch { message.error('加载失败') }
                      }}
                    >
                      查看实时
                    </Button>
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
          {(forkStatus === 'checking' || cloneStatus === 'checking') && <Tag style={{ fontSize: 10 }}><LoadingOutlined /> 检查中</Tag>}
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
                onChange={e => setRepoUrl(e.target.value)}
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
                loading={forkStatus === 'forking' || forkStatus === 'checking'}
                disabled={!repoUrl.trim() || !gitcodeToken.trim() || forkStatus === 'forking' || forkStatus === 'forked' || forkStatus === 'checking'}
                type={forkStatus === 'forked' ? 'default' : 'primary'}
              >
                {forkStatus === 'forked' ? '已 Fork' : forkStatus === 'forking' ? 'Fork 中...' : forkStatus === 'checking' ? '检测中...' : 'Fork 到我的账号'}
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
          {installStatus === 'checking' && <Tag color="blue" style={{ fontSize: 10 }}><LoadingOutlined /> 检测中</Tag>}
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
              loading={installStatus === 'installing' || installStatus === 'checking'}
              disabled={!selectedPlugin || !workDir.trim() || installStatus === 'installing' || installStatus === 'installed' || installStatus === 'checking'}
              type={installStatus === 'installed' ? 'default' : 'primary'}
            >
              {installStatus === 'installed' ? '已安装' : installStatus === 'installing' ? '安装中...' : installStatus === 'checking' ? '检测中...' : '安装到工作目录'}
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
        {selectedPlugin && (
          <div style={{ marginTop: 8 }}>
            <Button
              size="small"
              type="link"
              icon={<ApartmentOutlined />}
              onClick={async () => {
                setPluginDrawerOpen(true)
                if (!pluginDef || (pluginDef.plugin_id !== selectedPlugin)) {
                  setPluginDefLoading(true)
                  try {
                    const res = await getWorkflowDefinition(selectedPlugin)
                    setPluginDef(res.data)
                  } catch { setPluginDef(null) }
                  finally { setPluginDefLoading(false) }
                }
              }}
            >
              查看插件架构
            </Button>
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
                  { value: 0, label: '不限制 (默认)' },
                  { value: 600, label: '10 分钟' },
                  { value: 1800, label: '30 分钟' },
                  { value: 3600, label: '60 分钟' },
                ]}
              />
            </Col>
            <Col>
              <Tooltip title="步骤执行超时限制。默认不限制，长任务安全。">
                <WarningOutlined style={{ color: '#faad14' }} />
              </Tooltip>
            </Col>
          </Row>
          <Row align="middle" gutter={8}>
            <Col>
              <Switch
                size="small"
                checked={autoPipeline}
                onChange={setAutoPipeline}
                disabled={!gitcodeToken.trim()}
              />
            </Col>
            <Col>
              <Text style={{ fontSize: 12 }}>自动触发 CI/CD 流水线</Text>
            </Col>
            <Col>
              <Tooltip title="开启后，仿真完成后将自动提交 PR、触发流水线编译测试，失败时自动修复（需填写 GitCode Token）">
                <WarningOutlined style={{ color: autoPipeline ? '#1677ff' : '#d9d9d9', fontSize: 12 }} />
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
              {session.install_result && (
                <Tag color={session.install_result.status === 'failed' ? 'red' : session.install_result.status === 'skipped' ? 'default' : 'green'} style={{ fontSize: 10 }}>
                  插件: {session.install_result.status === 'installed' ? '已安装' : session.install_result.status === 'already_installed' ? '已存在' : session.install_result.status === 'failed' ? '安装失败' : session.install_result.status}
                  {session.install_result.skills?.length > 0 && ` (${session.install_result.skills.length} skills, ${session.install_result.agents?.length || 0} agents)`}
                </Tag>
              )}
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

      {/* 终端面板（常驻显示，进仿真页面即可见） */}
      {(session || simulating) && (
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
          extra={<Space size={4}>
            <Button size="small" type="text" icon={showTerminal ? <DownOutlined /> : <UpOutlined />} onClick={() => setShowTerminal(v => !v)} />
            {!simulating && terminalLines.length > 0 && (
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
          </Space>}
        >
          {showTerminal && (
          <div ref={termBoxRef} onScroll={e => {
            const el = e.target; setTermPinned(el.scrollHeight - el.scrollTop - el.clientHeight < 40)
          }} style={{
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
            {!simulating && terminalLines.length === 0 && (
              <div style={{ color: '#666', textAlign: 'center', padding: 20 }}>暂无终端输出</div>
            )}
            <div ref={termEndRef} />
          </div>
          )}
        </Card>
      )}

      {/* Skill 实时流程图（GitHub-CI 风格，运行时逐个点亮） */}
      {pluginDef && (
        <Card size="small" title={<Space><ApartmentOutlined /> Skill 实时流程图</Space>} extra={
          <Button size="small" type="link" onClick={() => setPluginDrawerOpen(true)}>全屏查看</Button>
        } style={{ marginBottom: 12 }}>
          <PluginArchGraph pluginDef={pluginDef} monitorInsights={monitorInsights} steps={steps} runtimeSkillStatus={runtimeSkillStatus} />
        </Card>
      )}

      {/* 步骤进度（完整生命周期：clone → 插件开发流程 → NPU → CI/CD） */}
      {lifecycleSteps.length > 0 && (
        <Card size="small" title={<Space><CodeOutlined /> 工作流步骤 ({lifecycleSteps.length})</Space>}>
          <div className="lifecycle-steps">
            <style>{`
              .lifecycle-steps .ant-steps-item.plugin-step {
                background: #f0f5ff;
                border-left: 3px solid #adc6ff;
                border-radius: 4px;
                padding-left: 8px !important;
                margin-left: -4px;
              }
              .lifecycle-steps .ant-steps-item.plugin-step .ant-steps-item-title {
                width: 100%;
              }
              /* 圆点与步骤名顶部对齐（默认垂直居中，title 变高会错位） */
              .lifecycle-steps .ant-steps-vertical .ant-steps-item-tail,
              .lifecycle-steps .ant-steps-vertical > .ant-steps-item > .ant-steps-item-container > .ant-steps-item-tail {
                margin-inline-start: 13px;
              }
              /* 分组标签：绝对定位浮在 item 上方，不占 title 高度，避免圆点错位 */
              .lifecycle-group-label {
                position: absolute;
                top: -16px;
                left: 0;
                font-size: 11px;
                font-weight: 500;
                color: #8c8c8c;
                line-height: 1;
                pointer-events: none;
              }
              .lifecycle-group-label.plugin {
                color: #1d39c4;
              }
              /* 带分组标签的首步多留出顶部空间 */
              .lifecycle-steps .ant-steps-item.has-group {
                margin-top: 18px;
                position: relative;
              }
              .lifecycle-steps .ant-steps-item.ext-step .ant-steps-icon {
                color: #8c8c8c;
              }
            `}</style>
            <Steps
              size="small"
              direction="vertical"
              current={lifecycleSteps.findIndex(s => s.status === 'running')}
              items={lifecycleSteps.map((s, i) => {
                const isExt = s.step_type === 'external'
                // 插件步骤：保留门禁/Skill遵从度 tag
                let stepTag = null
                if (!isExt) {
                  const compliance = s.skill_compliance
                  if (s.gate_passed === false) {
                    stepTag = <Tag color="red" style={{ fontSize: 10, marginLeft: 4 }}>门禁未通过</Tag>
                  } else if (s.status === 'failed') {
                    stepTag = <Tag color="red" style={{ fontSize: 10, marginLeft: 4 }}>失败</Tag>
                  } else if (compliance) {
                    stepTag = (
                      <Tag color={compliance.score >= 0.8 ? 'green' : compliance.score >= 0.5 ? 'orange' : 'red'} style={{ fontSize: 10, marginLeft: 4 }}>
                        {Math.round(compliance.score * 100)}%
                      </Tag>
                    )
                  }
                }
                // 外部步骤：显示阶段状态 tag
                const extStatusText = { pending: '待执行', running: '执行中', success: '通过', cloned: '已完成', failed: '失败', cancelled: '已取消', timeout: '超时' }[s.status] || s.status
                const extStatusColor = mapToStepsStatus(s.status) === 'finish' ? 'green'
                  : mapToStepsStatus(s.status) === 'error' ? 'red'
                  : mapToStepsStatus(s.status) === 'process' ? 'blue' : 'default'
                // 分组小标签（每组首步显示，绝对定位浮在 item 上方，不占 title 高度）
                let groupLabel = null
                if (isExt && s.step_category === 'clone') {
                  groupLabel = '▾ 前置准备'
                } else if (!isExt && lifecycleSteps.slice(0, i).every(x => x.step_type === 'external' || x.step_category === 'clone')) {
                  groupLabel = '▾ 插件开发流程'
                } else if (isExt && s.step_category === 'npu') {
                  groupLabel = '▾ 验收'
                }
                return {
                  className: `${isExt ? 'ext-step' : 'plugin-step'}${groupLabel ? ' has-group' : ''}`,
                  title: (
                    <div>
                      {groupLabel && (
                        <div className={!isExt ? 'lifecycle-group-label plugin' : 'lifecycle-group-label'}>
                          {groupLabel}
                        </div>
                      )}
                      <span
                        style={{ cursor: isExt ? 'default' : 'pointer' }}
                        onClick={() => { if (!isExt) setSelectedStepIndex(i) }}
                      >
                        {isExt && <span style={{ marginRight: 4 }}>{EXT_ICON[s.step_category]}</span>}
                        {s.step_name}
                        {stepTag}
                        {isExt && <Tag color={extStatusColor} style={{ fontSize: 10, marginLeft: 4 }}>{extStatusText}</Tag>}
                      </span>
                    </div>
                  ),
                  status: isExt ? mapToStepsStatus(s.status) : (s.status === 'running' ? 'process' : s.status === 'completed' ? 'finish' : s.status === 'failed' ? 'error' : 'wait'),
                  icon: isExt
                    ? (mapToStepsStatus(s.status) === 'finish'
                        ? <CheckCircleOutlined style={{ color: '#52c41a' }} />
                        : mapToStepsStatus(s.status) === 'process'
                          ? <LoadingOutlined />
                          : mapToStepsStatus(s.status) === 'error'
                            ? <CloseCircleOutlined style={{ color: '#ff4d4f' }} />
                            : <span style={{ color: '#8c8c8c' }}>{EXT_ICON[s.step_category]}</span>)
                    : (s.status === 'completed'
                        ? <CheckCircleOutlined style={{ color: s.gate_passed === false ? '#ff4d4f' : '#52c41a' }} />
                        : s.status === 'running'
                          ? <LoadingOutlined />
                          : s.status === 'failed'
                            ? <CloseCircleOutlined style={{ color: '#ff4d4f' }} />
                            : null),
                }
              })}
            />
          </div>
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
                门禁{selectedStep.gate_passed === true ? '通过' : selectedStep.gate_passed === null ? '跳过' : '未通过'}
                {selectedStep.gate_ai_override && ' (AI)'}
              </Tag>
            )}
            {selectedStep.ai_gate && (
              <Tag color={selectedStep.ai_gate.verdict === 'passed' ? 'green' : selectedStep.ai_gate.verdict === 'failed' ? 'red' : 'default'} style={{ fontSize: 10 }}>
                AI门禁: {selectedStep.ai_gate.verdict}
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
          {/* AI 门禁判断结果 */}
          {selectedStep.ai_gate && (
            <div style={{ marginBottom: 8, padding: '6px 8px', background: selectedStep.ai_gate.verdict === 'passed' ? '#f6ffed' : '#fff1f0', borderRadius: 4 }}>
              <Text strong style={{ fontSize: 12 }}>🤖 AI 门禁: {selectedStep.ai_gate.verdict}</Text>
              <div style={{ fontSize: 11, color: '#666', marginTop: 4 }}>{selectedStep.ai_gate.reasoning}</div>
              {selectedStep.ai_gate.found_files?.length > 0 && (
                <div style={{ marginTop: 4 }}>
                  <Text type="secondary" style={{ fontSize: 10 }}>找到的文件: </Text>
                  {selectedStep.ai_gate.found_files.map(f => <Tag key={f} style={{ fontSize: 9 }}>{f}</Tag>)}
                </div>
              )}
              {selectedStep.ai_gate.missing_core?.length > 0 && (
                <div style={{ marginTop: 4 }}>
                  <Text type="danger" style={{ fontSize: 10 }}>缺失要素: </Text>
                  {selectedStep.ai_gate.missing_core.map(m => <Tag key={m} color="red" style={{ fontSize: 9 }}>{m}</Tag>)}
                </div>
              )}
            </div>
          )}
          {/* 门禁产物 */}
          {selectedStep.gate_artifacts?.length > 0 && (
            <div style={{ marginBottom: 8 }}>
              <Tooltip title={`门禁 = 步骤完成后检查预期的产出物文件是否已生成（如 DESIGN.md、op_kernel 代码等）。通过表示所有预期文件都已创建。`}>
                <Text strong style={{ fontSize: 12 }}>
                  门禁检查: {selectedStep.gate_passed === true ? '✓ 通过' : selectedStep.gate_passed === null ? '— 跳过' : '✗ 未通过'}
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
                  门禁检查: {selectedStep.gate_passed === true ? '✓ 通过' : selectedStep.gate_passed === null ? '— 跳过' : '✗ 未通过'}
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
                    {selectedStep.skill_compliance.skills_referenced.map(s => {
                      const fromSub = (selectedStep.skill_compliance.skills_from_subagents || []).includes(s)
                      return <Tag key={s} color="green" style={{ fontSize: 10 }}>{s}{fromSub ? ' (sub)' : ''}</Tag>
                    })}
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
          {/* 监控 LLM 语义遵从度 */}
          {(() => {
            const mi = monitorInsights[selectedStep.step_id]
            if (!mi || !mi.skills_analysis?.length) return null
            const scoreColor = mi.overall_score >= 80 ? '#52c41a' : mi.overall_score >= 50 ? '#faad14' : '#ff4d4f'
            return (
              <div style={{ marginBottom: 8, padding: 8, background: '#fafafa', borderRadius: 6, border: '1px solid #f0f0f0' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                  <SafetyCertificateOutlined style={{ color: scoreColor }} />
                  <Text strong style={{ fontSize: 12 }}>语义遵从度: {mi.overall_score}分</Text>
                </div>
                {mi.skills_analysis.map((sa, idx) => {
                  const statusColor = sa.status === 'compliant' ? 'green' : sa.status === 'partial' ? 'orange' : sa.status === 'violation' ? 'red' : 'default'
                  const statusText = { compliant: '合规', partial: '部分合规', violation: '违规', not_detected: '未检测' }[sa.status] || sa.status
                  return (
                    <div key={idx} style={{ marginBottom: idx < mi.skills_analysis.length - 1 ? 6 : 0, padding: '4px 6px', background: '#fff', borderRadius: 4 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                        <Tag color={statusColor} style={{ fontSize: 9, lineHeight: '14px', padding: '0 4px', margin: 0 }}>{statusText}</Tag>
                        <Text strong style={{ fontSize: 11 }}>{sa.skill}</Text>
                        {sa.confidence != null && <Text type="secondary" style={{ fontSize: 9 }}>置信度 {Math.round(sa.confidence * 100)}%</Text>}
                      </div>
                      {sa.detail && <div style={{ fontSize: 11, color: '#666', marginTop: 2 }}>{sa.detail}</div>}
                      {sa.followed?.length > 0 && (
                        <div style={{ marginTop: 2 }}>
                          <Text type="secondary" style={{ fontSize: 10 }}>已遵守: </Text>
                          {sa.followed.map((f, fi) => <Tag key={fi} color="green" style={{ fontSize: 9, lineHeight: '12px', padding: '0 3px', margin: '0 2px' }}>{f}</Tag>)}
                        </div>
                      )}
                      {sa.violated?.length > 0 && (
                        <div style={{ marginTop: 2 }}>
                          <Text type="secondary" style={{ fontSize: 10 }}>违反: </Text>
                          {sa.violated.map((v, vi) => <Tag key={vi} color="red" style={{ fontSize: 9, lineHeight: '12px', padding: '0 3px', margin: '0 2px' }}>{v}</Tag>)}
                        </div>
                      )}
                      {sa.missing?.length > 0 && (
                        <div style={{ marginTop: 2 }}>
                          <Text type="secondary" style={{ fontSize: 10 }}>未检测: </Text>
                          {sa.missing.map((m, mi2) => <Tag key={mi2} style={{ fontSize: 9, lineHeight: '12px', padding: '0 3px', margin: '0 2px' }}>{m}</Tag>)}
                        </div>
                      )}
                    </div>
                  )
                })}
                {mi.warnings?.length > 0 && (
                  <div style={{ marginTop: 6, padding: '4px 6px', background: '#fffbe6', borderRadius: 4 }}>
                    <WarningOutlined style={{ color: '#faad14', marginRight: 4 }} />
                    <Text style={{ fontSize: 11 }}>{mi.warnings.join('; ')}</Text>
                  </div>
                )}
              </div>
            )
          })()}
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

      {/* 实时调用链旅程图 */}
      {journeyData.length > 0 && (
        <Card size="small" title={<Space><NodeIndexOutlined /> 实时调用链 ({journeyData.length} 步)</Space>}
          bodyStyle={{ padding: 8 }}
        >
          <div style={{ display: 'flex', gap: 8, overflowX: 'auto', paddingBottom: 4 }}>
            {journeyData.map((step, si) => {
              const isRunning = step.status === 'running'
              const isFailed = step.status === 'completed' && step.gate_passed === false
              const stepColor = isRunning ? '#1890ff' : isFailed ? '#ff4d4f' : '#52c41a'
              const agentCalls = step.calls.filter(c => c.type === 'agent')
              const topSkills = step.calls.filter(c => c.type === 'skill' && c.from === 'top')
              const subSkills = (step.skills_from_subagents || [])
              const missingSkills = (step.skills_missing || [])
              const referencedSkills = (step.skills_referenced || [])
              return (
                <div key={step.step_id} style={{
                  minWidth: 220, maxWidth: 300, flexShrink: 0,
                  border: `1px solid ${stepColor}40`, borderRadius: 6, padding: 8,
                  background: isRunning ? '#e6f7ff' : isFailed ? '#fff1f0' : '#f6ffed',
                }}>
                  {/* 步骤头 */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 6 }}>
                    <span style={{ fontSize: 11, fontWeight: 600, color: stepColor }}>
                      {si + 1}. {step.step_name}
                    </span>
                    {isRunning && <LoadingOutlined style={{ fontSize: 10, color: '#1890ff' }} />}
                    {step.status === 'completed' && !isFailed && <CheckCircleOutlined style={{ fontSize: 10, color: '#52c41a' }} />}
                    {isFailed && <CloseCircleOutlined style={{ fontSize: 10, color: '#ff4d4f' }} />}
                  </div>

                  {/* Agent 调用 */}
                  {agentCalls.map((ac, ai) => (
                    <div key={ai} style={{ marginLeft: 4, marginBottom: 4 }}>
                      <div style={{ fontSize: 10, color: '#722ed1', fontWeight: 500 }}>
                        🤖 {ac.name}
                        <span style={{ color: '#999', fontWeight: 400, marginLeft: 4 }}>{ac.ts}</span>
                      </div>
                      {ac.desc && <div style={{ fontSize: 9, color: '#999', marginLeft: 14, marginBottom: 2 }}>{ac.desc.slice(0, 50)}</div>}
                      {/* Agent 声明的 skills */}
                      {ac.skills?.length > 0 && (
                        <div style={{ marginLeft: 14 }}>
                          {ac.skills.map((sk, ski) => {
                            const isMissing = missingSkills.includes(sk)
                            const isReferenced = referencedSkills.includes(sk)
                            return (
                              <div key={ski} style={{
                                fontSize: 9, lineHeight: '16px',
                                color: isMissing ? '#ff4d4f' : isReferenced ? '#52c41a' : '#8c8c8c',
                              }}>
                                🎯 {sk}
                                {isMissing && <span style={{ color: '#ff4d4f' }}> ✗</span>}
                                {isReferenced && !isMissing && <span style={{ color: '#52c41a' }}> ✓</span>}
                              </div>
                            )
                          })}
                        </div>
                      )}
                    </div>
                  ))}

                  {/* 顶层 Skill 调用 */}
                  {topSkills.map((sc, ski) => (
                    <div key={ski} style={{ fontSize: 9, marginLeft: 4, color: '#389e0d', lineHeight: '16px' }}>
                      🎯 {sc.name} <span style={{ color: '#999' }}>{sc.ts}</span>
                    </div>
                  ))}

                  {/* Subagent 捕获的 Skill */}
                  {subSkills.length > 0 && agentCalls.length > 0 && (
                    <div style={{ marginLeft: 4, marginTop: 2, paddingTop: 2, borderTop: '1px dashed #d9d9d9' }}>
                      <div style={{ fontSize: 9, color: '#999', marginBottom: 2 }}>subagent 捕获:</div>
                      {subSkills.map((sk, ski) => (
                        <div key={ski} style={{ fontSize: 9, marginLeft: 14, color: '#389e0d', lineHeight: '16px' }}>
                          🎯 {sk} <span style={{ color: '#52c41a' }}>✓</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* 缺失 Skill */}
                  {missingSkills.length > 0 && (
                    <div style={{ marginLeft: 4, marginTop: 2, paddingTop: 2, borderTop: '1px dashed #ffccc7' }}>
                      <div style={{ fontSize: 9, color: '#ff4d4f', marginBottom: 2 }}>未引用:</div>
                      {missingSkills.map((sk, ski) => (
                        <div key={ski} style={{ fontSize: 9, marginLeft: 14, color: '#ff4d4f', lineHeight: '16px' }}>
                          🎯 {sk} <span style={{ color: '#ff4d4f' }}>✗</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* 空状态 */}
                  {step.calls.length === 0 && missingSkills.length === 0 && (
                    <div style={{ fontSize: 9, color: '#999', marginLeft: 4 }}>
                      {isRunning ? '执行中…' : '无调用记录'}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </Card>
      )}

      {/* 真机 NPU 远程测试面板 */}
      {(session?.status === 'completed' || session?.status === 'stopped' || npuTest) && (
        <NpuTestPanel
          npuTest={npuTest}
          logs={npuLogs}
          sessionId={session?.session_id}
          sessionStatus={session?.status}
          logEndRef={npuLogEndRef}
          boxRef={npuBoxRef}
          onBoxScroll={e => { const el = e.target; setNpuPinned(el.scrollHeight - el.scrollTop - el.clientHeight < 40) }}
          onTrigger={triggerNpuTest}
          onCancel={npuTest?.status === 'running' ? cancelNpuTestRun : null}
          onTriggerClaude={triggerNpuTestClaude}
        />
      )}

      {/* 流水线状态面板 */}
      {pipeline && (
        <PipelinePanel
          pipeline={pipeline}
          fixRounds={fixRounds}
          onCancel={pipeline?.status === 'running' && session?.session_id ? async () => {
            try {
              await cancelPipeline(session.session_id)
              setPipeline(prev => ({ ...(prev || {}), status: 'cancelled' }))
              addLog('warn', '流水线已手动取消')
              message.info('流水线已取消')
            } catch (e) {
              message.error('取消失败')
            }
          } : null}
          onTrigger={session?.status === 'completed' || session?.status === 'stopped' ? () => {
            if (!gitcodeToken.trim()) { message.warning('请先填写 GitCode Token'); return }
            const es = triggerPipelineSSE(session.session_id, gitcodeToken.trim())
            setPipeline(prev => ({ ...(prev || {}), status: 'running' }))
            addLog('info', '[Pipeline] 手动触发流水线...')
            es.addEventListener('pipeline_status', (e) => {
              const data = JSON.parse(e.data)
              setPipeline(prev => ({ ...(prev || {}), ...data }))
              if (data.message) addLog('info', `[Pipeline] ${data.message}`)
            })
            es.addEventListener('pipeline_start', (e) => {
              const data = JSON.parse(e.data)
              setPipeline(prev => ({
                ...(prev || {}), status: 'running',
                mr_url: data.mr_url, mr_iid: data.mr_iid,
                steps: data.steps || prev?.steps || [],
                triggered_at: data.triggered_at,
              }))
              addLog('info', `流水线已触发${data.mr_url ? ` — MR: ${data.mr_url}` : ''}`)
            })
            es.addEventListener('pipeline_step_update', (e) => {
              const data = JSON.parse(e.data)
              setPipeline(prev => ({
                ...(prev || {}),
                steps: data.steps || prev?.steps || [],
                mr_url: data.mr_url || prev?.mr_url,
                mr_iid: data.mr_iid || prev?.mr_iid,
              }))
              const stepStatus = data.step?.status || '更新'
              const stepName = data.step?.name || data.step_key
              const logType = stepStatus === 'success' ? 'success' : stepStatus === 'failed' ? 'error' : 'info'
              const msg = data.message ? ` — ${data.message}` : ''
              addLog(logType, `[Pipeline] ${stepName}: ${stepStatus}${msg}`)
            })
            es.addEventListener('pipeline_fix_round', (e) => {
              const data = JSON.parse(e.data)
              setFixRounds(prev => [...prev, data])
              addLog('warn', `修复轮次 ${data.round_number}: ${data.error_type}${data.error_log ? ' — ' + data.error_log.slice(0, 100) : ''}`)
            })
            es.addEventListener('pipeline_done', (e) => {
              const data = JSON.parse(e.data)
              setPipeline(prev => ({
                ...(prev || {}), status: data.status,
                steps: data.steps || prev?.steps || [],
                completed_at: data.completed_at,
              }))
              if (data.status === 'success') {
                addLog('success', '流水线全部通过')
              } else {
                const failedSteps = (data.steps || []).filter(s => s.status === 'failed')
                const failedNames = failedSteps.map(s => s.name || s.key).join(', ') || '未知'
                const errMsg = data.error ? ` — ${data.error}` : ''
                addLog('error', `流水线失败: ${failedNames}${errMsg}`)
              }
              message.info(data.status === 'success' ? 'CI/CD 流水线全部通过' : 'CI/CD 流水线存在失败')
              es.close()
            })
            es.onerror = () => {
              setPipeline(prev => ({ ...(prev || {}), status: prev?.status === 'running' ? 'failed' : prev?.status }))
              es.close()
            }
          } : null}
        />
      )}

      {/* 修复流程日志面板 */}
      {fixLog.length > 0 && (
        <Card size="small" title={
          <Space>
            <ToolOutlined />
            <span>修复流程</span>
            <Tag style={{ fontSize: 10 }}>{fixLog.length} 条</Tag>
          </Space>
        }
          extra={<Space size={4}>
            <Button size="small" type="text" icon={showFixLog ? <DownOutlined /> : <UpOutlined />} onClick={() => setShowFixLog(v => !v)} />
            <Button size="small" icon={<DownloadOutlined />} onClick={() => {
              const content = fixLog.map(l => `[${l.time}] [${l.type}] ${l.content}`).join('\n')
              const blob = new Blob([content], { type: 'text/plain' })
              const url = URL.createObjectURL(blob)
              const a = document.createElement('a')
              a.href = url
              a.download = `fix-log-${session?.session_id || 'log'}.txt`
              a.click()
              URL.revokeObjectURL(url)
            }}>下载</Button>
          </Space>}
        >
          {showFixLog && (
            <div style={{
              background: '#1a1a2e', borderRadius: 6, padding: 8,
              maxHeight: 300, overflowY: 'auto', fontFamily: 'Menlo, Monaco, monospace', fontSize: 12,
            }}>
              {fixLog.map((l, i) => {
                const color = l.type === 'start' ? '#faad14' : l.type === 'done' && l.content.includes('✅') ? '#52c41a' : l.type === 'done' ? '#ff4d4f' : l.type === 'tool_use' ? '#8ab4f8' : l.type === 'thinking' ? '#9aa0a6' : l.type === 'tool_result' ? '#5f6368' : '#e8eaed'
                return (
                  <div key={i} style={{ color, lineHeight: '18px', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                    <span style={{ color: '#666' }}>{l.time || ''} </span>
                    {l.content || ''}
                  </div>
                )
              })}
            </div>
          )}
        </Card>
      )}

      {/* Claude 工作流水（jsonl 实时镜像）—— claude 原生存档的完整 thinking/tool_use/tool_result 流水 */}
      {(simulating || jsonlLines.length > 0) && (
        <Card
          size="small"
          title={
            <Space>
              <FileTextOutlined />
              <span>Claude 工作流水</span>
              {simulating && <Spin size="small" />}
              <Tag style={{ fontSize: 10 }}>{jsonlLines.length} 行</Tag>
              {jsonlActiveFile && <Tag color="blue" style={{ fontSize: 10 }}>{jsonlActiveFile.slice(0, 8)}</Tag>}
            </Space>
          }
          extra={<Space size={4}>
            <Button size="small" type="text" icon={showJsonl ? <DownOutlined /> : <UpOutlined />} onClick={() => setShowJsonl(v => !v)} />
            <Text type="secondary" style={{ fontSize: 11 }}>jsonl 实时镜像</Text>
          </Space>}
        >
          {showJsonl && (
          <div ref={jsonlBoxRef} onScroll={e => {
            const el = e.target; setJsonlPinned(el.scrollHeight - el.scrollTop - el.clientHeight < 40)
          }} style={{
            background: '#1e1e1e', borderRadius: 6, padding: 8,
            maxHeight: 400, overflowY: 'auto', fontFamily: 'Menlo, Monaco, monospace', fontSize: 12,
          }}>
            {jsonlWaiting && jsonlLines.length === 0 && (
              <div style={{ color: '#888', textAlign: 'center', padding: 20 }}>等待 claude 会话启动…</div>
            )}
            {jsonlLines.map((l, i) => {
              const color = (
                l.kind === 'thinking' ? '#9aa0a6' :
                l.kind === 'text' ? '#e8eaed' :
                l.kind === 'tool_use' ? '#8ab4f8' :
                l.kind === 'tool_result' ? '#bdc1c6' :
                l.kind === 'switch' ? '#fdd663' :
                l.kind === 'subagent_switch' ? '#c586f0' :  // 紫色：子 Agent 流水切换
                '#5f6368'
              )
              const opacity = (l.kind === 'thinking' || l.kind === 'tool_result' || l.kind === 'system') ? 0.75 : 1
              const indent = (l.kind === 'tool_result') ? '    ' : ''
              const weight = (l.kind === 'tool_use' || l.kind === 'switch' || l.kind === 'subagent_switch') ? 600 : 400
              const ts = l.ts ? l.ts.slice(11, 19) : ''  // 取 HH:MM:SS
              return (
                <div key={i} style={{ color, opacity, fontWeight: weight, lineHeight: '18px', wordBreak: 'break-all', whiteSpace: 'pre-wrap' }}>
                  {ts && <span style={{ color: '#5f6368', marginRight: 6 }}>{ts}</span>}{indent}{l.summary || `[${l.type || l.kind}]`}
                </div>
              )
            })}
            <div ref={jsonlEndRef} />
          </div>
          )}
        </Card>
      )}

      {/* 实时 Skill 监控面板 */}
      {Object.keys(monitorInsights).length > 0 && (
        <Card
          size="small"
          title={
            <Space>
              <SafetyCertificateOutlined />
              <span>Skill 语义监控</span>
            </Space>
          }
          style={{ marginTop: 8 }}
        >
          <div style={{ maxHeight: 500, overflowY: 'auto' }}>
            {Object.entries(monitorInsights).map(([stepId, insight]) => (
              <div key={stepId} style={{ marginBottom: 12, padding: 10, background: '#fafafa', borderRadius: 6, border: '1px solid #f0f0f0' }}>
                {/* 步骤标题 + 总分 */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                  <Text strong style={{ fontSize: 12 }}>{stepId}</Text>
                  {insight.overall_score >= 0 && (
                    <Tag color={insight.overall_score >= 80 ? 'green' : insight.overall_score >= 50 ? 'orange' : 'red'} style={{ fontSize: 10 }}>
                      {insight.overall_score}分
                    </Tag>
                  )}
                </div>

                {/* 整体分析思路 */}
                {insight.analysis_process && (
                  <div style={{ marginBottom: 8, padding: '6px 8px', background: '#fff', borderRadius: 4, borderLeft: '3px solid #1677ff' }}>
                    <Text style={{ fontSize: 11, color: '#444' }}><Text strong style={{ fontSize: 11 }}>分析思路: </Text>{insight.analysis_process}</Text>
                  </div>
                )}

                {/* 总体评分依据 */}
                {insight.overall_reasoning && (
                  <div style={{ marginBottom: 8, padding: '4px 8px', background: '#fff', borderRadius: 4 }}>
                    <Text style={{ fontSize: 11, color: '#666' }}><Text strong style={{ fontSize: 11 }}>评分依据: </Text>{insight.overall_reasoning}</Text>
                  </div>
                )}

                {/* 每个 Skill 的详细分析 */}
                {(insight.skills_analysis || []).map((sa, idx) => {
                  const statusColor = sa.status === 'compliant' ? 'green' : sa.status === 'partial' ? 'orange' : sa.status === 'violation' ? 'red' : 'default'
                  const statusText = { compliant: '合规', partial: '部分', violation: '违规', not_detected: '未检测' }[sa.status] || sa.status
                  return (
                    <div key={idx} style={{ marginBottom: 8, padding: '6px 8px', background: '#fff', borderRadius: 4, border: `1px solid ${sa.status === 'violation' ? '#ffccc7' : sa.status === 'partial' ? '#ffe58f' : '#f0f0f0'}` }}>
                      {/* Skill 名 + 状态 */}
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                        <Tag color={statusColor} style={{ fontSize: 9, lineHeight: '12px', padding: '0 4px', margin: 0 }}>{statusText}</Tag>
                        <Text strong style={{ fontSize: 11 }}>{sa.skill}</Text>
                        {sa.confidence != null && <Text type="secondary" style={{ fontSize: 9 }}>置信度 {Math.round(sa.confidence * 100)}%</Text>}
                      </div>

                      {/* 一句话结论 */}
                      {sa.detail && (
                        <div style={{ fontSize: 11, color: '#333', marginBottom: 4 }}>{sa.detail}</div>
                      )}

                      {/* 检查了哪些约束 */}
                      {sa.constraints_checked?.length > 0 && (
                        <div style={{ marginBottom: 3 }}>
                          <Text type="secondary" style={{ fontSize: 10 }}>检查的约束: </Text>
                          {sa.constraints_checked.map((c, ci) => <Tag key={ci} color="blue" style={{ fontSize: 9, lineHeight: '12px', padding: '0 3px', margin: '1px 2px' }}>{c}</Tag>)}
                        </div>
                      )}

                      {/* 找到的证据 */}
                      {sa.evidence_found?.length > 0 && (
                        <div style={{ marginBottom: 3 }}>
                          <Text type="secondary" style={{ fontSize: 10 }}>支撑证据: </Text>
                          {sa.evidence_found.map((e, ei) => <Tag key={ei} color="green" style={{ fontSize: 9, lineHeight: '12px', padding: '0 3px', margin: '1px 2px' }}>{e}</Tag>)}
                        </div>
                      )}

                      {/* 缺失的证据 */}
                      {sa.evidence_missing?.length > 0 && (
                        <div style={{ marginBottom: 3 }}>
                          <Text type="secondary" style={{ fontSize: 10 }}>缺失证据: </Text>
                          {sa.evidence_missing.map((e, ei) => <Tag key={ei} color="orange" style={{ fontSize: 9, lineHeight: '12px', padding: '0 3px', margin: '1px 2px' }}>{e}</Tag>)}
                        </div>
                      )}

                      {/* 已遵守 / 违反 / 未检测 */}
                      {sa.followed?.length > 0 && (
                        <div style={{ marginBottom: 2 }}>
                          <Text type="secondary" style={{ fontSize: 10 }}>已遵守: </Text>
                          {sa.followed.map((f, fi) => <Tag key={fi} color="green" style={{ fontSize: 9, lineHeight: '12px', padding: '0 3px', margin: '1px 2px' }}>{f}</Tag>)}
                        </div>
                      )}
                      {sa.violated?.length > 0 && (
                        <div style={{ marginBottom: 2 }}>
                          <Text type="secondary" style={{ fontSize: 10 }}>违反: </Text>
                          {sa.violated.map((v, vi) => <Tag key={vi} color="red" style={{ fontSize: 9, lineHeight: '12px', padding: '0 3px', margin: '1px 2px' }}>{v}</Tag>)}
                        </div>
                      )}
                      {sa.missing?.length > 0 && (
                        <div style={{ marginBottom: 2 }}>
                          <Text type="secondary" style={{ fontSize: 10 }}>未检测: </Text>
                          {sa.missing.map((m, mi) => <Tag key={mi} style={{ fontSize: 9, lineHeight: '12px', padding: '0 3px', margin: '1px 2px' }}>{m}</Tag>)}
                        </div>
                      )}

                      {/* 详细推理过程 */}
                      {sa.reasoning && (
                        <div style={{ marginTop: 4, padding: '4px 6px', background: '#f6f8fa', borderRadius: 3, borderLeft: '2px solid #d9d9d9' }}>
                          <Text type="secondary" style={{ fontSize: 10 }}>推理过程: </Text>
                          <Text style={{ fontSize: 10, color: '#555' }}>{sa.reasoning}</Text>
                        </div>
                      )}
                    </div>
                  )
                })}

                {/* 警告 */}
                {insight.warnings?.filter(w => w !== 'LLM 未配置').length > 0 && (
                  <div style={{ marginTop: 4, padding: '3px 6px', background: '#fffbe6', borderRadius: 3, fontSize: 11, color: '#ad6800' }}>
                    <WarningOutlined style={{ marginRight: 4 }} />{insight.warnings.filter(w => w !== 'LLM 未配置').join('; ')}
                  </div>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* 程序日志面板 */}
      {showProgLog && (simulating || progLogs.length > 0) && (
        <Card
          size="small"
          title={
            <Space>
              <CodeOutlined style={{ color: '#722ed1' }} />
              <span>程序日志</span>
              <Tag style={{ fontSize: 10 }}>{progLogs.length}</Tag>
              <Button
                type="link" size="small" style={{ padding: 0, fontSize: 11 }}
                onClick={() => { setProgLogs([]); }}
              >清空</Button>
              <Button
                type="link" size="small" style={{ padding: 0, fontSize: 11 }}
                onClick={() => setShowProgLog(false)}
              >收起</Button>
            </Space>
          }
          extra={!simulating && progLogs.length > 0 && (
            <Button size="small" icon={<DownloadOutlined />} onClick={() => {
              const content = progLogs.map(l => {
                let line = `[${l.time || ''}] [${(l.level || 'INFO').toUpperCase()}] ${l.msg || ''}`
                if (l.extra) line += `  ${JSON.stringify(l.extra)}`
                return line
              }).join('\n')
              const blob = new Blob([content], { type: 'text/plain' })
              const url = URL.createObjectURL(blob)
              const a = document.createElement('a')
              a.href = url
              a.download = `proglog-${session?.session_id || 'log'}.txt`
              a.click()
              URL.revokeObjectURL(url)
            }}>下载</Button>
          )}
        >
          <div
            ref={progLogBoxRef}
            onScroll={() => {
              if (!progLogBoxRef.current) return
              const el = progLogBoxRef.current
              setProgLogPinned(el.scrollHeight - el.scrollTop - el.clientHeight < 30)
            }}
            style={{
              maxHeight: 350, overflowY: 'auto', background: '#1a1a2e', borderRadius: 6,
              padding: 8, fontSize: 11, fontFamily: 'Menlo, Monaco, "Courier New", monospace',
              color: '#d4d4d4', lineHeight: 1.6,
            }}
          >
            {progLogs.length === 0 && (
              <div style={{ color: '#666', textAlign: 'center', padding: 20 }}>等待程序日志...</div>
            )}
            {progLogs.map((log, i) => {
              const level = (log.level || 'INFO').toUpperCase()
              const color = level === 'ERROR' ? '#ff6b6b' : level === 'WARN' ? '#ffd93d' : level === 'DEBUG' ? '#6bcfff' : '#52c41a'
              return (
                <div key={i} style={{ marginBottom: 1, display: 'flex', gap: 6 }}>
                  <span style={{ color: '#666', flexShrink: 0 }}>{log.time || ''}</span>
                  <span style={{ color, flexShrink: 0, fontWeight: 'bold' }}>{level.padEnd(5)}</span>
                  <span style={{ color: '#d4d4d4', wordBreak: 'break-all' }}>
                    {log.msg || ''}
                    {log.extra && (
                      <span style={{ color: '#888' }}>  {JSON.stringify(log.extra)}</span>
                    )}
                  </span>
                </div>
              )
            })}
            <div ref={progLogEndRef} />
          </div>
        </Card>
      )}

      {/* 程序日志收起时的展开按钮 */}
      {!showProgLog && progLogs.length > 0 && (
        <Button
          type="dashed" size="small" block
          icon={<CodeOutlined style={{ color: '#722ed1' }} />}
          onClick={() => setShowProgLog(true)}
          style={{ marginBottom: 8 }}
        >
          展开程序日志（{progLogs.length} 条）
        </Button>
      )}

      {/* Claude 真机远程测试面板（共享同一 Claude 会话上下文） */}
      {showNpuClaude && (npuClaudeRunning || npuClaudeLogs.length > 0) && (
        <Card
          size="small"
          title={
            <Space>
              <ThunderboltOutlined style={{ color: '#13c2c2' }} />
              <span>Claude 真机远程测试</span>
              {npuClaudeRunning && <Tag color="processing">运行中</Tag>}
              <Tag style={{ fontSize: 10 }}>{npuClaudeLogs.length}</Tag>
              <Button type="link" size="small" style={{ padding: 0, fontSize: 11 }} onClick={() => { setNpuClaudeLogs([]) }}>清空</Button>
              <Button type="link" size="small" style={{ padding: 0, fontSize: 11 }} onClick={() => setShowNpuClaude(false)}>收起</Button>
            </Space>
          }
        >
          <div style={{
            maxHeight: 400, overflowY: 'auto', background: '#0d1117', borderRadius: 6,
            padding: 8, fontSize: 11, fontFamily: 'Menlo, Monaco, "Courier New", monospace',
            color: '#c9d1d9', lineHeight: 1.6,
          }}>
            {npuClaudeLogs.map((log, i) => {
              const t = log.type || ''
              const color = t === 'tool_use' ? '#79c0ff' : t === 'thinking' ? '#8b949e' : t === 'tool_result' ? '#7ee787' : t === 'done' ? '#f0883e' : '#c9d1d9'
              return (
                <div key={i} style={{ marginBottom: 1, display: 'flex', gap: 6 }}>
                  <span style={{ color: '#484f58', flexShrink: 0 }}>{log.time || ''}</span>
                  <span style={{ color: '#8b949e', flexShrink: 0 }}>{t.padEnd(11)}</span>
                  <span style={{ color, wordBreak: 'break-all' }}>{log.content || ''}</span>
                </div>
              )
            })}
            <div ref={npuClaudeEndRef} />
          </div>
        </Card>
      )}
      {!showNpuClaude && npuClaudeLogs.length > 0 && (
        <Button type="dashed" size="small" block icon={<ThunderboltOutlined style={{ color: '#13c2c2' }} />} onClick={() => setShowNpuClaude(true)} style={{ marginBottom: 8 }}>
          展开 Claude 真机测试（{npuClaudeLogs.length} 条）
        </Button>
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

      {/* 插件断点诊断（跨 session 病灶聚合） */}
      <Card size="small" style={{ marginBottom: 12 }} title={
        <Space>
          <SafetyCertificateOutlined />
          <span>插件断点诊断</span>
          {diagnosis?.meta && <Tag color="blue">{diagnosis.meta.session_count} 样本 · {diagnosis.meta.op_count} 算子</Tag>}
          <Tooltip title="聚合该插件所有已完成仿真，定位 cannbot-skills 工作流的断点与设计缺陷：哪一步最常失败、哪个 skill 最常被漏读、哪类错误最多。">
            <Text type="secondary" style={{ fontSize: 11 }}>?</Text>
          </Tooltip>
        </Space>
      } extra={
        <Space size={4}>
          <Select size="small" value={diagnosisLimit} onChange={setDiagnosisLimit} style={{ width: 90 }}
            options={[{ value: 20, label: '近20' }, { value: 50, label: '近50' }, { value: 100, label: '近100' }, { value: 200, label: '近200' }]} />
          <Button size="small" type="primary" ghost loading={diagnosisLoading}
            disabled={!selectedPlugin} onClick={runDiagnosis}>生成诊断</Button>
          {diagnosis?.meta?.session_count > 0 && (
            <Button size="small" icon={<DownloadOutlined />} onClick={handleExportDiagnosis}>报告</Button>
          )}
        </Space>
      }>
        {(!diagnosis || !diagnosis.meta || diagnosis.meta.session_count === 0) ? (
          <Empty description={diagnosis ? '该插件暂无已完成的仿真样本，无法聚合断点' : '点击「生成诊断」聚合该插件历史仿真的断点与病灶'} image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <Collapse activeKey={diagnosisOpen ? ['diag'] : []} onChange={k => setDiagnosisOpen(k.includes('diag'))} items={[{
            key: 'diag',
            label: <Space>
              <span>verdict 分布：</span>
              {Object.entries(diagnosis.meta.verdict_distribution || {}).map(([k, v]) => (
                <Tag key={k} color={k === 'PASS' ? 'green' : k === 'FAIL' ? 'red' : 'orange'} style={{ fontSize: 10 }}>{k}: {v}</Tag>
              ))}
              <span style={{ color: '#999', fontSize: 11 }}>（点击展开完整诊断）</span>
            </Space>,
            children: (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                {/* 1. DAG 断点叠加图 */}
                <div>
                  <Text strong style={{ fontSize: 12 }}>工作流断点热力图（节点颜色 = 跨样本失败率 / Skill 漏读频次）</Text>
                  <div style={{ marginTop: 8 }}>
                    <BreakpointDiagnosisGraph pluginDef={pluginDef} diagnosis={diagnosis} />
                  </div>
                </div>

                {/* 2. 步骤断点排行表 */}
                <div>
                  <Text strong style={{ fontSize: 12 }}>步骤失败排行（按失败率降序）</Text>
                  <Table size="small" style={{ marginTop: 8 }} pagination={false}
                    dataSource={(diagnosis.step_breakdown || []).map((s, i) => ({ ...s, key: s.step_id + i }))}
                    columns={[
                      { title: '步骤', dataIndex: 'step_name', width: 140,
                        render: (t, r) => <Tooltip title={r.step_id}><span>{t}</span></Tooltip> },
                      { title: '出现', dataIndex: 'appear', width: 60, align: 'center' },
                      { title: '失败', dataIndex: 'failed', width: 60, align: 'center' },
                      { title: '失败率', dataIndex: 'fail_rate', width: 80, align: 'center', sorter: (a, b) => b.fail_rate - a.fail_rate,
                        render: v => <Tag color={v >= 0.5 ? 'red' : v >= 0.3 ? 'orange' : v > 0 ? 'gold' : 'green'} style={{ fontSize: 10 }}>{Math.round(v * 100)}%</Tag> },
                      { title: '门禁未通过', dataIndex: 'gate_failed', width: 90, align: 'center' },
                      { title: '平均耗时', dataIndex: 'avg_duration_ms', width: 90, align: 'center',
                        render: v => v ? `${Math.round(v / 1000)}s` : '-' },
                      { title: '主要错误', dataIndex: 'error_categories',
                        render: cats => Object.entries(cats || {}).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
                          <Tag key={k} style={{ fontSize: 9, margin: 1 }}>{k}×{v}</Tag>
                        )) },
                    ]}
                  />
                </div>

                {/* 3. 错误类型分布 + 告警类型分布 */}
                <Row gutter={16}>
                  <Col span={12}>
                    <Text strong style={{ fontSize: 12 }}>错误类型分布</Text>
                    {Object.keys(diagnosis.error_category_distribution || {}).length === 0 ? (
                      <div style={{ color: '#999', fontSize: 11, marginTop: 8 }}>无错误</div>
                    ) : (
                      <ResponsiveContainer width="100%" height={200}>
                        <PieChart>
                          <Pie data={Object.entries(diagnosis.error_category_distribution).map(([k, v]) => ({ name: k, value: v }))}
                            dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={70} label>
                            {Object.keys(diagnosis.error_category_distribution).map((k, i) => (
                              <Cell key={k} fill={['#ff4d4f', '#fa8c16', '#faad14', '#1890ff', '#722ed1', '#13c2c2', '#8c8c8c'][i % 7]} />
                            ))}
                          </Pie>
                          <RTooltip />
                        </PieChart>
                      </ResponsiveContainer>
                    )}
                  </Col>
                  <Col span={12}>
                    <Text strong style={{ fontSize: 12 }}>告警类型分布</Text>
                    {Object.keys(diagnosis.alert_type_distribution || {}).length === 0 ? (
                      <div style={{ color: '#999', fontSize: 11, marginTop: 8 }}>无告警</div>
                    ) : (
                      <ResponsiveContainer width="100%" height={200}>
                        <BarChart data={Object.entries(diagnosis.alert_type_distribution).map(([k, v]) => ({ name: k, count: v }))} layout="vertical" margin={{ left: 20 }}>
                          <XAxis type="number" tick={{ fontSize: 10 }} />
                          <YAxis type="category" dataKey="name" width={130} tick={{ fontSize: 9 }} />
                          <RTooltip />
                          <Bar dataKey="count" fill="#fa541c" barSize={14} radius={[0, 4, 4, 0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    )}
                  </Col>
                </Row>

                {/* 4. Skill 漏读排行 */}
                <div>
                  <Text strong style={{ fontSize: 12 }}>Skill 漏读排行（哪个 skill 最常未被引用）</Text>
                  {(diagnosis.skill_missing_ranking || []).length === 0 ? (
                    <div style={{ color: '#999', fontSize: 11, marginTop: 8 }}>无漏读</div>
                  ) : (
                    <ResponsiveContainer width="100%" height={Math.min(280, (diagnosis.skill_missing_ranking.slice(0, 10).length) * 28 + 30)}>
                      <BarChart data={diagnosis.skill_missing_ranking.slice(0, 10).map(s => ({ name: s.skill, count: s.missing_count }))} layout="vertical" margin={{ left: 20 }}>
                        <XAxis type="number" tick={{ fontSize: 10 }} />
                        <YAxis type="category" dataKey="name" width={170} tick={{ fontSize: 9 }} />
                        <RTooltip formatter={v => [`${v} 次`, '漏读']} />
                        <Bar dataKey="count" fill="#ff4d4f" barSize={16} radius={[0, 4, 4, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  )}
                </div>

                {/* 5. 产物缺失排行 */}
                <div>
                  <Text strong style={{ fontSize: 12 }}>门禁产物缺失排行（哪个产出物最常未生成）</Text>
                  {(diagnosis.artifact_missing_ranking || []).length === 0 ? (
                    <div style={{ color: '#999', fontSize: 11, marginTop: 8 }}>无缺失</div>
                  ) : (
                    <Table size="small" style={{ marginTop: 8 }} pagination={false}
                      dataSource={diagnosis.artifact_missing_ranking.map((a, i) => ({ ...a, key: a.artifact + i }))}
                      columns={[
                        { title: '产物', dataIndex: 'artifact' },
                        { title: '缺失次数', dataIndex: 'missing_count', width: 100, align: 'center', sorter: (a, b) => b.missing_count - a.missing_count,
                          render: v => <Tag color="red">{v}</Tag> },
                        { title: '发生步骤', dataIndex: 'steps', render: steps => (steps || []).map(s => <Tag key={s} style={{ fontSize: 9 }}>{s}</Tag>) },
                      ]}
                    />
                  )}
                </div>
              </div>
            ),
          }]} />
        )}
      </Card>

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

      {/* 插件架构 Drawer */}
      <Drawer
        open={pluginDrawerOpen}
        onClose={() => setPluginDrawerOpen(false)}
        title={
          <Space>
            <ApartmentOutlined />
            <span>插件架构: {pluginDef?.plugin_name || selectedPlugin}</span>
          </Space>
        }
        width={Math.min(900, window.innerWidth * 0.85)}
        destroyOnClose
      >
        {pluginDefLoading ? (
          <div style={{ textAlign: 'center', padding: 60 }}><Spin tip="加载插件定义..." /></div>
        ) : pluginDef ? (
          <PluginArchGraph pluginDef={pluginDef} monitorInsights={monitorInsights} steps={steps} runtimeSkillStatus={runtimeSkillStatus} />
        ) : (
          <Empty description="无法加载插件定义" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
      </Drawer>
    </div>
  )
}
