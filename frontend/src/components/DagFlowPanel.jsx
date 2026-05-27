import { useState, useCallback, useRef, useMemo } from 'react'
import { ReactFlow, Handle, Position, useNodesState, useEdgesState, MarkerType } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { Tag, Button, Space, Progress, Popconfirm, Collapse } from 'antd'
import { PlayCircleOutlined, LoadingOutlined, CheckCircleOutlined, CloseCircleOutlined, ApartmentOutlined } from '@ant-design/icons'
import * as api from '../api'

// DAG 节点定义
const DAG_DEFS = [
  { id: 'prs',      label: '获取 PR',      apiFn: 'asyncFetchPrs',      params: { max_count: 0 },  icon: '📥' },
  { id: 'issues',   label: '获取 Issues',   apiFn: 'asyncFetchIssues',   params: { max_count: 0 },  icon: '📋' },
  { id: 'git_clone',label: '克隆仓库',       apiFn: 'asyncGitClone',                                  icon: '📂' },
  { id: 'comments', label: '获取评论',       apiFn: 'asyncFetchComments', params: { limit: 0 },      icon: '💬', dependsOn: ['prs'] },
  { id: 'timelines',label: '获取 Timeline',  apiFn: 'asyncFetchTimelines',params:{ limit: 0 },       icon: '⏱️', dependsOn: ['prs', 'issues'] },
  { id: 'files',    label: '获取 PR 文件',   apiFn: 'fetchPrFiles',      params: { limit: 0 },      icon: '📄', dependsOn: ['prs'] },
  { id: 'git_log',  label: '提取 Git Log',   apiFn: 'asyncGitExtract',   params: { max_count: 0 },  icon: '📝', dependsOn: ['git_clone'] },
  { id: 'profiles', label: '获取 Profile',   apiFn: 'asyncFetchProfiles',params:{ limit: 0 },       icon: '👤', dependsOn: ['comments', 'timelines'] },
]

// 拓扑分层
function getLayers(defs) {
  const layers = []
  const assigned = new Set()
  let remaining = [...defs]
  while (remaining.length > 0) {
    const layer = remaining.filter(d => !d.dependsOn || d.dependsOn.every(dep => assigned.has(dep)))
    if (layer.length === 0) break
    layers.push(layer)
    layer.forEach(d => assigned.add(d.id))
    remaining = remaining.filter(d => !assigned.has(d.id))
  }
  return layers
}

const LAYERS = getLayers(DAG_DEFS)

// 固定节点位置
const NODE_POSITIONS = {}
const Y_GAP = 140
const X_GAP = 220
const X_OFFSET = 20
LAYERS.forEach((layer, li) => {
  const totalWidth = (layer.length - 1) * X_GAP
  const maxLayerWidth = 4 * X_GAP // 最宽层有4个节点
  const startX = X_OFFSET + (maxLayerWidth - totalWidth) / 2
  layer.forEach((node, ni) => {
    NODE_POSITIONS[node.id] = { x: startX + ni * X_GAP, y: li * Y_GAP }
  })
})

const STATUS_CONFIG = {
  idle:     { color: '#d9d9d9', bg: '#fafafa', border: '#d9d9d9', text: '待执行', tagColor: 'default' },
  pending:  { color: '#8c8c8c', bg: '#f5f5f5', border: '#bfbfbf', text: '已排队', tagColor: 'default' },
  running:  { color: '#1890ff', bg: '#e6f7ff', border: '#1890ff', text: '运行中', tagColor: 'processing' },
  completed:{ color: '#52c41a', bg: '#f6ffed', border: '#52c41a', text: '已完成', tagColor: 'success' },
  failed:   { color: '#ff4d4f', bg: '#fff2f0', border: '#ff4d4f', text: '失败',   tagColor: 'error' },
}

