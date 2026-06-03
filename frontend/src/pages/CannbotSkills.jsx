import { useState, useEffect, useCallback, useRef } from 'react'
import {
  Card, Tag, Row, Col, Button, Spin, Empty, Drawer, Typography, Space,
  Input, message, Tooltip, Statistic, Progress, Tabs, Segmented, Timeline,
  Select, Dropdown,
} from 'antd'
import {
  SyncOutlined, DownloadOutlined, FolderOutlined, FileTextOutlined,
  SearchOutlined, RobotOutlined, CodeOutlined, ThunderboltOutlined,
  InfoCircleOutlined,
  CloudOutlined, AppstoreOutlined, DashboardOutlined, AuditOutlined,
  ToolOutlined, RocketOutlined, CheckCircleOutlined, ClockCircleOutlined,
  StarOutlined, ExperimentOutlined, FilePdfOutlined, FileMarkdownOutlined,
  DownOutlined, DeleteOutlined, WarningOutlined, SafetyCertificateOutlined,
} from '@ant-design/icons'
import {
  PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip as RTooltip,
  ResponsiveContainer,
} from 'recharts'
import {
  getCannbotStatus, getCannbotSkills, getCannbotSkillDetail,
  getCannbotSkillFile, cloneCannbotSkills, updateCannbotSkills,
  getCannbotStats, getCannbotEvaluation, getCannbotChangelog,
  getCannbotScenarios, installCannbotScenario, checkCannbotInstall,
  verifyCannbotInstall, uninstallCannbotScenario,
  getWorkflowDefinitions, simulateWorkflowStream, exportWorkflowReport,
  getWorkflowSimulations, getWorkflowSimulation,
} from '../api'
import OpsDevSession from './OpsDevSession'
import BreakpointTimeline from '../components/BreakpointTimeline'
import SkillHeatmapChart from '../components/SkillHeatmapChart'

const { Title, Text, Paragraph } = Typography
const { Search } = Input

const GRADE_COLORS = { A: '#52c41a', B: '#1890ff', C: '#faad14', D: '#fa541c', F: '#ff4d4f' }
const CATEGORY_COLORS = { ops: '#1677ff', model: '#52c41a', infra: '#fa8c16', graph: '#722ed1', 'ops-lab': '#13c2c2' }
const CATEGORY_LABELS = { ops: '算子开发', model: '模型推理', infra: '基础设施', graph: '计算图', 'ops-lab': '实验算子' }
const DIMENSION_LABELS = {
  docCompleteness: '文档完整度',
  contentQuality: '内容质量',
  references: '参考资料',
  activity: '活跃度',
  capability: '实际能力',
}

const GradeTag = ({ grade }) => (
  <Tag style={{ color: '#fff', fontWeight: 700, background: GRADE_COLORS[grade], border: 'none', minWidth: 28, textAlign: 'center' }}>
    {grade}
  </Tag>
)

