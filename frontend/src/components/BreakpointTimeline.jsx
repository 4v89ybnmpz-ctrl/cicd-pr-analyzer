/**
 * BreakpointTimeline — 断点时间线组件
 * 按严重性排序展示评估过程中检测到的工程能力断点
 */
import { Timeline, Tag, Typography, Empty } from 'antd'

const { Text } = Typography

const SEVERITY_CONFIG = {
  CRITICAL: { color: 'red', tag: 'error', label: 'CRITICAL' },
  HIGH: { color: 'orange', tag: 'warning', label: 'HIGH' },
  MEDIUM: { color: 'gold', tag: '', label: 'MEDIUM' },
  LOW: { color: 'blue', tag: '', label: 'LOW' },
}

const CATEGORY_LABELS = {
  SKILL_GAP: '技能缺失',
  CONSTRAINT_VIOLATION: '约束违反',
  MISSING_ARTIFACT: '产物缺失',
  GATE_FAILURE: '门禁失败',
  PROMPT_AMBIGUITY: 'Prompt 歧义',
  FIX_LOOP_RISK: '修复循环风险',
}

export default function BreakpointTimeline({ breakpoints, maxHeight = 400 }) {
  if (!breakpoints || breakpoints.length === 0) {
    return <Empty description="未检测到断点" image={Empty.PRESENTED_IMAGE_SIMPLE} />
  }

  // 按严重性排序
  const severityOrder = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 }
  const sorted = [...breakpoints].sort(
    (a, b) => (severityOrder[a.severity] ?? 3) - (severityOrder[b.severity] ?? 3)
  )

  const items = sorted.map((bp, i) => {
    const config = SEVERITY_CONFIG[bp.severity] || SEVERITY_CONFIG.LOW
    return {
      key: i,
      color: config.color,
      children: (
        <div style={{ marginBottom: 4 }}>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 4 }}>
            <Tag color={config.tag} style={{ margin: 0, fontSize: 11 }}>
              {config.label}
            </Tag>
            <Tag style={{ margin: 0, fontSize: 11 }}>
              {CATEGORY_LABELS[bp.category] || bp.category}
            </Tag>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {bp.step_id}
            </Text>
          </div>
          <div style={{ fontSize: 13, lineHeight: 1.6 }}>{bp.description}</div>
          {bp.recommendation && (
            <div style={{ fontSize: 12, color: '#52c41a', marginTop: 2 }}>
              建议: {bp.recommendation}
            </div>
          )}
        </div>
      ),
    }
  })

  return (
    <div style={{ maxHeight, overflowY: 'auto', paddingRight: 8 }}>
      <Timeline items={items} />
    </div>
  )
}
