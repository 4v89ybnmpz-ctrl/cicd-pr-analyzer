import { useState, useEffect } from 'react'
import { Card, Table, Tag, Typography, Drawer, Button, Spin, Empty, Space } from 'antd'
import { AuditOutlined, CheckCircleOutlined, CloseCircleOutlined, QuestionCircleOutlined } from '@ant-design/icons'
import { getArbitratorReports } from '../../api'

const { Text } = Typography

const SEVERITY_COLORS = { CRITICAL: 'error', HIGH: 'warning', MEDIUM: 'processing', LOW: 'default' }
const VERDICT_ICON = { pass: <CheckCircleOutlined style={{ color: '#52c41a' }} />, fail: <CloseCircleOutlined style={{ color: '#ff4d4f' }} />, unknown: <QuestionCircleOutlined style={{ color: '#faad14' }} /> }

export default function ArbitratorPanel({ sessionId, visible, onClose }) {
  const [loading, setLoading] = useState(false)
  const [reports, setReports] = useState([])
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!visible || !sessionId) return
    setLoading(true)
    setError(null)
    getArbitratorReports(sessionId)
      .then(res => setReports(res.data?.reports || []))
      .catch(e => setError(e._friendlyMsg || e.message))
      .finally(() => setLoading(false))
  }, [sessionId, visible])

  const allIssues = reports.flatMap(r =>
    (r.issues || []).map(iss => ({ ...iss, step_id: r.step_id, verdict: r.verdict, summary: r.summary }))
  )

  const columns = [
    {
      title: '步骤', dataIndex: 'step_id', width: 140,
      render: (v, row) => <Space size={4}>{VERDICT_ICON[row.verdict]}<Text>{v}</Text></Space>
    },
    {
      title: '严重', dataIndex: 'severity', width: 70,
      render: v => <Tag color={SEVERITY_COLORS[v]} style={{ fontSize: 10 }}>{v}</Tag>
    },
    {
      title: '分类', dataIndex: 'category', width: 100,
      render: v => <Tag style={{ fontSize: 10 }}>{v}</Tag>
    },
    {
      title: '问题', dataIndex: 'problem',
      render: v => <Text style={{ fontSize: 12 }}>{v}</Text>
    },
    {
      title: '建议', dataIndex: 'suggestion', width: 250,
      render: v => v ? <Text style={{ fontSize: 12, whiteSpace: 'pre-wrap' }}>{v}</Text> : '-'
    },
    {
      title: '修复命令', dataIndex: 'suggestion_action', width: 250,
      render: v => v ? <Text code style={{ fontSize: 11, whiteSpace: 'pre-wrap' }}>{v}</Text> : '-'
    },
  ]

  return (
    <Drawer
      title={<Space><AuditOutlined />裁判报告</Space>}
      open={visible}
      onClose={onClose}
      width={Math.min(1200, window.innerWidth * 0.9)}
      destroyOnClose
    >
      <Spin spinning={loading}>
        {error ? (
          <Empty description={`加载失败: ${error}`} />
        ) : reports.length === 0 ? (
          <Empty description="该会话暂无裁判报告（评估过程中每个步骤的 gate 检查会自动触发裁判）" />
        ) : (
          <>
            <div style={{ marginBottom: 12 }}>
              {reports.map(r => (
                <Space key={r.step_id} size={16} style={{ marginRight: 24, marginBottom: 8 }}>
                  {VERDICT_ICON[r.verdict]}
                  <Text strong style={{ fontSize: 12 }}>{r.step_id}</Text>
                  <Tag color={r.parsing_success !== false ? (r.verdict === 'pass' ? 'success' : 'error') : 'default'}>
                    {r.parsing_success !== false ? (r.verdict === 'pass' ? '通过' : '未通过') : '解析失败'}
                  </Tag>
                  <Text type="secondary" style={{ fontSize: 11 }}>{r.summary}</Text>
                </Space>
              ))}
            </div>
            <Table
              dataSource={allIssues}
              columns={columns}
              rowKey={(r, i) => `${r.step_id}-${i}`}
              size="small"
              pagination={{ pageSize: 20, size: 'small' }}
              locale={{ emptyText: '无断点（所有步骤通过）' }}
            />
          </>
        )}
      </Spin>
    </Drawer>
  )
}
