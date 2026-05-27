import { useState, useEffect } from 'react'
import {
  Card, Row, Col, Select, Button, Table, Tag, Spin, Alert, Space, message, Progress,
} from 'antd'
import { SwapOutlined, ReloadOutlined, TeamOutlined, TrophyOutlined } from '@ant-design/icons'
import { RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, ResponsiveContainer, Tooltip as RTooltip, Legend } from 'recharts'
import * as api from '../api'

const GRADE_COLORS = { A: '#52c41a', B: '#1890ff', C: '#faad14', D: '#fa541c', F: '#ff4d4f', 'N/A': '#d9d9d9' }
const PROJECT_COLORS = ['#1890ff', '#52c41a', '#faad14', '#ff4d4f', '#722ed1', '#13c2c2']

export default function ProjectCompare() {
  const [projects, setProjects] = useState([])
  const [selected, setSelected] = useState([])
  const [loading, setLoading] = useState(false)
  const [comparing, setComparing] = useState(false)
  const [result, setResult] = useState(null)

  useEffect(() => {
    setLoading(true)
    api.getProjectsOverview()
      .then(res => {
        const list = (res.data.projects || []).map(p => `${p.owner}/${p.repo}`)
        setProjects(list)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const handleCompare = async () => {
    if (selected.length < 2) {
      message.warning('请至少选择 2 个项目')
      return
    }
    setComparing(true)
    setResult(null)
    try {
      const res = await api.compareProjects({ projects: selected })
      setResult(res.data)
    } catch (e) {
      message.error(`对比失败: ${e.message}`)
    } finally {
      setComparing(false)
    }
  }

  // 准备雷达图数据
  const getRadarData = () => {
    if (!result?.comparison?.radar_data?.length) return []
    const dims = result.comparison.dimensions || []
    return dims.map(dim => {
      const point = { dimension: dim }
      result.comparison.radar_data.forEach(rd => {
        const val = rd.values.find(v => v.dimension === dim)
        point[rd.project] = val ? val.score : 0
      })
      return point
    })
  }

  // 对比表格列
  const getTableColumns = () => {
    if (!result?.projects) return []
    const cols = [
      {
        title: '维度', dataIndex: 'dimension', width: 140, fixed: 'left',
        render: (t) => <span style={{ fontWeight: 500 }}>{t}</span>,
      },
    ]
    result.projects.forEach((p, idx) => {
      cols.push({
        title: (
          <span>
            <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: PROJECT_COLORS[idx], marginRight: 6 }} />
            {p.project}
          </span>
        ),
        key: p.project,
        width: 150,
        render: (_, row) => {
          const ranking = row.rankings.find(r => r.project === p.project)
          if (!ranking) return '-'
          const color = ranking.rank === 1 ? '#52c41a' : ranking.rank === 2 ? '#1890ff' : '#999'
          return (
            <Space>
              <span style={{ fontWeight: 600, color }}>{ranking.score}</span>
              {ranking.rank === 1 && <Tag color="gold" style={{ margin: 0, fontSize: 10 }}>Top</Tag>}
            </Space>
          )
        },
      })
    })
    return cols
  }

  const radarData = getRadarData()

  return (
    <div>
      <Row gutter={[16, 16]} align="middle" style={{ marginBottom: 24 }}>
        <Col><h2 style={{ margin: 0 }}><SwapOutlined style={{ marginRight: 8, color: '#1890ff' }} />多仓库对比</h2></Col>
      </Row>

      <Card style={{ marginBottom: 16 }}>
        <Space wrap>
          <Select
            mode="multiple"
            value={selected}
            onChange={setSelected}
            options={projects.map(p => ({ value: p, label: p }))}
            style={{ minWidth: 400 }}
            placeholder="选择要对比的项目（至少 2 个）"
            showSearch
            maxTagCount={5}
          />
          <Button type="primary" icon={<SwapOutlined />} onClick={handleCompare} loading={comparing} disabled={selected.length < 2}>
            开始对比
          </Button>
        </Space>
      </Card>

      {comparing && <Spin size="large" style={{ display: 'block', margin: '60px auto' }} />}

      {result && !comparing && (
        <>
          {/* 总览卡片 */}
          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            {result.projects.map((p, idx) => (
              <Col xs={12} md={6} key={p.project}>
                <Card size="small" style={{ borderTop: `3px solid ${PROJECT_COLORS[idx]}` }}>
                  <div style={{ fontWeight: 600, marginBottom: 8, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {p.project}
                  </div>
                  {p.data_available ? (
                    <Space direction="vertical" size={4} style={{ width: '100%' }}>
                      <div>
                        <Progress
                          type="circle" percent={Math.round(p.overall_score)} size={50}
                          strokeColor={GRADE_COLORS[p.overall_grade] || '#1890ff'}
                          format={pct => <span style={{ fontSize: 14, fontWeight: 700 }}>{pct}</span>}
                        />
                      </div>
                      <Tag color={GRADE_COLORS[p.overall_grade] === '#52c41a' ? 'success' : 'processing'}>{p.overall_grade}</Tag>
                    </Space>
                  ) : (
                    <div style={{ color: '#999', padding: '8px 0' }}>数据不足</div>
                  )}
                </Card>
              </Col>
            ))}
          </Row>

          {/* 雷达图 + 排名表 */}
          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col xs={24} lg={10}>
              <Card title="维度雷达图">
                {radarData.length > 0 ? (
                  <ResponsiveContainer width="100%" height={350}>
                    <RadarChart data={radarData}>
                      <PolarGrid />
                      <PolarAngleAxis dataKey="dimension" tick={{ fontSize: 11 }} />
                      <PolarRadiusAxis angle={30} domain={[0, 100]} />
                      {result.comparison.radar_data.map((rd, i) => (
                        <Radar key={i} name={rd.project} dataKey={rd.project}
                          stroke={PROJECT_COLORS[i]} fill={PROJECT_COLORS[i]}
                          fillOpacity={0.15} strokeWidth={2} />
                      ))}
                      <RTooltip />
                      <Legend />
                    </RadarChart>
                  </ResponsiveContainer>
                ) : (
                  <div style={{ color: '#999', textAlign: 'center', padding: 40 }}>暂无数据</div>
                )}
              </Card>
            </Col>

            <Col xs={24} lg={14}>
              <Card title={<span><TrophyOutlined style={{ marginRight: 8 }} />维度排名对比</span>}>
                <Table
                  columns={getTableColumns()}
                  dataSource={result.comparison?.rankings || []}
                  rowKey="dimension"
                  pagination={false}
                  size="small"
                  scroll={{ x: 600 }}
                />
              </Card>
            </Col>
          </Row>

          {/* 贡献者重叠 */}
          {result.contributors_overlap?.length > 0 && (
            <Card title={<span><TeamOutlined style={{ marginRight: 8 }} />跨项目贡献者</span>}>
              <Table
                columns={[
                  { title: '用户', dataIndex: 'user', width: 160, render: (u) => <span style={{ fontWeight: 500 }}>{u}</span> },
                  { title: '活跃项目数', dataIndex: 'project_count', width: 100 },
                  { title: '总 PR 数', dataIndex: 'total_prs', width: 100 },
                  {
                    title: '项目分布', key: 'projects',
                    render: (_, r) => (
                      <Space wrap size={4}>
                        {Object.entries(r.details || {}).map(([proj, count]) => (
                          <Tag key={proj} style={{ margin: 0 }}>{proj}: {count} PR</Tag>
                        ))}
                      </Space>
                    ),
                  },
                ]}
                dataSource={result.contributors_overlap}
                rowKey="user"
                pagination={{ pageSize: 10, showTotal: (t) => `共 ${t} 位跨项目贡献者` }}
                size="small"
              />
            </Card>
          )}
        </>
      )}
    </div>
  )
}
