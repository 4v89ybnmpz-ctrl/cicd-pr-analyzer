import { useState, useEffect, useCallback } from 'react'
import {
  Card, Row, Col, Statistic, Spin, Alert, Tag, Space, Select,
  Progress, Tooltip, DatePicker, Segmented,
} from 'antd'
import {
  HeartOutlined, DashboardOutlined, FieldTimeOutlined,
  CheckCircleOutlined, TeamOutlined, AlertOutlined,
} from '@ant-design/icons'
import {
  Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  ResponsiveContainer, LineChart, Line, XAxis, YAxis,
  Tooltip as RTooltip, Legend,
} from 'recharts'
import * as api from '../api'

const { RangePicker } = DatePicker

const GRADE_COLORS = { A: '#52c41a', B: '#1890ff', C: '#faad14', D: '#fa541c', F: '#ff4d4f' }
const DIM_ICONS = {
  'PR 存活时间': <FieldTimeOutlined />,
  'Merge 率': <CheckCircleOutlined />,
  'Review 覆盖率': <DashboardOutlined />,
  'CI 成功率': <HeartOutlined />,
  '贡献者多样性': <TeamOutlined />,
  'Issue 响应速度': <AlertOutlined />,
}

function GradeTag({ grade }) {
  if (!grade) return null
  return <Tag color={GRADE_COLORS[grade] || '#999'} style={{ fontWeight: 700, fontSize: 14, padding: '0 10px' }}>{grade}</Tag>
}

