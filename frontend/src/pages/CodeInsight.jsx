import { useState, useEffect, useCallback } from 'react'
import {
  Card, Row, Col, Spin, Alert, Tag, Space, Select, DatePicker,
  Segmented, Statistic, Table, Tooltip, Typography,
} from 'antd'
import {
  CodeOutlined, BugOutlined, RocketOutlined, ToolOutlined,
  FileTextOutlined, ThunderboltOutlined, ExperimentOutlined,
  DashboardOutlined, QuestionCircleOutlined, UserOutlined,
} from '@ant-design/icons'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip as RTooltip, ResponsiveContainer, Legend, Cell,
} from 'recharts'
import * as api from '../api'

const { Paragraph } = Typography
const { RangePicker } = DatePicker

const CATEGORY_CONFIG = {
  feature: { label: '新功能', color: '#1890ff', icon: <RocketOutlined /> },
  bugfix: { label: 'Bug修复', color: '#ff4d4f', icon: <BugOutlined /> },
  refactor: { label: '重构', color: '#722ed1', icon: <ToolOutlined /> },
  docs: { label: '文档', color: '#52c41a', icon: <FileTextOutlined /> },
  test: { label: '测试', color: '#faad14', icon: <ExperimentOutlined /> },
  ci: { label: 'CI/构建', color: '#13c2c2', icon: <ThunderboltOutlined /> },
  perf: { label: '性能优化', color: '#fa541c', icon: <DashboardOutlined /> },
  other: { label: '其他', color: '#8c8c8c', icon: <CodeOutlined /> },
}

