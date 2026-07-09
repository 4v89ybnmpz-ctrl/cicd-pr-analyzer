/**
 * WorkflowSimPanel — 工作流评估 DAG 可视化
 * 使用 @xyflow/react 展示工作流步骤，节点颜色表示通过率，断点用红色标注
 */
import { useCallback, useMemo, useEffect } from 'react'
import {
  ReactFlow,
  Controls,
  Background,
  MarkerType,
  Handle,
  Position,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { Badge, Tooltip, Progress, Tag } from 'antd'

const SEVERITY_COLORS = {
  CRITICAL: '#ff4d4f',
  HIGH: '#fa541c',
  MEDIUM: '#faad14',
  LOW: '#1890ff',
}

const PASS_RATE_COLORS = (rate) => {
  if (rate >= 0.8) return '#52c41a'
  if (rate >= 0.6) return '#faad14'
  if (rate >= 0.4) return '#fa8c16'
  return '#ff4d4f'
}

function StepNode({ data }) {
  const { step, passRate, breakpoints, selected, onClick } = data
  const borderColor = PASS_RATE_COLORS(passRate)
  const safeBps = Array.isArray(breakpoints) ? breakpoints.filter(Boolean) : []
  const criticalCount = safeBps.filter(b => b.severity === 'CRITICAL').length
  const highCount = safeBps.filter(b => b.severity === 'HIGH').length

  return (
    <div
      onClick={onClick}
      style={{
        position: 'relative',
        padding: '10px 16px',
        borderRadius: 8,
        border: `2px solid ${selected ? '#1890ff' : borderColor}`,
        background: '#fff',
        minWidth: 160,
        cursor: 'pointer',
        boxShadow: selected ? '0 0 0 2px rgba(24,144,255,0.3)' : '0 1px 4px rgba(0,0,0,0.08)',
        transition: 'box-shadow 0.2s',
      }}
    >
      <Handle type="target" position={Position.Left} style={{ visibility: 'hidden' }} />
      <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4 }}>
        {(step.step_id || 'unknown').replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
      </div>
      <div style={{ fontSize: 12, color: '#666', marginBottom: 6 }}>{step.step_name}</div>
      <Progress
        percent={Math.round(passRate * 100)}
        size="small"
        strokeColor={borderColor}
        format={() => `${Math.round(passRate * 100)}%`}
      />
      {(criticalCount > 0 || highCount > 0) && (
        <div style={{ marginTop: 4, display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          {criticalCount > 0 && (
            <Tag color="error" style={{ fontSize: 11, margin: 0 }}>
              {criticalCount} CRITICAL
            </Tag>
          )}
          {highCount > 0 && (
            <Tag color="warning" style={{ fontSize: 11, margin: 0 }}>
              {highCount} HIGH
            </Tag>
          )}
        </div>
      )}
      <Handle type="source" position={Position.Right} style={{ visibility: 'hidden' }} />
    </div>
  )
}

const nodeTypes = { stepNode: StepNode }

export default function WorkflowSimPanel({ steps, onStepClick, selectedStepId }) {
  const buildNodes = useCallback(() => {
    if (!steps || steps.length === 0) return []

    return steps.map((stepResult, index) => {
      const passRate = stepResult.simulated_pass_rate ?? 0
      const breakpoints = Array.isArray(stepResult.breakpoints) ? stepResult.breakpoints.filter(Boolean) : []
      const stepId = stepResult.step_id || `step-${index}`
      return {
        id: stepId,
        type: 'stepNode',
        position: { x: 220 * index, y: 0 },
        data: {
          step: stepResult,
          passRate,
          breakpoints,
          selected: selectedStepId === stepId,
          onClick: () => onStepClick?.(stepId),
        },
      }
    })
  }, [steps, selectedStepId, onStepClick])

  const buildEdges = useCallback(() => {
    if (!steps || steps.length <= 1) return []
    return steps.slice(0, -1).map((step, i) => {
      const srcId = step.step_id || `step-${i}`
      const tgtId = steps[i + 1].step_id || `step-${i + 1}`
      return {
        id: `${srcId}-${tgtId}`,
        source: srcId,
        target: tgtId,
        animated: true,
        markerEnd: { type: MarkerType.ArrowClosed },
        style: { stroke: '#bbb', strokeWidth: 2 },
      }
    })
  }, [steps])

  const nodes = useMemo(buildNodes, [buildNodes])
  const edges = useMemo(buildEdges, [buildEdges])

  if (!steps || steps.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: 40, color: '#999' }}>
        暂无评估数据，请先执行评估
      </div>
    )
  }

  return (
    <div style={{ height: 200, width: '100%' }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        proOptions={{ hideAttribution: true }}
        minZoom={0.3}
        maxZoom={1.5}
      >
        <Controls showInteractive={false} />
        <Background color="#f0f0f0" gap={16} />
      </ReactFlow>
    </div>
  )
}