export default function ProjectHealth() {
  const [projects, setProjects] = useState([])
  const [selected, setSelected] = useState(null)
  const [dateRange, setDateRange] = useState(null)
  const [report, setReport] = useState(null)
  const [trends, setTrends] = useState([])
  const [granularity, setGranularity] = useState('month')
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
        api.getProjectHealth(selected.owner, selected.repo, params),
        api.getProjectHealthTrends(selected.owner, selected.repo, { granularity, ...params }),
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
    return <Alert type="info" message="暂无项目数据，请先在项目总览中获取数据" />
  }

  const dimensions = report?.dimensions || []
  const radarData = report?.radar_data || []
  const insights = report?.insights || []

  return (
    <div>
      {/* 顶部 */}
      <Row gutter={[16, 16]} align="middle" style={{ marginBottom: 24 }}>
        <Col>
          <h2 style={{ margin: 0 }}><HeartOutlined style={{ marginRight: 8, color: '#ff4d4f' }} />项目健康度</h2>
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
            <RangePicker value={dateRange} onChange={setDateRange} placeholder={['开始日期', '结束日期']} style={{ width: 240 }} />
          </Space>
        </Col>
      </Row>

      {loading && <Spin size="large" style={{ display: 'block', margin: '60px auto' }} />}
      {error && <Alert type="error" message={error} style={{ marginBottom: 16 }} />}

      {!loading && report && (
        <>
          {/* 综合评分 */}
          <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
            <Col xs={24} sm={8}>
              <Card bodyStyle={{ padding: '24px 20px', textAlign: 'center' }}>
                <div style={{ marginBottom: 8 }}>
                  <GradeTag grade={report.overall_grade} />
                </div>
                <Progress
                  type="circle"
                  percent={report.overall_score}
                  size={120}
                  strokeColor={GRADE_COLORS[report.overall_grade] || '#999'}
                  format={p => <span style={{ fontSize: 28, fontWeight: 700 }}>{p}</span>}
                />
                <div style={{ fontSize: 14, color: '#666', marginTop: 8 }}>综合健康度</div>
              </Card>
            </Col>
            <Col xs={24} sm={16}>
              <Card title="各维度评分" bodyStyle={{ padding: '8px 16px' }}>
                {dimensions.map((d, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', padding: '8px 0', borderBottom: i < dimensions.length - 1 ? '1px solid #f5f5f5' : 'none' }}>
                    <span style={{ width: 24, color: '#1890ff' }}>{DIM_ICONS[d.name] || <DashboardOutlined />}</span>
                    <span style={{ width: 120, fontWeight: 500, fontSize: 13 }}>{d.name}</span>
                    <div style={{ flex: 1, margin: '0 12px' }}>
                      <Progress
                        percent={d.score || 0}
                        size="small"
                        strokeColor={GRADE_COLORS[d.grade] || '#999'}
                        format={() => d.score != null ? `${d.score}` : '--'}
                      />
                    </div>
                    {d.grade && <Tag color={GRADE_COLORS[d.grade]} style={{ width: 28, textAlign: 'center', margin: 0 }}>{d.grade}</Tag>}
                    <span style={{ width: 50, textAlign: 'right', fontSize: 12, color: '#999' }}>权重 {d.weight}</span>
                  </div>
                ))}
              </Card>
            </Col>
          </Row>

          {/* 雷达图 + 洞察 */}
          <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
            <Col xs={24} lg={12}>
              <Card title="健康度雷达图" bodyStyle={{ padding: '12px 20px' }}>
                {radarData.length > 0 ? (
                  <ResponsiveContainer width="100%" height={320}>
                    <RadarChart data={radarData} cx="50%" cy="50%" outerRadius={120}>
                      <PolarGrid />
                      <PolarAngleAxis dataKey="dimension" tick={{ fontSize: 11 }} />
                      <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fontSize: 10 }} />
                      <RTooltip />
                      <Radar name="健康度" dataKey="score" stroke="#1890ff" fill="#1890ff" fillOpacity={0.3} />
                    </RadarChart>
                  </ResponsiveContainer>
                ) : <div style={{ textAlign: 'center', color: '#999', padding: 40 }}>暂无数据</div>}
              </Card>
            </Col>
            <Col xs={24} lg={12}>
              <Card title="洞察与建议" bodyStyle={{ padding: '12px 16px' }}>
                {insights.length > 0 ? insights.map((ins, i) => (
                  <Card
                    key={i}
                    size="small"
                    style={{ marginBottom: 8, borderLeft: `3px solid ${GRADE_COLORS[ins.grade] || '#999'}` }}
                    bodyStyle={{ padding: '8px 12px' }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', marginBottom: 4 }}>
                      <Tag color={GRADE_COLORS[ins.grade] || '#999'} style={{ fontWeight: 700 }}>{ins.grade}</Tag>
                      <span style={{ fontWeight: 600, marginLeft: 8 }}>{ins.name}</span>
                      <span style={{ marginLeft: 'auto', fontSize: 16, fontWeight: 700, color: GRADE_COLORS[ins.grade] || '#999' }}>
                        {typeof ins.value === 'number' ? ins.value : ins.value}
                      </span>
                    </div>
                    <div style={{ fontSize: 12, color: '#666', marginBottom: 2 }}>{ins.description}</div>
                    {ins.suggestion && <div style={{ fontSize: 12, color: '#1890ff' }}>💡 {ins.suggestion}</div>}
                  </Card>
                )) : <div style={{ textAlign: 'center', color: '#999', padding: 20 }}>暂无洞察</div>}
              </Card>
            </Col>
          </Row>

          {/* 维度详情 */}
          <Card title="维度详情" style={{ marginBottom: 24 }}>
            <Row gutter={[16, 16]}>
              {dimensions.map((d, i) => (
                <Col xs={12} sm={8} md={4} key={i}>
                  <Card size="small" style={{ textAlign: 'center', borderTop: `3px solid ${GRADE_COLORS[d.grade] || '#d9d9d9'}` }}>
                    <div style={{ fontSize: 12, color: '#999', marginBottom: 4 }}>{d.name}</div>
                    <div style={{ fontSize: 22, fontWeight: 700, color: GRADE_COLORS[d.grade] || '#999' }}>
                      {d.score != null ? d.score : '--'}
                    </div>
                    {d.grade && <Tag color={GRADE_COLORS[d.grade]} style={{ marginTop: 4 }}>{d.grade}</Tag>}
                    <div style={{ fontSize: 11, color: '#999', marginTop: 4, minHeight: 32 }}>{d.description || ''}</div>
                  </Card>
                </Col>
              ))}
            </Row>
          </Card>

          {/* 趋势图 */}
          <Card
            title="健康度趋势"
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
                  <YAxis yAxisId="left" />
                  <YAxis yAxisId="right" orientation="right" domain={[0, 100]} />
                  <RTooltip />
                  <Legend />
                  <Line yAxisId="left" type="monotone" dataKey="total_prs" name="PR 总数" stroke="#1890ff" strokeWidth={2} dot={{ r: 3 }} />
                  <Line yAxisId="left" type="monotone" dataKey="merged_prs" name="已合并 PR" stroke="#52c41a" strokeWidth={2} dot={{ r: 3 }} />
                  <Line yAxisId="right" type="monotone" dataKey="merge_score" name="Merge 评分" stroke="#722ed1" strokeWidth={2} dot={{ r: 3 }} />
                  <Line yAxisId="right" type="monotone" dataKey="diversity_score" name="多样性评分" stroke="#faad14" strokeWidth={2} dot={{ r: 3 }} />
                </LineChart>
              </ResponsiveContainer>
            ) : <div style={{ textAlign: 'center', color: '#999', padding: 40 }}>暂无趋势数据</div>}
          </Card>
        </>
      )}
    </div>
  )
}