// 自定义节点组件
function DagNode({ data }) {
  const { label, icon, status, progress, total } = data
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.idle
  const statusIcon = {
    idle: null,
    pending: <LoadingOutlined spin style={{ color: '#8c8c8c' }} />,
    running: <LoadingOutlined spin style={{ color: '#1890ff' }} />,
    completed: <CheckCircleOutlined style={{ color: '#52c41a' }} />,
    failed: <CloseCircleOutlined style={{ color: '#ff4d4f' }} />,
  }
  return (
    <div style={{
      padding: '10px 16px',
      borderRadius: 8,
      border: `2px solid ${cfg.border}`,
      background: cfg.bg,
      minWidth: 140,
      fontSize: 13,
      boxShadow: status === 'running' ? `0 0 8px ${cfg.border}40` : 'none',
      transition: 'all 0.3s',
    }}>
      <Handle type="target" position={Position.Top} style={{ background: '#bfbfbf', width: 6, height: 6 }} />
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <span>{icon} <b>{label}</b></span>
        {statusIcon[status]}
      </div>
      <div style={{ marginTop: 4 }}>
        <Tag color={cfg.tagColor} style={{ fontSize: 11, margin: 0 }}>{cfg.text}</Tag>
      </div>
      {status === 'running' && total > 0 && (
        <Progress percent={Math.round((progress || 0) / total * 100)} size="small" style={{ marginTop: 6 }} />
      )}
      <Handle type="source" position={Position.Bottom} style={{ background: '#bfbfbf', width: 6, height: 6 }} />
    </div>
  )
}

const nodeTypes = { dagNode: DagNode }

