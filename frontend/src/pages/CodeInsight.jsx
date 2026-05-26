import { useState, useEffect, useCallback } from 'react'
import {
  Card, Row, Col, Spin, Alert, Tag, Space, Select, DatePicker,
  Segmented, Statistic, Table, Tooltip, Typography, Button, message, InputNumber,
} from 'antd'
import {
  CodeOutlined, BugOutlined, RocketOutlined, ToolOutlined,
  FileTextOutlined, ThunderboltOutlined, ExperimentOutlined,
  DashboardOutlined, QuestionCircleOutlined, UserOutlined,
  CloudDownloadOutlined, RobotOutlined,
} from '@ant-design/icons'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip as RTooltip, ResponsiveContainer, Legend, Cell,
  LineChart, Line, CartesianGrid,
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
  security: { label: '安全修复', color: '#eb2f96', icon: <BugOutlined /> },
  other: { label: '其他', color: '#8c8c8c', icon: <CodeOutlined /> },
}

const SIZE_CONFIG = { S: { label: 'S', color: '#52c41a' }, M: { label: 'M', color: '#1890ff' }, L: { label: 'L', color: '#faad14' }, XL: { label: 'XL', color: '#ff4d4f' } }
const SCOPE_LABELS = { frontend: '前端', backend: '后端', infra: '基础设施', docs: '文档', fullstack: '全栈', unknown: '未知' }

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

