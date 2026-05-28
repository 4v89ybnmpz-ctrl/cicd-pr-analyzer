import { useState, useRef } from 'react'
import { Layout, Menu, theme, ConfigProvider, Result, Tag, Divider } from 'antd'
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
  GithubOutlined,
  CloudOutlined,
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
import AtomGitPullList from './pages/atomgit/PullList'
import AtomGitPullDetail from './pages/atomgit/PullDetail'
import AtomGitPullComments from './pages/atomgit/PullComments'
import AtomGitPullReviews from './pages/atomgit/PullReviews'
import AtomGitPullCommits from './pages/atomgit/PullCommits'
import AtomGitPullFiles from './pages/atomgit/PullFiles'
import AtomGitPullTimeline from './pages/atomgit/PullTimeline'
import AtomGitIssueList from './pages/atomgit/IssueList'
import AtomGitOverview from './pages/atomgit/Overview'
import CannbotSkills from './pages/CannbotSkills'

const { Header, Sider, Content } = Layout

// ==================== 平台配置 ====================
const PLATFORMS = {
  github: { label: 'GitHub', icon: <GithubOutlined />, color: '#24292f' },
  gitcode: { label: 'GitCode', icon: <GlobalOutlined />, color: '#7c3aed' },
  atomgit: { label: 'AtomGit', icon: <CloudOutlined />, color: '#1677ff' },
}

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

// ==================== AtomGit 菜单 ====================
const ATOMGIT_MENU = [
  { key: 'ag-overview', icon: <AppstoreOutlined />, label: '项目总览' },
  { key: 'ag-dashboard', icon: <DashboardOutlined />, label: '概览' },
  {
    key: 'ag-group-data', icon: <DatabaseOutlined />, label: '数据管理',
    children: [
      { key: 'ag-pulls', icon: <BranchesOutlined />, label: 'PR 列表' },
      { key: 'ag-detail', icon: <ProfileOutlined />, label: 'PR 详情' },
      { key: 'ag-comments', icon: <CommentOutlined />, label: 'PR 评论' },
      { key: 'ag-reviews', icon: <AuditOutlined />, label: 'PR Reviews' },
      { key: 'ag-commits', icon: <CodeOutlined />, label: 'PR Commits' },
      { key: 'ag-files', icon: <FileTextOutlined />, label: 'PR 变更文件' },
      { key: 'ag-timeline', icon: <ClockCircleOutlined />, label: 'PR 时间线' },
      { key: 'ag-issues', icon: <AlertOutlined />, label: 'Issues' },
    ],
  },
]

// ==================== 跨平台共享菜单 ====================
const SHARED_MENU = [
  { key: 'cannbot-skills', icon: <RobotOutlined />, label: 'CANN 技能库' },
  { key: 'shared-system', icon: <ToolOutlined />, label: '系统管理',
    children: [
      { key: 'tasks', icon: <ThunderboltOutlined />, label: '任务监控' },
      { key: 'data-export', icon: <DownloadOutlined />, label: '数据导出' },
      { key: 'notification-history', icon: <BellOutlined />, label: '通知历史' },
      { key: 'settings', icon: <SettingOutlined />, label: '系统设置' },
    ],
  },
]

const PLATFORM_MENUS = { github: GITHUB_MENU, gitcode: GITCODE_MENU, atomgit: ATOMGIT_MENU }

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
const GITHUB_PAGE_TO_GROUP = buildPageToGroup([...GITHUB_MENU, ...SHARED_MENU])
const GITCODE_PAGE_TO_GROUP = buildPageToGroup([...GITCODE_MENU, ...SHARED_MENU])
const ATOMGIT_PAGE_TO_GROUP = buildPageToGroup([...ATOMGIT_MENU, ...SHARED_MENU])

// 旧 key 映射
const SETTINGS_KEYS = new Set(['llm-config', 'notification-config', 'webhook-manager'])

// 占位页
function PlatformPlaceholder({ name, color }) {
  return (
    <Result
      status="info"
      title={`${name} 平台`}
      subTitle="功能开发中，敬请期待"
      extra={<Tag color={color}>{name.toLowerCase()}</Tag>}
    />
  )
}

