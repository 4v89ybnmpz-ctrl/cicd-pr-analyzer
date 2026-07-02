/**
 * BreakpointDiagnosisGraph — 插件断点诊断 DAG
 * 复用 PluginArchGraph 的四列布局思路（Primary→Step→Agent→Skill），
 * 但节点按「跨样本失败率 / Skill 漏读频次」着色，定位插件工作流的病灶。
 *
 * 着色规则：
 *   - step 节点：按 fail_rate 映射热色（≥0.5 深红+glow，≥0.3 红，>0 橙，=0 绿），右上角 badge 显示失败次数
 *   - skill 节点：按 missing_count（漏读频次）映射（>0 橙→红，=0 绿）
 *   - primary/agent 节点：聚合其下游 step 的失败情况，取最高失败率着色
 */
import { useMemo } from 'react'
import { Tag, Tooltip, Typography, Empty } from 'antd'
import {
  CodeOutlined, RobotOutlined, FileTextOutlined, ThunderboltOutlined,
} from '@ant-design/icons'
import {
  ReactFlow, Controls, Background, MarkerType, Handle, Position,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'

const { Text } = Typography

const ARCH_Y_GAP = 68
const ARCH_X_GAP = 240

const NODE_BASE = {
  primary: { icon: <RobotOutlined style={{ color: '#1890ff' }} />, label: 'Primary' },
  step:    { icon: <CodeOutlined style={{ color: '#8c8c8c' }} />, label: 'Step' },
  agent:   { icon: <ThunderboltOutlined style={{ color: '#722ed1' }} />, label: 'Subagent' },
  skill:   { icon: <FileTextOutlined style={{ color: '#52c41a' }} />, label: 'Skill' },
}

// 失败率 → 热色 {border, bg, glow, tag}
function heatByFailRate(failRate) {
  if (failRate == null) return null
  if (failRate >= 0.5) return { border: '#ff4d4f', bg: '#ffccc7', glow: '0 0 12px #ff4d4f66', level: '深红' }
  if (failRate >= 0.3) return { border: '#ff7875', bg: '#fff1f0', glow: '0 0 8px #ff787555', level: '红' }
  if (failRate > 0)    return { border: '#fa8c16', bg: '#fff7e6', glow: 'none', level: '橙' }
  return { border: '#52c41a', bg: '#f6ffed', glow: 'none', level: '健康' }
}

// 漏读次数 → 热色
function heatByMissing(missing) {
  if (missing == null || missing === 0) return { border: '#52c41a', bg: '#f6ffed', glow: 'none', level: '健康' }
  if (missing >= 3) return { border: '#ff4d4f', bg: '#fff1f0', glow: '0 0 10px #ff4d4f55', level: '红' }
  return { border: '#fa8c16', bg: '#fff7e6', glow: 'none', level: '橙' }
}

function collectAllSkills(def) {
  const m = new Map()
  for (const s of def.required_skills || []) if (!m.has(s)) m.set(s, 'primary')
  for (const a of def.agent_defs || []) for (const s of a.skills || []) if (!m.has(s)) m.set(s, a.name)
  for (const st of def.steps || []) for (const s of st.required_skills || []) if (!m.has(s)) m.set(s, st.step_id)
  return [...m.keys()]
}

function DiagnosisNode({ data }) {
  const { label, nodeType, heat, badge, detail } = data
  const base = NODE_BASE[nodeType] || NODE_BASE.step
  const borderColor = heat ? heat.border : '#bfbfbf'
  const bgColor = heat ? heat.bg : '#fafafa'
  const glow = heat && heat.glow !== 'none' ? heat.glow : 'none'
  return (
    <Tooltip title={
      <div style={{ fontSize: 12 }}>
        <div><b>{base.label}:</b> {label}</div>
        {detail && <div style={{ marginTop: 4, opacity: 0.9 }}>{detail}</div>}
      </div>
    } placement="top" mouseEnterDelay={0.3}>
      <div style={{
        position: 'relative',
        padding: '7px 12px', borderRadius: 7,
        border: `2px solid ${borderColor}`, background: bgColor,
        minWidth: 150, maxWidth: 200, fontSize: 12, cursor: 'default',
        boxShadow: glow, transition: 'box-shadow 0.15s',
      }}>
        <Handle type="target" position={Position.Left} style={{ visibility: 'hidden' }} />
        <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          {base.icon}
          <Text ellipsis style={{ flex: 1, fontWeight: 500, fontSize: 11 }}>{label}</Text>
          <Tag style={{ fontSize: 8, lineHeight: '12px', padding: '0 3px', margin: 0 }}>{base.label}</Tag>
        </div>
        {badge > 0 && (
          <div style={{
            position: 'absolute', top: -8, right: -8,
            minWidth: 18, height: 18, borderRadius: 9, padding: '0 4px',
            background: '#ff4d4f', color: '#fff', fontSize: 10, fontWeight: 700,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            border: '1.5px solid #fff', boxShadow: '0 0 4px #ff4d4f88',
          }}>{badge}</div>
        )}
        <Handle type="source" position={Position.Right} style={{ visibility: 'hidden' }} />
      </div>
    </Tooltip>
  )
}

const nodeTypes = { diagnosisNode: DiagnosisNode }

export default function BreakpointDiagnosisGraph({ pluginDef, diagnosis }) {
  const { nodes, edges } = useMemo(() => {
    if (!pluginDef) return { nodes: [], edges: [] }
    const steps = pluginDef.steps || []
    const agents = pluginDef.agent_defs || []
    const skills = collectAllSkills(pluginDef)
    const maxCount = Math.max(1, steps.length, agents.length, skills.length)
    const totalH = maxCount * ARCH_Y_GAP
    const cy = (count) => (totalH - count * ARCH_Y_GAP) / 2 + ARCH_Y_GAP / 2 - 20

    // step_id -> 病灶数据
    const stepMap = {}
    for (const sb of (diagnosis?.step_breakdown) || []) stepMap[sb.step_id] = sb
    // skill -> 漏读数据
    const skillMissing = {}
    for (const sm of (diagnosis?.skill_missing_ranking) || []) skillMissing[sm.skill] = sm

    const nodes = [], edges = []

    // Primary：聚合所有 step 的失败率取最高
    const allFailRates = Object.values(stepMap).map(s => s.fail_rate).filter(r => r != null)
    const primaryFailRate = allFailRates.length ? Math.max(...allFailRates) : null
    nodes.push({
      id: 'primary', type: 'diagnosisNode',
      position: { x: 0, y: cy(1) },
      data: {
        label: pluginDef.plugin_name || pluginDef.plugin_id, nodeType: 'primary',
        heat: primaryFailRate != null ? heatByFailRate(primaryFailRate) : null,
        detail: `${steps.length} 步 · ${agents.length} 代理 · ${skills.length} 技能`,
      },
    })

    // Steps
    steps.forEach((step, i) => {
      const sid = step.step_id || `step_${i}`
      const sb = stepMap[sid]
      const failRate = sb?.fail_rate
      const cats = sb?.error_categories || {}
      const topCat = Object.entries(cats).sort((a, b) => b[1] - a[1])[0]
      nodes.push({
        id: sid, type: 'diagnosisNode',
        position: { x: ARCH_X_GAP, y: cy(steps.length) + i * ARCH_Y_GAP },
        data: {
          label: step.name || sid, nodeType: 'step',
          heat: failRate != null ? heatByFailRate(failRate) : null,
          badge: sb?.failed || 0,
          detail: sb ? `出现 ${sb.appear} 次 · 失败 ${sb.failed} · 失败率 ${Math.round((failRate || 0) * 100)}% · 门禁未通过 ${sb.gate_failed}${topCat ? ` · 主要错误 ${topCat[0]}×${topCat[1]}` : ''}` : '无样本数据',
        },
      })
      edges.push({ id: `p-${sid}`, source: 'primary', target: sid, markerEnd: { type: MarkerType.ArrowClosed, width: 10, height: 10, color: '#bbb' }, style: { stroke: '#bbb', strokeWidth: 1.5 } })
    })

    // Agents
    agents.forEach((agent, i) => {
      const aid = `agent_${agent.name}`
      // 聚合该 agent 关联 step 的失败率取最高
      const linked = steps.filter(st => {
        const dt = st.dispatch_target || ''
        return dt === agent.name || dt.includes(agent.name)
      })
      const linkedRates = linked.map(st => stepMap[st.step_id]?.fail_rate).filter(r => r != null)
      const agentRate = linkedRates.length ? Math.max(...linkedRates) : null
      nodes.push({
        id: aid, type: 'diagnosisNode',
        position: { x: ARCH_X_GAP * 2, y: cy(agents.length) + i * ARCH_Y_GAP },
        data: {
          label: agent.name, nodeType: 'agent',
          heat: agentRate != null ? heatByFailRate(agentRate) : null,
          badge: linked.reduce((sum, st) => sum + (stepMap[st.step_id]?.failed || 0), 0),
          detail: agent.skills?.length ? `Skills: ${agent.skills.slice(0, 3).join(', ')}${agent.skills.length > 3 ? '...' : ''}` : '',
        },
      })
      let hasConn = false
      steps.forEach(step => {
        const dt = step.dispatch_target || ''
        if (dt === agent.name || dt.includes(agent.name)) {
          edges.push({ id: `${step.step_id}-${aid}`, source: step.step_id, target: aid, markerEnd: { type: MarkerType.ArrowClosed, width: 10, height: 10, color: '#722ed1' }, style: { stroke: '#bfbfbf', strokeWidth: 1.5 } })
          hasConn = true
        }
      })
      if (!hasConn) {
        edges.push({ id: `p-${aid}`, source: 'primary', target: aid, markerEnd: { type: MarkerType.ArrowClosed, width: 10, height: 10, color: '#722ed1' }, style: { stroke: '#d9d9d9', strokeWidth: 1, strokeDasharray: '4 4' } })
      }
    })

    // Skills
    skills.forEach((skill, i) => {
      const skid = `skill_${skill}`
      const sm = skillMissing[skill]
      nodes.push({
        id: skid, type: 'diagnosisNode',
        position: { x: ARCH_X_GAP * 3, y: cy(skills.length) + i * ARCH_Y_GAP },
        data: {
          label: skill, nodeType: 'skill',
          heat: heatByMissing(sm?.missing_count || 0),
          badge: sm?.missing_count || 0,
          detail: sm ? `跨 ${sm.in_sessions} session 漏读 ${sm.missing_count} 次 · 步骤: ${(sm.steps || []).join(', ') || '-'}` : '无漏读',
        },
      })
    })

    // Agent → Skill
    agents.forEach(agent => {
      const aid = `agent_${agent.name}`
      for (const skill of agent.skills || []) {
        const skid = `skill_${skill}`
        if (nodes.some(n => n.id === skid)) {
          edges.push({ id: `${aid}-${skid}`, source: aid, target: skid, markerEnd: { type: MarkerType.ArrowClosed, width: 10, height: 10, color: '#52c41a' }, style: { stroke: '#bfbfbf', strokeWidth: 1.5 } })
        }
      }
    })
    // Primary → Skills (dashed)
    for (const skill of pluginDef.required_skills || []) {
      const skid = `skill_${skill}`
      if (nodes.some(n => n.id === skid)) {
        edges.push({ id: `p-${skid}`, source: 'primary', target: skid, markerEnd: { type: MarkerType.ArrowClosed, width: 10, height: 10, color: '#1890ff' }, style: { stroke: '#d9d9d9', strokeWidth: 1, strokeDasharray: '6 3' } })
      }
    }

    return { nodes, edges }
  }, [pluginDef, diagnosis])

  if (!pluginDef) {
    return <Empty description="未加载插件定义，无法渲染诊断 DAG" image={Empty.PRESENTED_IMAGE_SIMPLE} />
  }

  const counts = [1, pluginDef.steps?.length || 0, pluginDef.agent_defs?.length || 0, collectAllSkills(pluginDef).length]
  const graphH = Math.max(...counts, 2) * ARCH_Y_GAP + 80

  return (
    <div>
      {/* 图例 */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 12, flexWrap: 'wrap', alignItems: 'center' }}>
        <Text type="secondary" style={{ fontSize: 11 }}>节点热度：</Text>
        {[{ l: '健康(0%)', c: '#52c41a', b: '#f6ffed' }, { l: '橙(>0%)', c: '#fa8c16', b: '#fff7e6' }, { l: '红(≥30%)', c: '#ff7875', b: '#fff1f0' }, { l: '深红(≥50%)', c: '#ff4d4f', b: '#ffccc7' }].map(it => (
          <div key={it.l} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <div style={{ width: 12, height: 12, borderRadius: 3, border: `2px solid ${it.c}`, background: it.b }} />
            <Text style={{ fontSize: 11, color: '#666' }}>{it.l}</Text>
          </div>
        ))}
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <div style={{ minWidth: 16, height: 16, borderRadius: 8, background: '#ff4d4f', color: '#fff', fontSize: 9, display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1.5px solid #fff' }}>N</div>
          <Text style={{ fontSize: 11, color: '#666' }}>失败/漏读次数</Text>
        </div>
      </div>

      <div style={{ height: Math.min(graphH, 600), width: '100%', border: '1px solid #f0f0f0', borderRadius: 8 }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
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