export default function CodeInsight({ onNavigate }) {
  const [projects, setProjects] = useState([])
  const [selected, setSelected] = useState(null)
  const [dateRange, setDateRange] = useState(null)
  const [granularity, setGranularity] = useState('week')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [fetching, setFetching] = useState(false)
  const [fetchLimit, setFetchLimit] = useState(10)
  const [mergedFilter, setMergedFilter] = useState('all')
  const [aiAnalysis, setAiAnalysis] = useState(null)
  const [aiLoading, setAiLoading] = useState(false)
  const [aiFocus, setAiFocus] = useState('overview')

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

  const handleFetchData = useCallback(async () => {
    if (!selected) return
    setFetching(true)
    const { owner, repo } = selected
    try {
      message.loading({ content: `正在获取 ${owner}/${repo} PR 详情...`, key: 'fetch', duration: 0 })
      await api.fetchPrDetails(owner, repo, { limit: fetchLimit })
      message.loading({ content: `正在获取 ${owner}/${repo} PR 文件变更...`, key: 'fetch', duration: 0 })
      await api.fetchAllPrFiles(owner, repo, { limit: fetchLimit })
      message.success({ content: '数据获取完成，正在刷新洞察...', key: 'fetch' })
      fetchData()
    } catch (e) {
      message.error({ content: `获取失败: ${e.message}`, key: 'fetch' })
    }
    setFetching(false)
  }, [selected, fetchLimit, fetchData])

  const handleAiAnalyze = useCallback(async () => {
    if (!selected) return
    setAiLoading(true)
    setAiAnalysis(null)
    const { owner, repo } = selected
    try {
      const params = { focus: aiFocus }
      if (dateRange?.[0]) params.start_date = dateRange[0].format('YYYY-MM-DD')
      if (dateRange?.[1]) params.end_date = dateRange[1].format('YYYY-MM-DD')
      const res = await api.aiAnalyzeCodeChanges(owner, repo, params)
      if (res.data?.error) {
        setAiAnalysis({ analysis: `**AI 分析不可用**\n\n${res.data.error}${!res.data.ai_ready ? '\n\n请前往 [AI 配置](llm-config) 页面配置 LLM' : ''}`, focus: params.focus, total_prs_analyzed: 0, generated_at: new Date().toISOString() })
      } else {
        setAiAnalysis(res.data)
      }
    } catch (e) {
      message.error(`AI 分析失败: ${e.message}`)
    }
    setAiLoading(false)
  }, [selected, aiFocus, dateRange])

  if (projects.length === 0 && !loading) {
    return <Alert type="info" message="暂无项目数据" />
  }

  const categoryCounts = data?.category_counts || {}
  const fileTypeCounts = data?.file_type_counts || {}
  const periods = data?.periods || []
  const diffAnalysis = data?.diff_analysis || {}

  // 全局合入筛选：过滤 classified_prs，重新计算所有统计数据
  const allPrs = data?.classified_prs || []
  const filteredPrs = mergedFilter === 'all' ? allPrs : allPrs.filter(pr => mergedFilter === 'merged' ? pr.merged : !pr.merged)

  const filteredCategoryCounts = {}
  const filteredFileTypeCounts = {}
  let filteredAdditions = 0, filteredDeletions = 0
  filteredPrs.forEach(pr => {
    filteredCategoryCounts[pr.category] = (filteredCategoryCounts[pr.category] || 0) + 1
    pr.file_types?.forEach(ft => { filteredFileTypeCounts[ft] = (filteredFileTypeCounts[ft] || 0) + 1 })
    filteredAdditions += pr.additions || 0
    filteredDeletions += pr.deletions || 0
  })

  // 过滤 periods 中的 prs
  const filteredPeriods = periods.map(p => {
    const fPrs = mergedFilter === 'all' ? p.prs : p.prs.filter(pr => mergedFilter === 'merged' ? pr.merged : !pr.merged)
    const fCats = {}, fFt = {}, fContribs = {}
    let fAdd = 0, fDel = 0
    fPrs.forEach(pr => {
      fCats[pr.category] = (fCats[pr.category] || 0) + 1
      pr.file_types?.forEach(ft => { fFt[ft] = (fFt[ft] || 0) + 1 })
      const u = pr.user; if (u) fContribs[u] = (fContribs[u] || 0) + 1
      fAdd += pr.additions || 0; fDel += pr.deletions || 0
    })
    return {
      ...p, prs: fPrs, category_counts: fCats, additions: fAdd, deletions: fDel,
      file_type_counts: dictSort(fFt, 10), top_contributors: Object.entries(fContribs).sort((a,b) => b[1]-a[1]).slice(0, 10),
    }
  }).filter(p => p.prs.length > 0)

  // 重新生成过滤后的 period summary
  filteredPeriods.forEach(p => {
    if (!p.prs.length) return
    const catNames = { feature: '新功能', bugfix: 'Bug修复', refactor: '重构', docs: '文档', test: '测试', ci: 'CI/构建', perf: '性能优化', other: '其他' }
    const lines = [`${p.period}: ${p.prs.length} 个 PR`]
    const catParts = Object.entries(p.category_counts).sort((a,b) => b[1]-a[1]).map(([c,n]) => `${catNames[c]||c} ${n}`)
    lines.push('变更类型：' + catParts.join('、'))
    lines.push(`代码变更：+${p.additions}/-${p.deletions}`)
    if (Object.keys(p.file_type_counts).length) lines.push('涉及语言：' + Object.keys(p.file_type_counts).slice(0,5).join('、'))
    if (p.top_contributors.length) lines.push('贡献者：' + p.top_contributors.slice(0,5).map(([u,c]) => `${u}(${c})`).join('、'))
    const keyPrs = p.prs.slice(0,3).filter(pr => pr.title).map(pr => `#${pr.pr_number} ${pr.title.slice(0,60)}`)
    if (keyPrs.length) lines.push('关键 PR：' + keyPrs.join('; '))
    p.summary = lines.join('\n')
  })

  function dictSort(obj, limit) { return Object.fromEntries(Object.entries(obj).sort((a,b) => b[1]-a[1]).slice(0, limit)) }

  const barData = Object.entries(filteredCategoryCounts).map(([k, v]) => ({
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
    { title: '作者', dataIndex: 'user', key: 'user', width: 140, ellipsis: true, render: v => <Tooltip title={v}><Tag icon={<UserOutlined />} style={{ maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis' }}>{v}</Tag></Tooltip> },
    { title: '+/-', key: 'changes', width: 110, render: (_, r) => <span><span style={{ color: '#52c41a' }}>+{r.additions}</span> / <span style={{ color: '#ff4d4f' }}>-{r.deletions}</span></span> },
    { title: '体积', dataIndex: 'size', key: 'size', width: 50, render: v => { const c = SIZE_CONFIG[v] || SIZE_CONFIG.M; return <Tag color={c.color} style={{ fontSize: 11 }}>{c.label}</Tag> } },
    { title: '范围', dataIndex: 'scope', key: 'scope', width: 70, render: v => <Tag style={{ fontSize: 11 }}>{SCOPE_LABELS[v] || v}</Tag> },
    {
      title: '风险', key: 'risk', width: 80,
      render: (_, r) => {
        const flags = r.risk_flags || []
        if (!flags.length) return <span style={{ color: '#d9d9d9' }}>-</span>
        return <Space size={2}>{flags.map(f => <Tag key={f} color="red" style={{ fontSize: 10 }}>{f === 'xl_pr' ? 'XL' : f === 'too_many_files' ? '多文件' : f === 'breaking_change' ? 'BREAK' : '大新增'}</Tag>)}</Space>
      },
    },
    { title: '语言', dataIndex: 'file_types', key: 'file_types', width: 120, render: v => v?.slice(0, 2).map(t => <Tag key={t} style={{ fontSize: 11 }}>{t}</Tag>) },
    {
      title: '代码变更', key: 'diff', width: 200,
      render: (_, r) => {
        const ds = r.diff_summary
        if (!ds) return <span style={{ color: '#d9d9d9' }}>-</span>
        const syms = ds.symbols_by_type || {}
        const fnAdded = (syms.function_added || []).slice(0, 2)
        const clsAdded = (syms.class_added || []).slice(0, 2)
        const patterns = ds.pattern_counts || {}
        return (
          <Tooltip title={
            <div style={{ maxWidth: 300, fontSize: 11 }}>
              {fnAdded.length > 0 && <div>新增函数: {fnAdded.join(', ')}</div>}
              {clsAdded.length > 0 && <div>新增类: {clsAdded.join(', ')}</div>}
              {ds.added_imports?.length > 0 && <div>新增 import: {ds.added_imports.slice(0, 3).join('; ')}</div>}
              {ds.removed_imports?.length > 0 && <div>删除 import: {ds.removed_imports.slice(0, 3).join('; ')}</div>}
              {Object.entries(patterns).length > 0 && <div>模式: {Object.entries(patterns).map(([k, v]) => `${k}×${v}`).join(', ')}</div>}
            </div>
          }>
            <Space size={4}>
              {fnAdded.length > 0 && <Tag color="blue" style={{ fontSize: 10 }}>+{fnAdded.length}fn</Tag>}
              {clsAdded.length > 0 && <Tag color="purple" style={{ fontSize: 10 }}>+{clsAdded.length}cls</Tag>}
              {patterns.adds_error_handling && <Tag color="red" style={{ fontSize: 10 }}>err</Tag>}
              {patterns.adds_logging && <Tag color="cyan" style={{ fontSize: 10 }}>log</Tag>}
              {patterns.pure_addition && <Tag color="green" style={{ fontSize: 10 }}>add</Tag>}
              {patterns.pure_deletion && <Tag color="red" style={{ fontSize: 10 }}>del</Tag>}
            </Space>
          </Tooltip>
        )
      },
    },
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
            <Segmented size="small" value={mergedFilter} onChange={setMergedFilter} options={[{ label: '全部 PR', value: 'all' }, { label: '已合入', value: 'merged' }, { label: '未合入', value: 'unmerged' }]} />
            <InputNumber min={1} max={100} value={fetchLimit} onChange={setFetchLimit} size="small" style={{ width: 60 }} addonBefore="取" />
            <Button type="primary" size="small" icon={<CloudDownloadOutlined />} loading={fetching} onClick={handleFetchData}>
              拉取数据
            </Button>
            <Button type="primary" size="small" icon={<RobotOutlined />} loading={aiLoading} onClick={handleAiAnalyze}
              style={{ background: '#722ed1', borderColor: '#722ed1' }}>
              AI 深度分析
            </Button>
            {onNavigate && <a onClick={() => onNavigate('llm-config')} style={{ fontSize: 12, color: '#722ed1', marginLeft: 4, cursor: 'pointer' }}>AI配置</a>}
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
                <Statistic title="PR 总数" value={filteredPrs.length} valueStyle={{ color: '#1890ff' }} />
              </Card>
            </Col>
            <Col span={6}>
              <Card bodyStyle={{ padding: '16px 20px', textAlign: 'center' }}>
                <Statistic title="新增行" value={filteredAdditions} prefix="+" valueStyle={{ color: '#52c41a' }} />
              </Card>
            </Col>
            <Col span={6}>
              <Card bodyStyle={{ padding: '16px 20px', textAlign: 'center' }}>
                <Statistic title="删除行" value={filteredDeletions} prefix="-" valueStyle={{ color: '#ff4d4f' }} />
              </Card>
            </Col>
            <Col span={6}>
              <Card bodyStyle={{ padding: '16px 20px', textAlign: 'center' }}>
                <Statistic title="变更类型" value={Object.keys(filteredCategoryCounts).length} valueStyle={{ color: '#722ed1' }} />
              </Card>
            </Col>
          </Row>
          <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
            <Col span={6}>
              <Card bodyStyle={{ padding: '16px 20px', textAlign: 'center' }}>
                <Statistic title="变更速率" value={data?.pr_velocity || 0} suffix="PR/天" valueStyle={{ color: '#13c2c2' }} />
              </Card>
            </Col>
            <Col span={6}>
              <Card bodyStyle={{ padding: '16px 20px', textAlign: 'center' }}>
                <Statistic title="风险项" value={Object.values(data?.risk_summary || {}).reduce((a, b) => a + b, 0)} valueStyle={{ color: (Object.values(data?.risk_summary || {}).reduce((a, b) => a + b, 0) > 0 ? '#ff4d4f' : '#52c41a') }} />
              </Card>
            </Col>
            <Col span={6}>
              <Card bodyStyle={{ padding: '16px 20px', textAlign: 'center' }}>
                <Statistic title="高耦合对" value={(data?.high_coupling || []).length} valueStyle={{ color: '#faad14' }} />
              </Card>
            </Col>
            <Col span={6}>
              <Card bodyStyle={{ padding: '16px 20px', textAlign: 'center' }}>
                <Statistic title="高Churn文件" value={(data?.high_churn_files || []).length} valueStyle={{ color: '#fa541c' }} />
              </Card>
            </Col>
          </Row>

          {/* 整体摘要 */}
          {data.overall_summary && (
            <Card style={{ marginBottom: 24 }} bodyStyle={{ padding: '12px 20px', background: '#f6f8fa', whiteSpace: 'pre-wrap', fontSize: 13, lineHeight: 1.8 }}>
              {data.overall_summary}
            </Card>
          )}

          {/* AI 深度分析面板 */}
          <Card
            title={<span><RobotOutlined style={{ marginRight: 8, color: '#722ed1' }} />AI 深度分析</span>}
            style={{ marginBottom: 24 }}
            extra={
              <Space>
                <Segmented size="small" value={aiFocus} onChange={setAiFocus} options={[
                  { label: '综合', value: 'overview' },
                  { label: '风险', value: 'risk' },
                  { label: '架构', value: 'architecture' },
                  { label: '质量', value: 'quality' },
                ]} />
                <Button type="primary" size="small" icon={<RobotOutlined />} loading={aiLoading} onClick={handleAiAnalyze}
                  style={{ background: '#722ed1', borderColor: '#722ed1' }}>
                  分析
                </Button>
              </Space>
            }
          >
            {aiLoading && (
              <div style={{ textAlign: 'center', padding: 40 }}>
                <Spin size="large" />
                <div style={{ marginTop: 12, color: '#999' }}>AI 正在分析代码变更...</div>
              </div>
            )}
            {!aiLoading && !aiAnalysis && (
              <div style={{ textAlign: 'center', padding: 30, color: '#999' }}>
                <RobotOutlined style={{ fontSize: 32, marginBottom: 8, color: '#d9d9d9' }} />
                <div>点击"分析"按钮，AI 将深度分析代码变更的意图、风险、架构影响</div>
                <div style={{ marginTop: 4, fontSize: 12 }}>可选择分析焦点：综合 / 风险 / 架构 / 质量</div>
                {onNavigate && <div style={{ marginTop: 8 }}><a onClick={() => onNavigate('llm-config')} style={{ color: '#722ed1', cursor: 'pointer' }}>前往 AI 配置页面 →</a></div>}
              </div>
            )}
            {aiAnalysis && aiAnalysis.analysis && (
              <div style={{ padding: '0 4px', fontSize: 13, lineHeight: 1.8 }}>
                <div style={{ marginBottom: 8, color: '#999', fontSize: 12 }}>
                  分析了 {aiAnalysis.total_prs_analyzed} 个 PR · 焦点: {{
                    overview: '综合分析', risk: '风险分析', architecture: '架构影响', quality: '代码质量'
                  }[aiAnalysis.focus]} · {aiAnalysis.generated_at?.slice(0, 19)}
                </div>
                <div style={{ whiteSpace: 'pre-wrap' }}>{aiAnalysis.analysis}</div>
              </div>
            )}
          </Card>

          {/* Diff 分析汇总 */}
          {diffAnalysis && (diffAnalysis.total_added_lines > 0 || diffAnalysis.total_removed_lines > 0) && (
            <Card title="代码变更内容分析" style={{ marginBottom: 24 }} bodyStyle={{ padding: '12px 16px' }}>
              <Row gutter={[24, 12]}>
                <Col span={8}>
                  <Statistic title="Diff 新增行" value={diffAnalysis.total_added_lines} prefix="+" valueStyle={{ color: '#52c41a' }} />
                </Col>
                <Col span={8}>
                  <Statistic title="Diff 删除行" value={diffAnalysis.total_removed_lines} prefix="-" valueStyle={{ color: '#ff4d4f' }} />
                </Col>
                <Col span={8}>
                  <Statistic title="变更模式" value={Object.keys(diffAnalysis.pattern_counts || {}).length} valueStyle={{ color: '#722ed1' }} />
                </Col>
              </Row>
              <Row gutter={[24, 12]} style={{ marginTop: 12 }}>
                {Object.entries(diffAnalysis.symbols_by_type || {}).map(([type, syms]) => {
                  const labels = { function_added: '新增函数', function_removed: '删除函数', class_added: '新增类', class_removed: '删除类', decorator_added: '新增装饰器' }
                  if (!syms.length) return null
                  return (
                    <Col key={type} span={12} style={{ marginBottom: 8 }}>
                      <div style={{ fontWeight: 500, fontSize: 13, marginBottom: 4 }}>{labels[type] || type}</div>
                      <Space wrap size={4}>
                        {syms.map(s => <Tag key={s} style={{ fontSize: 11 }}>{s}</Tag>)}
                      </Space>
                    </Col>
                  )
                })}
              </Row>
              {diffAnalysis.added_imports?.length > 0 && (
                <div style={{ marginTop: 8 }}>
                  <span style={{ fontWeight: 500, fontSize: 13 }}>新增 import: </span>
                  <Space wrap size={4}>{diffAnalysis.added_imports.map(i => <Tag key={i} color="green" style={{ fontSize: 11 }}>{i}</Tag>)}</Space>
                </div>
              )}
              {diffAnalysis.removed_imports?.length > 0 && (
                <div style={{ marginTop: 8 }}>
                  <span style={{ fontWeight: 500, fontSize: 13 }}>删除 import: </span>
                  <Space wrap size={4}>{diffAnalysis.removed_imports.map(i => <Tag key={i} color="red" style={{ fontSize: 11 }}>{i}</Tag>)}</Space>
                </div>
              )}
              {Object.entries(diffAnalysis.pattern_counts || {}).length > 0 && (
                <div style={{ marginTop: 8 }}>
                  <span style={{ fontWeight: 500, fontSize: 13 }}>变更模式: </span>
                  <Space wrap size={4}>
                    {Object.entries(diffAnalysis.pattern_counts).map(([k, v]) => <Tag key={k} style={{ fontSize: 11 }}>{k}: {v}</Tag>)}
                  </Space>
                </div>
              )}
            </Card>
          )}

          {/* 重构模式 + API 变更 + 高 Churn + 高耦合 */}
          <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
            {(diffAnalysis.refactor_counts && Object.keys(diffAnalysis.refactor_counts).length > 0) && (
              <Col xs={24} lg={8}>
                <Card title="重构模式" bodyStyle={{ padding: '8px 12px' }}>
                  {Object.entries(diffAnalysis.refactor_counts).map(([k, v]) => (
                    <div key={k} style={{ display: 'flex', justifyContent: 'space-between', padding: '3px 0', borderBottom: '1px solid #f5f5f5', fontSize: 12 }}>
                      <span>{k}</span><Tag color="purple">{v}</Tag>
                    </div>
                  ))}
                </Card>
              </Col>
            )}
            {(diffAnalysis.api_changes && diffAnalysis.api_changes.length > 0) && (
              <Col xs={24} lg={8}>
                <Card title="API 变更" bodyStyle={{ padding: '8px 12px' }}>
                  {diffAnalysis.api_changes.slice(0, 8).map((ac, i) => (
                    <div key={i} style={{ padding: '3px 0', borderBottom: '1px solid #f5f5f5', fontSize: 12 }}>
                      <Tag color={ac.type === 'api_added' ? 'green' : ac.type === 'api_removed' ? 'red' : 'orange'} style={{ fontSize: 10 }}>{ac.type === 'api_added' ? '新增' : ac.type === 'api_removed' ? '删除' : '修改'}</Tag>
                      <span style={{ fontWeight: 500 }}>{ac.symbol}</span>
                    </div>
                  ))}
                </Card>
              </Col>
            )}
            {(data?.high_churn_files || []).length > 0 && (
              <Col xs={24} lg={8}>
                <Card title="高 Churn 文件 Top 10" bodyStyle={{ padding: '8px 12px' }}>
                  {(data.high_churn_files || []).slice(0, 10).map((f, i) => (
                    <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '3px 0', borderBottom: '1px solid #f5f5f5', fontSize: 11 }}>
                      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '70%' }}>{f.filename}</span>
                      <Tag color={f.pr_count >= 5 ? 'red' : f.pr_count >= 3 ? 'orange' : 'blue'}>{f.pr_count} PRs</Tag>
                    </div>
                  ))}
                </Card>
              </Col>
            )}
          </Row>

          {(data?.high_coupling || []).length > 0 && (
            <Card title="高耦合文件对（同变更频率）" style={{ marginBottom: 24 }} bodyStyle={{ padding: '8px 12px' }}>
              {(data.high_coupling || []).slice(0, 10).map((c, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', padding: '3px 0', borderBottom: '1px solid #f5f5f5', fontSize: 11 }}>
                  <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.files[0]}</span>
                  <span style={{ margin: '0 6px', color: '#999' }}>↔</span>
                  <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.files[1]}</span>
                  <Tag color={c.count >= 4 ? 'red' : 'orange'} style={{ marginLeft: 8 }}>{c.count}次</Tag>
                </div>
              ))}
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
                {Object.entries(filteredFileTypeCounts).map(([lang, count], i) => (
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
          {filteredPeriods.length > 0 && (
            <Card title="阶段性变更摘要" style={{ marginBottom: 24 }} bodyStyle={{ padding: '8px 16px' }}>
              {filteredPeriods.map((p, i) => {
                const da = p.diff_analysis || {}
                const hasDiff = da.total_added_lines > 0 || da.total_removed_lines > 0
                return (
                  <Card key={i} size="small" style={{ marginBottom: 8, background: '#fafafa' }} bodyStyle={{ padding: '8px 12px' }}>
                    <div style={{ fontSize: 13, whiteSpace: 'pre-wrap', lineHeight: 1.7 }}>{p.summary}</div>
                    <div style={{ marginTop: 6, display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'flex-start' }}>
                      {/* 分类标签 */}
                      <div>
                        {Object.entries(p.category_counts || {}).map(([cat, cnt]) => {
                          const cfg = CATEGORY_CONFIG[cat] || CATEGORY_CONFIG.other
                          return <Tag key={cat} color={cfg.color} style={{ fontSize: 11, margin: 2 }}>{cfg.label} {cnt}</Tag>
                        })}
                      </div>
                      {/* 文件类型 */}
                      {Object.keys(p.file_type_counts || {}).length > 0 && (
                        <div style={{ marginLeft: 8 }}>
                          <span style={{ fontSize: 11, color: '#999', marginRight: 4 }}>语言:</span>
                          {Object.entries(p.file_type_counts).slice(0, 5).map(([ft, cnt]) => (
                            <Tag key={ft} style={{ fontSize: 10, margin: 1 }}>{ft} {cnt}</Tag>
                          ))}
                        </div>
                      )}
                      {/* 贡献者 */}
                      {(p.top_contributors || []).length > 0 && (
                        <div style={{ marginLeft: 8 }}>
                          <span style={{ fontSize: 11, color: '#999', marginRight: 4 }}>贡献:</span>
                          {(p.top_contributors || []).slice(0, 5).map(([u, c]) => (
                            <Tag key={u} icon={<UserOutlined />} style={{ fontSize: 10, margin: 1 }}>{u}({c})</Tag>
                          ))}
                        </div>
                      )}
                    </div>
                    {/* 阶段级 diff 分析 */}
                    {hasDiff && (
                      <div style={{ marginTop: 6, padding: '6px 8px', background: '#f0f5ff', borderRadius: 4, fontSize: 12 }}>
                        <div style={{ fontWeight: 500, marginBottom: 4, color: '#1890ff' }}>代码变更内容</div>
                        <Row gutter={[16, 4]}>
                          <Col span={8}>
                            <span style={{ color: '#52c41a' }}>+{da.total_added_lines}</span>
                            <span style={{ color: '#999', margin: '0 4px' }}>/</span>
                            <span style={{ color: '#ff4d4f' }}>-{da.total_removed_lines}</span>
                            <span style={{ color: '#999', marginLeft: 4 }}>行</span>
                          </Col>
                          <Col span={16}>
                            {Object.entries(da.symbols_by_type || {}).map(([type, syms]) => {
                              const labels = { function_added: '+fn', function_removed: '-fn', class_added: '+cls', class_removed: '-cls', decorator_added: '+dec' }
                              if (!syms.length) return null
                              return <Tag key={type} color="blue" style={{ fontSize: 10, margin: 1 }}>{labels[type] || type}: {syms.length}</Tag>
                            })}
                            {Object.entries(da.pattern_counts || {}).slice(0, 3).map(([k, v]) => (
                              <Tag key={k} style={{ fontSize: 10, margin: 1 }}>{k}: {v}</Tag>
                            ))}
                          </Col>
                        </Row>
                      </div>
                    )}
                  </Card>
                )
              })}
            </Card>
          )}

          {/* 阶段趋势图表 */}
          {data.period_trends && data.period_trends.trend_points?.length > 1 && (
            <Card title="阶段趋势" style={{ marginBottom: 24 }} bodyStyle={{ padding: '12px 16px' }}>
              {data.period_trends.insight && (
                <div style={{ fontSize: 12, color: '#666', marginBottom: 12, padding: '6px 10px', background: '#f6f8fa', borderRadius: 4 }}>
                  {data.period_trends.insight}
                </div>
              )}
              <Row gutter={[16, 16]}>
                {/* PR 数趋势 */}
                <Col xs={24} lg={8}>
                  <div style={{ fontWeight: 500, fontSize: 13, marginBottom: 8 }}>PR 数量趋势</div>
                  <ResponsiveContainer width="100%" height={200}>
                    <LineChart data={data.period_trends.trend_points}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="period" tick={{ fontSize: 10 }} />
                      <YAxis tick={{ fontSize: 10 }} />
                      <RTooltip />
                      <Line type="monotone" dataKey="pr_count" stroke="#1890ff" strokeWidth={2} name="PR数" dot={{ r: 3 }} />
                    </LineChart>
                  </ResponsiveContainer>
                </Col>
                {/* 增删行趋势 */}
                <Col xs={24} lg={8}>
                  <div style={{ fontWeight: 500, fontSize: 13, marginBottom: 8 }}>增删行趋势</div>
                  <ResponsiveContainer width="100%" height={200}>
                    <LineChart data={data.period_trends.trend_points}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="period" tick={{ fontSize: 10 }} />
                      <YAxis tick={{ fontSize: 10 }} />
                      <RTooltip />
                      <Legend iconType="circle" wrapperStyle={{ fontSize: 11 }} />
                      <Line type="monotone" dataKey="additions" stroke="#52c41a" strokeWidth={2} name="新增" dot={{ r: 3 }} />
                      <Line type="monotone" dataKey="deletions" stroke="#ff4d4f" strokeWidth={2} name="删除" dot={{ r: 3 }} />
                    </LineChart>
                  </ResponsiveContainer>
                </Col>
                {/* 净变更趋势 */}
                <Col xs={24} lg={8}>
                  <div style={{ fontWeight: 500, fontSize: 13, marginBottom: 8 }}>净变更趋势</div>
                  <ResponsiveContainer width="100%" height={200}>
                    <LineChart data={data.period_trends.trend_points}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="period" tick={{ fontSize: 10 }} />
                      <YAxis tick={{ fontSize: 10 }} />
                      <RTooltip />
                      <Line type="monotone" dataKey="net_change" stroke="#722ed1" strokeWidth={2} name="净变更" dot={{ r: 3 }} />
                    </LineChart>
                  </ResponsiveContainer>
                </Col>
              </Row>
              {/* 环比变化率 */}
              {data.period_trends.trend_points.filter(p => p.pr_count_change !== null).length > 0 && (
                <div style={{ marginTop: 16 }}>
                  <div style={{ fontWeight: 500, fontSize: 13, marginBottom: 8 }}>环比变化率</div>
                  <ResponsiveContainer width="100%" height={200}>
                    <LineChart data={data.period_trends.trend_points}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="period" tick={{ fontSize: 10 }} />
                      <YAxis tick={{ fontSize: 10 }} unit="%" />
                      <RTooltip formatter={v => v !== null ? `${v}%` : '-'} />
                      <Legend iconType="circle" wrapperStyle={{ fontSize: 11 }} />
                      <Line type="monotone" dataKey="pr_count_change" stroke="#1890ff" strokeWidth={2} name="PR数" dot={{ r: 3 }} connectNulls />
                      <Line type="monotone" dataKey="additions_change" stroke="#52c41a" strokeWidth={2} name="新增行" dot={{ r: 3 }} connectNulls />
                      <Line type="monotone" dataKey="deletions_change" stroke="#ff4d4f" strokeWidth={2} name="删除行" dot={{ r: 3 }} connectNulls />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}
            </Card>
          )}

          {/* PR 列表 */}
          <Card title="变更 PR 列表">
            <Table
              size="small"
              dataSource={filteredPrs.map((pr, i) => ({ key: i, ...pr }))}
              columns={prColumns}
              pagination={{ pageSize: 20, showTotal: t => `共 ${t} 个 PR` }}
              scroll={{ x: 1200 }}
            />
          </Card>
        </>
      )}
    </div>
  )
}
