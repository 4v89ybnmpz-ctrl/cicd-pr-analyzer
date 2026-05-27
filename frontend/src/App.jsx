import { useState, useRef } from 'react'
import { Layout, Menu, theme, ConfigProvider, Segmented, Result, Button, Tag } from 'antd'
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
  SwapOutlined,
  DatabaseOutlined,
  PieChartOutlined,
  CodeSandboxOutlined,
  ToolOutlined,
  DownloadOutlined,
  GlobalOutlined,
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
import Settings from './pages/Settings'
import NotificationHistory from './pages/NotificationHistory'
import DataExport from './pages/DataExport'
import ProjectCompare from './pages/ProjectCompare'
import GitCodeMrList from './pages/gitcode/MrList'
import GitCodeMrDetails from './pages/gitcode/MrDetails'
import GitCodeMrComments from './pages/gitcode/MrComments'

const { Header, Sider, Content } = Layout

// ==================== GitHub 菜单 ====================
const GITHUB_MENU = [
  { key: 'dashboard', icon: <DashboardOutlined />, label: '概览' },
  { key: 'projects-overview', icon: <AppstoreOutlined />, label: '项目总览' },
  {
    key: 'group-data', icon: <DatabaseOutlined />, label: '数据管理',
    children: [
      { key: 'prs', icon: <FileTextOutlined />, label: 'PR 列表' },
      { key: 'details', icon: <ProfileOutlined />, label: 'PR 详情' },
      { key: 'comments', icon: <CommentOutlined />, label: 'PR 评论' },
      { key: 'issues', icon: <AlertOutlined />, label: 'Issues' },
      { key: 'issue-timelines', icon: <ClockCircleOutlined />, label: 'Issue Timelines' },
      { key: 'git-log', icon: <BranchesOutlined />, label: 'Git Log' },
      { key: 'aggregate', icon: <BarChartOutlined />, label: '聚合统计' },
    ],
  },
  {
    key: 'group-analysis', icon: <PieChartOutlined />, label: '质量分析',
    children: [
      { key: 'review-quality', icon: <AuditOutlined />, label: 'Review 质量' },
      { key: 'project-health', icon: <HeartOutlined />, label: '项目健康度' },
      { key: 'trend-alerts', icon: <BellOutlined />, label: '趋势预警' },
      { key: 'project-compare', icon: <SwapOutlined />, label: '多仓库对比' },
    ],
  },
  {
    key: 'group-code', icon: <CodeSandboxOutlined />, label: '代码洞察',
    children: [
      { key: 'code-heatmap', icon: <HeatMapOutlined />, label: '变更热力图' },
      { key: 'code-insight', icon: <CodeOutlined />, label: '变更洞察' },
    ],
  },
  {
    key: 'group-people', icon: <TeamOutlined />, label: '开发者',
    children: [
      { key: 'profiles', icon: <UserOutlined />, label: '评论者 Profile' },
      { key: 'dev-relations', icon: <TeamOutlined />, label: '开发者关系' },
    ],
  },
  { key: 'agent-studio', icon: <RobotOutlined />, label: 'Agent 工作室' },
  {
    key: 'group-system', icon: <ToolOutlined />, label: '系统管理',
    children: [
      { key: 'tasks', icon: <ThunderboltOutlined />, label: '任务监控' },
      { key: 'data-export', icon: <DownloadOutlined />, label: '数据导出' },
      { key: 'notification-history', icon: <BellOutlined />, label: '通知历史' },
      { key: 'settings', icon: <SettingOutlined />, label: '系统设置' },
    ],
  },
]

// ==================== GitCode 菜单 ====================
const GITCODE_MENU = [
  { key: 'gc-dashboard', icon: <DashboardOutlined />, label: '概览' },
  {
    key: 'gc-group-data', icon: <DatabaseOutlined />, label: '数据管理',
    children: [
      { key: 'gc-mrs', icon: <BranchesOutlined />, label: 'MR 列表' },
      { key: 'gc-details', icon: <ProfileOutlined />, label: 'MR 详情' },
      { key: 'gc-comments', icon: <CommentOutlined />, label: 'MR 评论' },
    ],
  },
]

const MENUS = { github: GITHUB_MENU, gitcode: GITCODE_MENU }

// 构建 page key → group key 的映射
function buildPageToGroup(menu) {
  const map = {}
  menu.forEach(item => {
    if (item.children) {
      item.children.forEach(child => { map[child.key] = item.key })
    }
  })
  return map
}
const GITHUB_PAGE_TO_GROUP = buildPageToGroup(GITHUB_MENU)
const GITCODE_PAGE_TO_GROUP = buildPageToGroup(GITCODE_MENU)

// 旧 key 映射
const SETTINGS_KEYS = new Set(['llm-config', 'notification-config', 'webhook-manager'])

// GitCode 占位页
function GitCodePlaceholder() {
  return (
    <Result
      status="info"
      title="GitCode 平台"
      subTitle="功能开发中，敬请期待"
      extra={<Tag color="purple">gitcode.net</Tag>}
    />
  )
}

