import { useState, useEffect, useCallback } from 'react'
import {
  Card, Row, Col, Spin, Alert, Tag, Space, Select, InputNumber, Badge,
} from 'antd'
import {
  AlertOutlined, WarningOutlined, InfoCircleOutlined,
  ThunderboltOutlined, FieldTimeOutlined, TeamOutlined, HeartOutlined,
} from '@ant-design/icons'

const SEVERITY_CONFIG = {
  critical: { color: '#ff4d4f', icon: <AlertOutlined />, label: '严重', tagColor: 'error' },
  warning: { color: '#faad14', icon: <WarningOutlined />, label: '警告', tagColor: 'warning' },
  info: { color: '#1890ff', icon: <InfoCircleOutlined />, label: '提示', tagColor: 'processing' },
}

const TYPE_ICONS = {
  ci_failure: <ThunderboltOutlined />,
  review_delay: <FieldTimeOutlined />,
  contributor_loss: <TeamOutlined />,
  pr_lifetime: <HeartOutlined />,
}

export default function TrendAlerts() {
  const [projects, setProjects] = useState([])
  const [selected, setSelected] = useState(null)
  const [periodDays, setPeriodDays] = useState(7)
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.getProjectsOverview()
      .then(res => {
        const list = res.data.projects || []
        setProjects(list)
        if (list.length > 0) setSelected(list[0])
      })
      .catch(() => {})
  }, [])

  const fetchData = useCallback(async () => {
    if (!selected) return
    setLoading(true)
    setError(null)
    try {
      const res = await api.getTrendAlerts(selected.owner, selected.repo, { period_days: periodDays })
      setReport(res.data)
    } catch (e) {
      setError(e.message)
    }
    setLoading(false)
  }, [selected, periodDays])

  useEffect(() => { fetchData() }, [fetchData])

  if (projects.length === 0 && !loading) {
    return <Alert type="info" message="暂无项目数据" />
  }

  const alerts = report?.alerts || []
  const summary = report?.summary || {}

  return (
    <div>
      <Row gutter={[16, 16]} align="middle" style={{ marginBottom: 24 }}>
        <Col>
          <h2 style={{ margin: 0 }}><AlertOutlined style={{ marginRight: 8, color: '#ff4d4f' }} />趋势预警</h2>
        </Col>
        <Col flex="auto" />
        <Col>
          <Space>
            <Select
              value={selected ? `${selected.owner}/${selected.repo}` : undefined}
              onChange={v => {
                const p = projects.find(x => `${x.owner}/${x.repo}` === v)
                if (p) setSelected(p)
              }}
              style={{ width: 240 }}
              placeholder="选择项目"
              showSearch
              options={projects.map(p => ({ value: `${p.owner}/${p.repo}`, label: `${p.owner}/${p.repo}` }))}
            />
            <span style={{ fontSize: 13, color: '#666' }}>对比周期</span>
            <InputNumber min={1} max={90} value={periodDays} onChange={v => setPeriodDays(v || 7)} style={{ width: 70 }} addonAfter="天" />
          </Space>
        </Col>
      </Row>

      {loading && <Spin size="large" style={{ display: 'block', margin: '60px auto' }} />}
      {error && <Alert type="error" message={error} style={{ marginBottom: 16 }} />}

      {!loading && report && (
        <>
          {/* 摘要 */}
          <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
            <Col span={6}>
              <Card bodyStyle={{ padding: '16px 20px', textAlign: 'center' }}>
                <Badge count={summary.critical || 0} offset={[8, 0]}>
                  <span style={{ fontSize: 16, fontWeight: 600 }}>总预警</span>
                </Badge>
                <div style={{ fontSize: 32, fontWeight: 700, color: (summary.total || 0) > 0 ? '#ff4d4f' : '#52c41a', marginTop: 8 }}>
                  {summary.total || 0}
                </div>
              </Card>
            </Col>
            <Col span={6}>
              <Card bodyStyle={{ padding: '16px 20px', textAlign: 'center' }}>
                <div style={{ fontSize: 14, color: '#999' }}>严重</div>
                <div style={{ fontSize: 28, fontWeight: 700, color: '#ff4d4f', marginTop: 4 }}>{summary.critical || 0}</div>
              </Card>
            </Col>
            <Col span={6}>
              <Card bodyStyle={{ padding: '16px 20px', textAlign: 'center' }}>
                <div style={{ fontSize: 14, color: '#999' }}>警告</div>
                <div style={{ fontSize: 28, fontWeight: 700, color: '#faad14', marginTop: 4 }}>{summary.warning || 0}</div>
              </Card>
            </Col>
            <Col span={6}>
              <Card bodyStyle={{ padding: '16px 20px', textAlign: 'center' }}>
                <div style={{ fontSize: 14, color: '#999' }}>提示</div>
                <div style={{ fontSize: 28, fontWeight: 700, color: '#1890ff', marginTop: 4 }}>{summary.info || 0}</div>
              </Card>
            </Col>
          </Row>

          {/* 预警列表 */}
          {alerts.length > 0 ? (
            alerts.map((alert, i) => {
              const cfg = SEVERITY_CONFIG[alert.severity] || SEVERITY_CONFIG.info
              return (
                <Card
                  key={i}
                  style={{ marginBottom: 12, borderLeft: `4px solid ${cfg.color}` }}
                  bodyStyle={{ padding: '12px 20px' }}
                >
                  <Row align="middle" gutter={[16, 8]}>
                    <Col>
                      <Tag color={cfg.tagColor} style={{ fontSize: 13, fontWeight: 600, padding: '2px 10px' }}>
                        {cfg.icon} {cfg.label}
                      </Tag>
                    </Col>
                    <Col>
                      <Tag icon={TYPE_ICONS[alert.alert_type] || <AlertOutlined />} style={{ fontSize: 12 }}>
                        {alert.alert_type.replace('_', ' ')}
                      </Tag>
                    </Col>
                    <Col flex="auto">
                      <span style={{ fontWeight: 600, fontSize: 15 }}>{alert.title}</span>
                    </Col>
                    {alert.change_rate != null && (
                      <Col>
                        <span style={{ fontSize: 16, fontWeight: 700, color: cfg.color }}>
                          {alert.change_rate > 0 ? '+' : ''}{alert.change_rate}%
                        </span>
                      </Col>
                    )}
                  </Row>
                  <div style={{ fontSize: 13, color: '#666', marginTop: 6 }}>{alert.description}</div>
                  <Row gutter={[24, 4]} style={{ marginTop: 6 }}>
                    {alert.current_value != null && (
                      <Col><span style={{ fontSize: 12, color: '#999' }}>当前: <b style={{ color: '#333' }}>{alert.current_value}</b></span></Col>
                    )}
                    {alert.previous_value != null && (
                      <Col><span style={{ fontSize: 12, color: '#999' }}>上期: <b style={{ color: '#333' }}>{alert.previous_value}</b></span></Col>
                    )}
                    {alert.threshold != null && (
                      <Col><span style={{ fontSize: 12, color: '#999' }}>阈值: {alert.threshold}</span></Col>
                    )}
                    {alert.dimension && (
                      <Col><span style={{ fontSize: 12, color: '#999' }}>维度: {alert.dimension}</span></Col>
                    )}
                  </Row>
                  {alert.suggestion && (
                    <div style={{ fontSize: 12, color: '#1890ff', marginTop: 6 }}>💡 {alert.suggestion}</div>
                  )}
                </Card>
              )
            })
          ) : (
            <Card style={{ textAlign: 'center', padding: 40 }}>
              <div style={{ fontSize: 48, color: '#52c41a', marginBottom: 12 }}>✅</div>
              <div style={{ fontSize: 16, fontWeight: 600, color: '#52c41a' }}>一切正常，暂无预警</div>
              <div style={{ fontSize: 13, color: '#999', marginTop: 4 }}>对比周期: 近 {periodDays} 天 vs 前 {periodDays} 天</div>
            </Card>
          )}
        </>
      )}
    </div>
  )
}
