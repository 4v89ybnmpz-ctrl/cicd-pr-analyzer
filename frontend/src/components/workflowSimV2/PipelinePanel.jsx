import {
  Card,
  Tag,
  Button,
  Progress,
  Space,
  Typography,
  Collapse,
} from 'antd'
import {
  PlayCircleOutlined,
  StopOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
  ClockCircleOutlined,
  ReloadOutlined,
  ApiOutlined,
} from '@ant-design/icons'
import '@xyflow/react/dist/style.css'

const { Text } = Typography

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
 * PipelinePanel — CI/CD 编排流程展示
 *
 * 展示 8 步编排流程的真实状态：
 * 1. 提交代码  2. 推送到 Fork 仓库  3. 向上游创建 PR
 * 4. 触发编译  5. 等待 CI/CD 结果  6. 分析失败原因
 * 7. 自动修复  8. 提交修复并重试
 *
 * SSE 事件驱动：
 *   pipeline_start       — 流水线开始
 *   pipeline_step_update — 编排步骤状态变化
 *   pipeline_done        — 流水线完成
 *   pipeline_fix_round   — 修复循环记录
 *   pipeline_status      — 中间状态同步
 */
// 新版编排步骤 key 集合（用于检测旧数据）
const NEW_STEP_KEYS = new Set(['git_commit', 'git_push', 'create_pr', 'trigger_ci', 'wait_ci', 'analyze_failure', 'auto_fix', 'fix_commit_retry'])

function normalizePipelineSteps(pipeline) {
  const raw = pipeline.steps || pipeline.stages || []
  if (raw.length === 0) return []
  // 检测旧格式（compile/unit_test 等）→ 丢弃，返回空数组让面板显示"未触发"
  if (!NEW_STEP_KEYS.has(raw[0]?.key)) return []
  return raw
}

export default function PipelinePanel({ pipeline, fixRounds, onTrigger, onCancel }) {
  if (!pipeline) return null

  const steps = normalizePipelineSteps(pipeline)
  const { status, mr_url } = pipeline

  // 未触发或旧数据兼容：steps 为空或全部 pending 时显示触发提示
  if (steps.length === 0 || (status === 'pending' && steps.every(s => s.status === 'pending'))) {
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
          <Text type="secondary">CI/CD 流水线未触发</Text>
          <br />
          <Text type="secondary" style={{ fontSize: 11 }}>
            提交代码 → 推送 → 创建 PR → 触发编译 → 等待结果 → 自动修复
          </Text>
          <div style={{ marginTop: 12 }}>
            <Button
              type="primary"
              size="small"
              icon={<PlayCircleOutlined />}
              onClick={onTrigger || undefined}
              disabled={!onTrigger}
            >
              手动触发流水线
            </Button>
            {!onTrigger && (
              <div style={{ marginTop: 6, fontSize: 11, color: '#faad14' }}>
                请先完成仿真后再触发流水线
              </div>
            )}
          </div>
        </div>
      </Card>
    )
  }

  // 计算进度
  const completedSteps = steps.filter(s => s.status === 'success' || s.status === 'failed').length
  const progressPercent = steps.length > 0 ? Math.round((completedSteps / steps.length) * 100) : 0

  // 流水线整体状态
  const overallIcon = status === 'success'
    ? <CheckCircleOutlined style={{ color: '#52c41a' }} />
    : status === 'failed' || status === 'timeout'
      ? <CloseCircleOutlined style={{ color: '#ff4d4f' }} />
      : status === 'cancelled'
        ? <StopOutlined style={{ color: '#faad14' }} />
        : status === 'running'
          ? <LoadingOutlined style={{ color: '#1677ff' }} />
          : <ClockCircleOutlined />

  // 当前运行中的步骤
  const runningStep = steps.find(s => s.status === 'running')

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
              查看 PR
            </a>
          )}
          {onCancel && status === 'running' && (
            <Button size="small" danger icon={<StopOutlined />} onClick={onCancel} style={{ fontSize: 11 }}>
              终止
            </Button>
          )}
          {onTrigger && (status === 'success' || status === 'failed' || status === 'timeout' || status === 'cancelled') && (
            <Button size="small" icon={<ReloadOutlined />} onClick={onTrigger} style={{ fontSize: 11 }}>
              重新触发
            </Button>
          )}
        </Space>
      }
    >
      {/* 整体进度条 */}
      <Progress
        percent={progressPercent}
        status={status === 'failed' || status === 'timeout' || status === 'cancelled' ? 'exception' : status === 'success' ? 'success' : 'active'}
        size="small"
        style={{ marginBottom: 12 }}
      />

      {/* 当前状态提示 */}
      {runningStep && (
        <div style={{ marginBottom: 8, padding: '6px 10px', background: '#e6f7ff', borderRadius: 4, fontSize: 12 }}>
          <LoadingOutlined style={{ marginRight: 6, color: '#1677ff' }} />
          <span>正在执行: <strong>{runningStep.name}</strong></span>
        </div>
      )}

      {/* 步骤列表（垂直布局） */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
        {steps.map((step, idx) => {
          const icon = PIPELINE_STAGE_ICON[step.status] || PIPELINE_STAGE_ICON.pending
          const isFailed = step.status === 'failed'
          const isRunning = step.status === 'running'

          return (
            <div key={step.key || idx}>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  padding: '8px 12px',
                  borderRadius: 6,
                  background: PIPELINE_STAGE_BG[step.status] || PIPELINE_STAGE_BG.pending,
                  border: `1px solid ${PIPELINE_STAGE_BORDER[step.status] || PIPELINE_STAGE_BORDER.pending}`,
                  marginBottom: idx < steps.length - 1 ? 2 : 0,
                  cursor: isFailed && step.log ? 'pointer' : 'default',
                  transition: 'all 0.3s',
                }}
              >
                <div style={{ width: 22, textAlign: 'center' }}>{icon}</div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <Text strong style={{ fontSize: 12 }}>{step.name}</Text>
                    {isFailed && <Tag color="red" style={{ fontSize: 9, lineHeight: '14px', padding: '0 4px', margin: 0 }}>失败</Tag>}
                    {isRunning && <Tag color="blue" style={{ fontSize: 9, lineHeight: '14px', padding: '0 4px', margin: 0 }}>执行中</Tag>}
                    {step.status === 'success' && <Tag color="green" style={{ fontSize: 9, lineHeight: '14px', padding: '0 4px', margin: 0 }}>完成</Tag>}
                  </div>
                  {step.log && isFailed && (
                    <div style={{ fontSize: 11, color: '#ff4d4f', marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {step.log.slice(0, 120)}
                    </div>
                  )}
                </div>
                {step.duration_ms > 0 && (
                  <Text type="secondary" style={{ fontSize: 10 }}>
                    {(step.duration_ms / 1000).toFixed(1)}s
                  </Text>
                )}
              </div>
              {/* 连接线 */}
              {idx < steps.length - 1 && (
                <div style={{
                  width: 2, height: 8, background: '#d9d9d9', marginLeft: 22,
                }} />
              )}
            </div>
          )
        })}
      </div>

      {/* 失败步骤错误日志（可展开） */}
      {steps.some(s => s.status === 'failed' && s.log) && (
        <Collapse
          size="small"
          style={{ marginTop: 12 }}
          items={steps
            .filter(s => s.status === 'failed' && s.log)
            .map(s => ({
              key: s.key,
              label: (
                <Space>
                  <CloseCircleOutlined style={{ color: '#ff4d4f' }} />
                  <span>{s.name} — 失败详情</span>
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
              </div>
            ))}
          </div>
        </div>
      )}
    </Card>
  )
}
