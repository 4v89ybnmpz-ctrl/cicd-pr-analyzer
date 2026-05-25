import { useState, useEffect, useCallback } from 'react'
import {
  Card, Row, Col, Spin, Alert, Tag, Space, Select, InputNumber, Badge,
  Tooltip, Typography,
} from 'antd'
import {
  AlertOutlined, WarningOutlined, InfoCircleOutlined,
  ThunderboltOutlined, FieldTimeOutlined, TeamOutlined, HeartOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons'
import * as api from '../api'

const { Text } = Typography

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

const RULES_CONTENT = (
  <div style={{ maxWidth: 520, fontSize: 12, lineHeight: 1.8 }}>
    <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 6 }}>预警规则逻辑</div>
    <div style={{ color: '#999', marginBottom: 8 }}>对比「本期」与「上期」指标，检测环比异常变化</div>

    <div style={{ fontWeight: 600, color: '#ff4d4f', marginTop: 8 }}>① CI 失败率突增预警</div>
    <div>数据源：<Text code>cicd_results</Text> 集合，按时间分两期计算 failure_rate</div>
    <div>变化量 = 本期失败率 − 上期失败率（百分点）</div>
    <div>触发条件：</div>
    <div style={{ paddingLeft: 12 }}>
      <Tag color="error" style={{ margin: 0 }}>严重</Tag> 变化量 &gt; 20% &nbsp;
      <Tag color="warning" style={{ margin: 0 }}>警告</Tag> 变化量 &gt; 10% &nbsp;
      <Tag color="processing" style={{ margin: 0 }}>提示</Tag> 变化量 &gt; 5%
    </div>
    <div>示例：上期失败率 10% → 本期 35%，变化量 25% → 触发「严重」</div>

    <div style={{ fontWeight: 600, color: '#faad14', marginTop: 10 }}>② Review 响应变慢预警</div>
    <div>数据源：<Text code>pr_reviews</Text> + <Text code>pr_details</Text>，计算首次 review 平均延迟</div>
    <div>变化率 = (本期延迟 − 上期延迟) / 上期延迟 × 100%</div>
    <div>触发条件：</div>
    <div style={{ paddingLeft: 12 }}>
      <Tag color="error" style={{ margin: 0 }}>严重</Tag> 变化率 &gt; 50% &nbsp;
      <Tag color="warning" style={{ margin: 0 }}>警告</Tag> 变化率 &gt; 30% &nbsp;
      <Tag color="processing" style={{ margin: 0 }}>提示</Tag> 变化率 &gt; 15%
    </div>
    <div>示例：上期平均 4h → 本期 8h，变化率 100% → 触发「严重」</div>

    <div style={{ fontWeight: 600, color: '#1890ff', marginTop: 10 }}>③ 活跃贡献者流失预警</div>
    <div>数据源：<Text code>pr_details</Text>，按时间分两期统计独立贡献者数</div>
    <div>流失率 = (上期人数 − 本期人数) / 上期人数 × 100%</div>
    <div>触发条件：</div>
    <div style={{ paddingLeft: 12 }}>
      <Tag color="error" style={{ margin: 0 }}>严重</Tag> 流失率 &gt; 40% &nbsp;
      <Tag color="warning" style={{ margin: 0 }}>警告</Tag> 流失率 &gt; 25% &nbsp;
      <Tag color="processing" style={{ margin: 0 }}>提示</Tag> 流失率 &gt; 10%
    </div>
    <div>示例：上期 10 人 → 本期 8 人，流失率 20% → 触发「提示」</div>

    <div style={{ fontWeight: 600, color: '#722ed1', marginTop: 10 }}>④ PR 存活时间增长预警</div>
    <div>数据源：<Text code>pr_details</Text>，计算已合并 PR 的平均存活时间（created_at → merged_at）</div>
    <div>变化率 = (本期存活 − 上期存活) / 上期存活 × 100%</div>
    <div>触发条件：</div>
    <div style={{ paddingLeft: 12 }}>
      <Tag color="error" style={{ margin: 0 }}>严重</Tag> 变化率 &gt; 50% &nbsp;
      <Tag color="warning" style={{ margin: 0 }}>警告</Tag> 变化率 &gt; 30% &nbsp;
      <Tag color="processing" style={{ margin: 0 }}>提示</Tag> 变化率 &gt; 15%
    </div>
    <div>示例：上期平均 24h → 本期 40h，变化率 67% → 触发「严重」</div>

    <div style={{ borderTop: '1px solid #f0f0f0', marginTop: 10, paddingTop: 8, color: '#999' }}>
      <div>时间窗口：本期 = [今天 − N天, 今天]，上期 = [今天 − 2N天, 今天 − N天]</div>
      <div>N 为「对比周期」天数，默认 7 天</div>
    </div>
  </div>
)

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
        <Col>
          <Tooltip title={RULES_CONTENT} placement="bottomLeft" overlayStyle={{ maxWidth: 560 }} color="#fff" overlayInnerStyle={{ color: '#333' }}>
            <Tag style={{ cursor: 'pointer', fontSize: 13, padding: '2px 10px' }}>
              <QuestionCircleOutlined /> 逻辑介绍
            </Tag>
          </Tooltip>
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
