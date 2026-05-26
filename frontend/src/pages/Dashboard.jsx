import { useState, useEffect } from 'react'
import { Card, Statistic, Row, Col, Spin, Alert, Tag, Space, Progress, Tooltip, Button } from 'antd'
import {
  DatabaseOutlined, FileTextOutlined, CommentOutlined, CheckCircleOutlined,
  AlertOutlined, ClockCircleOutlined, UserOutlined, ThunderboltOutlined,
  RightOutlined, AppstoreOutlined, BranchesOutlined, TeamOutlined,
  BarChartOutlined, RocketOutlined, GlobalOutlined,
} from '@ant-design/icons'
import * as api from '../api'

export default function Dashboard({ onNavigate }) {
  const [stats, setStats] = useState(null)
  const [overview, setOverview] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    Promise.all([
      api.getDatabaseStats().then(res => res.data.stats).catch(() => null),
      api.getProjectsOverview().then(res => res.data.projects || []).catch(() => []),
    ]).then(([s, p]) => {
      setStats(s)
      setOverview(p)
    }).catch(err => setError(err.message))
    .finally(() => setLoading(false))
  }, [])

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

  return (
    <div>
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
    </div>
  )
}
