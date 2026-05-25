import { useState, useEffect, useCallback } from 'react'
import {
  Card, Row, Col, Statistic, Spin, Alert, Tag, Space, Select,
  Progress, Table, Tooltip, DatePicker, Segmented,
} from 'antd'
import {
  CheckCircleOutlined, ClockCircleOutlined, AuditOutlined,
  TeamOutlined, FileTextOutlined,
} from '@ant-design/icons'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip as RTooltip, ResponsiveContainer,
  PieChart, Pie, Cell, LineChart, Line, Legend,
} from 'recharts'
import * as api from '../api'

const { RangePicker } = DatePicker

const GRADE_COLORS = { A: '#52c41a', B: '#1890ff', C: '#faad14', D: '#fa541c', F: '#ff4d4f' }
const PIE_COLORS = ['#52c41a', '#ff4d4f', '#1890ff', '#d9d9d9', '#faad14']

function GradeBadge({ grade }) {
  if (!grade) return null
  return <Tag color={GRADE_COLORS[grade] || '#999'} style={{ fontWeight: 700, fontSize: 13, padding: '0 8px' }}>{grade}</Tag>
}

export default function ReviewQuality() {
  const [projects, setProjects] = useState([])
  const [selected, setSelected] = useState(null)
  const [dateRange, setDateRange] = useState(null)
  const [report, setReport] = useState(null)
  const [trends, setTrends] = useState([])
  const [granularity, setGranularity] = useState('week')
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
      const params = {}
      if (dateRange && dateRange[0]) params.start_date = dateRange[0].format('YYYY-MM-DD')
      if (dateRange && dateRange[1]) params.end_date = dateRange[1].format('YYYY-MM-DD')

      const [reportRes, trendsRes] = await Promise.all([
        api.getReviewQuality(selected.owner, selected.repo, { ...params, top_n: 10 }),
        api.getReviewQualityTrends(selected.owner, selected.repo, { granularity, ...params }),
      ])
      setReport(reportRes.data)
      setTrends(trendsRes.data.trends || [])
    } catch (e) {
      setError(e.message)
    }
    setLoading(false)
  }, [selected, dateRange, granularity])

  useEffect(() => { fetchData() }, [fetchData])

  if (projects.length === 0 && !loading) {
    return <Alert type="info" message="暂无项目数据，请先在项目总览中获取 PR Reviews 数据" />
  }

  const coverage = report?.coverage || {}
  const delay = report?.delay || {}
  const depth = report?.depth || {}
  const stateDist = report?.state_distribution || {}
  const topReviewers = report?.top_reviewers || []
  const insights = report?.insights || []

  const coverageInsight = insights.find(i => i.name === 'Review 覆盖率')
  const delayInsight = insights.find(i => i.name === '首次 Review 延迟')
  const depthInsight = insights.find(i => i.name === 'Review 深度')

  const pieData = [
    { name: 'APPROVED', value: stateDist.approved || 0 },
    { name: 'CHANGES_REQ', value: stateDist.changes_requested || 0 },
    { name: 'COMMENTED', value: stateDist.commented || 0 },
    { name: 'DISMISSED', value: stateDist.dismissed || 0 },
    { name: 'PENDING', value: stateDist.pending || 0 },
  ].filter(d => d.value > 0)

  const delayBarData = [
    { label: '平均', hours: delay.avg_first_review_delay_hours },
    { label: '中位数', hours: delay.median_first_review_delay_hours },
    { label: 'P90', hours: delay.p90_first_review_delay_hours },
  ].filter(d => d.hours != null)

  const reviewerColumns = [
    { title: '#', key: 'rank', width: 40, render: (_, __, i) => i + 1 },
    { title: 'Reviewer', dataIndex: 'user', key: 'user', render: v => <a href={`https://github.com/${v}`} target="_blank" rel="noopener noreferrer">{v}</a> },
    { title: 'Review 数', dataIndex: 'review_count', key: 'review_count', sorter: (a, b) => a.review_count - b.review_count, render: v => <Tag color="blue">{v}</Tag> },
    { title: 'APPROVED', dataIndex: 'approved_count', key: 'approved_count', render: v => <Tag color="green">{v}</Tag> },
    { title: 'CHANGES_REQ', dataIndex: 'changes_requested_count', key: 'changes_requested_count', render: v => v > 0 ? <Tag color="red">{v}</Tag> : <Tag>0</Tag> },
    { title: '平均评论长度', dataIndex: 'avg_body_length', key: 'avg_body_length', render: v => v != null ? Math.round(v) : '-', sorter: (a, b) => (a.avg_body_length || 0) - (b.avg_body_length || 0) },
  ]

  return (
    <div>
      {/* 顶部：项目选择 + 日期范围 */}
      <Row gutter={[16, 16]} align="middle" style={{ marginBottom: 24 }}>
        <Col>
          <h2 style={{ margin: 0 }}><AuditOutlined style={{ marginRight: 8, color: '#1890ff' }} />Review 质量评估</h2>
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
            <RangePicker
              value={dateRange}
              onChange={setDateRange}
              placeholder={['开始日期', '结束日期']}
              style={{ width: 240 }}
            />
          </Space>
        </Col>
      </Row>

      {loading && <Spin size="large" style={{ display: 'block', margin: '60px auto' }} />}
      {error && <Alert type="error" message={error} style={{ marginBottom: 16 }} />}

      {!loading && report && (
        <>
          {/* 核心指标卡片 */}
          <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
            <Col xs={12} sm={6}>
              <Card bodyStyle={{ padding: '16px 20px' }} style={{ borderLeft: '3px solid #1890ff' }}>
                <Statistic
                  title={<Space>Review 覆盖率 <GradeBadge grade={coverageInsight?.grade} /></Space>}
                  value={coverage.coverage_rate ?? '--'}
                  suffix={coverage.coverage_rate != null ? '%' : ''}
                  prefix={<CheckCircleOutlined />}
                  valueStyle={{ color: '#1890ff', fontSize: 24 }}
                />
                <div style={{ fontSize: 12, color: '#999', marginTop: 4 }}>
                  {coverage.prs_with_review ?? 0} / {coverage.total_prs ?? 0} PR 有 review
                </div>
              </Card>
            </Col>
            <Col xs={12} sm={6}>
              <Card bodyStyle={{ padding: '16px 20px' }} style={{ borderLeft: '3px solid #faad14' }}>
                <Statistic
                  title={<Space>首次 Review 延迟 <GradeBadge grade={delayInsight?.grade} /></Space>}
                  value={delay.avg_first_review_delay_hours ?? '--'}
                  suffix={delay.avg_first_review_delay_hours != null ? 'h' : ''}
                  prefix={<ClockCircleOutlined />}
                  valueStyle={{ color: '#faad14', fontSize: 24 }}
                />
                <div style={{ fontSize: 12, color: '#999', marginTop: 4 }}>
                  中位 {delay.median_first_review_delay_hours ?? '--'}h · P90 {delay.p90_first_review_delay_hours ?? '--'}h
                </div>
              </Card>
            </Col>
            <Col xs={12} sm={6}>
              <Card bodyStyle={{ padding: '16px 20px' }} style={{ borderLeft: '3px solid #52c41a' }}>
                <Statistic
                  title={<Space>Review 深度 <GradeBadge grade={depthInsight?.grade} /></Space>}
                  value={depth.body_rate ?? '--'}
                  suffix={depth.body_rate != null ? '%' : ''}
                  prefix={<FileTextOutlined />}
                  valueStyle={{ color: '#52c41a', fontSize: 24 }}
                />
                <div style={{ fontSize: 12, color: '#999', marginTop: 4 }}>
                  有内容 {depth.reviews_with_body ?? 0} / {depth.total_reviews ?? 0}
                </div>
              </Card>
            </Col>
            <Col xs={12} sm={6}>
              <Card bodyStyle={{ padding: '16px 20px' }} style={{ borderLeft: '3px solid #722ed1' }}>
                <Statistic
                  title="总 Review 数"
                  value={delay.total_reviews ?? 0}
                  prefix={<TeamOutlined />}
                  valueStyle={{ color: '#722ed1', fontSize: 24 }}
                />
                <div style={{ fontSize: 12, color: '#999', marginTop: 4 }}>
                  平均 {coverage.avg_reviewers_per_pr ?? '--'} reviewer/PR
                </div>
              </Card>
            </Col>
          </Row>

          {/* 状态分布 + 延迟分布 */}
          <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
            <Col xs={24} lg={12}>
              <Card title="Review 状态分布" bodyStyle={{ padding: '12px 20px' }}>
                {pieData.length > 0 ? (
                  <ResponsiveContainer width="100%" height={260}>
                    <PieChart>
                      <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={90} label={({ name, value }) => `${name}: ${value}`}>
                        {pieData.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                      </Pie>
                      <RTooltip />
                    </PieChart>
                  </ResponsiveContainer>
                ) : <div style={{ textAlign: 'center', color: '#999', padding: 40 }}>暂无数据</div>}
              </Card>
            </Col>
            <Col xs={24} lg={12}>
              <Card title="首次 Review 延迟分布" bodyStyle={{ padding: '12px 20px' }}>
                {delayBarData.length > 0 ? (
                  <ResponsiveContainer width="100%" height={260}>
                    <BarChart data={delayBarData} barSize={48}>
                      <XAxis dataKey="label" />
                      <YAxis unit="h" />
                      <RTooltip formatter={v => [`${v}h`, '延迟']} />
                      <Bar dataKey="hours" fill="#faad14" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : <div style={{ textAlign: 'center', color: '#999', padding: 40 }}>暂无数据</div>}
              </Card>
            </Col>
          </Row>

          {/* Top Reviewer + 洞察项 */}
          <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
            <Col xs={24} lg={14}>
              <Card title={<span><TeamOutlined style={{ marginRight: 8 }} />Top Reviewer</span>}>
                <Table
                  size="small"
                  dataSource={topReviewers.map((r, i) => ({ key: i, ...r }))}
                  columns={reviewerColumns}
                  pagination={false}
                />
              </Card>
            </Col>
            <Col xs={24} lg={10}>
              <Card title="洞察与建议" bodyStyle={{ padding: '12px 16px' }}>
                {insights.length > 0 ? insights.map((ins, i) => (
                  <Card
                    key={i}
                    size="small"
                    style={{ marginBottom: 8, borderLeft: `3px solid ${GRADE_COLORS[ins.grade] || '#999'}` }}
                    bodyStyle={{ padding: '8px 12px' }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', marginBottom: 4 }}>
                      <GradeBadge grade={ins.grade} />
                      <span style={{ fontWeight: 600, marginLeft: 8 }}>{ins.name}</span>
                      <span style={{ marginLeft: 'auto', fontSize: 16, fontWeight: 700, color: GRADE_COLORS[ins.grade] || '#999' }}>
                        {typeof ins.value === 'number' ? (ins.name.includes('延迟') ? `${ins.value}h` : `${ins.value}%`) : ins.value}
                      </span>
                    </div>
                    <div style={{ fontSize: 12, color: '#666', marginBottom: 2 }}>{ins.description}</div>
                    {ins.suggestion && <div style={{ fontSize: 12, color: '#1890ff' }}>💡 {ins.suggestion}</div>}
                  </Card>
                )) : <div style={{ textAlign: 'center', color: '#999', padding: 20 }}>暂无洞察</div>}
              </Card>
            </Col>
          </Row>

          {/* 趋势图 */}
          <Card
            title="Review 质量趋势"
            extra={
              <Segmented
                size="small"
                value={granularity}
                onChange={setGranularity}
                options={[
                  { label: '按日', value: 'day' },
                  { label: '按周', value: 'week' },
                  { label: '按月', value: 'month' },
                ]}
              />
            }
          >
            {trends.length > 0 ? (
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={trends}>
                  <XAxis dataKey="period" tick={{ fontSize: 11 }} />
                  <YAxis yAxisId="left" unit="个" />
                  <YAxis yAxisId="right" orientation="right" unit="个/PR" />
                  <RTooltip />
                  <Legend />
                  <Line yAxisId="left" type="monotone" dataKey="pr_count" name="有 Review 的 PR" stroke="#1890ff" strokeWidth={2} dot={{ r: 3 }} />
                  <Line yAxisId="left" type="monotone" dataKey="total_reviews" name="Review 总数" stroke="#722ed1" strokeWidth={2} dot={{ r: 3 }} />
                  <Line yAxisId="right" type="monotone" dataKey="avg_reviews_per_pr" name="平均 Review/PR" stroke="#52c41a" strokeWidth={2} dot={{ r: 3 }} />
                </LineChart>
              </ResponsiveContainer>
            ) : <div style={{ textAlign: 'center', color: '#999', padding: 40 }}>暂无趋势数据</div>}
          </Card>
        </>
      )}
    </div>
  )
}