function App() {
  const savedPage = localStorage.getItem('currentPage') || 'dashboard'
  const resolvedPage = SETTINGS_KEYS.has(savedPage) ? 'settings' : savedPage
  const initPlatform = resolvedPage.startsWith('gc-')
    ? 'gitcode'
    : (localStorage.getItem('currentPlatform') || 'github')

  const [platform, setPlatform] = useState(initPlatform)
  const defaultPage = platform === 'gitcode' ? 'gc-dashboard' : 'dashboard'
  const [page, setPage] = useState(
    platform === 'gitcode' ? (resolvedPage.startsWith('gc-') ? resolvedPage : 'gc-dashboard')
    : resolvedPage
  )
  const [openKeys, setOpenKeys] = useState(() => {
    const map = platform === 'gitcode' ? GITCODE_PAGE_TO_GROUP : GITHUB_PAGE_TO_GROUP
    const group = map[page]
    return group ? [group] : []
  })
  const [prDataFilter, setPrDataFilter] = useState(null)
  const [userReposUsername, setUserReposUsername] = useState('')
  const githubVisited = useRef(new Set())
  const gitcodeVisited = useRef(new Set([page]))
  // 初始标记
  if (platform === 'github') githubVisited.current.add(page)
  else gitcodeVisited.current.add(page)

  const getVisitedRef = () => platform === 'github' ? githubVisited : gitcodeVisited

  const navigate = (key, username, extra) => {
    const target = SETTINGS_KEYS.has(key) ? 'settings' : key
    setPage(target)
    localStorage.setItem('currentPage', target)
    getVisitedRef().current.add(target)
    const map = platform === 'gitcode' ? GITCODE_PAGE_TO_GROUP : GITHUB_PAGE_TO_GROUP
    const group = map[target]
    if (group && !openKeys.includes(group)) setOpenKeys([...openKeys, group])
    if (username) setUserReposUsername(username)
    if (extra && extra.owner && extra.repo) setPrDataFilter({ owner: extra.owner, repo: extra.repo })
  }

  const handlePageChange = (key) => {
    setPage(key)
    localStorage.setItem('currentPage', key)
    getVisitedRef().current.add(key)
    const map = platform === 'gitcode' ? GITCODE_PAGE_TO_GROUP : GITHUB_PAGE_TO_GROUP
    const group = map[key]
    if (group && !openKeys.includes(group)) setOpenKeys([...openKeys, group])
  }

  const handleOpenChange = (keys) => { setOpenKeys(keys) }

  const handlePlatformChange = (val) => {
    setPlatform(val)
    localStorage.setItem('currentPlatform', val)
    const newDefault = val === 'gitcode' ? 'gc-dashboard' : 'dashboard'
    setPage(newDefault)
    localStorage.setItem('currentPage', newDefault)
    getVisitedRef().current.add(newDefault)
    setOpenKeys([])
  }

  // GitHub 页面组件
  const githubPages = {
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
    'settings': <Settings />,
    'data-export': <DataExport />,
    'notification-history': <NotificationHistory />,
    'project-compare': <ProjectCompare />,
    'tasks': <Tasks />,
    'user-repos': <UserRepos username={userReposUsername} onBack={() => setPage('profiles')} />,
    'aggregate': <Aggregate />,
  }

  // GitCode 页面组件（独立，不共享 GitHub 页面）
  const gitcodePages = {
    'gc-dashboard': <GitCodePlaceholder />,
    'gc-mrs': <GitCodeMrList />,
    'gc-details': <GitCodeMrDetails />,
    'gc-comments': <GitCodeMrComments />,
  }

  const activePages = platform === 'gitcode' ? gitcodePages : githubPages
  const visitedRef = getVisitedRef()

  return (
    <ConfigProvider theme={{ algorithm: theme.defaultAlgorithm }}>
      <Layout style={{ minHeight: '100vh' }}>
        <Sider width={220} style={{ background: '#fff' }}>
          <div style={{ height: 48, display: 'flex', alignItems: 'center', justifyContent: 'center', borderBottom: '1px solid #f0f0f0' }}>
            <h2 style={{ margin: 0, color: '#1890ff' }}>PR Analyzer</h2>
          </div>
          <div style={{ padding: '8px 16px 12px', borderBottom: '1px solid #f0f0f0' }}>
            <Segmented
              block
              value={platform}
              options={[
                { value: 'github', label: 'GitHub' },
                { value: 'gitcode', label: 'GitCode' },
              ]}
              onChange={handlePlatformChange}
            />
          </div>
          <Menu
            mode="inline"
            selectedKeys={[page]}
            openKeys={openKeys}
            onOpenChange={handleOpenChange}
            items={MENUS[platform]}
            onClick={({ key }) => handlePageChange(key)}
            style={{ borderRight: 0 }}
          />
        </Sider>
        <Layout>
          <Header style={{ background: '#fff', padding: '0 24px', borderBottom: '1px solid #f0f0f0', display: 'flex', alignItems: 'center' }}>
            <h2 style={{ margin: 0 }}>{platform === 'gitcode' ? 'GitCode' : 'GitHub'} 数据分析平台</h2>
          </Header>
          <Content style={{ margin: 24, padding: 24, background: '#fff', borderRadius: 8, minHeight: 280 }}>
            {Object.entries(activePages).map(([key, component]) => (
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
