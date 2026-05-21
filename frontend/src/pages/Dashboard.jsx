import { useState, useEffect } from 'react'
import { Card, Statistic, Row, Col, Spin, Alert, Tag, Space } from 'antd'
import {
  DatabaseOutlined, FileTextOutlined, CommentOutlined, CheckCircleOutlined,
  AlertOutlined, ClockCircleOutlined, UserOutlined, ThunderboltOutlined,
} from '@ant-design/icons'
import * as api from '../api'

export default function Dashboard({ onNavigate }) {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.getDatabaseStats()
      .then(res => setStats(res.data.stats))
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />
  if (error) return <Alert type="error" message={error} />

  const cards = [
    { title: 'PR 数据', value: stats?.pr_data_count || 0, icon: <FileTextOutlined />, color: '#1890ff', page: 'prs', desc: '按仓库分组的 PR 概览' },
    { title: 'PR 详情', value: stats?.pr_details_count || 0, icon: <DatabaseOutlined />, color: '#52c41a', page: 'details', desc: '单个 PR 的详细信息' },
    { title: 'PR 评论', value: stats?.pr_comments_count || 0, icon: <CommentOutlined />, color: '#faad14', page: 'comments', desc: '逐条存储的评论数据' },
    { title: 'Issues', value: stats?.issues_count || 0, icon: <AlertOutlined />, color: '#eb2f96', page: 'issues', desc: 'GitHub Issues 数据' },
    { title: 'Issue Timelines', value: stats?.issue_timelines_count || 0, icon: <ClockCircleOutlined />, color: '#722ed1', page: 'issue-timelines', desc: 'Issue/PR 的 Timeline 事件' },
    { title: '评论者 Profile', value: stats?.user_profiles_count || 0, icon: <UserOutlined />, color: '#13c2c2', page: 'profiles', desc: '开发者的 GitHub Profile' },
    { title: '数据库', value: stats?.status === 'connected' ? '已连接' : '未连接', icon: <CheckCircleOutlined />, color: stats?.status === 'connected' ? '#52c41a' : '#ff4d4f', desc: stats?.database },
  ]

  return (
    <div>
      <h2 style={{ marginBottom: 24 }}>数据库概览</h2>

      <Row gutter={[16, 16]}>
        {cards.map((item, i) => (
          <Col xs={24} sm={12} md={8} lg={6} key={i}>
            <Card
              hoverable={!!item.page}
              onClick={() => item.page && onNavigate(item.page)}
              style={{ cursor: item.page ? 'pointer' : 'default' }}
            >
              <Statistic
                title={item.title}
                value={item.value}
                prefix={item.icon}
                valueStyle={{ color: item.color, fontSize: item.page ? 24 : 18 }}
              />
              <div style={{ marginTop: 8, color: '#999', fontSize: 12 }}>{item.desc}</div>
            </Card>
          </Col>
        ))}
      </Row>

      <Card title="数据分布" style={{ marginTop: 24 }}>
        <Row gutter={[16, 12]}>
          <Col span={24}>
            <Space size={8} wrap>
              {[
                { label: 'PR 数据', count: stats?.pr_data_count || 0, color: '#1890ff' },
                { label: 'PR 详情', count: stats?.pr_details_count || 0, color: '#52c41a' },
                { label: 'PR 评论', count: stats?.pr_comments_count || 0, color: '#faad14' },
                { label: 'Issues', count: stats?.issues_count || 0, color: '#eb2f96' },
                { label: 'Timelines', count: stats?.issue_timelines_count || 0, color: '#722ed1' },
                { label: 'Profiles', count: stats?.user_profiles_count || 0, color: '#13c2c2' },
                { label: '开发者项目', count: stats?.user_contributed_repos_count || 0, color: '#fa541c' },
              ].map((item, i) => (
                <Tag key={i} color={item.color} style={{ fontSize: 13, padding: '4px 10px', margin: 2 }}>
                  {item.label}: {item.count}
                </Tag>
              ))}
            </Space>
          </Col>
        </Row>
      </Card>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} md={12}>
          <Card title="快捷操作" size="small">
            <Space direction="vertical" style={{ width: '100%' }}>
              {[
                { label: '获取 PR 数据', page: 'prs' },
                { label: '获取 Issues', page: 'issues' },
                { label: '获取 Timelines', page: 'issue-timelines' },
                { label: '获取评论者 Profile', page: 'profiles' },
                { label: '任务监控', page: 'tasks' },
              ].map((item, i) => (
                <a key={i} onClick={() => onNavigate(item.page)} style={{ display: 'block', cursor: 'pointer' }}>
                  {item.label} →
                </a>
              ))}
            </Space>
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card title="功能说明" size="small">
            <Space direction="vertical" style={{ width: '100%', color: '#666', fontSize: 13 }}>
              <span>1. 在各页面点击"获取"按钮会创建异步任务并跳转到任务监控页</span>
              <span>2. 重复提交同一任务会提示"正在进行中"</span>
              <span>3. 点击开发者 Profile 的"项目"按钮可查看其参与的项目</span>
              <span>4. Timeline 数据同时包含 Issue 和 PR 的事件</span>
              <span>5. 开发者区域基于 location/blog 自动推断</span>
            </Space>
          </Card>
        </Col>
      </Row>
    </div>
  )
}
