/**
 * PluginGraphPanel — 插件 Skill/Agent 关系图
 * 水平 DAG 展示插件的编排架构：Primary → Steps → Subagents → Skills
 * 使用 @xyflow/react (ReactFlow) 实现 GitHub Actions 风格的可视化
 */
import { useState, useEffect, useCallback, useMemo } from 'react'
import {
  ReactFlow, Controls, Background, MarkerType, Handle, Position,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { Select, Card, Tag, Tooltip, Empty, Spin, Space, Typography } from 'antd'
import {
  ApartmentOutlined, RobotOutlined, ThunderboltOutlined,
  FileTextOutlined, CodeOutlined,
} from '@ant-design/icons'
import { getWorkflowDefinitions, getWorkflowDefinition } from '../api'

const { Text } = Typography

// 布局常量
const X_GAP = 260
const Y_GAP = 72
const Y_OFFSET = 20
const NODE_WIDTH = 180
const NODE_HEIGHT = 48

// 节点类型配置
const NODE_STYLES = {
  primary: {
    border: '#1890ff', bg: '#e6f7ff', tagColor: 'blue',
    icon: <RobotOutlined style={{ color: '#1890ff' }} />,
    label: 'Primary',
  },
  step: {
    border: '#8c8c8c', bg: '#f5f5f5', tagColor: 'default',
    icon: <CodeOutlined style={{ color: '#8c8c8c' }} />,
    label: 'Step',
  },
  agent: {
    border: '#722ed1', bg: '#f9f0ff', tagColor: 'purple',
    icon: <ThunderboltOutlined style={{ color: '#722ed1' }} />,
    label: 'Subagent',
  },
  skill: {
    border: '#52c41a', bg: '#f6ffed', tagColor: 'success',
    icon: <FileTextOutlined style={{ color: '#52c41a' }} />,
    label: 'Skill',
  },
}

// 自定义节点
function GraphNode({ data }) {
  const { label, nodeType, description, extra } = data
  const style = NODE_STYLES[nodeType] || NODE_STYLES.step
  return (
    <Tooltip
      title={
        <div style={{ fontSize: 12 }}>
          <div><strong>{style.label}:</strong> {label}</div>
          {description && <div style={{ marginTop: 4, opacity: 0.85 }}>{description}</div>}
          {extra && <div style={{ marginTop: 4 }}>{extra}</div>}
        </div>
      }
      placement="top"
    >
      <div style={{
        padding: '8px 14px',
        borderRadius: 8,
        border: `2px solid ${style.border}`,
        background: style.bg,
        minWidth: NODE_WIDTH,
        maxWidth: 220,
        fontSize: 13,
        cursor: 'default',
        transition: 'box-shadow 0.2s',
      }}
      onMouseEnter={e => e.currentTarget.style.boxShadow = `0 0 8px ${style.border}40`}
      onMouseLeave={e => e.currentTarget.style.boxShadow = 'none'}
      >
        <Handle type="target" position={Position.Left} style={{ visibility: 'hidden' }} />
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {style.icon}
          <Text ellipsis style={{ flex: 1, fontWeight: 500, fontSize: 12 }}>{label}</Text>
          <Tag color={style.tagColor} style={{ fontSize: 9, lineHeight: '14px', padding: '0 4px', margin: 0 }}>
            {style.label}
          </Tag>
        </div>
        <Handle type="source" position={Position.Right} style={{ visibility: 'hidden' }} />
      </div>
    </Tooltip>
  )
}

const nodeTypes = { graphNode: GraphNode }

// 收集所有 skill（去重，保留来源信息）
function collectAllSkills(pluginDef) {
  const skillMap = new Map()
  // 来自 primary 的 required_skills
  for (const s of pluginDef.required_skills || []) {
    if (!skillMap.has(s)) skillMap.set(s, 'primary')
  }
  // 来自 agent_defs 的 skills
  for (const agent of pluginDef.agent_defs || []) {
    for (const s of agent.skills || []) {
      if (!skillMap.has(s)) skillMap.set(s, agent.name)
    }
  }
  // 来自 steps 的 required_skills
  for (const step of pluginDef.steps || []) {
    for (const s of step.required_skills || []) {
      if (!skillMap.has(s)) skillMap.set(s, step.step_id)
    }
  }
  return [...skillMap.keys()]
}

// 构建 DAG 节点和边
function layoutPluginGraph(pluginDef) {
  if (!pluginDef) return { nodes: [], edges: [] }

  const nodes = []
  const edges = []
  const steps = pluginDef.steps || []
  const agentDefs = pluginDef.agent_defs || []
  const allSkills = collectAllSkills(pluginDef)

  // 计算每层高度以垂直居中
  const layerCounts = [1, steps.length, agentDefs.length, allSkills.length]
  const maxCount = Math.max(...layerCounts, 1)
  const totalHeight = maxCount * Y_GAP

  // 垂直居中辅助函数
  const centerY = (count) => Y_OFFSET + (totalHeight - count * Y_GAP) / 2 + Y_GAP / 2

  // --- Column 0: Primary Agent ---
  nodes.push({
    id: 'primary',
    type: 'graphNode',
    position: { x: 0, y: centerY(1) - NODE_HEIGHT / 2 },
    data: {
      label: pluginDef.plugin_name || pluginDef.plugin_id,
      nodeType: 'primary',
      description: pluginDef.description || '',
      extra: `${steps.length} 步骤 · ${agentDefs.length} 子代理 · ${allSkills.length} 技能`,
    },
  })

  // --- Column 1: Workflow Steps ---
  const stepCenterY = centerY(steps.length)
  steps.forEach((step, i) => {
    const stepId = step.step_id || `step_${i}`
    nodes.push({
      id: stepId,
      type: 'graphNode',
      position: { x: X_GAP, y: stepCenterY + i * Y_GAP - NODE_HEIGHT / 2 },
      data: {
        label: step.name || stepId,
        nodeType: 'step',
        description: step.gate_condition || '',
        extra: step.dispatch_target ? `→ ${step.dispatch_target}` : '',
      },
    })
    // Primary → Step
    edges.push({
      id: `primary-${stepId}`,
      source: 'primary',
      target: stepId,
      animated: false,
      markerEnd: { type: MarkerType.ArrowClosed, width: 12, height: 12, color: '#bbb' },
      style: { stroke: '#bbb', strokeWidth: 1.5 },
    })
  })

  // --- Column 2: Subagents ---
  const agentCenterY = centerY(agentDefs.length)
  agentDefs.forEach((agent, i) => {
    const agentId = `agent_${agent.name}`
    nodes.push({
      id: agentId,
      type: 'graphNode',
      position: { x: X_GAP * 2, y: agentCenterY + i * Y_GAP - NODE_HEIGHT / 2 },
      data: {
        label: agent.name,
        nodeType: 'agent',
        description: agent.description || '',
        extra: agent.skills?.length ? `Skills: ${agent.skills.slice(0, 3).join(', ')}${agent.skills.length > 3 ? '...' : ''}` : '',
      },
    })

    // 找到 dispatch 到此 agent 的 steps
    steps.forEach((step) => {
      const stepId = step.step_id
      const dt = step.dispatch_target || ''
      if (dt === agent.name || dt.includes(agent.name)) {
        edges.push({
          id: `${stepId}-${agentId}`,
          source: stepId,
          target: agentId,
          animated: false,
          markerEnd: { type: MarkerType.ArrowClosed, width: 12, height: 12, color: '#722ed1' },
          style: { stroke: '#bfbfbf', strokeWidth: 1.5 },
        })
      }
    })

    // 如果没有任何 step 连到此 agent（可能 step 没有 dispatch_target），从 primary 连
    const hasStepConnection = steps.some(s => {
      const dt = s.dispatch_target || ''
      return dt === agent.name || dt.includes(agent.name)
    })
    if (!hasStepConnection) {
      edges.push({
        id: `primary-${agentId}`,
        source: 'primary',
        target: agentId,
        animated: false,
        markerEnd: { type: MarkerType.ArrowClosed, width: 12, height: 12, color: '#722ed1' },
        style: { stroke: '#bfbfbf', strokeWidth: 1.5, strokeDasharray: '4 4' },
      })
    }
  })

  // --- Column 3: Skills ---
  const skillCenterY = centerY(allSkills.length)
  allSkills.forEach((skill, i) => {
    const skillId = `skill_${skill}`
    nodes.push({
      id: skillId,
      type: 'graphNode',
      position: { x: X_GAP * 3, y: skillCenterY + i * Y_GAP - NODE_HEIGHT / 2 },
      data: {
        label: skill,
        nodeType: 'skill',
        description: '',
      },
    })
  })

  // Agent → Skill 连线
  agentDefs.forEach((agent) => {
    const agentId = `agent_${agent.name}`
    for (const skill of agent.skills || []) {
      const skillId = `skill_${skill}`
      if (nodes.some(n => n.id === skillId)) {
        edges.push({
          id: `${agentId}-${skillId}`,
          source: agentId,
          target: skillId,
          animated: false,
          markerEnd: { type: MarkerType.ArrowClosed, width: 12, height: 12, color: '#52c41a' },
          style: { stroke: '#bfbfbf', strokeWidth: 1.5 },
        })
      }
    }
  })

  // Primary → Skills 直接连线（跳过中间层，用虚线）
  for (const skill of pluginDef.required_skills || []) {
    const skillId = `skill_${skill}`
    if (nodes.some(n => n.id === skillId)) {
      edges.push({
        id: `primary-${skillId}`,
        source: 'primary',
        target: skillId,
        animated: false,
        markerEnd: { type: MarkerType.ArrowClosed, width: 12, height: 12, color: '#1890ff' },
        style: { stroke: '#d9d9d9', strokeWidth: 1, strokeDasharray: '6 3' },
      })
    }
  }

  return { nodes, edges }
}

// 图例
function Legend() {
  const items = [
    { label: 'Primary', color: '#1890ff', bg: '#e6f7ff' },
    { label: 'Step', color: '#8c8c8c', bg: '#f5f5f5' },
    { label: 'Subagent', color: '#722ed1', bg: '#f9f0ff' },
    { label: 'Skill', color: '#52c41a', bg: '#f6ffed' },
  ]
  return (
    <div style={{ display: 'flex', gap: 12, marginBottom: 12 }}>
      {items.map(item => (
        <div key={item.label} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <div style={{
            width: 12, height: 12, borderRadius: 3,
            border: `2px solid ${item.color}`, background: item.bg,
          }} />
          <Text style={{ fontSize: 11, color: '#666' }}>{item.label}</Text>
        </div>
      ))}
      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
        <div style={{ width: 24, borderTop: '1px dashed #d9d9d9' }} />
        <Text style={{ fontSize: 11, color: '#666' }}>直接调用</Text>
      </div>
    </div>
  )
}

export default function PluginGraphPanel() {
  const [plugins, setPlugins] = useState([])
  const [selectedPlugin, setSelectedPlugin] = useState(null)
  const [pluginDef, setPluginDef] = useState(null)
  const [loading, setLoading] = useState(false)
  const [defLoading, setDefLoading] = useState(false)

  // 加载插件列表
  useEffect(() => {
    setLoading(true)
    getWorkflowDefinitions()
      .then(res => {
        const list = res.data?.plugins || []
        setPlugins(list)
        if (list.length > 0) setSelectedPlugin(list[0].plugin_id)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  // 加载选中插件的完整定义
  useEffect(() => {
    if (!selectedPlugin) { setPluginDef(null); return }
    setDefLoading(true)
    getWorkflowDefinition(selectedPlugin)
      .then(res => setPluginDef(res.data))
      .catch(() => setPluginDef(null))
      .finally(() => setDefLoading(false))
  }, [selectedPlugin])

  const { nodes, edges } = useMemo(() => layoutPluginGraph(pluginDef), [pluginDef])

  const graphHeight = useMemo(() => {
    if (!pluginDef) return 300
    const counts = [
      1,
      pluginDef.steps?.length || 0,
      pluginDef.agent_defs?.length || 0,
      collectAllSkills(pluginDef).length,
    ]
    return Math.max(...counts, 2) * Y_GAP + 80
  }, [pluginDef])

  return (
    <Card
      size="small"
      title={
        <Space>
          <ApartmentOutlined />
          <span>插件架构关系图</span>
        </Space>
      }
    >
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        {/* 插件选择器 */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Text strong style={{ fontSize: 12 }}>选择插件:</Text>
          <Select
            style={{ width: 360 }}
            value={selectedPlugin}
            onChange={setSelectedPlugin}
            loading={loading}
            placeholder="选择插件查看架构"
            options={plugins.map(p => ({
              value: p.plugin_id,
              label: `${p.plugin_name || p.plugin_id} (${p.steps_count} 步 · ${p.agents_count} 代理 · ${p.skills_count} 技能)`,
            }))}
            showSearch
            optionFilterProp="label"
          />
          {defLoading && <Spin size="small" />}
        </div>

        {/* 图例 */}
        {pluginDef && <Legend />}

        {/* DAG 图 */}
        {pluginDef && nodes.length > 0 ? (
          <div style={{ height: graphHeight, width: '100%', border: '1px solid #f0f0f0', borderRadius: 8 }}>
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
        ) : !selectedPlugin ? (
          <Empty description="请选择插件查看架构" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : defLoading ? (
          <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
        ) : (
          <Empty description="该插件没有可解析的工作流定义" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}

        {/* 统计信息 */}
        {pluginDef && (
          <div style={{ display: 'flex', gap: 16, padding: '8px 0', borderTop: '1px solid #f0f0f0' }}>
            <Tag color="blue">Primary: 1</Tag>
            <Tag color="default">Steps: {pluginDef.steps?.length || 0}</Tag>
            <Tag color="purple">Subagents: {pluginDef.agent_defs?.length || 0}</Tag>
            <Tag color="success">Skills: {collectAllSkills(pluginDef).length}</Tag>
            <Tag>Edges: {edges.length}</Tag>
          </div>
        )}
      </Space>
    </Card>
  )
}