function App() {
  const savedPage = localStorage.getItem('currentPage') || 'dashboard'
  const resolvedPage = SETTINGS_KEYS.has(savedPage) ? 'settings' : savedPage
  const initPlatform = resolvedPage.startsWith('gc-')
    ? 'gitcode'
    : resolvedPage.startsWith('ag-')
    ? 'atomgit'
    : (localStorage.getItem('currentPlatform') || 'github')

  const [platform, setPlatform] = useState(initPlatform)
  const defaultPage = platform === 'gitcode' ? 'gc-dashboard' : platform === 'atomgit' ? 'ag-overview' : 'dashboard'
  const [page, setPage] = useState(
    platform === 'gitcode' ? (resolvedPage.startsWith('gc-') ? resolvedPage : 'gc-dashboard')
    : platform === 'atomgit' ? (resolvedPage.startsWith('ag-') ? resolvedPage : 'ag-overview')
    : resolvedPage
  )
  const [openKeys, setOpenKeys] = useState(() => {
    const map = platform === 'gitcode' ? GITCODE_PAGE_TO_GROUP : platform === 'atomgit' ? ATOMGIT_PAGE_TO_GROUP : GITHUB_PAGE_TO_GROUP
    const group = map[page]
    return group ? [group] : []
  })
  const [prDataFilter, setPrDataFilter] = useState(null)
  const [userReposUsername, setUserReposUsername] = useState('')
  const githubVisited = useRef(new Set())
  const gitcodeVisited = useRef(new Set([page]))
  const atomgitVisited = useRef(new Set([page]))
  if (platform === 'github') githubVisited.current.add(page)
  else if (platform === 'gitcode') gitcodeVisited.current.add(page)
  else atomgitVisited.current.add(page)

  const getVisitedRef = () => platform === 'github' ? githubVisited : platform === 'gitcode' ? gitcodeVisited : atomgitVisited
  const getPageToGroup = () => platform === 'gitcode' ? GITCODE_PAGE_TO_GROUP : platform === 'atomgit' ? ATOMGIT_PAGE_TO_GROUP : GITHUB_PAGE_TO_GROUP

  const navigate = (key, username, extra) => {
    const target = SETTINGS_KEYS.has(key) ? 'settings' : key
    setPage(target)
    localStorage.setItem('currentPage', target)
    getVisitedRef().current.add(target)
    const group = getPageToGroup()[target]
    if (group && !openKeys.includes(group)) setOpenKeys([...openKeys, group])
    if (username) setUserReposUsername(username)
    if (extra && extra.owner && extra.repo) setPrDataFilter({ owner: extra.owner, repo: extra.repo })
  }

  const handlePageChange = (key) => {
    setPage(key)
    localStorage.setItem('currentPage', key)
    getVisitedRef().current.add(key)
    const group = getPageToGroup()[key]
    if (group && !openKeys.includes(group)) setOpenKeys([...openKeys, group])
  }

  const handleOpenChange = (keys) => { setOpenKeys(keys) }

  const handlePlatformChange = (val) => {
    setPlatform(val)
    localStorage.setItem('currentPlatform', val)
    const newDefault = val === 'gitcode' ? 'gc-dashboard' : val === 'atomgit' ? 'ag-overview' : 'dashboard'
    setPage(newDefault)
    localStorage.setItem('currentPage', newDefault)
    getVisitedRef().current.add(newDefault)
    setOpenKeys([])
  }

  // 合并当前平台菜单 + 共享菜单
  const currentMenu = [...PLATFORM_MENUS[platform], ...SHARED_MENU]

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

  // GitCode 页面组件
  const gitcodePages = {
    'gc-dashboard': <PlatformPlaceholder name="GitCode" color="purple" />,
    'gc-mrs': <GitCodeMrList />,
    'gc-details': <GitCodeMrDetails />,
    'gc-comments': <GitCodeMrComments />,
  }

  // AtomGit 页面组件
  const atomgitPages = {
    'ag-overview': <AtomGitOverview />,
    'ag-dashboard': <PlatformPlaceholder name="AtomGit" color="blue" />,
    'ag-pulls': <AtomGitPullList />,
    'ag-detail': <AtomGitPullDetail />,
    'ag-comments': <AtomGitPullComments />,
    'ag-reviews': <AtomGitPullReviews />,
    'ag-commits': <AtomGitPullCommits />,
    'ag-files': <AtomGitPullFiles />,
    'ag-timeline': <AtomGitPullTimeline />,
    'ag-issues': <AtomGitIssueList />,
  }

  // 共享页面（所有平台可见）
  const sharedPages = {
    'settings': <Settings />,
    'tasks': <Tasks />,
    'data-export': <DataExport />,
    'notification-history': <NotificationHistory />,
    'cannbot-skills': <CannbotSkills />,
  }

  // 合并当前平台页面 + 共享页面
  const platformPages = platform === 'gitcode' ? gitcodePages : platform === 'atomgit' ? atomgitPages : githubPages
  const activePages = { ...platformPages, ...sharedPages }
  const visitedRef = getVisitedRef()

  const currentPlatformConfig = PLATFORMS[platform] || PLATFORMS.github

  return (
    <ConfigProvider theme={{ algorithm: theme.defaultAlgorithm, token: { colorPrimary: currentPlatformConfig.color } }}>
      <Layout style={{ minHeight: '100vh' }}>
        <Sider
          width={220}
          style={{
            background: 'linear-gradient(180deg, #001529 0%, #002140 100%)',
            overflow: 'auto',
            height: '100vh',
            position: 'sticky',
            top: 0,
            left: 0,
          }}
        >
          {/* Logo */}
          <div style={{ height: 56, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
            <DashboardOutlined style={{ fontSize: 20, color: '#1890ff' }} />
            <span style={{ color: '#fff', fontSize: 17, fontWeight: 600, letterSpacing: 1 }}>PR Analyzer</span>
          </div>
          {/* 平台切换 */}
          <div style={{ padding: '0 16px 12px' }}>
            <div style={{ display: 'flex', gap: 6, background: 'rgba(255,255,255,0.08)', borderRadius: 8, padding: 3 }}>
              {Object.entries(PLATFORMS).map(([key, cfg]) => (
                <button
                  key={key}
                  onClick={() => handlePlatformChange(key)}
                  style={{
                    flex: 1,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: 5,
                    padding: '7px 0',
                    border: 'none',
                    borderRadius: 6,
                    cursor: 'pointer',
                    fontSize: 12,
                    fontWeight: platform === key ? 600 : 400,
                    color: platform === key ? '#fff' : 'rgba(255,255,255,0.55)',
                    background: platform === key ? cfg.color : 'transparent',
                    transition: 'all 0.25s',
                    boxShadow: platform === key ? '0 2px 4px rgba(0,0,0,0.2)' : 'none',
                  }}
                >
                  {cfg.icon}
                  <span>{cfg.label}</span>
                </button>
              ))}
            </div>
          </div>
          {/* 菜单 - 暗色主题 */}
          <Menu
            mode="inline"
            selectedKeys={[page]}
            openKeys={openKeys}
            onOpenChange={handleOpenChange}
            items={currentMenu}
            onClick={({ key }) => handlePageChange(key)}
            theme="dark"
            style={{ borderRight: 0, background: 'transparent' }}
          />
        </Sider>
        <Layout>
          <Header style={{ background: '#fff', padding: '0 24px', borderBottom: '1px solid #f0f0f0', display: 'flex', alignItems: 'center', gap: 10, height: 56, lineHeight: 56 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 28, height: 28, borderRadius: 6, background: `rgba(${parseInt(currentPlatformConfig.color.slice(1,3),16)},${parseInt(currentPlatformConfig.color.slice(3,5),16)},${parseInt(currentPlatformConfig.color.slice(5,7),16)},0.07)`, fontSize: 16, color: currentPlatformConfig.color }}>
                {currentPlatformConfig.icon}
              </span>
              <h2 style={{ margin: 0, fontSize: 16, fontWeight: 600, color: '#1f1f1f' }}>{currentPlatformConfig.label} 数据分析平台</h2>
            </div>
          </Header>
          <Content style={{ margin: 20, padding: 20, background: '#f5f5f5', borderRadius: 0, minHeight: 'calc(100vh - 96px)' }}>
            <div style={{ background: '#fff', borderRadius: 8, padding: 20, minHeight: 'calc(100vh - 136px)' }}>
              {Object.entries(activePages).map(([key, component]) => (
                <div key={key} style={{ display: key === page ? 'block' : 'none' }}>
                  {visitedRef.current.has(key) ? component : null}
                </div>
              ))}
            </div>
          </Content>
        </Layout>
      </Layout>
    </ConfigProvider>
  )
}

export default App
