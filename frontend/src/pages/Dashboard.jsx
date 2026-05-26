import { useState, useEffect } from 'react'
import { Card, Statistic, Row, Col, Spin, Alert, Tag, Space, Progress, Tooltip, Timeline, Segmented } from 'antd'
import {
  DatabaseOutlined, FileTextOutlined, CommentOutlined, CheckCircleOutlined,
  AlertOutlined, ClockCircleOutlined, UserOutlined, ThunderboltOutlined,
  RightOutlined, AppstoreOutlined, BranchesOutlined, TeamOutlined,
  BarChartOutlined, RocketOutlined, GlobalOutlined, HistoryOutlined,
  TrophyOutlined, HeartFilled, ExclamationCircleOutlined,
} from '@ant-design/icons'
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip as RTooltip } from 'recharts'
import * as api from '../api'

// PR 状态颜色
const STATE_COLORS = { open: '#1890ff', closed: '#52c41a', merged: '#722ed1' }
const STATE_LABELS = { open: 'Open', closed: 'Closed', merged: 'Merged' }

// 健康度评级颜色
const GRADE_COLORS = { A: '#52c41a', B: '#1890ff', C: '#faad14', D: '#fa541c', F: '#f5222d', 'N/A': '#d9d9d9' }

export default function Dashboard({ onNavigate }) {
  const [stats, setStats] = useState(null)
  const [overview, setOverview] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // 新增状态
  const [prStateData, setPrStateData] = useState([])
  const [activities, setActivities] = useState([])
  const [contributors, setContributors] = useState([])
  const [contributorSort, setContributorSort] = useState('total_activity')
  const [healthSnapshots, setHealthSnapshots] = useState([])

  useEffect(() => {
    Promise.all([
      api.getDatabaseStats().then(res => res.data.stats).catch(() => null),
      api.getProjectsOverview().then(res => res.data.projects || []).catch(() => []),
      api.getAggregate().then(res => {
        const byState = res.data?.stats?.by_state || []
        return byState
      }).catch(() => []),
      api.getRecentActivities({ limit: 15 }).then(res => res.data.activities || []).catch(() => []),
      api.getTopContributors({ limit: 10, sort_by: contributorSort }).then(res => res.data.contributors || []).catch(() => []),
      api.getBatchHealth().then(res => res.data.snapshots || []).catch(() => []),
    ]).then(([s, p, stateData, acts, contribs, health]) => {
      setStats(s)
      setOverview(p)
      setPrStateData(stateData)
      setActivities(acts)
      setContributors(contribs)
      setHealthSnapshots(health)
    }).catch(err => setError(err.message))
    .finally(() => setLoading(false))
  }, [])

  // 贡献者排序切换
  useEffect(() => {
    api.getTopContributors({ limit: 10, sort_by: contributorSort })
      .then(res => setContributors(res.data.contributors || []))
      .catch(() => {})
  }, [contributorSort])

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />
  if (error) return <Alert type="error" message={error} />

  const dbOk = stats?.status === 'connected'

  const statCards = [
    { title: 'PR 数据', value: stats?.pr_data_count || 0, icon: <FileTextOutlined />, color: '#1890ff', page: 'prs' },
    { title: 'PR 评论', value: stats?.pr_comments_count || 0, icon: <CommentOutlined />, color: '#faad14', page: 'comments' },
    { title: 'Issues', value: stats?.issues_count || 0, icon: <AlertOutlined />, color: '#eb2f96', page: 'issues' },
    { title: 'Issue Timelines', value: stats?.issue_timelines_count || 0, icon: <ClockCircleOutlined />, color: '#722ed1', page: 'issue-timelines' },
    { title: '评论者 Profile', value: stats?.user_profiles_count || 0, icon: <UserOutlined />, color: '#13c2c2', page: 'profiles' },
    { title: 'Git Commits', value: overview.reduce((s, p) => s + (p.commits_count || 0), 0), icon: <BranchesOutlined />, color: '#fa541c', page: 'git-log' },
  ]

  const totalRecords = statCards.reduce((s, c) => s + (typeof c.value === 'number' ? c.value : 0), 0)

  const quickNav = [
    { label: '项目总览', icon: <AppstoreOutlined />, page: 'projects-overview', desc: '管理项目、获取数据' },
    { label: 'Git Log', icon: <BranchesOutlined />, page: 'git-log', desc: '查看提交记录' },
    { label: '开发者关系', icon: <TeamOutlined />, page: 'dev-relations', desc: '互动关系图谱' },
    { label: '任务监控', icon: <ThunderboltOutlined />, page: 'tasks', desc: '异步任务状态' },
    { label: '聚合统计', icon: <BarChartOutlined />, page: 'aggregate', desc: '数据聚合分析' },
  ]

  const topProjects = overview
    .map(p => ({
      ...p,
      total: (p.pr_count || 0) + (p.comments_count || 0) + (p.issues_count || 0) + (p.commits_count || 0),
    }))
    .sort((a, b) => b.total - a.total)
    .slice(0, 5)

  const maxTotal = topProjects.length > 0 ? topProjects[0].total : 1

  // 格式化时间
  const formatTimeAgo = (dateStr) => {
    if (!dateStr) return ''
    try {
      const diff = Date.now() - new Date(dateStr).getTime()
      const mins = Math.floor(diff / 60000)
      if (mins < 60) return `${mins} 分钟前`
      const hours = Math.floor(mins / 60)
      if (hours < 24) return `${hours} 小时前`
      const days = Math.floor(hours / 24)
      if (days < 30) return `${days} 天前`
      return new Date(dateStr).toLocaleDateString('zh-CN')
    } catch { return dateStr }
  }

  // 活动类型配置
  const activityConfig = {
    pr_created: { color: '#1890ff', icon: <FileTextOutlined />, label: '创建 PR' },
    comment: { color: '#faad14', icon: <CommentOutlined />, label: '评论 PR' },
    issue_opened: { color: '#eb2f96', icon: <AlertOutlined />, label: '打开 Issue' },
    issue_closed: { color: '#52c41a', icon: <CheckCircleOutlined />, label: '关闭 Issue' },
  }

  // PR 状态环形图数据
  const pieData = prStateData.map(s => ({
    name: STATE_LABELS[s._id] || s._id,
    value: s.count,
    color: STATE_COLORS[s._id] || '#999',
  }))

  // 贡献者排序选项
  const sortOptions = [
    { label: '总活跃度', value: 'total_activity' },
    { label: 'PR 数', value: 'pr_count' },
    { label: '评论数', value: 'comment_count' },
  ]

  const maxContributorActivity = contributors.length > 0 ? contributors[0].total_activity : 1

  return (
    <div>
      {/* 现有布局：标题行 */}
      <Row gutter={[16, 16]} align="middle" style={{ marginBottom: 24 }}>
        <Col flex="auto">
          <h2 style={{ margin: 0 }}><RocketOutlined style={{ marginRight: 8, color: '#1890ff' }} />数据概览</h2>
        </Col>
        <Col>
          <Tag color={dbOk ? 'success' : 'error'} style={{ fontSize: 13, padding: '4px 12px' }}>
            <CheckCircleOutlined /> {dbOk ? '数据库已连接' : '数据库未连接'} · {stats?.database}
          </Tag>
          <Tag style={{ fontSize: 13, padding: '4px 12px' }}>
            <GlobalOutlined /> {overview.length} 个项目
          </Tag>
        </Col>
      </Row>

      {/* 现有布局：统计卡片行 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 8 }}>
        <Col xs={24} sm={12} md={8} lg={4}>
          <Card bodyStyle={{ padding: '16px 20px' }}>
            <Statistic
              title="总记录数"
              value={totalRecords}
              valueStyle={{ color: '#1890ff', fontSize: 28, fontWeight: 700 }}
              prefix={<DatabaseOutlined />}
            />
          </Card>
        </Col>
        {statCards.map((item, i) => (
          <Col xs={24} sm={12} md={8} lg={4} key={i}>
            <Card
              hoverable
              bodyStyle={{ padding: '16px 20px' }}
              onClick={() => item.page && onNavigate(item.page)}
              style={{ cursor: 'pointer', borderLeft: `3px solid ${item.color}` }}
            >
              <Statistic
                title={item.title}
                value={item.value}
                prefix={item.icon}
                valueStyle={{ color: item.color, fontSize: 22 }}
              />
            </Card>
          </Col>
        ))}
      </Row>

      {/* 现有布局：活跃项目 + 快捷导航 */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={14}>
          <Card
            title={<span><AppstoreOutlined style={{ marginRight: 8 }} />活跃项目</span>}
            extra={<a onClick={() => onNavigate('projects-overview')}>查看全部 <RightOutlined /></a>}
            bodyStyle={{ padding: '12px 20px' }}
          >
            {topProjects.length > 0 ? topProjects.map((p, i) => (
              <div
                key={i}
                style={{
                  display: 'flex', alignItems: 'center', padding: '8px 0',
                  borderBottom: i < topProjects.length - 1 ? '1px solid #f5f5f5' : 'none',
                  cursor: 'pointer',
                }}
                onClick={() => onNavigate('projects-overview')}
              >
                <span style={{ width: 24, fontWeight: 700, color: i < 3 ? '#1890ff' : '#999' }}>#{i + 1}</span>
                <span style={{ flex: 1, fontWeight: 500, fontSize: 14 }}>{p.owner}/{p.repo}</span>
                <div style={{ flex: 2, margin: '0 16px' }}>
                  <Progress
                    percent={Math.round((p.total / maxTotal) * 100)}
                    showInfo={false}
                    strokeColor={i === 0 ? '#1890ff' : i === 1 ? '#52c41a' : '#faad14'}
                    size="small"
                  />
                </div>
                <Space size={4}>
                  {p.pr_count > 0 && <Tooltip title="PR"><Tag color="blue" style={{ margin: 0 }}>{p.pr_count}</Tag></Tooltip>}
                  {p.commits_count > 0 && <Tooltip title="Commits"><Tag color="orange" style={{ margin: 0 }}>{p.commits_count}</Tag></Tooltip>}
                  {p.comments_count > 0 && <Tooltip title="评论"><Tag color="gold" style={{ margin: 0 }}>{p.comments_count}</Tag></Tooltip>}
                  {p.issues_count > 0 && <Tooltip title="Issues"><Tag color="pink" style={{ margin: 0 }}>{p.issues_count}</Tag></Tooltip>}
                </Space>
              </div>
            )) : <div style={{ color: '#999', textAlign: 'center', padding: 20 }}>暂无项目数据</div>}
          </Card>
        </Col>

        <Col xs={24} lg={10}>
          <Card
            title={<span><ThunderboltOutlined style={{ marginRight: 8 }} />快捷导航</span>}
            bodyStyle={{ padding: '8px 16px' }}
          >
            {quickNav.map((item, i) => (
              <div
                key={i}
                onClick={() => onNavigate(item.page)}
                style={{
                  display: 'flex', alignItems: 'center', padding: '10px 8px',
                  borderBottom: i < quickNav.length - 1 ? '1px solid #f5f5f5' : 'none',
                  cursor: 'pointer', borderRadius: 4,
                }}
                onMouseEnter={e => e.currentTarget.style.background = '#f0f5ff'}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
              >
                <span style={{ fontSize: 18, marginRight: 12, color: '#1890ff' }}>{item.icon}</span>
                <span style={{ flex: 1 }}>
                  <div style={{ fontWeight: 500 }}>{item.label}</div>
                  <div style={{ fontSize: 12, color: '#999' }}>{item.desc}</div>
                </span>
                <RightOutlined style={{ color: '#ccc' }} />
              </div>
            ))}
          </Card>

          <Card
            title={<span><BarChartOutlined style={{ marginRight: 8 }} />数据分布</span>}
            style={{ marginTop: 16 }}
            bodyStyle={{ padding: '12px 16px' }}
          >
            <Space wrap size={[8, 8]}>
              {statCards.map((item, i) => (
                <Tag key={i} color={item.color} style={{ fontSize: 12, padding: '3px 8px' }}>
                  {item.title}: {typeof item.value === 'number' ? item.value.toLocaleString() : item.value}
                </Tag>
              ))}
              <Tag color="#fa541c" style={{ fontSize: 12, padding: '3px 8px' }}>
                开发者项目: {(stats?.user_contributed_repos_count || 0).toLocaleString()}
              </Tag>
            </Space>
          </Card>
        </Col>
      </Row>

      {/* ===== 新增 Row 3：PR 状态分布 + 最近活动时间线 ===== */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={10}>
          <Card
            title={<span><BarChartOutlined style={{ marginRight: 8 }} />PR 状态分布</span>}
            bodyStyle={{ padding: '16px' }}
          >
            {pieData.length > 0 ? (
              <div style={{ textAlign: 'center' }}>
                <ResponsiveContainer width="100%" height={200}>
                  <PieChart>
                    <Pie
                      data={pieData}
                      cx="50%"
                      cy="50%"
                      innerRadius={55}
                      outerRadius={90}
                      dataKey="value"
                      paddingAngle={2}
                    >
                      {pieData.map((entry, i) => (
                        <Cell key={i} fill={entry.color} />
                      ))}
                    </Pie>
                    <RTooltip formatter={(val) => val.toLocaleString()} />
                  </PieChart>
                </ResponsiveContainer>
                <Space wrap size={[12, 8]} style={{ marginTop: 8 }}>
                  {pieData.map((item, i) => (
                    <Tag key={i} style={{ fontSize: 13, padding: '2px 10px' }}>
                      <span style={{
                        display: 'inline-block', width: 10, height: 10,
                        borderRadius: '50%', background: item.color, marginRight: 6,
                      }} />
                      {item.name}: {item.value.toLocaleString()}
                    </Tag>
                  ))}
                </Space>
              </div>
            ) : (
              <div style={{ color: '#999', textAlign: 'center', padding: 40 }}>暂无 PR 状态数据</div>
            )}
          </Card>
        </Col>

        <Col xs={24} lg={14}>
          <Card
            title={<span><HistoryOutlined style={{ marginRight: 8 }} />最近活动</span>}
            extra={activities.length > 0 && <a onClick={() => onNavigate('aggregate')}>查看更多 <RightOutlined /></a>}
            bodyStyle={{ padding: '12px 20px', maxHeight: 360, overflowY: 'auto' }}
          >
            {activities.length > 0 ? (
              <Timeline
                items={activities.slice(0, 12).map((act, i) => {
                  const cfg = activityConfig[act.type] || { color: '#999', icon: <ClockCircleOutlined />, label: act.type }
                  return {
                    color: cfg.color,
                    children: (
                      <div key={i} style={{ fontSize: 13 }}>
                        <div>
                          <span style={{ color: '#666', marginRight: 8 }}>{formatTimeAgo(act.created_at)}</span>
                          <span style={{ fontWeight: 500 }}>{act.user}</span>
                          <span style={{ color: '#999', margin: '0 4px' }}>{cfg.label}</span>
                          <Tag color={cfg.color} style={{ fontSize: 11, margin: 0, padding: '0 4px' }}>
                            {cfg.label}
                          </Tag>
                        </div>
                        <div style={{ color: '#555', marginTop: 2 }}>
                          {act.type === 'comment'
                            ? <span>"{act.body_preview}" — {act.owner}/{act.repo}#{act.pr_number}</span>
                            : <span>{act.title || `#${act.number}`} — {act.owner}/{act.repo}</span>
                          }
                        </div>
                      </div>
                    ),
                  }
                })}
              />
            ) : (
              <div style={{ color: '#999', textAlign: 'center', padding: 40 }}>暂无活动记录</div>
            )}
          </Card>
        </Col>
      </Row>

      {/* ===== 新增 Row 4：贡献者排行 + 项目健康度快照 ===== */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={10}>
          <Card
            title={<span><TrophyOutlined style={{ marginRight: 8 }} />贡献者排行</span>}
            extra={
              <Segmented
                size="small"
                options={sortOptions}
                value={contributorSort}
                onChange={setContributorSort}
              />
            }
            bodyStyle={{ padding: '12px 20px' }}
          >
            {contributors.length > 0 ? contributors.map((c, i) => (
              <div
                key={i}
                style={{
                  display: 'flex', alignItems: 'center', padding: '8px 0',
                  borderBottom: i < contributors.length - 1 ? '1px solid #f5f5f5' : 'none',
                }}
              >
                <span style={{ width: 28, fontWeight: 700, color: i < 3 ? '#1890ff' : '#999', fontSize: 14 }}>
                  {i < 3 ? ['🥇', '🥈', '🥉'][i] : `#${i + 1}`}
                </span>
                <span style={{ flex: 1, fontWeight: 500 }}>{c.user}</span>
                <div style={{ flex: 2, margin: '0 12px' }}>
                  <Progress
                    percent={Math.round((c.total_activity / maxContributorActivity) * 100)}
                    showInfo={false}
                    strokeColor={i === 0 ? '#1890ff' : i === 1 ? '#52c41a' : '#faad14'}
                    size="small"
                  />
                </div>
                <Space size={4}>
                  {c.pr_count > 0 && <Tooltip title="PR"><Tag color="blue" style={{ margin: 0, fontSize: 11 }}>{c.pr_count}</Tag></Tooltip>}
                  {c.comment_count > 0 && <Tooltip title="评论"><Tag color="gold" style={{ margin: 0, fontSize: 11 }}>{c.comment_count}</Tag></Tooltip>}
                  {c.issue_count > 0 && <Tooltip title="Issue"><Tag color="pink" style={{ margin: 0, fontSize: 11 }}>{c.issue_count}</Tag></Tooltip>}
                </Space>
              </div>
            )) : (
              <div style={{ color: '#999', textAlign: 'center', padding: 20 }}>暂无贡献者数据</div>
            )}
          </Card>
        </Col>

        <Col xs={24} lg={14}>
          <Card
            title={<span><HeartFilled style={{ marginRight: 8, color: '#eb2f96' }} />项目健康度快照</span>}
            extra={<a onClick={() => onNavigate('aggregate')}>详情 <RightOutlined /></a>}
            bodyStyle={{ padding: '12px 16px' }}
          >
            {healthSnapshots.length > 0 ? (
              <Row gutter={[12, 12]}>
                {healthSnapshots.map((h, i) => (
                  <Col xs={12} md={8} key={i}>
                    <Card
                      hoverable
                      size="small"
                      onClick={() => onNavigate('aggregate')}
                      style={{
                        textAlign: 'center',
                        borderLeft: `3px solid ${GRADE_COLORS[h.overall_grade] || '#d9d9d9'}`,
                        cursor: 'pointer',
                      }}
                      bodyStyle={{ padding: '12px 8px' }}
                    >
                      <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 8, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {h.owner}/{h.repo}
                      </div>
                      {h.data_available ? (
                        <>
                          <Progress
                            type="circle"
                            percent={Math.round(h.overall_score)}
                            size={64}
                            strokeColor={GRADE_COLORS[h.overall_grade] || '#1890ff'}
                            format={percent => <span style={{ fontSize: 16, fontWeight: 700 }}>{percent}</span>}
                          />
                          <div style={{ marginTop: 6 }}>
                            <Tag color={GRADE_COLORS[h.overall_grade] === '#52c41a' ? 'success' : GRADE_COLORS[h.overall_grade] === '#1890ff' ? 'processing' : 'warning'} style={{ fontWeight: 600 }}>
                              {h.overall_grade}
                            </Tag>
                          </div>
                        </>
                      ) : (
                        <div style={{ color: '#d9d9d9', padding: '18px 0' }}>
                          <ExclamationCircleOutlined style={{ fontSize: 24 }} />
                          <div style={{ fontSize: 12, marginTop: 4 }}>数据不足</div>
                        </div>
                      )}
                    </Card>
                  </Col>
                ))}
              </Row>
            ) : (
              <div style={{ color: '#999', textAlign: 'center', padding: 20 }}>暂无健康度数据</div>
            )}
          </Card>
        </Col>
      </Row>
    </div>
  )
}
