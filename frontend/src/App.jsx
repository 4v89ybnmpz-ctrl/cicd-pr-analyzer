import { useState, useRef } from 'react'
import { Layout, Menu, theme, ConfigProvider } from 'antd'
import {
  DashboardOutlined,
  FileTextOutlined,
  ProfileOutlined,
  CommentOutlined,
  BarChartOutlined,
  UserOutlined,
  AlertOutlined,
  ClockCircleOutlined,
  ThunderboltOutlined,
  AppstoreOutlined,
  BranchesOutlined,
  TeamOutlined,
  RobotOutlined,
  AuditOutlined,
  HeartOutlined,
  BellOutlined,
  HeatMapOutlined,
  CodeOutlined,
  SettingOutlined,
} from '@ant-design/icons'
import Dashboard from './pages/Dashboard'
import PrList from './pages/PrList'
import PrData from './pages/PrData'
import PrDetails from './pages/PrDetails'
import Comments from './pages/Comments'
import Aggregate from './pages/Aggregate'
import Profiles from './pages/Profiles'
import Issues from './pages/Issues'
import IssueTimelines from './pages/IssueTimelines'
import Tasks from './pages/Tasks'
import UserRepos from './pages/UserRepos'
import ProjectsOverview from './pages/ProjectsOverview'
import GitLog from './pages/GitLog'
import DeveloperRelations from './pages/DeveloperRelations'
import AgentStudio from './pages/AgentStudio'
import ReviewQuality from './pages/ReviewQuality'
import ProjectHealth from './pages/ProjectHealth'
import TrendAlerts from './pages/TrendAlerts'
import CodeHeatmap from './pages/CodeHeatmap'
import CodeInsight from './pages/CodeInsight'
import LlmConfig from './pages/LlmConfig'

const { Header, Sider, Content } = Layout

const menuItems = [
  { key: 'dashboard', icon: <DashboardOutlined />, label: '概览' },
  { key: 'projects-overview', icon: <AppstoreOutlined />, label: '项目总览' },
  { key: 'prs', icon: <FileTextOutlined />, label: 'PR 列表' },
  { key: 'details', icon: <ProfileOutlined />, label: 'PR 详情' },
  { key: 'comments', icon: <CommentOutlined />, label: 'PR 评论' },
  { key: 'profiles', icon: <UserOutlined />, label: '评论者 Profile' },
  { key: 'issues', icon: <AlertOutlined />, label: 'Issues' },
  { key: 'issue-timelines', icon: <ClockCircleOutlined />, label: 'Issue Timelines' },
  { key: 'git-log', icon: <BranchesOutlined />, label: 'Git Log' },
  { key: 'dev-relations', icon: <TeamOutlined />, label: '开发者关系' },
  { key: 'review-quality', icon: <AuditOutlined />, label: 'Review 质量' },
  { key: 'project-health', icon: <HeartOutlined />, label: '项目健康度' },
  { key: 'trend-alerts', icon: <BellOutlined />, label: '趋势预警' },
  { key: 'code-heatmap', icon: <HeatMapOutlined />, label: '变更热力图' },
  { key: 'code-insight', icon: <CodeOutlined />, label: '变更洞察' },
  { key: 'agent-studio', icon: <RobotOutlined />, label: 'Agent 工作室' },
  { key: 'llm-config', icon: <SettingOutlined />, label: 'AI 配置' },
  { key: 'aggregate', icon: <BarChartOutlined />, label: '聚合统计' },
  { key: 'tasks', icon: <ThunderboltOutlined />, label: '任务监控' },
]

function App() {
  const [page, setPage] = useState(() => localStorage.getItem('currentPage') || 'dashboard')
  const [prDataFilter, setPrDataFilter] = useState(null)
  const [userReposUsername, setUserReposUsername] = useState('')
  const visitedRef = useRef(new Set([localStorage.getItem('currentPage') || 'dashboard']))

  const navigate = (key, username, extra) => {
    setPage(key)
    localStorage.setItem('currentPage', key)
    visitedRef.current.add(key)
    if (username) setUserReposUsername(username)
    if (extra && extra.owner && extra.repo) setPrDataFilter({ owner: extra.owner, repo: extra.repo })
  }

  const handlePageChange = (key) => {
    setPage(key)
    localStorage.setItem('currentPage', key)
    visitedRef.current.add(key)
  }

  // 所有页面组件
  const pages = {
    'dashboard': <Dashboard onNavigate={navigate} />,
    'projects-overview': <ProjectsOverview />,
    'prs': <PrList onNavigate={navigate} setFilter={setPrDataFilter} />,
    'prdata': <PrData filter={prDataFilter} onBack={() => setPage('prs')} />,
    'details': <PrDetails />,
    'comments': <Comments />,
    'profiles': <Profiles onNavigate={navigate} />,
    'issues': <Issues onNavigate={navigate} />,
    'issue-timelines': <IssueTimelines onNavigate={navigate} />,
    'git-log': <GitLog />,
    'dev-relations': <DeveloperRelations />,
    'review-quality': <ReviewQuality />,
    'project-health': <ProjectHealth />,
    'trend-alerts': <TrendAlerts />,
    'code-heatmap': <CodeHeatmap />,
    'code-insight': <CodeInsight onNavigate={navigate} />,
    'agent-studio': <AgentStudio onNavigate={navigate} />,
    'llm-config': <LlmConfig />,
    'tasks': <Tasks />,
    'user-repos': <UserRepos username={userReposUsername} onBack={() => setPage('profiles')} />,
    'aggregate': <Aggregate />,
  }

  return (
    <ConfigProvider theme={{ algorithm: theme.defaultAlgorithm }}>
      <Layout style={{ minHeight: '100vh' }}>
        <Sider width={200} style={{ background: '#fff' }}>
          <div style={{ height: 64, display: 'flex', alignItems: 'center', justifyContent: 'center', borderBottom: '1px solid #f0f0f0' }}>
            <h2 style={{ margin: 0, color: '#1890ff' }}>PR Analyzer</h2>
          </div>
          <Menu
            mode="inline"
            selectedKeys={[page]}
            items={menuItems}
            onClick={({ key }) => handlePageChange(key)}
            style={{ borderRight: 0 }}
          />
        </Sider>
        <Layout>
          <Header style={{ background: '#fff', padding: '0 24px', borderBottom: '1px solid #f0f0f0', display: 'flex', alignItems: 'center' }}>
            <h2 style={{ margin: 0 }}>GitHub PR 数据分析平台</h2>
          </Header>
          <Content style={{ margin: 24, padding: 24, background: '#fff', borderRadius: 8, minHeight: 280 }}>
            {Object.entries(pages).map(([key, component]) => (
              <div key={key} style={{ display: key === page ? 'block' : 'none' }}>
                {visitedRef.current.has(key) ? component : null}
              </div>
            ))}
          </Content>
        </Layout>
      </Layout>
    </ConfigProvider>
  )
}

export default App
