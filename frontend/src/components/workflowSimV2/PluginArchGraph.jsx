import { useState, useCallback, useRef, useMemo } from 'react'
import {
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import {
  LoadingOutlined,
  CodeOutlined,
  RobotOutlined,
  FileTextOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import {
  ReactFlow,
  Controls,
  Background,
  MarkerType,
  Handle,
  Position,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'

const { Text } = Typography

const ARCH_NODE_STYLES = {
  primary: { border: '#1890ff', bg: '#e6f7ff', tagColor: 'blue', icon: <RobotOutlined style={{ color: '#1890ff' }} />, label: 'Primary' },
  step:    { border: '#8c8c8c', bg: '#f5f5f5', tagColor: 'default', icon: <CodeOutlined style={{ color: '#8c8c8c' }} />, label: 'Step' },
  agent:   { border: '#722ed1', bg: '#f9f0ff', tagColor: 'purple', icon: <ThunderboltOutlined style={{ color: '#722ed1' }} />, label: 'Subagent' },
  skill:   { border: '#52c41a', bg: '#f6ffed', tagColor: 'success', icon: <FileTextOutlined style={{ color: '#52c41a' }} />, label: 'Skill' },
}

const MONITOR_STATUS_STYLES = {
  compliant:    { border: '#52c41a', bg: '#f6ffed', glow: '0 0 10px #52c41a40' },
  partial:      { border: '#faad14', bg: '#fffbe6', glow: '0 0 10px #faad1440' },
  violation:    { border: '#ff4d4f', bg: '#fff2f0', glow: '0 0 10px #ff4d4f40' },
  not_detected: { border: '#d9d9d9', bg: '#fafafa', glow: 'none' },
}

// skill 运行时状态样式 + 聚合优先级（failed > running > passed > expected > pending）
const RUNTIME_STATUS_STYLES = {
  pending:  { border: '#d9d9d9', bg: '#fafafa', label: null },
  expected: { border: '#91caff', bg: '#e6f4ff', label: '待用', dashed: true },
  running:  { border: '#1677ff', bg: '#e6f4ff', label: '运行中', pulse: true },
  passed:   { border: '#52c41a', bg: '#f6ffed', label: '已用' },
  failed:   { border: '#ff4d4f', bg: '#fff2f0', label: '失败' },
}
const RUNTIME_STATUS_RANK = { failed: 4, running: 3, passed: 2, expected: 1, pending: 0 }

const ARCH_Y_GAP = 68
const ARCH_X_GAP = 240

function ArchNode({ data }) {
  const { label, nodeType, description, extra, highlighted, dimmed, monitorStatus, monitorDetail, runtimeStatus, compliance } = data
  const s = ARCH_NODE_STYLES[nodeType] || ARCH_NODE_STYLES.step
  const ms = monitorStatus ? MONITOR_STATUS_STYLES[monitorStatus] : null
  const rt = runtimeStatus ? RUNTIME_STATUS_STYLES[runtimeStatus] : null
  // 颜色优先级：runtime（实时真值）> monitor（事后语义）> 默认
  const borderColor = rt ? rt.border : (ms ? ms.border : s.border)
  const bgColor = rt ? rt.bg : (ms ? ms.bg : s.bg)
  const opacity = dimmed ? 0.2 : 1
  const glow = highlighted ? `0 0 14px ${borderColor}80` : (rt && runtimeStatus === 'running' ? `0 0 12px ${borderColor}66` : (ms ? ms.glow : 'none'))
  const bw = highlighted ? 3 : 2
  const statusLabel = rt?.label || (monitorStatus ? { compliant: '已正确引用', partial: '部分引用', violation: '未引用', not_detected: '待验证' }[monitorStatus] : null)
  const isRunning = runtimeStatus === 'running'
  return (
    <Tooltip title={
      <div style={{ fontSize: 12 }}>
        <div><b>{s.label}:</b> {label}</div>
        {description && <div style={{ marginTop: 4, opacity: 0.85 }}>{description}</div>}
        {extra && <div style={{ marginTop: 4 }}>{extra}</div>}
        {rt?.label && <div style={{ marginTop: 4, color: rt.border }}><b>运行状态:</b> {rt.label}</div>}
        {compliance && (
          <div style={{ marginTop: 4, borderTop: '1px solid #eee', paddingTop: 4 }}>
            <div><b>Agent/Skill 引用:</b> {compliance.refs.length > 0 ? compliance.refs.slice(0,4).join(', ') : '无'}{compliance.refs.length > 4 ? ` +${compliance.refs.length - 4}` : ''}</div>
            {compliance.miss.length > 0 && <div style={{ color: '#ff4d4f' }}>缺失: {compliance.miss.slice(0,3).join(', ')}</div>}
            <div style={{ marginTop: 2, fontSize: 10, color: '#999' }}>预期 {compliance.exps.length} 个，引用 {compliance.refs.length} 个</div>
          </div>
        )}
        {monitorDetail && <div style={{ marginTop: 4, borderTop: '1px solid #eee', paddingTop: 4 }}>
          <div><b>监控判定:</b> {monitorStatus ? { compliant: '已正确引用', partial: '部分引用', violation: '未引用', not_detected: '待验证' }[monitorStatus] : '-'}</div>
          <div style={{ marginTop: 2, opacity: 0.85 }}>{monitorDetail}</div>
        </div>}
      </div>
    } placement="top" mouseEnterDelay={0.4}>
      <div style={{
        padding: '7px 12px', borderRadius: 7,
        border: `${bw}px ${rt?.dashed ? 'dashed' : 'solid'} ${borderColor}`,
        background: bgColor, minWidth: 150, maxWidth: 200, fontSize: 12, cursor: 'default',
        boxShadow: glow, opacity, transition: 'opacity 0.15s, box-shadow 0.15s, border-width 0.15s',
        animation: isRunning ? 'archNodePulse 1.2s ease-in-out infinite' : 'none',
      }}>
        <Handle type="target" position={Position.Left} style={{ visibility: 'hidden' }} />
        <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          {isRunning ? <LoadingOutlined style={{ color: borderColor }} /> : s.icon}
          <Text ellipsis style={{ flex: 1, fontWeight: 500, fontSize: 11 }}>{label}</Text>
          {statusLabel && <span style={{ fontSize: 8, color: borderColor, fontWeight: 600 }}>{statusLabel}</span>}
          <Tag color={s.tagColor} style={{ fontSize: 8, lineHeight: '12px', padding: '0 3px', margin: 0 }}>{s.label}</Tag>
        </div>
        <Handle type="source" position={Position.Right} style={{ visibility: 'hidden' }} />
      </div>
    </Tooltip>
  )
}

const archNodeTypes = { archNode: ArchNode }

function collectAllSkills(def) {
  const m = new Map()
  for (const s of def.required_skills || []) if (!m.has(s)) m.set(s, 'primary')
  for (const a of def.agent_defs || []) for (const s of a.skills || []) if (!m.has(s)) m.set(s, a.name)
  for (const st of def.steps || []) for (const s of st.required_skills || []) if (!m.has(s)) m.set(s, st.step_id)
  return [...m.keys()]
}

// 分层布局：用于有 sub_steps 的插件（如 ops-registry-invoke，4 大阶段 + 子 step）
// 结构：Primary → Phase → SubStep → Agent → Skill
function layoutHierarchical(def, skills, agents) {
  const nodes = [], edges = []
  const phases = def.steps || []
  const hasAgents = agents.length > 0

  // 展平所有子 step，记录所属 phase
  const allSubs = []
  phases.forEach(phase => {
    (phase.sub_steps || []).forEach(sub => allSubs.push({ ...sub, phase_id: phase.step_id }))
  })

  const maxCount = Math.max(1, phases.length, allSubs.length, agents.length, skills.length)
  const totalH = maxCount * ARCH_Y_GAP
  const cy = (count) => (totalH - count * ARCH_Y_GAP) / 2 + ARCH_Y_GAP / 2 - 20

  // Primary (x=0)
  nodes.push({ id: 'primary', type: 'archNode', position: { x: 0, y: cy(1) }, data: { label: def.plugin_name || def.plugin_id, nodeType: 'primary', description: def.description || '', extra: `${phases.length} 阶段 · ${allSubs.length} 子step · ${agents.length} 代理 · ${skills.length} 技能 · 分层` }})

  // Phase 大阶段节点 (x=GAP)
  phases.forEach((phase, i) => {
    nodes.push({ id: phase.step_id, type: 'archNode', position: { x: ARCH_X_GAP, y: cy(phases.length) + i * ARCH_Y_GAP }, data: { label: phase.name, nodeType: 'step', extra: `${phase.sub_steps?.length || 0} 子step` }})
    edges.push({ id: `p-${phase.step_id}`, source: 'primary', target: phase.step_id, animated: false, markerEnd: { type: MarkerType.ArrowClosed, width: 10, height: 10, color: '#bbb' }, style: { stroke: '#bbb', strokeWidth: 1.8 }})
  })

  // SubStep 子步骤节点 (x=GAP*2)
  allSubs.forEach((sub, i) => {
    const sid = sub.step_id
    nodes.push({ id: sid, type: 'archNode', position: { x: ARCH_X_GAP * 2, y: cy(allSubs.length) + i * ARCH_Y_GAP }, data: { label: sub.name, nodeType: 'step', extra: sub.dispatch_target ? `→ ${sub.dispatch_target}` : '' }})
    edges.push({ id: `${sub.phase_id}-${sid}`, source: sub.phase_id, target: sid, animated: false, markerEnd: { type: MarkerType.ArrowClosed, width: 10, height: 10, color: '#bbb' }, style: { stroke: '#d9d9d9', strokeWidth: 1 }})
  })

  // Agent 节点 (x=GAP*3)
  if (hasAgents) {
    agents.forEach((agent, i) => {
      const aid = `agent_${agent.name}`
      nodes.push({ id: aid, type: 'archNode', position: { x: ARCH_X_GAP * 3, y: cy(agents.length) + i * ARCH_Y_GAP }, data: { label: agent.name, nodeType: 'agent', description: agent.description || '', extra: agent.skills?.length ? `Skills: ${agent.skills.slice(0, 3).join(', ')}${agent.skills.length > 3 ? '...' : ''}` : '' }})
    })
  }

  // Skill 节点 (x=GAP*4)
  skills.forEach((skill, i) => {
    const skid = `skill_${skill}`
    nodes.push({ id: skid, type: 'archNode', position: { x: ARCH_X_GAP * 4, y: cy(skills.length) + i * ARCH_Y_GAP }, data: { label: skill, nodeType: 'skill' }})
  })

  // SubStep → Agent（dispatch 匹配）
  if (hasAgents) {
    allSubs.forEach(sub => {
      const dt = sub.dispatch_target || ''
      if (!dt) return
      agents.forEach(agent => {
        if (dt === agent.name || dt.includes(agent.name)) {
          edges.push({ id: `${sub.step_id}-agent_${agent.name}`, source: sub.step_id, target: `agent_${agent.name}`, animated: false, markerEnd: { type: MarkerType.ArrowClosed, width: 10, height: 10, color: '#722ed1' }, style: { stroke: '#bfbfbf', strokeWidth: 1.2 }})
        }
      })
    })
    // Agent → Skill
    agents.forEach(agent => {
      const aid = `agent_${agent.name}`
      for (const skill of agent.skills || []) {
        const skid = `skill_${skill}`
        if (nodes.some(n => n.id === skid)) {
          edges.push({ id: `${aid}-${skid}`, source: aid, target: skid, animated: false, markerEnd: { type: MarkerType.ArrowClosed, width: 10, height: 10, color: '#52c41a' }, style: { stroke: '#bfbfbf', strokeWidth: 1.2 }})
        }
      }
    })
  }

  // SubStep → Skill 兜底（dispatch 是 skill 名而非 agent，如 4.2→ascendc-code-review）
  allSubs.forEach(sub => {
    const dt = sub.dispatch_target || ''
    if (!dt) return
    const viaAgent = hasAgents && agents.some(a => dt === a.name || dt.includes(a.name))
    if (viaAgent) return
    skills.forEach(skill => {
      if (dt.includes(skill)) {
        const skid = `skill_${skill}`
        if (nodes.some(n => n.id === skid)) {
          edges.push({ id: `${sub.step_id}-${skid}`, source: sub.step_id, target: skid, animated: false, markerEnd: { type: MarkerType.ArrowClosed, width: 10, height: 10, color: '#52c41a' }, style: { stroke: '#bfbfbf', strokeWidth: 1, strokeDasharray: '4 3' }})
        }
      }
    })
  })

  // Primary → Skill（required_skills 虚线）
  for (const skill of def.required_skills || []) {
    const skid = `skill_${skill}`
    if (nodes.some(n => n.id === skid)) {
      edges.push({ id: `p-${skid}`, source: 'primary', target: skid, animated: false, markerEnd: { type: MarkerType.ArrowClosed, width: 10, height: 10, color: '#1890ff' }, style: { stroke: '#d9d9d9', strokeWidth: 1, strokeDasharray: '6 3' }})
    }
  }

  return { nodes, edges }
}

function layoutArchGraph(def) {
  const nodes = [], edges = []
  const steps = def.steps || []
  const agents = def.agent_defs || []
  const skills = collectAllSkills(def)
  // 分层模式：step 有 sub_steps（如 ops-registry-invoke 4 大阶段 + 子 step）
  if (steps.some(s => s.sub_steps?.length > 0)) return layoutHierarchical(def, skills, agents)
  const hasAgents = agents.length > 0
  const directMode = !hasAgents  // 直接模式：无 subagent，主 Claude 直接调 skill

  // 列布局：直接模式三列（Primary/Step/Skill），派发/混合四列（+Agent）
  const skillX = directMode ? ARCH_X_GAP * 2 : ARCH_X_GAP * 3
  const maxCount = Math.max(1, steps.length, agents.length, skills.length)
  const totalH = maxCount * ARCH_Y_GAP
  const cy = (count) => (totalH - count * ARCH_Y_GAP) / 2 + ARCH_Y_GAP / 2 - 20

  // Primary
  nodes.push({ id: 'primary', type: 'archNode', position: { x: 0, y: cy(1) }, data: { label: def.plugin_name || def.plugin_id, nodeType: 'primary', description: def.description || '', extra: `${steps.length} 步 · ${agents.length} 代理 · ${skills.length} 技能${directMode ? ' · 直接模式' : ''}` }})

  // Steps
  steps.forEach((step, i) => {
    const sid = step.step_id || `step_${i}`
    nodes.push({ id: sid, type: 'archNode', position: { x: ARCH_X_GAP, y: cy(steps.length) + i * ARCH_Y_GAP }, data: { label: step.name || sid, nodeType: 'step', description: step.gate_condition || '', extra: step.dispatch_target ? `→ ${step.dispatch_target}` : '' }})
    edges.push({ id: `p-${sid}`, source: 'primary', target: sid, animated: false, markerEnd: { type: MarkerType.ArrowClosed, width: 10, height: 10, color: '#bbb' }, style: { stroke: '#bbb', strokeWidth: 1.5 }})
  })

  // Agents（仅派发/混合模式画 Agent 列）
  if (hasAgents) {
    agents.forEach((agent, i) => {
      const aid = `agent_${agent.name}`
      nodes.push({ id: aid, type: 'archNode', position: { x: ARCH_X_GAP * 2, y: cy(agents.length) + i * ARCH_Y_GAP }, data: { label: agent.name, nodeType: 'agent', description: agent.description || '', extra: agent.skills?.length ? `Skills: ${agent.skills.slice(0, 3).join(', ')}${agent.skills.length > 3 ? '...' : ''}` : '' }})

      let hasConn = false
      steps.forEach(step => {
        const dt = step.dispatch_target || ''
        if (dt === agent.name || dt.includes(agent.name)) {
          edges.push({ id: `${step.step_id}-${aid}`, source: step.step_id, target: aid, animated: false, markerEnd: { type: MarkerType.ArrowClosed, width: 10, height: 10, color: '#722ed1' }, style: { stroke: '#bfbfbf', strokeWidth: 1.5 }})
          hasConn = true
        }
      })
      if (!hasConn) {
        edges.push({ id: `p-${aid}`, source: 'primary', target: aid, animated: false, markerEnd: { type: MarkerType.ArrowClosed, width: 10, height: 10, color: '#722ed1' }, style: { stroke: '#d9d9d9', strokeWidth: 1, strokeDasharray: '4 4' }})
      }
    })
  }

  // Skills
  skills.forEach((skill, i) => {
    const skid = `skill_${skill}`
    nodes.push({ id: skid, type: 'archNode', position: { x: skillX, y: cy(skills.length) + i * ARCH_Y_GAP }, data: { label: skill, nodeType: 'skill' }})
  })

  // Agent → Skill（仅派发/混合）
  if (hasAgents) {
    agents.forEach(agent => {
      const aid = `agent_${agent.name}`
      for (const skill of agent.skills || []) {
        const skid = `skill_${skill}`
        if (nodes.some(n => n.id === skid)) {
          edges.push({ id: `${aid}-${skid}`, source: aid, target: skid, animated: false, markerEnd: { type: MarkerType.ArrowClosed, width: 10, height: 10, color: '#52c41a' }, style: { stroke: '#bfbfbf', strokeWidth: 1.5 }})
        }
      }
    })
  }

  // Step → Skill（直接模式主线 / 混合模式兜底）：dispatch_target 提到的 skill
  // 已通过 Agent 中转的 step（dispatch 匹配 agent 名）不重复画
  steps.forEach(step => {
    const dt = step.dispatch_target || ''
    if (!dt) return
    const viaAgent = hasAgents && agents.some(a => dt === a.name || dt.includes(a.name))
    if (viaAgent) return  // 派发模式走 Step→Agent→Skill，不重复
    skills.forEach(skill => {
      if (dt.includes(skill)) {
        const skid = `skill_${skill}`
        if (nodes.some(n => n.id === skid)) {
          edges.push({ id: `${step.step_id}-${skid}`, source: step.step_id, target: skid, animated: false, markerEnd: { type: MarkerType.ArrowClosed, width: 10, height: 10, color: '#52c41a' }, style: { stroke: directMode ? '#52c41a' : '#bfbfbf', strokeWidth: directMode ? 1.5 : 1, ...(directMode ? {} : { strokeDasharray: '4 3' }) }})
        }
      }
    })
  })

  // Primary → Skills（required_skills 虚线）：直接模式省略（Step→Skill 已表达），派发/混合保留
  if (!directMode) {
    for (const skill of def.required_skills || []) {
      const skid = `skill_${skill}`
      if (nodes.some(n => n.id === skid)) {
        edges.push({ id: `p-${skid}`, source: 'primary', target: skid, animated: false, markerEnd: { type: MarkerType.ArrowClosed, width: 10, height: 10, color: '#1890ff' }, style: { stroke: '#d9d9d9', strokeWidth: 1, strokeDasharray: '6 3' }})
      }
    }
  }

  return { nodes, edges }
}

export default function PluginArchGraph({ pluginDef, monitorInsights, steps, runtimeSkillStatus, subStepProgress = {} }) {
  const { nodes: rawNodes, edges: rawEdges } = useMemo(() => layoutArchGraph(pluginDef), [pluginDef])
  const [hoveredId, setHoveredId] = useState(null)
  const leaveTimerRef = useRef(null)

  const handleNodeEnter = useCallback((_event, node) => {
    if (leaveTimerRef.current) { clearTimeout(leaveTimerRef.current); leaveTimerRef.current = null }
    setHoveredId(node.id)
  }, [])

  const handleNodeLeave = useCallback(() => {
    leaveTimerRef.current = setTimeout(() => setHoveredId(null), 80)
  }, [])

  const graphH = useMemo(() => {
    const counts = [1, pluginDef.steps?.length || 0, pluginDef.agent_defs?.length || 0, collectAllSkills(pluginDef).length]
    return Math.max(...counts, 2) * ARCH_Y_GAP + 80
  }, [pluginDef])

  const allSkills = collectAllSkills(pluginDef)

  // 计算 hover 时的路径链高亮：上游祖先 + 下游子孙（不含兄弟分支）
  // 算法：从 hoveredId 沿反向边回溯到所有祖先，再从每个祖先正向展开整棵子树，
  // 但仅保留 hoveredId 所在路径上的祖先及其下游，排除与 hoveredId 无关的兄弟分支。
  // 简化实现：先找 hoveredId 的所有上游祖先（沿 target→source 反向），
  // 然后对 hoveredId 和每个祖先做正向 BFS，只取 hoveredId 可达的那条路径上的下游。
  // 最终高亮 = hoveredId 自身 + 所有上游祖先 + 从 hoveredId 出发的全部下游。
  const { highlightedNodes, highlightedEdges } = useMemo(() => {
    if (!hoveredId) return { highlightedNodes: new Set(), highlightedEdges: new Set() }
    const hNodes = new Set([hoveredId])
    const hEdges = new Set()

    // 正向邻接表（source → targets）
    const fwd = new Map()
    // 反向邻接表（target → sources）
    const rev = new Map()
    for (const e of rawEdges) {
      if (!fwd.has(e.source)) fwd.set(e.source, [])
      fwd.get(e.source).push({ neighbor: e.target, edgeId: e.id })
      if (!rev.has(e.target)) rev.set(e.target, [])
      rev.get(e.target).push({ neighbor: e.source, edgeId: e.id })
    }

    // 1) 反向回溯：找所有上游祖先
    const ancestorQueue = [hoveredId]
    while (ancestorQueue.length > 0) {
      const cur = ancestorQueue.shift()
      for (const { neighbor, edgeId } of rev.get(cur) || []) {
        if (!hNodes.has(neighbor)) {
          hNodes.add(neighbor)
          hEdges.add(edgeId)
          ancestorQueue.push(neighbor)
        }
      }
    }

    // 2) 正向展开：从 hoveredId 出发的所有下游
    const descQueue = [hoveredId]
    while (descQueue.length > 0) {
      const cur = descQueue.shift()
      for (const { neighbor, edgeId } of fwd.get(cur) || []) {
        if (!hNodes.has(neighbor)) {
          hNodes.add(neighbor)
          hEdges.add(edgeId)
          descQueue.push(neighbor)
        }
      }
    }

    return { highlightedNodes: hNodes, highlightedEdges: hEdges }
  }, [hoveredId, rawEdges])

  // 计算每个节点的监控状态
  const nodeMonitorMap = useMemo(() => {
    const m = {}
    if (!monitorInsights) return m
    for (const insight of Object.values(monitorInsights)) {
      for (const sa of insight.skills_analysis || []) {
        m[`skill_${sa.skill}`] = { status: sa.status, detail: sa.detail }
      }
    }
    return m
  }, [monitorInsights])

  // 计算每个节点的运行时状态（runtimeStatus）：skill 聚合多 step、step/agent 从执行状态推导
  const nodeRuntimeMap = useMemo(() => {
    const m = {}
    // skill：聚合该 skill 在各 step 的状态，取优先级最高者
    for (const [skill, perStep] of Object.entries(runtimeSkillStatus || {})) {
      let best = 'pending'
      for (const st of Object.values(perStep)) {
        if (RUNTIME_STATUS_RANK[st] > RUNTIME_STATUS_RANK[best]) best = st
      }
      m[`skill_${skill}`] = best
    }
    // step：从 steps 执行状态映射 runtime
    const STEP_MAP = { running: 'running', completed: 'passed', failed: 'failed' }
    for (const s of steps || []) {
      if (s.status && STEP_MAP[s.status]) m[s.step_id] = STEP_MAP[s.status]
    }
    // sub_step：从 subStepProgress 映射子步骤节点 runtime（[SUBSTEP:xxx] 标记推送的进度）
    for (const [subName, status] of Object.entries(subStepProgress || {})) {
      const sid = "step_" + subName.replace(/[^\w]/g, "_").replace(/_+/g, "_").replace(/^_|_$/g, "")
      if (status === 'running') m[sid] = 'running'
    }
    // agent：若其下属任一 step 在 running 则 running，否则若都完成则 passed
    for (const agent of pluginDef.agent_defs || []) {
      const aid = `agent_${agent.name}`
      const linked = (pluginDef.steps || []).filter(st => {
        const dt = st.dispatch_target || ''
        return dt === agent.name || dt.includes(agent.name)
      })
      const statuses = linked.map(st => m[st.step_id]).filter(Boolean)
      if (statuses.includes('running')) m[aid] = 'running'
      else if (statuses.length && statuses.every(x => x === 'passed')) m[aid] = 'passed'
      else if (statuses.includes('failed')) m[aid] = 'failed'
      // 兜底：该 agent 声明的 skill 若有已点亮的（passed/running），agent 也跟着亮
      // （应对主 claude 直接调度 agent、step 状态未更新时 agent 仍能点亮）
      if (!m[aid]) {
        const skStatuses = (agent.skills || []).map(sk => m[`skill_${sk}`]).filter(Boolean)
        if (skStatuses.includes('running')) m[aid] = 'running'
        else if (skStatuses.includes('passed')) m[aid] = 'passed'
      }
    }
    return m
  }, [runtimeSkillStatus, steps, pluginDef, subStepProgress])

  // 从 steps 运行时数据中提取耗时和 token（展示在 phase 节点上）
  const stepTimingMap = useMemo(() => {
    const m = {}
    for (const s of steps || []) {
      if (s.duration_ms > 0 || s.token_usage?.input) {
        const dur = s.duration_ms > 0 ? `${(s.duration_ms / 1000).toFixed(0)}s` : ''
        const tok = s.token_usage?.input ? `${((s.token_usage.input + (s.token_usage.output || 0)) / 1000).toFixed(0)}k` : ''
        m[s.step_id] = [dur, tok].filter(Boolean).join(' · ')
      }
    }
    return m
  }, [steps])

  // 每个 phase 的 skill compliance 状态（用于 tooltip 展示 agent/skill 引用）
  const stepComplianceMap = useMemo(() => {
    const m = {}
    for (const s of steps || []) {
      const sc = s.skill_compliance
      if (sc) {
        const refs = sc.skills_referenced || []
        const exps = sc.skills_expected || []
        const miss = sc.skills_missing || []
        m[s.step_id] = { refs, exps, miss, score: sc.score }
      }
    }
    return m
  }, [steps])

  // 注入 highlighted/dimmed/monitorStatus/runtimeStatus 到节点 data
  const nodes = useMemo(() => rawNodes.map(n => {
    const mon = nodeMonitorMap[n.id]
    const rt = nodeRuntimeMap[n.id] || null
    const timing = stepTimingMap[n.id] || ''
    const comp = stepComplianceMap[n.id]
    return {
      ...n,
      data: {
        ...n.data,
        highlighted: hoveredId ? highlightedNodes.has(n.id) : false,
        dimmed: hoveredId ? !highlightedNodes.has(n.id) : false,
        monitorStatus: mon?.status || null,
        monitorDetail: mon?.detail || null,
        runtimeStatus: rt,
        extra: n.data.extra ? `${n.data.extra} | ${timing}` : timing,
        compliance: comp || null,
      },
    }
  }), [rawNodes, hoveredId, highlightedNodes, nodeMonitorMap, nodeRuntimeMap, stepTimingMap, stepComplianceMap])

  // 高亮边、暗化非关联边；runtime running/passed 的下游边也流动起来
  const edges = useMemo(() => rawEdges.map(e => {
    const isHighlighted = highlightedEdges.has(e.id)
    const isDimmed = hoveredId && !isHighlighted
    const baseStroke = e.style?.stroke || '#bbb'
    const rtTarget = nodeRuntimeMap[e.target]
    const rtFlow = rtTarget === 'running' || rtTarget === 'passed'
    const flowColor = rtTarget === 'running' ? '#1677ff' : rtTarget === 'passed' ? '#52c41a' : '#1890ff'
    return {
      ...e,
      animated: isHighlighted || rtFlow,
      style: {
        ...e.style,
        stroke: isDimmed ? '#eee' : isHighlighted ? '#1890ff' : rtFlow ? flowColor : baseStroke,
        strokeWidth: isHighlighted ? 2.5 : rtFlow ? 2 : e.style?.strokeWidth || 1.5,
        opacity: isDimmed ? 0.15 : 1,
      },
    }
  }), [rawEdges, hoveredId, highlightedEdges, nodeRuntimeMap])

  return (
    <div>
      <style>{`@keyframes archNodePulse{0%,100%{box-shadow:0 0 8px ${RUNTIME_STATUS_STYLES.running.border}55}50%{box-shadow:0 0 16px ${RUNTIME_STATUS_STYLES.running.border}99}}`}</style>
      {/* 图例 */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 12, flexWrap: 'wrap' }}>
        {[{ l: 'Primary', c: '#1890ff', b: '#e6f7ff' }, { l: 'Step', c: '#8c8c8c', b: '#f5f5f5' }, { l: 'Subagent', c: '#722ed1', b: '#f9f0ff' }, { l: 'Skill', c: '#52c41a', b: '#f6ffed' }].map(it => (
          <div key={it.l} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <div style={{ width: 12, height: 12, borderRadius: 3, border: `2px solid ${it.c}`, background: it.b }} />
            <Text style={{ fontSize: 11, color: '#666' }}>{it.l}</Text>
          </div>
        ))}
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <div style={{ width: 24, borderTop: '1px dashed #d9d9d9' }} />
          <Text style={{ fontSize: 11, color: '#666' }}>直接调用</Text>
        </div>
        {Object.keys(monitorInsights || {}).length > 0 && (
          <>
            <div style={{ width: 12, borderTop: '1px solid #eee', margin: '0 4px' }} />
            {[{l:'已正确引用',c:'#52c41a',b:'#f6ffed'},{l:'部分引用',c:'#faad14',b:'#fffbe6'},{l:'未引用',c:'#ff4d4f',b:'#fff2f0'},{l:'待验证',c:'#d9d9d9',b:'#fafafa'}].map(it => (
              <div key={it.l} style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                <div style={{ width: 10, height: 10, borderRadius: 2, border: `2px solid ${it.c}`, background: it.b }} />
                <Text style={{ fontSize: 10, color: '#666' }}>{it.l}</Text>
              </div>
            ))}
          </>
        )}
      </div>

      {/* 统计 */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
        <Tag color="blue">Primary: 1</Tag>
        <Tag color="default">Steps: {pluginDef.steps?.length || 0}</Tag>
        <Tag color="purple">Subagents: {pluginDef.agent_defs?.length || 0}</Tag>
        <Tag color="success">Skills: {allSkills.length}</Tag>
        <Tag>连边: {rawEdges.length}</Tag>
      </div>

      {/* 描述 */}
      {pluginDef.description && (
        <div style={{ marginBottom: 12, padding: '6px 10px', background: '#fafafa', borderRadius: 4, fontSize: 12, color: '#666' }}>
          {pluginDef.description}
        </div>
      )}

      {/* DAG */}
      <div style={{ height: Math.min(graphH, 600), width: '100%', border: '1px solid #f0f0f0', borderRadius: 8 }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={archNodeTypes}
          onNodeMouseEnter={handleNodeEnter}
          onNodeMouseLeave={handleNodeLeave}
          fitView
          fitViewOptions={{ padding: 0.15 }}
          proOptions={{ hideAttribution: true }}
          minZoom={0.3}
          maxZoom={1.5}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
        >
          <Controls showInteractive={false} />
          <Background color="#f5f5f5" gap={16} />
        </ReactFlow>
      </div>
    </div>
  )
}