export default function DagFlowPanel({ owner, repo, onDone }) {
  const [nodeStatuses, setNodeStatuses] = useState(() =>
    Object.fromEntries(DAG_DEFS.map(d => [d.id, { status: 'idle', progress: 0, total: 0, taskId: null }]))
  )
  const [running, setRunning] = useState(false)
  const pollRef = useRef(null)

  // 构建 React Flow 节点
  const initialNodes = useMemo(() =>
    DAG_DEFS.map(d => ({
      id: d.id,
      type: 'dagNode',
      position: NODE_POSITIONS[d.id],
      data: { label: d.label, icon: d.icon, status: 'idle', progress: 0, total: 0 },
    }))
  , [])

  // 构建 React Flow 边
  const initialEdges = useMemo(() => {
    const edges = []
    DAG_DEFS.forEach(d => {
      (d.dependsOn || []).forEach(dep => {
        edges.push({
          id: `${dep}->${d.id}`,
          source: dep,
          target: d.id,
          animated: false,
          markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color: '#bfbfbf' },
          style: { stroke: '#bfbfbf', strokeWidth: 2 },
        })
      })
    })
    return edges
  }, [])

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)

  const updateNode = useCallback((nodeId, updates) => {
    setNodeStatuses(prev => ({ ...prev, [nodeId]: { ...prev[nodeId], ...updates } }))
    setNodes(nds => nds.map(n => n.id === nodeId ? { ...n, data: { ...n.data, ...updates } } : n))
  }, [setNodes])

  const updateEdgeStyle = useCallback((sourceId, targetId, color, animated) => {
    setEdges(eds => eds.map(e => e.id === `${sourceId}->${targetId}` ?
      { ...e, animated, style: { ...e.style, stroke: color }, markerEnd: { ...e.markerEnd, color } } : e
    ))
  }, [setEdges])

  // 轮询单个任务状态
  const pollTask = async (nodeId, taskId) => {
    try {
      const res = await api.getTask(taskId)
      const task = res.data.task || res.data
      updateNode(nodeId, {
        status: task.status,
        progress: task.progress || 0,
        total: task.total || 0,
      })
      return task.status
    } catch {
      // 请求失败时保持当前状态，不判定为失败
      return nodeStatuses[nodeId]?.status || 'pending'
    }
  }

  // 等待一组任务全部完成
  const waitForTasks = (taskMap) => new Promise((resolve) => {
    if (Object.keys(taskMap).length === 0) { resolve(); return }
    const statuses = {}
    const interval = setInterval(async () => {
      for (const [nodeId, taskId] of Object.entries(taskMap)) {
        if (statuses[nodeId] === 'completed' || statuses[nodeId] === 'failed') continue
        const st = await pollTask(nodeId, taskId)
        statuses[nodeId] = st
        if (st === 'completed') {
          updateNode(nodeId, { status: 'completed' })
          // 高亮出边
          DAG_DEFS.filter(d => (d.dependsOn || []).includes(nodeId)).forEach(d => {
            updateEdgeStyle(nodeId, d.id, '#52c41a', true)
          })
        } else if (st === 'failed') {
          updateNode(nodeId, { status: 'failed' })
        }
      }
      // 检查是否全部完成
      const done = Object.values(statuses).filter(s => s === 'completed' || s === 'failed').length
      if (done >= Object.keys(taskMap).length) {
        clearInterval(interval)
        resolve(statuses)
      }
    }, 2000)
    pollRef.current = interval
  })

  // 执行 DAG
  const runDag = async () => {
    setRunning(true)
    // 重置所有状态
    DAG_DEFS.forEach(d => {
      updateNode(d.id, { status: 'idle', progress: 0, total: 0 })
    })
    setEdges(eds => eds.map(e => ({
      ...e,
      animated: false,
      style: { ...e.style, stroke: '#bfbfbf' },
      markerEnd: { ...e.markerEnd, color: '#bfbfbf' },
    })))

    const layers = getLayers(DAG_DEFS)
    for (const layer of layers) {
      // 并行创建本层所有任务
      const taskMap = {}
      for (const def of layer) {
        updateNode(def.id, { status: 'pending' })
        try {
          let res
          if (def.params) {
            const [paramName, paramValue] = Object.entries(def.params)[0]
            res = await api[def.apiFn](owner, repo, { [paramName]: paramValue })
          } else {
            res = await api[def.apiFn](owner, repo)
          }
          const taskId = res.data?.task?.task_id
          if (taskId) {
            taskMap[def.id] = taskId
            updateNode(def.id, { status: 'running', taskId })
          } else {
            // 没有返回 task（可能是同步接口直接完成了）
            updateNode(def.id, { status: 'completed' })
          }
        } catch (e) {
          updateNode(def.id, { status: 'failed' })
        }
      }

      // 等待本层全部完成
      if (Object.keys(taskMap).length > 0) {
        const results = await waitForTasks(taskMap)
        // 如果本层有任何失败，可以决定是否继续（这里选择继续）
      }
    }

    setRunning(false)
    if (onDone) onDone()
  }

  // 停止轮询
  const stopDag = () => {
    if (pollRef.current) clearInterval(pollRef.current)
    setRunning(false)
  }

  const proOptions = { hideAttribution: true }

  return (
    <Collapse
      size="small"
      defaultActiveKey={[]}
      items={[{
        key: 'dag',
        label: (
          <Space>
            <ApartmentOutlined />
            <b>流程编排</b>
            <Tag color={running ? 'processing' : 'default'}>{running ? '执行中' : '待执行'}</Tag>
          </Space>
        ),
        extra: running ? (
          <Button size="small" danger onClick={(e) => { e.stopPropagation(); stopDag() }}>停止</Button>
        ) : (
          <Popconfirm
            title="将按依赖顺序执行全部数据拉取任务，上游完成后才启动下游，确认？"
            onConfirm={runDag}
            okText="确认执行"
            cancelText="取消"
          >
            <Button
              type="primary"
              size="small"
              icon={<PlayCircleOutlined />}
              onClick={(e) => e.stopPropagation()}
            >
              执行全部
            </Button>
          </Popconfirm>
        ),
        children: (
          <div style={{ height: LAYERS.length * Y_GAP + 60, background: '#fff' }}>
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              nodeTypes={nodeTypes}
              proOptions={proOptions}
              fitView
              nodesDraggable={false}
              nodesConnectable={false}
              elementsSelectable={false}
              zoomOnScroll={false}
              zoomOnPinch={false}
              zoomOnDoubleClick={false}
              panOnDrag={false}
              minZoom={1}
              maxZoom={1}
            />
          </div>
        ),
      }]}
    />
  )
}