export default function CannbotSkills() {
  const [status, setStatus] = useState(null)
  const [stats, setStats] = useState(null)
  const [evaluation, setEvaluation] = useState(null)
  const [changelog, setChangelog] = useState(null)
  const [scenarios, setScenarios] = useState([])
  const [loading, setLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState('')
  const [activeTab, setActiveTab] = useState('overview')

  // 详情 Drawer
  const [selectedSkill, setSelectedSkill] = useState(null)
  const [detail, setDetail] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [fileContent, setFileContent] = useState(null)
  const [drawerOpen, setDrawerOpen] = useState(false)

  // 筛选
  const [searchText, setSearchText] = useState('')
  const [filterCategory, setFilterCategory] = useState('all')
  const [filterGrade, setFilterGrade] = useState('all')
  const [selectedTool, setSelectedTool] = useState('claude')

  const loadAll = useCallback(async () => {
    setLoading(true)
    try {
      const [statusRes, statsRes, evalRes, logRes, sceneRes] = await Promise.all([
        getCannbotStatus(),
        getCannbotStats().catch(() => ({ data: null })),
        getCannbotEvaluation().catch(() => ({ data: null })),
        getCannbotChangelog().catch(() => ({ data: null })),
        getCannbotScenarios().catch(() => ({ data: { scenarios: [] } })),
      ])
      setStatus(statusRes.data)
      if (statsRes.data) setStats(statsRes.data)
      if (evalRes.data) setEvaluation(evalRes.data)
      if (logRes.data) setChangelog(logRes.data)
      if (sceneRes.data) setScenarios(sceneRes.data.scenarios || [])
    } catch (e) {
      message.error(e._friendlyMsg || '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadAll() }, [loadAll])

  const handleClone = async () => {
    setActionLoading('clone')
    try {
      const res = await cloneCannbotSkills()
      message.success(res.data.status === 'already_exists' ? '仓库已存在' : 'Clone 成功')
      loadAll()
    } catch (e) {
      message.error(e.response?.data?.detail || 'Clone 失败')
    } finally {
      setActionLoading('')
    }
  }

  const handleUpdate = async () => {
    setActionLoading('update')
    try {
      await updateCannbotSkills()
      message.success('更新成功')
      loadAll()
    } catch (e) {
      message.error(e.response?.data?.detail || '更新失败')
    } finally {
      setActionLoading('')
    }
  }

  const openDetail = async (skill) => {
    setSelectedSkill(skill)
    setDrawerOpen(true)
    setDetailLoading(true)
    setDetail(null)
    setFileContent(null)
    try {
      const res = await getCannbotSkillDetail(skill.id)
      setDetail(res.data)
    } catch {
      message.error('加载详情失败')
    } finally {
      setDetailLoading(false)
    }
  }

  const openFile = async (filePath) => {
    try {
      const res = await getCannbotSkillFile(filePath)
      setFileContent({ path: res.data.path, content: res.data.content })
    } catch {
      message.error('文件读取失败')
    }
  }

  // 筛选后的评估列表
  const filteredEval = (evaluation?.skills || []).filter(s => {
    if (searchText) {
      const q = searchText.toLowerCase()
      if (!s.name.toLowerCase().includes(q) && !s.description?.toLowerCase().includes(q)) return false
    }
    if (filterCategory !== 'all' && s.category !== filterCategory) return false
    if (filterGrade !== 'all' && s.grade !== filterGrade) return false
    return true
  })

  // 未 clone 时显示
  if (!status?.cloned && !loading) {
    return (
      <div style={{ padding: 4 }}>
        <Empty description="请先 Clone 仓库" style={{ marginTop: 60 }}>
          <Button type="primary" size="large" icon={<DownloadOutlined />} onClick={handleClone}>
            Clone cannbot-skills 仓库
          </Button>
        </Empty>
      </div>
    )
  }

  return (
    <div style={{ padding: 4 }}>
      {/* 头部状态栏 */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Row justify="space-between" align="middle">
          <Col>
            <Space size="large">
              <Space>
                <RobotOutlined style={{ fontSize: 20, color: '#1677ff' }} />
                <Title level={5} style={{ margin: 0 }}>CANNBot Skills</Title>
              </Space>
              {status?.cloned && (
                <>
                  <Tag color="green">已 Clone</Tag>
                  <Text type="secondary">{status.branch} @ {status.commit}</Text>
                </>
              )}
            </Space>
          </Col>
          <Col>
            <Space>
              <Button icon={<SyncOutlined />} loading={actionLoading === 'update'} onClick={handleUpdate}>
                更新
              </Button>
              <Button icon={<SyncOutlined spin={loading} onClick={loadAll} />} loading={loading}>
                刷新数据
              </Button>
            </Space>
          </Col>
        </Row>
      </Card>

      {/* 三个 Tab */}
      <Tabs activeKey={activeTab} onChange={setActiveTab} items={[
        {
          key: 'overview',
          label: <span><DashboardOutlined /> 概览</span>,
          children: <OverviewTab stats={stats} evaluation={evaluation} changelog={changelog} />,
        },
        {
          key: 'evaluation',
          label: <span><AuditOutlined /> 技能评估</span>,
          children: (
            <EvaluationTab
              evaluation={evaluation}
              filtered={filteredEval}
              searchText={searchText}
              setSearchText={setSearchText}
              filterCategory={filterCategory}
              setFilterCategory={setFilterCategory}
              filterGrade={filterGrade}
              setFilterGrade={setFilterGrade}
              onOpenDetail={openDetail}
            />
          ),
        },
        {
          key: 'install',
          label: <span><RocketOutlined /> 场景安装</span>,
          children: (
            <InstallTab scenarios={scenarios} selectedTool={selectedTool} setSelectedTool={setSelectedTool} />
          ),
        },
        {
          key: 'test',
          label: <span><ThunderboltOutlined /> Skill 测试</span>,
          children: <TestTab scenarios={scenarios} />,
        },
        {
          key: 'workflow-sim',
          label: <span><ExperimentOutlined /> 工作流仿真</span>,
          children: <WorkflowSimTab />,
        },
        {
          key: 'ops-dev',
          label: <span><CodeOutlined /> 算子开发 V2</span>,
          children: <OpsDevSession />,
        },
      ]} />

      {/* 技能详情 Drawer */}
      <Drawer
        title={
          <Space>
            {selectedSkill && <GradeTag grade={selectedSkill.grade} />}
            <span>{selectedSkill?.name || '技能详情'}</span>
            {selectedSkill && (
              <Tag color={CATEGORY_COLORS[selectedSkill.category]}>
                {CATEGORY_LABELS[selectedSkill.category] || selectedSkill.category}
              </Tag>
            )}
          </Space>
        }
        open={drawerOpen}
        onClose={() => { setDrawerOpen(false); setFileContent(null) }}
        width={640}
      >
        <Spin spinning={detailLoading}>
          {selectedSkill && evaluation && (
            <div style={{ marginBottom: 16 }}>
              <Text strong>质量评分</Text>
              <div style={{ marginTop: 8 }}>
                {Object.entries(selectedSkill.dimensions || {}).map(([key, dim]) => (
                  <Row key={key} align="middle" gutter={8} style={{ marginBottom: 4 }}>
                    <Col span={5}><Text type="secondary" style={{ fontSize: 12 }}>{DIMENSION_LABELS[key]}</Text></Col>
                    <Col span={14}>
                      <Progress percent={dim.score} size="small" strokeColor={dim.score >= 75 ? '#52c41a' : dim.score >= 60 ? '#faad14' : '#ff4d4f'} />
                    </Col>
                    <Col span={5}><Text style={{ fontSize: 12 }}>{dim.score}分</Text></Col>
                  </Row>
                ))}
              </div>
              <div style={{ marginTop: 4 }}>
                {Object.entries(selectedSkill.dimensions || {}).map(([key, dim]) => (
                  <Text key={key} type="secondary" style={{ fontSize: 11, display: 'block' }}>
                    {DIMENSION_LABELS[key]}：{dim.detail}
                  </Text>
                ))}
              </div>
            </div>
          )}
          {detail && (
            <div>
              {detail.files && detail.files.length > 0 && (
                <div style={{ marginBottom: 12 }}>
                  <Text strong>文件列表</Text>
                  <div style={{ marginTop: 6, display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                    {detail.files.map(f => (
                      <Tag
                        key={f}
                        icon={f.endsWith('.md') ? <FileTextOutlined /> : <FolderOutlined />}
                        style={{ cursor: 'pointer', fontSize: 11 }}
                        color={fileContent?.path === f ? 'blue' : 'default'}
                        onClick={() => openFile(f)}
                      >
                        {f}
                      </Tag>
                    ))}
                  </div>
                </div>
              )}
              <div style={{
                background: '#f6f8fa', borderRadius: 8, padding: 14,
                maxHeight: 'calc(100vh - 380px)', overflow: 'auto',
                fontSize: 12, lineHeight: 1.6,
              }}>
                {(fileContent?.content || detail.content) ? (
                  <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', margin: 0, fontFamily: 'inherit' }}>
                    {fileContent?.content || detail.content}
                  </pre>
                ) : (
                  <Text type="secondary">暂无文档内容</Text>
                )}
              </div>
            </div>
          )}
        </Spin>
      </Drawer>
    </div>
  )
}

// ==================== Tab 1: 概览 ====================
function OverviewTab({ stats, evaluation, changelog }) {
  if (!stats) return <Empty description="暂无统计数据" />

  const avgScore = evaluation?.summary?.avgScore || 0
  const avgGrade = avgScore >= 90 ? 'A' : avgScore >= 75 ? 'B' : avgScore >= 60 ? 'C' : avgScore >= 40 ? 'D' : 'F'

  // 等级分布饼图数据
  const gradeDist = evaluation?.summary?.gradeDistribution || {}
  const pieData = Object.entries(gradeDist).filter(([, v]) => v > 0).map(([name, value]) => ({ name, value }))

  // 分类分布柱状图数据
  const catData = Object.entries(stats.categories || {}).map(([key, count]) => ({
    name: CATEGORY_LABELS[key] || key,
    count,
    fill: CATEGORY_COLORS[key] || '#999',
  }))

  // Timeline 数据（取最近 10 条）
  const timelineItems = (changelog?.entries || []).slice(0, 10).map(entry => ({
    children: (
      <div>
        <Text strong style={{ fontSize: 12 }}>{entry.date}</Text>
        <div>
          {entry.features.map((f, i) => <Tag key={i} color="green" style={{ fontSize: 11, margin: 2 }}>{f}</Tag>)}
          {entry.enhancements.map((f, i) => <Tag key={i} color="blue" style={{ fontSize: 11, margin: 2 }}>{f}</Tag>)}
          {entry.fixes.map((f, i) => <Tag key={i} color="orange" style={{ fontSize: 11, margin: 2 }}>{f}</Tag>)}
        </div>
      </div>
    ),
  }))

  return (
    <div>
      {/* 说明 */}
      <Tooltip color="rgba(0,0,0,0.88)" overlayStyle={{ maxWidth: 480 }} title={
        <div style={{ maxHeight: '60vh', overflow: 'auto', paddingRight: 4 }}>
          <b>概览页数据来源：</b><br />
          • 技能总数：遍历 ops/model/infra/graph/ops-lab 五个目录，统计含 SKILL.md 或 README.md 的子目录数量<br />
          • 插件/场景数量：遍历 plugins-official/ 和 plugins-community/ 目录计数<br />
          • Agent 数量：统计各插件内 agents/ 子目录的 .md 文件数<br />
          • 总提交数：执行 git rev-list --count HEAD<br />
          • 整体评分：取所有技能五维评估分的均值，换算为 A-F 等级<br />
          • 等级分布饼图：统计所有技能中 A/B/C/D/F 各有多少个<br />
          • 分类柱状图：按 ops/model/infra/graph/ops-lab 统计技能数量<br />
          • 更新 Timeline：正则解析 CHANGELOG.md，提取日期和分类条目<br />
          首次加载可能需 5-10 秒（需遍历 78 个 Skill 目录 + git log 分析）。
        </div>
      }>
        <Tag icon={<InfoCircleOutlined />} color="blue" style={{ marginBottom: 12, cursor: 'help' }}>数据来源说明</Tag>
      </Tooltip>
      {/* 统计卡片 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col xs={12} sm={6}>
          <Card size="small" hoverable>
            <Statistic title="技能总数" value={stats.totalSkills} prefix={<CodeOutlined />} valueStyle={{ color: '#1677ff' }} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small" hoverable>
            <Statistic title="插件/场景" value={stats.totalPlugins} prefix={<AppstoreOutlined />} valueStyle={{ color: '#722ed1' }} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small" hoverable>
            <Statistic title="Agent 数量" value={stats.totalAgents} prefix={<RobotOutlined />} valueStyle={{ color: '#52c41a' }} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small" hoverable>
            <Statistic title="总提交" value={stats.commitCount} prefix={<ClockCircleOutlined />} suffix={
              <Text type="secondary" style={{ fontSize: 12 }}> ({stats.firstCommit} ~ {stats.latestCommit})</Text>
            } valueStyle={{ color: '#fa8c16', fontSize: 22 }} />
          </Card>
        </Col>
      </Row>

      {/* 整体评分 + 图表 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        {/* 整体评分 */}
        <Col xs={24} sm={8}>
          <Card size="small" title="整体质量评分" style={{ textAlign: 'center' }}>
            <Progress
              type="circle"
              percent={Math.round(avgScore)}
              size={120}
              strokeColor={GRADE_COLORS[avgGrade]}
              format={() => <span style={{ fontSize: 28, fontWeight: 700, color: GRADE_COLORS[avgGrade] }}>{avgGrade}</span>}
            />
            <div style={{ marginTop: 8 }}>
              <Text type="secondary">平均 {avgScore} 分 / 共 {evaluation?.summary?.totalSkills || 0} 个技能</Text>
            </div>
          </Card>
        </Col>
        {/* 等级分布 */}
        <Col xs={24} sm={8}>
          <Card size="small" title="质量等级分布">
            {pieData.length > 0 ? (
              <ResponsiveContainer width="100%" height={160}>
                <PieChart>
                  <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={60} innerRadius={35} label={({ name, value }) => `${name}: ${value}`}>
                    {pieData.map(d => <Cell key={d.name} fill={GRADE_COLORS[d.name]} />)}
                  </Pie>
                  <RTooltip />
                </PieChart>
              </ResponsiveContainer>
            ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />}
          </Card>
        </Col>
        {/* 分类分布 */}
        <Col xs={24} sm={8}>
          <Card size="small" title="分类技能数">
            <ResponsiveContainer width="100%" height={160}>
              <BarChart data={catData} layout="vertical">
                <XAxis type="number" hide />
                <YAxis type="category" dataKey="name" width={70} tick={{ fontSize: 11 }} />
                <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                  {catData.map(d => <Cell key={d.name} fill={d.fill} />)}
                </Bar>
                <RTooltip />
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </Col>
      </Row>

      {/* 最近更新 */}
      {timelineItems.length > 0 && (
        <Card size="small" title={
          <Space>
            <span>最近更新</span>
            {changelog?.commitCount30d && <Tag>{changelog.commitCount30d} commits / 30天</Tag>}
          </Space>
        }>
          <Timeline items={timelineItems} style={{ maxHeight: 300, overflow: 'auto', paddingTop: 4 }} />
        </Card>
      )}
    </div>
  )
}

// ==================== Tab 2: 技能评估列表 ====================
function EvaluationTab({ evaluation, filtered, searchText, setSearchText, filterCategory, setFilterCategory, filterGrade, setFilterGrade, onOpenDetail }) {
  if (!evaluation) return <Empty description="暂无评估数据" />

  const categories = [{ label: '全部', value: 'all' }, ...Object.entries(CATEGORY_LABELS).map(([value, label]) => ({ label, value }))]
  const grades = [{ label: '全部', value: 'all' }, ...['A', 'B', 'C', 'D', 'F'].map(g => ({ label: `${g} (${evaluation.summary.gradeDistribution[g] || 0})`, value: g }))]

  return (
    <div>
      {/* 说明 */}
      <Tooltip color="rgba(0,0,0,0.88)" overlayStyle={{ maxWidth: 520 }} title={
        <div style={{ maxHeight: '60vh', overflow: 'auto', paddingRight: 4 }}>
          <b>五维评分规则</b><br />
          总分 = 文档×20% + 内容×20% + 参考×15% + 活跃×15% + 能力×30%<br /><br />
          <b>1. 文档完整度 (20%)</b><br />
          SKILL.md 存在(+40) → frontmatter 有 name(+20) → 有 description(+20) → description 超 20 字(+10) → 不超 1024 字(+10)<br /><br />
          <b>2. 内容质量 (20%)</b><br />
          基础分 50 → 命中触发关键词（Ascend/算子/Kernel/Tiling/调试/debug/测试/UT/性能/精度/NPU/API 等 24 词）每词 +5，最多 +30 → 含代码块(+10) → 含编号步骤(+10)<br /><br />
          <b>3. 参考资料 (15%)</b><br />
          无 references=0 → 空目录=10 → 有文件: 40+文件数×12 → 5 个文件以上=100<br /><br />
          <b>4. 活跃度 (15%)</b><br />
          git log 获取该目录最后 commit 距今天数：7天内=100 → 14天=80 → 30天=60 → 60天=40 → 更久=20<br /><br />
          <b>5. 实际能力 (30%)</b><br />
          scripts/ 有可执行文件(+30) → 有 workflows/scenarios/templates(+20) → description 含触发条件短语如"当用户/适用场景/触发条件"(+20) → 代码块≥6个(+15)/≥2个(+8) → 编号步骤≥5个(+15)/≥2个(+8)<br /><br />
          等级：≥90=A(绿) ≥75=B(蓝) ≥60=C(黄) ≥40=D(橙) &lt;40=F(红)<br /><br />
          点击技能卡片可查看各维度评分细节、SKILL.md 全文、文件列表。
        </div>
      }>
        <Tag icon={<InfoCircleOutlined />} color="blue" style={{ marginBottom: 12, cursor: 'help' }}>评分规则说明</Tag>
      </Tooltip>
      {/* 筛选栏 */}
      <Row gutter={12} style={{ marginBottom: 16 }} align="middle">
        <Col>
          <Search
            placeholder="搜索技能..."
            allowClear
            value={searchText}
            onChange={e => setSearchText(e.target.value)}
            style={{ width: 220 }}
          />
        </Col>
        <Col>
          <Space>
            <Text type="secondary" style={{ fontSize: 12 }}>分类：</Text>
            <Segmented options={categories} value={filterCategory} onChange={setFilterCategory} size="small" />
          </Space>
        </Col>
        <Col>
          <Space>
            <Text type="secondary" style={{ fontSize: 12 }}>等级：</Text>
            <Segmented options={grades} value={filterGrade} onChange={setFilterGrade} size="small" />
          </Space>
        </Col>
        <Col>
          <Text type="secondary" style={{ fontSize: 12 }}>共 {filtered.length} 个</Text>
        </Col>
      </Row>

      {/* 技能卡片列表 */}
      <Row gutter={[12, 12]}>
        {filtered.map(skill => (
          <Col key={skill.id} xs={24} sm={12} md={8}>
            <Card
              hoverable
              size="small"
              onClick={() => onOpenDetail(skill)}
              style={{ borderLeft: `3px solid ${GRADE_COLORS[skill.grade]}` }}
            >
              <Row justify="space-between" align="middle">
                <Col flex="auto">
                  <Tooltip title={skill.name}>
                    <Text strong ellipsis style={{ fontSize: 13, maxWidth: '80%', display: 'inline-block' }}>{skill.name}</Text>
                  </Tooltip>
                </Col>
                <Col>
                  <Space size={4}>
                    <GradeTag grade={skill.grade} />
                    <Text strong style={{ color: GRADE_COLORS[skill.grade], fontSize: 13 }}>{skill.score}</Text>
                  </Space>
                </Col>
              </Row>
              <div style={{ marginTop: 6 }}>
                {Object.entries(skill.dimensions || {}).map(([key, dim]) => (
                  <Row key={key} align="middle" gutter={4} style={{ marginBottom: 2 }}>
                    <Col span={6}><Text type="secondary" style={{ fontSize: 10 }}>{DIMENSION_LABELS[key]}</Text></Col>
                    <Col span={18}>
                      <Progress
                        percent={dim.score}
                        size="small"
                        showInfo={false}
                        strokeColor={dim.score >= 75 ? '#52c41a' : dim.score >= 60 ? '#faad14' : '#ff4d4f'}
                      />
                    </Col>
                  </Row>
                ))}
              </div>
              <Row justify="space-between" style={{ marginTop: 4 }}>
                <Col>
                  <Tag color={CATEGORY_COLORS[skill.category]} style={{ fontSize: 10 }}>
                    {CATEGORY_LABELS[skill.category] || skill.category}
                  </Tag>
                </Col>
                <Col>
                  <Space size={8}>
                    <Text type="secondary" style={{ fontSize: 10 }}>{skill.fileCount} 文件</Text>
                    <Text type="secondary" style={{ fontSize: 10 }}>{skill.totalSize}</Text>
                    {skill.lastUpdated && <Text type="secondary" style={{ fontSize: 10 }}>{skill.lastUpdated}</Text>}
                  </Space>
                </Col>
              </Row>
            </Card>
          </Col>
        ))}
      </Row>
      {filtered.length === 0 && <Empty description="没有匹配的技能" />}
    </div>
  )
}

// ==================== Tab 3: 场景安装 ====================
function InstallTab({ scenarios, selectedTool, setSelectedTool }) {
  const toolNames = { claude: 'Claude Code', cursor: 'Cursor', trae: 'Trae', opencode: 'OpenCode' }

  const getInstallCmd = (scenario) => {
    if (!scenario.installCmd) return '暂无安装命令'
    return `cd external/cannbot-skills/${scenario.path}\n${scenario.installCmd.replace('<tool>', selectedTool)}`
  }

  return (
    <div>
      {/* 说明 */}
      <Tooltip color="rgba(0,0,0,0.88)" overlayStyle={{ maxWidth: 480 }} title={
        <div style={{ maxHeight: '60vh', overflow: 'auto', paddingRight: 4 }}>
          <b>场景安装逻辑：</b><br />
          • 扫描 plugins-official/ 和 plugins-community/ 目录，列出所有可用安装场景<br />
          • 每个场景的名称和描述从 AGENTS.md 的 frontmatter description 字段提取<br />
          • Agent 列表来自场景内 agents/ 子目录的 .md 文件名<br />
          • 安装命令模板来自 init.sh 或 install.sh 文件名检测<br />
          • 选择 AI 工具后，命令中的 &lt;tool&gt; 自动替换为 claude/cursor/trae/opencode<br />
          • 点击代码块右侧的复制按钮即可复制完整命令到终端执行<br /><br />
          <b>安装后效果：</b>安装脚本会在项目目录下创建软链接到 .claude/skills/（或对应工具的配置目录），AI 工具启动后自动加载这些技能。
        </div>
      }>
        <Tag icon={<InfoCircleOutlined />} color="blue" style={{ marginBottom: 12, cursor: 'help' }}>安装逻辑说明</Tag>
      </Tooltip>
      {/* 工具选择 */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space>
          <Text strong>选择 AI 工具：</Text>
          <Segmented
            options={Object.entries(toolNames).map(([value, label]) => ({ value, label }))}
            value={selectedTool}
            onChange={setSelectedTool}
          />
        </Space>
      </Card>

      {/* 场景列表 */}
      <Row gutter={[16, 16]}>
        {scenarios.map(s => (
          <Col key={s.id} xs={24} sm={12} md={8}>
            <Card
              size="small"
              title={
                <Space>
                  <Tag color={s.type === 'official' ? 'blue' : 'default'}>
                    {s.type === 'official' ? '官方' : '社区'}
                  </Tag>
                  <Text strong style={{ fontSize: 13 }}>{s.name}</Text>
                </Space>
              }
            >
              <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 8, minHeight: 32 }}>
                {s.description || '暂无描述'}
              </Paragraph>

              {s.agents.length > 0 && (
                <div style={{ marginBottom: 8 }}>
                  <Text type="secondary" style={{ fontSize: 11 }}>包含 Agent：</Text>
                  <div style={{ marginTop: 2 }}>
                    {s.agents.slice(0, 4).map(a => (
                      <Tag key={a} style={{ fontSize: 10, margin: 1 }}>{a}</Tag>
                    ))}
                    {s.agents.length > 4 && <Tag style={{ fontSize: 10 }}>+{s.agents.length - 4}</Tag>}
                  </div>
                </div>
              )}

              <Row justify="space-between" style={{ marginBottom: 8 }}>
                <Text type="secondary" style={{ fontSize: 11 }}>{s.fileCount} 文件 / {s.size}</Text>
              </Row>

              {s.hasInit ? (
                <Paragraph
                  copyable
                  style={{ marginBottom: 0, fontSize: 11 }}
                >
                  <pre style={{
                    background: '#1e1e1e', color: '#d4d4d4', padding: '8px 10px',
                    borderRadius: 4, margin: 0, fontSize: 11, whiteSpace: 'pre-wrap',
                  }}>
                    {getInstallCmd(s)}
                  </pre>
                </Paragraph>
              ) : (
                <Text type="secondary" style={{ fontSize: 11 }}>请参考 Plugin 市场安装</Text>
              )}
            </Card>
          </Col>
        ))}
      </Row>
      {scenarios.length === 0 && <Empty description="暂无安装场景" />}
    </div>
  )
}

// ==================== Tab 4: Skill 测试（安装 + 启动） ====================

// 场景对应的示例提示词
const SCENARIO_EXAMPLES = {
  'ops-direct-invoke': '帮我开发一个 abs 算子，支持 float16 数据类型，shape 主要是 [1,128]、[4,2048]、[32,4096]',
  'ops-registry-invoke': '帮我开发一个 Add 算子，支持 float16 和 float32，注册到 CANN 算子库',
  'ops-code-reviewer': '帮我 review 一下 ascendc_add_kernel.cpp 的代码质量',
  'catlass-op-generator': '帮我用 catlass 框架生成一个 matmul 算子',
  'triton-op-generator': '帮我写一个 Triton 算子实现 softmax',
  'model-infer-optimize': '帮我优化模型推理性能，分析 ResNet50 在昇腾 NPU 上的瓶颈',
  'pypto-op-orchestrator': '帮我编排一个 PyPTO 算子流水线，包括数据预处理和后处理',
  'torch-compile': '帮我用 torch.compile 在昇腾 NPU 上加速模型训练',
}
const DEFAULT_EXAMPLE = '帮我开发一个 Ascend C 算子'

function TestTab({ scenarios }) {
  const [selectedTool, setSelectedTool] = useState('claude')
  const [selectedScenario, setSelectedScenario] = useState('')
  const [installLevel, setInstallLevel] = useState('project')
  const [installing, setInstalling] = useState(false)
  const [installResult, setInstallResult] = useState(null)
  const [checkResult, setCheckResult] = useState(null)
  const [checking, setChecking] = useState(false)
  const [currentStep, setCurrentStep] = useState(0) // 0=选择, 1=安装中, 2=成功, 3=失败
  const [uninstalling, setUninstalling] = useState(false)
  const [verifyResult, setVerifyResult] = useState(null)
  const [verifying, setVerifying] = useState(false)
  const justUninstalled = useRef(false)

  const toolLabels = { claude: 'Claude Code', cursor: 'Cursor', trae: 'Trae', opencode: 'OpenCode' }
  const toolInstallHints = {
    claude: '在终端输入 claude 启动 CLI（需要已安装 Claude Code）',
    cursor: '打开 Cursor IDE，打开项目文件夹，Agent 会自动加载',
    trae: '打开 Trae IDE，打开项目文件夹，Agent 会自动加载',
    opencode: '在终端输入 opencode 启动（需要已安装 OpenCode）',
  }

  const currentScenarioObj = scenarios.find(s => s.path === selectedScenario)
  const examplePrompt = SCENARIO_EXAMPLES[currentScenarioObj?.id] || DEFAULT_EXAMPLE

  const handleInstall = async () => {
    if (!selectedScenario) { message.warning('请选择场景'); return }
    setCurrentStep(1)
    setInstalling(true)
    setInstallResult(null)
    try {
      const res = await installCannbotScenario({
        scenario_path: selectedScenario,
        tool: selectedTool,
        level: installLevel,
      })
      setInstallResult(res.data)
      setCurrentStep(res.data.success ? 2 : 3)
      if (res.data.success) message.success('安装成功')
      else message.error('安装失败')
      doCheck()
    } catch (e) {
      setInstallResult({ success: false, errors: e.response?.data?.detail || '安装失败', output: '' })
      setCurrentStep(3)
    } finally {
      setInstalling(false)
    }
  }

  const doCheck = async () => {
    if (!selectedScenario) return
    setChecking(true)
    try {
      const res = await checkCannbotInstall(selectedScenario)
      setCheckResult(res.data)
    } catch { message.error('检测失败') }
    finally { setChecking(false) }
  }

  // 选择场景时自动检测
  useEffect(() => { if (selectedScenario) doCheck() }, [selectedScenario])

  // 一致性校验
  const doVerify = async () => {
    if (!selectedScenario) return
    setVerifying(true)
    try {
      const res = await verifyCannbotInstall(selectedScenario, selectedTool)
      setVerifyResult(res.data)
    } catch { message.error('校验失败') }
    finally { setVerifying(false) }
  }

  // 卸载
  const handleUninstall = async () => {
    if (!selectedScenario) return
    setUninstalling(true)
    try {
      const res = await uninstallCannbotScenario({
        scenario_path: selectedScenario,
        tool: selectedTool,
      })
      if (res.data.success) {
        message.success(`已卸载: ${res.data.removed_skills.length} skills, ${res.data.removed_agents.length} agents`)
        setVerifyResult(null)
        setInstallResult(null)
        setCheckResult(null)
        setCurrentStep(0)
        justUninstalled.current = true
        doCheck()
      } else {
        message.warning(`卸载完成但有错误: ${res.data.errors?.join('; ')}`)
        setCheckResult(null)
        setInstallResult(null)
        setCurrentStep(0)
        justUninstalled.current = true
        doCheck()
      }
    } catch (e) {
      message.error(e.response?.data?.detail || '卸载失败')
    } finally { setUninstalling(false) }
  }

  // 检测完成后判断是否自动跳步
  useEffect(() => {
    if (!checkResult || currentStep !== 0 || !selectedScenario || justUninstalled.current) {
      justUninstalled.current = false
      return
    }
    const toolInfo = checkResult.tools?.[selectedTool]
    if (toolInfo?.installed) {
      setCurrentStep(2)
      if (!installResult) {
        // 优先匹配当前场景的安装产物（通过 manifest.team 与 scenario 目录名比对）
        const scenarioId = selectedScenario.split('/').pop()
        const allArts = [...(toolInfo.project || []), ...(toolInfo.global || [])]
        const existing = allArts.filter(a => a.exists && (a.skills?.length > 0 || a.agents?.length > 0))
        // 优先找 manifest.team 匹配当前场景的
        let realArt = existing.find(a => a.manifest?.team === scenarioId)
        // 其次取第一个
        if (!realArt) realArt = existing[0]
        setInstallResult({
          success: true,
          installDir: realArt?.configDir || '',
          artifacts: realArt || { skills: [], agents: [], configFiles: [] },
        })
      }
    }
  }, [checkResult, selectedScenario, selectedTool])

  const renderArtifacts = (artifacts, levelLabel) => {
    if (!artifacts || artifacts.length === 0) return null
    return artifacts.filter(a => a.exists).map((art, i) => (
      <div key={i} style={{ marginTop: 6, padding: '8px 10px', background: '#fafafa', borderRadius: 6 }}>
        <Space size={4} style={{ marginBottom: 4 }}>
          <Tag color={levelLabel === '项目级' ? 'blue' : 'purple'} style={{ fontSize: 10 }}>{levelLabel}</Tag>
          <Text type="secondary" style={{ fontSize: 11, fontFamily: 'monospace' }}>{art.configDir}</Text>
        </Space>
        {art.skills.length > 0 && (
          <div>
            <Text style={{ fontSize: 11, fontWeight: 600 }}>Skills ({art.skills.length})</Text>
            <div style={{ marginTop: 2, display: 'flex', flexWrap: 'wrap', gap: 2 }}>
              {art.skills.slice(0, 10).map(s => (
                <Tooltip key={s.name} title={s.isSymlink ? `→ ${s.target}` : ''}>
                  <Tag style={{ fontSize: 10 }} color={s.isSymlink ? 'blue' : 'default'}>
                    {s.isSymlink && <CloudOutlined style={{ marginRight: 2 }} />}{s.name}
                  </Tag>
                </Tooltip>
              ))}
              {art.skills.length > 10 && <Tag style={{ fontSize: 10 }}>+{art.skills.length - 10}</Tag>}
            </div>
          </div>
        )}
        {art.agents.length > 0 && (
          <div style={{ marginTop: 4 }}>
            <Text style={{ fontSize: 11, fontWeight: 600 }}>Agents ({art.agents.length})</Text>
            <div style={{ marginTop: 2, display: 'flex', flexWrap: 'wrap', gap: 2 }}>
              {art.agents.map(a => <Tag key={a.name} style={{ fontSize: 10 }} color="purple">{a.name}</Tag>)}
            </div>
          </div>
        )}
        {art.manifest && (
          <div style={{ marginTop: 4, display: 'flex', gap: 6 }}>
            <Tag style={{ fontSize: 10 }}>{art.manifest.team}</Tag>
            <Tag style={{ fontSize: 10 }}>{art.manifest.install_time}</Tag>
          </div>
        )}
      </div>
    ))
  }

  // 步骤图标
  const StepIcon = ({ step, done, active, icon }) => (
    <div style={{
      width: 32, height: 32, borderRadius: '50%',
      background: done ? '#52c41a' : active ? '#1677ff' : '#d9d9d9',
      color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontSize: 14, fontWeight: 600,
    }}>
      {done ? <CheckCircleOutlined /> : icon}
    </div>
  )

  return (
    <div>
      {/* 步骤条 */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Row justify="center" align="middle" gutter={24}>
          {[
            { title: '选择 & 安装', icon: <AppstoreOutlined /> },
            { title: '启动使用', icon: <RocketOutlined /> },
          ].map((s, i) => {
            const stepIdx = i * 2
            const done = currentStep > stepIdx
            const active = currentStep === stepIdx || (i === 1 && currentStep === 2)
            return (
              <Col key={i}>
                <div style={{
                  display: 'flex', alignItems: 'center', gap: 8,
                  opacity: active || done ? 1 : 0.4,
                  cursor: i === 0 ? 'pointer' : 'default',
                }} onClick={() => i === 0 && setCurrentStep(0)}>
                  <StepIcon step={i} done={done} active={active} icon={s.icon} />
                  <div>
                    <Text strong style={{ fontSize: 13, color: active || done ? '#1f1f1f' : '#bfbfbf' }}>
                      步骤 {i + 1}
                    </Text>
                    <div><Text type="secondary" style={{ fontSize: 11 }}>{s.title}</Text></div>
                  </div>
                </div>
              </Col>
            )
          })}
        </Row>
      </Card>

      {/* ===== Step 0/1: 选择 + 安装 ===== */}
      {(currentStep === 0 || currentStep === 1) && (
        <Row gutter={16}>
          <Col xs={24} md={10}>
            <Card size="small" title="安装配置">
              <div style={{ marginBottom: 12 }}>
                <Text strong style={{ display: 'block', marginBottom: 4 }}>AI 工具</Text>
                <Segmented
                  block
                  options={Object.entries(toolLabels).map(([value, label]) => ({ value, label }))}
                  value={selectedTool}
                  onChange={val => { setSelectedTool(val); setCheckResult(null) }}
                />
              </div>
              <div style={{ marginBottom: 12 }}>
                <Text strong style={{ display: 'block', marginBottom: 4 }}>安装场景</Text>
                <select
                  value={selectedScenario}
                  onChange={e => { setSelectedScenario(e.target.value); setInstallResult(null); setCurrentStep(0) }}
                  style={{ width: '100%', padding: '6px 8px', borderRadius: 6, border: '1px solid #d9d9d9', fontSize: 13 }}
                >
                  <option value="">-- 请选择 --</option>
                  {scenarios.map(s => (
                    <option key={s.id} value={s.path}>
                      [{s.type === 'official' ? '官方' : '社区'}] {s.name}
                    </option>
                  ))}
                </select>
                {currentScenarioObj?.description && (
                  <Text type="secondary" style={{ fontSize: 11, marginTop: 4, display: 'block' }}>
                    {currentScenarioObj.description}
                  </Text>
                )}
              </div>
              <div style={{ marginBottom: 12 }}>
                <Text strong style={{ display: 'block', marginBottom: 4 }}>安装级别</Text>
                <Segmented
                  block
                  options={[
                    { value: 'project', label: '项目级（推荐）' },
                    { value: 'global', label: '全局级' },
                  ]}
                  value={installLevel}
                  onChange={setInstallLevel}
                />
                <Text type="secondary" style={{ fontSize: 11, marginTop: 4, display: 'block' }}>
                  {installLevel === 'project' ? '安装到 .claude/ 目录，仅本项目生效' : '安装到 ~/.claude/，所有项目生效'}
                </Text>
              </div>
              <Button
                type="primary"
                icon={<RocketOutlined />}
                loading={installing}
                onClick={handleInstall}
                disabled={!selectedScenario}
                block
                size="large"
              >
                {installing ? '安装中...' : checkResult?.tools?.[selectedTool]?.installed ? '重新安装' : `安装到${installLevel === 'project' ? '项目' : '全局'}`}
              </Button>
              {checkResult?.tools?.[selectedTool]?.installed && (
                <Text type="secondary" style={{ fontSize: 11, marginTop: 4, display: 'block', textAlign: 'center' }}>
                  此场景已安装，可直接进入下一步，或点击重新安装
                </Text>
              )}
              {checkResult?.tools?.[selectedTool]?.installed && (
                <Button
                  icon={<CheckCircleOutlined />}
                  onClick={() => setCurrentStep(2)}
                  block
                  size="large"
                  style={{ marginTop: 8 }}
                >
                  跳过安装，直接使用
                </Button>
              )}
              {checkResult?.tools?.[selectedTool]?.installed && (
                <Button
                  danger
                  icon={<DeleteOutlined />}
                  loading={uninstalling}
                  onClick={handleUninstall}
                  block
                  style={{ marginTop: 8 }}
                >
                  卸载此场景
                </Button>
              )}
            </Card>
          </Col>
          <Col xs={24} md={14}>
            <Card size="small" title={
              <Space>
                <span>安装状态</span>
                <Button size="small" icon={<AuditOutlined />} loading={checking} onClick={doCheck} disabled={!selectedScenario}>刷新</Button>
                {checkResult?.tools?.[selectedTool]?.installed && (
                  <Button size="small" icon={<SafetyCertificateOutlined />} loading={verifying} onClick={doVerify}>校验一致性</Button>
                )}
              </Space>
            }>
              {checking ? (
                <div style={{ textAlign: 'center', padding: 40 }}><Spin size="large" /></div>
              ) : !checkResult ? (
                <Empty description="选择场景后查看安装状态" />
              ) : (
                Object.entries(checkResult.tools).map(([tool, info]) => (
                  <div key={tool} style={{
                    marginBottom: 8, padding: '8px 12px', borderRadius: 6,
                    borderLeft: `3px solid ${info.installed ? '#52c41a' : '#d9d9d9'}`,
                    opacity: tool === selectedTool ? 1 : 0.5,
                  }}>
                    <Space>
                      <Text strong>{toolLabels[tool]}</Text>
                      <Tag color={info.installed ? 'green' : 'default'}>{info.installed ? '已安装' : '未安装'}</Tag>
                    </Space>
                    {renderArtifacts(info.project, '项目级')}
                    {renderArtifacts(info.global, '全局级')}
                  </div>
                ))
              )}
            </Card>
          </Col>
        </Row>
      )}

      {/* 一致性校验结果（Step 0 和 Step 2 都展示） */}
      {verifyResult && verifyResult.installed && verifyResult.match && (
        <Card size="small" title={<Space><SafetyCertificateOutlined />一致性校验 — {currentScenarioObj?.name}</Space>} style={{ marginTop: 16 }}
          extra={<Tag color={verifyResult.match.skills_match && verifyResult.match.agents_match ? 'green' : 'orange'}>
            {verifyResult.match.skills_match && verifyResult.match.agents_match ? '全部匹配' : '存在差异'}
          </Tag>}>
          <Row gutter={16}>
            <Col span={12}>
              <Text strong>Skills</Text>
              <div style={{ marginTop: 4 }}>
                <Space size={4}>
                  <Tag color={verifyResult.match.skills_match ? 'green' : 'orange'}>
                    白名单: {verifyResult.match.expected_skills_count}
                  </Tag>
                  <Tag color={verifyResult.match.actual_skills_count === verifyResult.match.expected_skills_count ? 'green' : 'orange'}>
                    已安装: {verifyResult.match.actual_skills_count}
                  </Tag>
                </Space>
              </div>
              {verifyResult.match.skills_missing.length > 0 && (
                <div style={{ marginTop: 4 }}>
                  <Text type="danger" style={{ fontSize: 12 }}>缺失 ({verifyResult.match.skills_missing.length}):</Text>
                  <div style={{ marginTop: 2 }}>
                    {verifyResult.match.skills_missing.map(s => <Tag key={s} color="red" style={{ fontSize: 11, margin: 1 }}>{s}</Tag>)}
                  </div>
                </div>
              )}
              {verifyResult.match.skills_extra.length > 0 && (
                <div style={{ marginTop: 4 }}>
                  <Text type="warning" style={{ fontSize: 12 }}>多余 ({verifyResult.match.skills_extra.length}):</Text>
                  <div style={{ marginTop: 2 }}>
                    {verifyResult.match.skills_extra.slice(0, 10).map(s => <Tag key={s} color="orange" style={{ fontSize: 11, margin: 1 }}>{s}</Tag>)}
                    {verifyResult.match.skills_extra.length > 10 && <Tag style={{ fontSize: 11 }}>+{verifyResult.match.skills_extra.length - 10}</Tag>}
                  </div>
                </div>
              )}
            </Col>
            <Col span={12}>
              <Text strong>Agents</Text>
              <div style={{ marginTop: 4 }}>
                <Space size={4}>
                  <Tag color={verifyResult.match.agents_match ? 'green' : 'orange'}>
                    白名单: {verifyResult.match.expected_agents_count}
                  </Tag>
                  <Tag color={verifyResult.match.actual_agents_count === verifyResult.match.expected_agents_count ? 'green' : 'orange'}>
                    已安装: {verifyResult.match.actual_agents_count}
                  </Tag>
                </Space>
              </div>
              {verifyResult.match.agents_missing.length > 0 && (
                <div style={{ marginTop: 4 }}>
                  <Text type="danger" style={{ fontSize: 12 }}>缺失:</Text>
                  <div style={{ marginTop: 2 }}>
                    {verifyResult.match.agents_missing.map(a => <Tag key={a} color="red" style={{ fontSize: 11, margin: 1 }}>{a}</Tag>)}
                  </div>
                </div>
              )}
              {verifyResult.match.agents_extra.length > 0 && (
                <div style={{ marginTop: 4 }}>
                  <Text type="warning" style={{ fontSize: 12 }}>多余:</Text>
                  <div style={{ marginTop: 2 }}>
                    {verifyResult.match.agents_extra.map(a => <Tag key={a} color="orange" style={{ fontSize: 11, margin: 1 }}>{a}</Tag>)}
                  </div>
                </div>
              )}
            </Col>
          </Row>
        </Card>
      )}

      {/* ===== Step 2: 安装成功 → 启动指引 ===== */}
      {currentStep === 2 && (
        <div>
          {/* 成功状态栏 */}
          <Card size="small" style={{ marginBottom: 16 }}>
            <Row justify="space-between" align="middle">
              <Col>
                <Space>
                  <Tag color="green" icon={<CheckCircleOutlined />}>安装成功</Tag>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {currentScenarioObj?.name} → {toolLabels[selectedTool]} ({installLevel === 'project' ? '项目级' : '全局级'})
                  </Text>
                </Space>
              </Col>
              <Col>
                <Space>
                  {installResult?.artifacts && (
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      Skills: {installResult.artifacts.skills?.length || 0} / Agents: {installResult.artifacts.agents?.length || 0}
                    </Text>
                  )}
                  <Button size="small" icon={<SafetyCertificateOutlined />} loading={verifying} onClick={doVerify}>校验一致性</Button>
                  <Button size="small" danger icon={<DeleteOutlined />} loading={uninstalling} onClick={handleUninstall}>卸载</Button>
                  <Button size="small" onClick={() => { setCurrentStep(0); setInstallResult(null) }}>重新安装</Button>
                </Space>
              </Col>
            </Row>
          </Card>

          {/* 启动指南 */}
          <Card style={{ marginBottom: 16, borderColor: '#1677ff', borderWidth: 2 }}>
            <div style={{ textAlign: 'center', marginBottom: 20 }}>
              <RocketOutlined style={{ fontSize: 36, color: '#1677ff', marginBottom: 8 }} />
              <Title level={4} style={{ margin: 0 }}>启动 {toolLabels[selectedTool]} 开始使用</Title>
              <Text type="secondary">安装已完成，按以下步骤操作</Text>
            </div>

            {/* 步骤 1 */}
            <Card size="small" style={{ marginBottom: 12, background: '#fafafa' }}>
              <Row align="middle" gutter={12}>
                <Col>
                  <div style={{ width: 28, height: 28, borderRadius: '50%', background: '#1677ff', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700 }}>1</div>
                </Col>
                <Col flex="auto">
                  <Text strong>打开终端，进入项目目录</Text>
                  <div style={{ marginTop: 4 }}>
                    <Paragraph copyable={{ text: `cd ${installResult?.installDir?.replace(/\/.claude$/, '') || '你的项目目录'}` }} style={{ marginBottom: 0 }}>
                      <code style={{ background: '#f0f0f0', padding: '4px 8px', borderRadius: 4, fontSize: 13 }}>
                        cd {installResult?.installDir?.replace(/\/.claude$/, '') || '你的项目目录'}
                      </code>
                    </Paragraph>
                  </div>
                </Col>
              </Row>
            </Card>

            {/* 步骤 2 */}
            <Card size="small" style={{ marginBottom: 12, background: '#fafafa' }}>
              <Row align="middle" gutter={12}>
                <Col>
                  <div style={{ width: 28, height: 28, borderRadius: '50%', background: '#1677ff', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700 }}>2</div>
                </Col>
                <Col flex="auto">
                  <Text strong>启动 {toolLabels[selectedTool]}</Text>
                  <div style={{ marginTop: 4 }}>
                    <Text type="secondary" style={{ fontSize: 12 }}>{toolInstallHints[selectedTool]}</Text>
                  </div>
                  {(selectedTool === 'claude' || selectedTool === 'opencode') && (
                    <div style={{ marginTop: 6 }}>
                      <Paragraph copyable={{ text: selectedTool === 'claude' ? 'claude' : 'opencode' }} style={{ marginBottom: 0 }}>
                        <code style={{ background: '#f0f0f0', padding: '4px 8px', borderRadius: 4, fontSize: 13 }}>
                          {selectedTool === 'claude' ? 'claude' : 'opencode'}
                        </code>
                      </Paragraph>
                    </div>
                  )}
                </Col>
              </Row>
            </Card>

            {/* 步骤 3 */}
            <Card size="small" style={{ marginBottom: 12, background: '#f0fff0', borderColor: '#b7eb8f' }}>
              <Row align="middle" gutter={12}>
                <Col>
                  <div style={{ width: 28, height: 28, borderRadius: '50%', background: '#52c41a', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700 }}>3</div>
                </Col>
                <Col flex="auto">
                  <Text strong>输入需求，CANNBot 自动调度 Skills 和 Agents 完成</Text>
                  <div style={{
                    marginTop: 8, padding: '10px 14px', background: '#fff',
                    border: '1px solid #d9d9d9', borderRadius: 6, position: 'relative',
                  }}>
                    <Tag color="blue" style={{ position: 'absolute', top: -8, right: 12, fontSize: 10 }}>
                      示例提示词 — 点击复制
                    </Tag>
                    <Paragraph copyable style={{ marginBottom: 0, fontSize: 13 }}>
                      {examplePrompt}
                    </Paragraph>
                  </div>
                </Col>
              </Row>
            </Card>

            {/* Agent 角色 */}
            {currentScenarioObj?.agents?.length > 0 && (
              <Card size="small" title={<Text strong style={{ fontSize: 13 }}>已安装的 Agent 角色</Text>}>
                <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 8 }}>
                  输入需求后，CANNBot 主 Agent 会自动按流程调度这些 Sub-Agent 协作完成
                </Text>
                <Row gutter={[8, 8]}>
                  {currentScenarioObj.agents.map(a => (
                    <Col key={a} xs={24} sm={12}>
                      <div style={{ padding: '6px 10px', background: '#fafafa', borderRadius: 4, display: 'flex', alignItems: 'center', gap: 6 }}>
                        <RobotOutlined style={{ color: '#722ed1' }} />
                        <Text style={{ fontSize: 12 }}>{a}</Text>
                      </div>
                    </Col>
                  ))}
                </Row>
              </Card>
            )}
          </Card>

          {/* 已安装 Skills */}
          {installResult?.artifacts?.skills?.length > 0 && (
            <Card size="small" title={
              <Space>
                <Text strong>已安装的 Skills ({installResult.artifacts.skills.length})</Text>
                <Text type="secondary" style={{ fontSize: 11 }}>Agent 会自动调用这些能力模块</Text>
              </Space>
            }>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                {installResult.artifacts.skills.map(s => (
                  <Tooltip key={s.name} title={s.isSymlink ? `软链接 → ${s.target}` : ''}>
                    <Tag icon={s.isSymlink ? <CloudOutlined /> : null} style={{ fontSize: 11 }}>{s.name}</Tag>
                  </Tooltip>
                ))}
              </div>
            </Card>
          )}

          {/* 内嵌终端 */}
          <Card size="small" title={
            <Space>
              <CodeOutlined />
              <Text strong>交互式终端</Text>
              <Text type="secondary" style={{ fontSize: 11 }}>直接在页面中启动 {toolLabels[selectedTool]}，测试 Skill 效果</Text>
            </Space>
          } style={{ marginTop: 16 }}>
            <EmbeddedTerminal
              cwd={installResult?.installDir?.replace(/\/.claude$/, '') || ''}
              tool={selectedTool}
              examplePrompt={examplePrompt}
            />
          </Card>
        </div>
      )}

      {/* ===== Step 3: 安装失败 ===== */}
      {currentStep === 3 && (
        <div>
          <Card style={{ marginBottom: 16, borderColor: '#ff4d4f', borderWidth: 2 }}>
            <div style={{ textAlign: 'center', padding: 16 }}>
              <Tag color="red" style={{ fontSize: 14, padding: '4px 12px' }}>安装失败</Tag>
              <div style={{ marginTop: 12 }}>
                <Button type="primary" onClick={() => setCurrentStep(0)}>返回重试</Button>
              </div>
            </div>
          </Card>
          {installResult && (
            <Card size="small" title="错误日志">
              <pre style={{
                background: '#fff2f0', padding: 12, borderRadius: 6, fontSize: 11,
                maxHeight: 400, overflow: 'auto', whiteSpace: 'pre-wrap', margin: 0, lineHeight: 1.6,
              }}>
                {installResult.errors || installResult.output || '无输出'}
              </pre>
            </Card>
          )}
        </div>
      )}
    </div>
  )
}

// ==================== 内嵌终端组件 ====================
function EmbeddedTerminal({ cwd, tool, examplePrompt }) {
  const containerRef = useRef(null)
  const termRef = useRef(null)
  const wsRef = useRef(null)
  const [termOpen, setTermOpen] = useState(false)
  const [connected, setConnected] = useState(false)

  const toolCmd = { claude: 'claude', opencode: 'opencode', cursor: null, trae: null }

  const openTerminal = () => {
    if (termRef.current) return
    setTermOpen(true)

    Promise.all([
      import('@xterm/xterm'),
      import('@xterm/addon-fit'),
      import('@xterm/xterm/css/xterm.css'),
    ]).then(([{ Terminal }, { FitAddon }]) => {
      const term = new Terminal({
        cursorBlink: true,
        fontSize: 13,
        fontFamily: 'Menlo, Monaco, "Courier New", monospace',
        theme: {
          background: '#1e1e1e',
          foreground: '#d4d4d4',
          cursor: '#ffffff',
          selectionBackground: '#264f78',
        },
        rows: 20,
        cols: 80,
      })
      const fitAddon = new FitAddon()
      term.loadAddon(fitAddon)
      term.open(containerRef.current)
      setTimeout(() => fitAddon.fit(), 50)

      termRef.current = term

      const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
      const ws = new WebSocket(`${protocol}//${location.host}/ws/terminal`)
      ws.binaryType = 'arraybuffer'
      wsRef.current = ws

      ws.addEventListener('open', () => {
        setConnected(true)
        term.writeln('\x1b[32m终端已连接\x1b[0m\r')
        if (cwd) ws.send(`cd ${cwd}\n`)
      })

      ws.addEventListener('message', (e) => {
        if (e.data instanceof ArrayBuffer) {
          term.write(new Uint8Array(e.data))
        } else {
          term.write(e.data)
        }
      })

      ws.addEventListener('close', () => {
        setConnected(false)
        term.writeln('\r\n\x1b[33m终端已断开\x1b[0m')
      })

      ws.addEventListener('error', () => {
        setConnected(false)
        term.writeln('\r\n\x1b[31m连接失败，请确认后端已启动\x1b[0m')
      })

      term.onData((data) => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(data)
        }
      })

      const resizeObs = new ResizeObserver(() => {
        try { fitAddon.fit() } catch {}
      })
      if (containerRef.current) resizeObs.observe(containerRef.current)
      term._resizeObs = resizeObs
    })
  }

  const sendCmd = (cmd) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(cmd + '\n')
    }
  }

  return (
    <div>
      {!termOpen ? (
        <div style={{ textAlign: 'center', padding: 24 }}>
          <Button type="primary" size="large" icon={<CodeOutlined />} onClick={openTerminal}>
            打开终端
          </Button>
          <div style={{ marginTop: 8 }}>
            <Text type="secondary" style={{ fontSize: 12 }}>打开交互式终端，自动进入项目目录</Text>
          </div>
        </div>
      ) : (
        <div>
          <div style={{ marginBottom: 8, display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <Space size={4}>
              <Tag color={connected ? 'green' : 'default'} style={{ fontSize: 11 }}>
                {connected ? '已连接' : '未连接'}
              </Tag>
              {cwd && <Text type="secondary" style={{ fontSize: 11 }}>{cwd}</Text>}
            </Space>
            <div style={{ flex: 1 }} />
            {toolCmd[tool] && (
              <Button size="small" icon={<RocketOutlined />} onClick={() => sendCmd(toolCmd[tool])} disabled={!connected}>
                启动 {tool}
              </Button>
            )}
            <Button size="small" icon={<ThunderboltOutlined />} onClick={() => sendCmd(examplePrompt)} disabled={!connected}>
              发送示例提示词
            </Button>
          </div>
          <div
            ref={containerRef}
            style={{ height: 420, background: '#1e1e1e', borderRadius: 6, padding: 4, overflow: 'hidden' }}
          />
        </div>
      )}
    </div>
  )
}

// ==================== 工作流仿真 Tab ====================

function WorkflowSimTab() {
  const [definitions, setDefinitions] = useState([])
  const [selectedPlugin, setSelectedPlugin] = useState(null)
  const [persona, setPersona] = useState('intermediate')
  const [stepResults, setStepResults] = useState([])        // 逐步累积的步骤结果
  const [summary, setSummary] = useState(null)              // 最终汇总
  const [selectedStepId, setSelectedStepId] = useState(null)
  const [simulating, setSimulating] = useState(false)
  const [currentStepInfo, setCurrentStepInfo] = useState(null) // 当前正在执行的步骤
  const [totalSteps, setTotalSteps] = useState(0)
  const [defsLoading, setDefsLoading] = useState(false)
  const [logs, setLogs] = useState([])                      // 实时日志
  const [exporting, setExporting] = useState(false)
  const [historyList, setHistoryList] = useState([])          // 历史仿真列表
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyDetailLoading, setHistoryDetailLoading] = useState(false)
  const esRef = useRef(null)

  // 加载工作流定义列表
  useEffect(() => {
    setDefsLoading(true)
    getWorkflowDefinitions()
      .then(res => setDefinitions(res.data?.plugins || []))
      .catch(() => {})
      .finally(() => setDefsLoading(false))
  }, [])

  // 清理 SSE 连接
  useEffect(() => {
    return () => { if (esRef.current) esRef.current.close() }
  }, [])

  // 加载历史仿真列表
  const loadHistory = useCallback(() => {
    setHistoryLoading(true)
    getWorkflowSimulations({ limit: 30 })
      .then(res => setHistoryList(res.data?.simulations || []))
      .catch(() => {})
      .finally(() => setHistoryLoading(false))
  }, [])

  useEffect(() => { loadHistory() }, [loadHistory])

  // 加载历史仿真详情
  const loadHistoryDetail = useCallback(async (simId) => {
    setHistoryDetailLoading(true)
    try {
      const res = await getWorkflowSimulation(simId)
      const data = res.data
      setStepResults(data.steps || [])
      setSummary(data)
      setSelectedStepId(null)
      setSimulating(false)
      setCurrentStepInfo(null)
      setLogs([])
      message.success('历史仿真加载成功')
    } catch (e) {
      message.error('加载失败: ' + (e._friendlyMsg || e.message))
    } finally {
      setHistoryDetailLoading(false)
    }
  }, [])

  const addLog = useCallback((type, text) => {
    setLogs(prev => [...prev, { time: new Date().toLocaleTimeString(), type, text }])
  }, [])

  // 启动 SSE 实时仿真
  const handleSimulate = useCallback(() => {
    if (!selectedPlugin) { message.warning('请先选择插件'); return }

    // 重置状态
    setStepResults([])
    setSummary(null)
    setSelectedStepId(null)
    setCurrentStepInfo(null)
    setLogs([])
    setSimulating(true)

    // 关闭旧连接
    if (esRef.current) esRef.current.close()

    const es = simulateWorkflowStream(selectedPlugin, persona)
    esRef.current = es

    es.addEventListener('start', (e) => {
      const data = JSON.parse(e.data)
      setTotalSteps(data.total_steps)
      addLog('info', `开始仿真: ${data.plugin_name} (${data.total_steps} 步, 角色: ${data.persona})`)
    })

    es.addEventListener('step_start', (e) => {
      const data = JSON.parse(e.data)
      setCurrentStepInfo(data)
      setSelectedStepId(data.step_id)
      addLog('info', `[${data.step_index + 1}/${data.total}] 仿真 ${data.step_name}...`)
    })

    es.addEventListener('step_done', (e) => {
      const stepData = JSON.parse(e.data)
      setStepResults(prev => [...prev, stepData])
      setSelectedStepId(stepData.step_id)

      const bpCount = stepData.breakpoints?.length || 0
      const passPct = Math.round((stepData.simulated_pass_rate || 0) * 100)
      if (bpCount > 0) {
        const critical = stepData.breakpoints.filter(b => b.severity === 'CRITICAL').length
        addLog('warn', `${stepData.step_name} 完成 — 通过率 ${passPct}%, ${bpCount} 个断点${critical > 0 ? ` (${critical} CRITICAL)` : ''}`)
      } else {
        addLog('success', `${stepData.step_name} 完成 — 通过率 ${passPct}%`)
      }
    })

    es.addEventListener('summary', (e) => {
      const data = JSON.parse(e.data)
      setSummary(data)
      setSimulating(false)
      setCurrentStepInfo(null)
      addLog('info', `仿真完成 — 总通过率 ${Math.round(data.overall_pass_rate * 100)}%, ${data.total_breakpoints} 个断点, Token: ${data.total_tokens?.toLocaleString()}`)
      message.success('仿真完成')
      loadHistory()
      es.close()
    })

    es.addEventListener('error', (e) => {
      // SSE error event or connection error
      if (e.data) {
        try {
          const data = JSON.parse(e.data)
          addLog('error', `错误: ${data.error}`)
          message.error(data.error)
        } catch { /* ignore */ }
      }
      setSimulating(false)
      setCurrentStepInfo(null)
      es.close()
    })

    es.onerror = () => {
      if (simulating) {
        addLog('error', '连接断开')
        message.error('仿真连接断开')
      }
      setSimulating(false)
      setCurrentStepInfo(null)
    }
  }, [selectedPlugin, persona, addLog, simulating])

  // 导出报告
  const handleExport = useCallback(async (format) => {
    if (!summary || stepResults.length === 0) {
      message.warning('请先完成仿真后再导出')
      return
    }
    setExporting(true)
    try {
      const res = await exportWorkflowReport({
        format,
        summary,
        step_results: stepResults,
      })
      const ext = format === 'pdf' ? 'pdf' : 'md'
      const filename = `simulation_${summary.plugin_name || 'report'}_${summary.simulation_id || Date.now()}.${ext}`
      const url = URL.createObjectURL(res.data)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      message.success('报告导出成功')
    } catch (e) {
      message.error(`导出失败: ${e._friendlyMsg || e.message}`)
    } finally {
      setExporting(false)
    }
  }, [summary, stepResults])

  // 所有断点汇总
  const allBreakpoints = stepResults.flatMap(s => s.breakpoints || [])
  const skillCoverage = (() => {
    let total = 0, used = 0
    stepResults.forEach(s => {
      total += (s.skills_missing?.length || 0) + (s.skills_used?.length || 0)
      used += s.skills_used?.length || 0
    })
    return total > 0 ? Math.round(used / total * 100) : 0
  })()

  // 选中的步骤详情
  const selectedStep = stepResults.find(s => s.step_id === selectedStepId)
  const doneCount = stepResults.length

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* 控制栏 */}
      <Card size="small">
        <Row gutter={12} align="middle">
          <Col>
            <Text strong>插件:</Text>
            <Select
              style={{ width: 240, marginLeft: 8 }}
              placeholder="选择插件"
              loading={defsLoading}
              value={selectedPlugin}
              onChange={setSelectedPlugin}
              options={definitions.map(d => ({
                value: d.plugin_id,
                label: `${d.plugin_name} (${d.steps_count} 步)`,
              }))}
            />
          </Col>
          <Col>
            <Text strong>角色:</Text>
            <Segmented
              style={{ marginLeft: 8 }}
              value={persona}
              onChange={setPersona}
              options={[
                { label: '新手', value: 'novice' },
                { label: '中级', value: 'intermediate' },
                { label: '资深', value: 'experienced' },
              ]}
            />
          </Col>
          <Col>
            <Button
              type="primary"
              icon={<ExperimentOutlined />}
              loading={simulating}
              onClick={handleSimulate}
              disabled={!selectedPlugin}
            >
              {simulating ? '仿真中...' : '启动仿真'}
            </Button>
          </Col>
          {simulating && totalSteps > 0 && (
            <Col span={6}>
              <Progress
                percent={Math.round(doneCount / totalSteps * 100)}
                size="small"
                format={() => `${doneCount}/${totalSteps} 步`}
              />
            </Col>
          )}
          {summary && (
            <Col>
              <Tag color="blue">Token: {summary.total_tokens?.toLocaleString()}</Tag>
              <Tag color="green">成本: ${summary.estimated_cost_usd}</Tag>
            </Col>
          )}
          {summary && (
            <Col>
              <Dropdown menu={{
                items: [
                  { key: 'pdf', label: '导出 PDF', icon: <FilePdfOutlined /> },
                  { key: 'markdown', label: '导出 Markdown', icon: <FileMarkdownOutlined /> },
                ],
                onClick: ({ key }) => handleExport(key),
              }}>
                <Button icon={<DownloadOutlined />} loading={exporting}>
                  导出报告 <DownOutlined />
                </Button>
              </Dropdown>
            </Col>
          )}
        </Row>
      </Card>

      {/* 实时仿真过程 */}
      {(simulating || stepResults.length > 0) && (
        <Card
          title={
            <span>
              <ExperimentOutlined style={{ marginRight: 8 }} />
              仿真过程 {simulating && <Spin size="small" style={{ marginLeft: 8 }} />}
            </span>
          }
          size="small"
        >
          {/* DAG 图 */}
          {stepResults.length > 0 && (
            <WorkflowSimPanel
              steps={stepResults}
              selectedStepId={selectedStepId}
              onStepClick={setSelectedStepId}
            />
          )}

          {/* 当前步骤指示 */}
          {simulating && currentStepInfo && (
            <div style={{ marginTop: 12, padding: '8px 12px', background: '#e6f7ff', borderRadius: 6, borderLeft: '3px solid #1890ff' }}>
              <Spin size="small" style={{ marginRight: 8 }} />
              <Text strong>正在仿真: {currentStepInfo.step_name}</Text>
              <Text type="secondary" style={{ marginLeft: 8 }}>
                ({currentStepInfo.step_index + 1}/{currentStepInfo.total})
              </Text>
            </div>
          )}

          {/* 选中步骤的详情 */}
          {selectedStep && (
            <div style={{ marginTop: 12, padding: 12, background: '#fafafa', borderRadius: 6 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                <Text strong style={{ fontSize: 14 }}>{selectedStep.step_name}</Text>
                <Tag color={selectedStep.simulated_pass_rate >= 0.7 ? 'success' : 'error'}>
                  通过率 {Math.round((selectedStep.simulated_pass_rate || 0) * 100)}%
                </Tag>
              </div>
              <Progress
                percent={Math.round((selectedStep.simulated_pass_rate || 0) * 100)}
                size="small"
                strokeColor={selectedStep.simulated_pass_rate >= 0.7 ? '#52c41a' : '#ff4d4f'}
                style={{ marginBottom: 10 }}
              />
              {selectedStep.skills_used?.length > 0 && (
                <div style={{ marginBottom: 6 }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>使用 Skills: </Text>
                  {selectedStep.skills_used.map(s => (
                    <Tag key={s} color="green" style={{ fontSize: 11 }}>{s}</Tag>
                  ))}
                </div>
              )}
              {selectedStep.skills_missing?.length > 0 && (
                <div style={{ marginBottom: 6 }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>缺失 Skills: </Text>
                  {selectedStep.skills_missing.map(s => (
                    <Tag key={s} color="red" style={{ fontSize: 11 }}>{s}</Tag>
                  ))}
                </div>
              )}
              {selectedStep.breakpoints?.length > 0 && (
                <div style={{ marginBottom: 6 }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>断点 ({selectedStep.breakpoints.length}):</Text>
                  {selectedStep.breakpoints.map((bp, i) => (
                    <div key={i} style={{ marginLeft: 8, marginTop: 4, fontSize: 12 }}>
                      <Tag color={bp.severity === 'CRITICAL' ? 'error' : bp.severity === 'HIGH' ? 'warning' : ''} style={{ fontSize: 10 }}>
                        {bp.severity}
                      </Tag>
                      <Tag style={{ fontSize: 10 }}>{bp.category}</Tag>
                      <span>{bp.description}</span>
                    </div>
                  ))}
                </div>
              )}
              {selectedStep.llm_response_summary && (
                <div style={{ marginTop: 8 }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>LLM 回复:</Text>
                  <Paragraph
                    type="secondary"
                    ellipsis={{ rows: 4, expandable: true, symbol: '展开全部' }}
                    style={{ fontSize: 12, marginTop: 4, background: '#fff', padding: 8, borderRadius: 4, border: '1px solid #e8e8e8' }}
                  >
                    {selectedStep.llm_response_summary}
                  </Paragraph>
                </div>
              )}
            </div>
          )}
        </Card>
      )}

      {/* 实时日志 */}
      {(simulating || logs.length > 0) && (
        <Card title="仿真日志" size="small">
          <div style={{ maxHeight: 200, overflowY: 'auto', background: '#1e1e1e', borderRadius: 6, padding: 8, fontFamily: 'monospace', fontSize: 12 }}>
            {logs.map((log, i) => (
              <div key={i} style={{ marginBottom: 2 }}>
                <span style={{ color: '#888' }}>[{log.time}]</span>{' '}
                <span style={{ color: log.type === 'error' ? '#ff4d4f' : log.type === 'warn' ? '#faad14' : log.type === 'success' ? '#52c41a' : '#1890ff' }}>
                  {log.text}
                </span>
              </div>
            ))}
            {simulating && (
              <div style={{ color: '#888' }}>
                <Spin size="small" style={{ marginRight: 4 }} />等待下一步...
              </div>
            )}
          </div>
        </Card>
      )}

      {/* 统计卡片 (完成后) */}
      {summary && (
        <Row gutter={12}>
          <Col span={6}>
            <Card size="small">
              <Statistic
                title="总体通过率"
                value={Math.round(summary.overall_pass_rate * 100)}
                suffix="%"
                valueStyle={{ color: summary.overall_pass_rate >= 0.7 ? '#52c41a' : '#ff4d4f' }}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic
                title="断点总数"
                value={summary.total_breakpoints}
                suffix={`(${summary.critical_breakpoints} CRITICAL)`}
                valueStyle={{ color: summary.total_breakpoints > 0 ? '#fa541c' : '#52c41a' }}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic title="Skill 覆盖率" value={skillCoverage} suffix="%" />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic
                title="匹配反模式"
                value={summary.antipatterns_matched?.length || 0}
                valueStyle={{ color: '#722ed1' }}
              />
            </Card>
          </Col>
        </Row>
      )}

      {/* 断点时间线 */}
      {allBreakpoints.length > 0 && (
        <Card title={`断点列表 (${allBreakpoints.length})`} size="small">
          <BreakpointTimeline breakpoints={allBreakpoints} maxHeight={300} />
        </Card>
      )}

      {/* Skill 热力图 */}
      {summary?.skill_heatmap && Object.keys(summary.skill_heatmap).length > 0 && (
        <Card title="Skill 利用热力图" size="small">
          <SkillHeatmapChart heatmap={summary.skill_heatmap} steps={stepResults} />
        </Card>
      )}

      {/* 反模式匹配 */}
      {summary?.antipatterns_matched?.length > 0 && (
        <Card title="匹配的反模式" size="small">
          {summary.antipatterns_matched.map((ap, i) => (
            <div key={i} style={{
              marginBottom: 8, padding: '8px 12px',
              background: '#fffbe6', borderLeft: `3px solid ${ap.severity === 'CRITICAL' ? '#ff4d4f' : ap.severity === 'HIGH' ? '#fa541c' : '#faad14'}`,
              borderRadius: 4,
            }}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <Tag color={ap.severity === 'CRITICAL' ? 'error' : 'warning'}>{ap.severity}</Tag>
                <Text strong>{ap.name}</Text>
                <Text type="secondary" style={{ fontSize: 12 }}>易感性: {Math.round(ap.susceptibility * 100)}%</Text>
              </div>
              <Text type="secondary" style={{ fontSize: 12 }}>{ap.mitigation}</Text>
            </div>
          ))}
        </Card>
      )}

      {/* 历史仿真记录 */}
      {historyList.length > 0 && (
        <Card
          title={
            <span>
              <ClockCircleOutlined style={{ marginRight: 8 }} />
              历史仿真记录
              <Button type="link" size="small" onClick={loadHistory} loading={historyLoading} style={{ marginLeft: 8 }}>刷新</Button>
            </span>
          }
          size="small"
        >
          <div style={{ maxHeight: 320, overflowY: 'auto' }}>
            {historyList.map((sim) => {
              const passPct = Math.round((sim.overall_pass_rate || 0) * 100)
              const passColor = passPct >= 70 ? '#52c41a' : passPct >= 50 ? '#faad14' : '#ff4d4f'
              return (
                <div
                  key={sim.simulation_id}
                  onClick={() => loadHistoryDetail(sim.simulation_id)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 12,
                    padding: '8px 12px', marginBottom: 4, borderRadius: 6,
                    background: summary?.simulation_id === sim.simulation_id ? '#e6f7ff' : '#fafafa',
                    borderLeft: `3px solid ${passColor}`,
                    cursor: 'pointer',
                  }}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <Text strong ellipsis style={{ fontSize: 13 }}>{sim.plugin_name}</Text>
                      <Tag style={{ fontSize: 11 }}>{sim.persona}</Tag>
                      {sim.critical_breakpoints > 0 && (
                        <Tag color="error" style={{ fontSize: 10 }}>{sim.critical_breakpoints} CRITICAL</Tag>
                      )}
                    </div>
                    <div style={{ fontSize: 11, color: '#999', marginTop: 2 }}>
                      {sim.compared_at ? new Date(sim.compared_at).toLocaleString() : ''} · {sim.steps_count} 步 · Token {sim.total_tokens?.toLocaleString()}
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: 16, fontWeight: 600, color: passColor }}>{passPct}%</div>
                    <div style={{ fontSize: 10, color: '#999' }}>通过率</div>
                  </div>
                  <Button
                    type="link" size="small" loading={historyDetailLoading}
                    onClick={(e) => { e.stopPropagation(); loadHistoryDetail(sim.simulation_id) }}
                  >
                    查看
                  </Button>
                </div>
              )
            })}
          </div>
        </Card>
      )}

      {/* 空状态 */}
      {!simulating && stepResults.length === 0 && (
        <Card>
          <Empty
            description="选择插件和角色后点击「启动仿真」，LLM 将实时模拟开发者走完整个工作流"
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        </Card>
      )}
    </div>
  )
}