const INSIGHT_RULES = (
  <div style={{ maxWidth: 520, fontSize: 12, lineHeight: 1.8 }}>
    <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 6 }}>变更洞察规则</div>
    <div style={{ color: '#999', marginBottom: 8 }}>基于 PR 标题、body、文件路径和标签自动分类变更类型</div>
    <div style={{ fontWeight: 600, marginTop: 8 }}>分类规则（优先级从高到低）</div>
    <div>1. <Tag color="cyan">CI/构建</Tag> — 标题含 ci/build/pipeline/docker，或文件在 .github/workflows/ 等</div>
    <div>2. <Tag color="gold">测试</Tag> — 标题含 test/spec，或文件在 test/、*.test.* 等</div>
    <div>3. <Tag color="green">文档</Tag> — 标题含 doc/readme，或文件 *.md/*.rst 等</div>
    <div>4. <Tag color="red">Bug修复</Tag> — 标题含 fix/bug/issue/hotfix/crash，或标签含 bug</div>
    <div>5. <Tag color="orange">性能优化</Tag> — 标题含 perf/optim/speed/cache 等</div>
    <div>6. <Tag color="purple">重构</Tag> — 标题含 refactor/clean/rename/deprecat，或标签含 refactor</div>
    <div>7. <Tag color="blue">新功能</Tag> — 标题含 feat/add/new/implement/support，或标签含 feature</div>
    <div>8. <Tag>其他</Tag> — 不匹配以上任何规则</div>
    <div style={{ fontWeight: 600, marginTop: 8 }}>阶段性摘要</div>
    <div>按周/月分桶，每个阶段统计分类占比和关键 PR，生成自然语言摘要</div>
  </div>
)

export default function CodeInsight() {
  const [projects, setProjects] = useState([])
  const [selected, setSelected] = useState(null)
  const [dateRange, setDateRange] = useState(null)
  const [granularity, setGranularity] = useState('week')
  const [data, setData] = useState(null)
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
      const params = { granularity }
      if (dateRange?.[0]) params.start_date = dateRange[0].format('YYYY-MM-DD')
      if (dateRange?.[1]) params.end_date = dateRange[1].format('YYYY-MM-DD')
      const res = await api.getCodeInsight(selected.owner, selected.repo, params)
      setData(res.data)
    } catch (e) {
      setError(e.message)
    }
    setLoading(false)
  }, [selected, dateRange, granularity])

  useEffect(() => { fetchData() }, [fetchData])

  if (projects.length === 0 && !loading) {
    return <Alert type="info" message="暂无项目数据" />
  }

  const categoryCounts = data?.category_counts || {}
  const fileTypeCounts = data?.file_type_counts || {}
  const periods = data?.periods || []

  const barData = Object.entries(categoryCounts).map(([k, v]) => ({
    category: (CATEGORY_CONFIG[k] || {}).label || k,
    count: v,
    fill: (CATEGORY_CONFIG[k] || {}).color || '#8c8c8c',
  }))

  const prColumns = [
    {
      title: '分类', dataIndex: 'category', key: 'category', width: 100,
      render: v => {
        const cfg = CATEGORY_CONFIG[v] || CATEGORY_CONFIG.other
        return <Tag color={cfg.color} icon={cfg.icon}>{cfg.label}</Tag>
      },
      filters: Object.entries(CATEGORY_CONFIG).map(([k, v]) => ({ text: v.label, value: k })),
      onFilter: (v, r) => r.category === v,
    },
    { title: 'PR', dataIndex: 'pr_number', key: 'pr_number', width: 60, render: v => <a href={`https://github.com/${data?.owner}/${data?.repo}/pull/${v}`} target="_blank" rel="noopener noreferrer">#{v}</a> },
    { title: '标题', dataIndex: 'title', key: 'title', ellipsis: true },
    { title: '作者', dataIndex: 'user', key: 'user', width: 100, render: v => <Tooltip title={v}><Tag icon={<UserOutlined />}>{v}</Tag></Tooltip> },
    { title: '+/-', key: 'changes', width: 100, render: (_, r) => <span><span style={{ color: '#52c41a' }}>+{r.additions}</span> / <span style={{ color: '#ff4d4f' }}>-{r.deletions}</span></span> },
    { title: '语言', dataIndex: 'file_types', key: 'file_types', width: 120, render: v => v?.slice(0, 2).map(t => <Tag key={t} style={{ fontSize: 11 }}>{t}</Tag>) },
  ]

  return (
    <div>
      <Row gutter={[16, 16]} align="middle" style={{ marginBottom: 24 }}>
        <Col>
          <h2 style={{ margin: 0 }}><CodeOutlined style={{ marginRight: 8, color: '#722ed1' }} />代码变更洞察</h2>
        </Col>
        <Col>
          <Tooltip title={INSIGHT_RULES} placement="bottomLeft" overlayStyle={{ maxWidth: 560 }} color="#fff" overlayInnerStyle={{ color: '#333' }}>
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
              onChange={v => { const p = projects.find(x => `${x.owner}/${x.repo}` === v); if (p) setSelected(p) }}
              style={{ width: 240 }}
              placeholder="选择项目"
              showSearch
              options={projects.map(p => ({ value: `${p.owner}/${p.repo}`, label: `${p.owner}/${p.repo}` }))}
            />
            <RangePicker value={dateRange} onChange={setDateRange} placeholder={['开始日期', '结束日期']} style={{ width: 240 }} />
            <Segmented size="small" value={granularity} onChange={setGranularity} options={[{ label: '按日', value: 'day' }, { label: '按周', value: 'week' }, { label: '按月', value: 'month' }]} />
          </Space>
        </Col>
      </Row>

      {loading && <Spin size="large" style={{ display: 'block', margin: '60px auto' }} />}
      {error && <Alert type="error" message={error} style={{ marginBottom: 16 }} />}

      {!loading && data && (
        <>
          {/* 摘要统计 */}
          <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
            <Col span={6}>
              <Card bodyStyle={{ padding: '16px 20px', textAlign: 'center' }}>
                <Statistic title="PR 总数" value={data.total_prs || 0} valueStyle={{ color: '#1890ff' }} />
              </Card>
            </Col>
            <Col span={6}>
              <Card bodyStyle={{ padding: '16px 20px', textAlign: 'center' }}>
                <Statistic title="新增行" value={data.total_additions || 0} prefix="+" valueStyle={{ color: '#52c41a' }} />
              </Card>
            </Col>
            <Col span={6}>
              <Card bodyStyle={{ padding: '16px 20px', textAlign: 'center' }}>
                <Statistic title="删除行" value={data.total_deletions || 0} prefix="-" valueStyle={{ color: '#ff4d4f' }} />
              </Card>
            </Col>
            <Col span={6}>
              <Card bodyStyle={{ padding: '16px 20px', textAlign: 'center' }}>
                <Statistic title="变更类型" value={Object.keys(categoryCounts).length} valueStyle={{ color: '#722ed1' }} />
              </Card>
            </Col>
          </Row>

          {/* 整体摘要 */}
          {data.overall_summary && (
            <Card style={{ marginBottom: 24 }} bodyStyle={{ padding: '12px 20px', background: '#f6f8fa', whiteSpace: 'pre-wrap', fontSize: 13, lineHeight: 1.8 }}>
              {data.overall_summary}
            </Card>
          )}

          {/* 分类分布 + 语言分布 */}
          <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
            <Col xs={24} lg={12}>
              <Card title="变更类型分布">
                {barData.length > 0 ? (
                  <ResponsiveContainer width="100%" height={260}>
                    <BarChart data={barData} barSize={36}>
                      <XAxis dataKey="category" tick={{ fontSize: 12 }} />
                      <YAxis />
                      <RTooltip />
                      <Bar dataKey="count">
                        {barData.map((entry, i) => (
                          <Cell key={i} fill={entry.fill} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                ) : <div style={{ textAlign: 'center', color: '#999', padding: 40 }}>暂无数据</div>}
              </Card>
            </Col>
            <Col xs={24} lg={12}>
              <Card title="涉及语言 Top 15" bodyStyle={{ padding: '12px 16px' }}>
                {Object.entries(fileTypeCounts).map(([lang, count], i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', padding: '4px 0', borderBottom: '1px solid #f5f5f5' }}>
                    <span style={{ width: 24, fontWeight: 700, color: i < 3 ? '#1890ff' : '#999' }}>#{i + 1}</span>
                    <span style={{ flex: 1, fontWeight: 500, fontSize: 13 }}>{lang}</span>
                    <Tag color={i < 3 ? 'blue' : 'default'}>{count}</Tag>
                  </div>
                ))}
              </Card>
            </Col>
          </Row>

          {/* 阶段性摘要 */}
          {periods.length > 0 && (
            <Card title="阶段性变更摘要" style={{ marginBottom: 24 }} bodyStyle={{ padding: '8px 16px' }}>
              {periods.map((p, i) => (
                <Card key={i} size="small" style={{ marginBottom: 8, background: '#fafafa' }} bodyStyle={{ padding: '8px 12px' }}>
                  <div style={{ fontSize: 13, whiteSpace: 'pre-wrap', lineHeight: 1.7 }}>{p.summary}</div>
                  <div style={{ marginTop: 4 }}>
                    {Object.entries(p.category_counts || {}).map(([cat, cnt]) => {
                      const cfg = CATEGORY_CONFIG[cat] || CATEGORY_CONFIG.other
                      return <Tag key={cat} color={cfg.color} style={{ fontSize: 11, margin: 2 }}>{cfg.label} {cnt}</Tag>
                    })}
                  </div>
                </Card>
              ))}
            </Card>
          )}

          {/* PR 列表 */}
          <Card title="变更 PR 列表">
            <Table
              size="small"
              dataSource={data.classified_prs?.map((pr, i) => ({ key: i, ...pr })) || []}
              columns={prColumns}
              pagination={{ pageSize: 20, showTotal: t => `共 ${t} 个 PR` }}
              scroll={{ x: 700 }}
            />
          </Card>
        </>
      )}
    </div>
  )
}
