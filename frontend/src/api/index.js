import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 60000,
})

// 全局错误拦截器
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status
    const msg = error.response?.data?.detail || error.message
    if (status === 429) {
      error._friendlyMsg = '请求频率超限，请稍后重试'
    } else if (status === 503) {
      error._friendlyMsg = '服务暂不可用，请稍后重试'
    } else if (status === 401) {
      error._friendlyMsg = '认证失败，请检查配置'
    } else if (!error.response && error.code === 'ECONNABORTED') {
      error._friendlyMsg = '请求超时，请稍后重试'
    } else if (!error.response) {
      error._friendlyMsg = '网络错误，请检查连接'
    }
    return Promise.reject(error)
  }
)

export const getDatabaseStats = () => api.get('/database/stats')

export const getProjectsOverview = () => api.get('/database/projects/overview')

export const registerProject = (owner, repo) => api.post('/database/projects/register', null, { params: { owner, repo } })

export const getRepoStats = (owner, repo) => api.get(`/github/repos/${owner}/${repo}/stats`)

export const getGitRepoStatus = (owner, repo) => api.get(`/git/repos/${owner}/${repo}/status`)

export const getGitLogSummary = (owner, repo) => api.get(`/git/repos/${owner}/${repo}/log/summary`)

export const getGitLogCommits = (owner, repo, params) => api.get(`/git/repos/${owner}/${repo}/log/commits`, { params })

export const getGitBranches = (owner, repo) => api.get(`/git/repos/${owner}/${repo}/branches`)

export const getGitProjects = () => api.get('/git/projects')

export const asyncGitClone = (owner, repo) => api.post(`/git/tasks/clone/${owner}/${repo}`)

export const asyncGitExtract = (owner, repo, maxCount, branch) => {
  const mc = typeof maxCount === 'object' ? (maxCount.max_count || 0) : (maxCount || 0)
  const params = { max_count: mc }
  if (branch) params.branch = branch
  return api.post(`/git/tasks/extract/${owner}/${repo}`, null, { params })
}

export const asyncGitUpdate = (owner, repo) =>
  api.post(`/git/tasks/update/${owner}/${repo}`)

export const deleteGitRepo = (owner, repo) => api.delete(`/git/repos/${owner}/${repo}`)

export const getPrList = (params) => api.get('/database/prs', { params })

export const getPrData = (owner, repo) => api.get(`/database/prs/${owner}/${repo}`)

export const deletePrData = (owner, repo) => api.delete(`/database/prs/${owner}/${repo}`)

export const getComments = (params) => api.get('/database/comments', { params })

export const getDetails = (params) => api.get('/database/details', { params })

export const getTimeline = (params) => api.get('/database/timeline', { params })

export const getReviews = (params) => api.get('/database/reviews', { params })

export const getAggregate = (params) => api.get('/database/aggregate', { params })

export const getHealth = () => api.get('/health')

export const fetchGithubPrs = (owner, repo, params) =>
  api.get(`/github/prs/${owner}/${repo}`, { params })

export const fetchGithubComments = (owner, repo, params) =>
  api.get(`/github/prs/${owner}/${repo}/comments`, { params })

export const triggerCicdAnalysis = (owner, repo) =>
  api.post(`/analysis/cicd/analyze/${owner}/${repo}`)

export const getCicdReport = (owner, repo) =>
  api.get(`/analysis/cicd/report/${owner}/${repo}`)

export const getReviewQuality = (owner, repo, params) =>
  api.get(`/analysis/review-quality/${owner}/${repo}`, { params })

export const getReviewQualityTrends = (owner, repo, params) =>
  api.get(`/analysis/review-quality/${owner}/${repo}/trends`, { params })

export const getProjectHealth = (owner, repo, params) =>
  api.get(`/analysis/health/${owner}/${repo}`, { params })

export const getProjectHealthTrends = (owner, repo, params) =>
  api.get(`/analysis/health/${owner}/${repo}/trends`, { params })

export const getTrendAlerts = (owner, repo, params) =>
  api.get(`/analysis/alerts/${owner}/${repo}`, { params })

export const getCodeHeatmap = (owner, repo, params) =>
  api.get(`/analysis/code-heatmap/${owner}/${repo}`, { params })

export const getCodeInsight = (owner, repo, params) =>
  api.get(`/analysis/code-insight/${owner}/${repo}`, { params })

export const aiAnalyzeCodeChanges = (owner, repo, params) =>
  api.post(`/analysis/code-insight/${owner}/${repo}/ai-analyze`, null, { params, timeout: 120000 })

export const fetchPrDetails = (owner, repo, params) =>
  api.get(`/github/prs/${owner}/${repo}/details`, { params })

export const fetchAllPrFiles = (owner, repo, params) =>
  api.get(`/github/prs/${owner}/${repo}/files`, { params })

export const fetchPrFiles = (owner, repo, params) =>
  api.post(`/github/tasks/files/${owner}/${repo}`, null, { params })

export const getCommenterProfiles = (owner, repo, limit = 20) =>
  api.get(`/github/prs/${owner}/${repo}/commenters/profiles?limit=${limit}`)

export const getDeveloperRelations = (owner, repo) => api.get('/database/developer-relations', { params: { owner, repo } })

export const getCommentProjects = () => {
  // 复用 comments 的 aggregate 来获取有评论数据的项目
  return api.get('/database/comments/projects')
}

export const getUserProfiles = (params) => api.get('/database/profiles', { params })

export const getIssues = (params) => api.get('/database/issues', { params })

export const getIssueProjects = () => api.get('/database/issues/projects')

export const fetchGithubIssues = (owner, repo, params) =>
  api.get(`/github/issues/${owner}/${repo}`, { params })

export const getUserRepos = (username, params) =>
  api.get(`/github/users/${username}/repos`, { params })

export const getUserReposFromDB = (params) =>
  api.get('/database/user-repos', { params })

export const updatePrs = (owner, repo) =>
  api.post(`/github/prs/${owner}/${repo}/update`)

export const updateIssues = (owner, repo) =>
  api.post(`/github/issues/${owner}/${repo}/update`)

export const updateComments = (owner, repo) =>
  api.post(`/github/prs/${owner}/${repo}/comments/update`)

export const getIssueTimelines = (params) => api.get('/database/issue-timelines', { params })

export const getIssueTimelineProjects = () => api.get('/database/issue-timelines/projects')

export const fetchIssueTimelines = (owner, repo, limit) =>
  api.get(`/github/issues/${owner}/${repo}/timelines?limit=${limit}`)

export const getTaskList = (params) => api.get('/tasks', { params })

export const getTask = (taskId) => api.get(`/tasks/${taskId}`)

export const getTaskLogs = (taskId) => api.get(`/tasks/${taskId}/logs`)

export const deleteTask = (taskId) => api.delete(`/tasks/${taskId}`)

export const asyncFetchPrs = (owner, repo, params) =>
  api.post(`/github/tasks/prs/${owner}/${repo}`, null, { params })

export const asyncFetchIssues = (owner, repo, params) =>
  api.post(`/github/tasks/issues/${owner}/${repo}`, null, { params })

export const asyncFetchComments = (owner, repo, params) =>
  api.post(`/github/tasks/comments/${owner}/${repo}`, null, { params })

export const asyncFetchTimelines = (owner, repo, params) =>
  api.post(`/github/tasks/timelines/${owner}/${repo}`, null, { params })

export const asyncFetchProfiles = (owner, repo, params) =>
  api.post(`/github/tasks/profiles/${owner}/${repo}`, null, { params })

// Agent API
export const agentAnalyze = (params) => api.post('/agent/analyze', params, { timeout: 300000 })
export const agentAnalyzeAsync = (params) => api.post('/agent/analyze/async', params, { timeout: 30000 })
export const getAgentStatus = (taskId) => api.get(`/agent/status/${taskId}`)
export const getAgentTasks = () => api.get('/agent/tasks')
export const getAgentHealth = () => api.get('/health')
export const getAgentsStatus = () => api.get('/agent/agents/status')
export const getAgentBlackboard = () => api.get('/agent/blackboard')
export const getAgentTraces = (params) => api.get('/agent/traces', { params })
export const getAgentTrace = (traceId) => api.get(`/agent/traces/${traceId}`)
export const getAgentProjectTraces = (owner, repo) => api.get(`/agent/traces/project/${owner}/${repo}`)
export const getAgentCost = () => api.get('/agent/cost')
export const getAgentArtifacts = (owner, repo) => api.get(`/agent/artifacts/${owner}/${repo}`)
export const getAgentArtifactSnapshot = (owner, repo) => api.get(`/agent/artifacts/${owner}/${repo}/snapshot`)
export const agentChat = (params) => api.post('/agent/chat', params, { timeout: 120000 })
export const getLlmConfig = () => api.get('/agent/llm/config')
export const updateLlmConfig = (params) =>
  api.put('/agent/llm/config', null, { params })

export const testLlmConnection = () =>
  api.post('/agent/llm/test', null, { timeout: 30000 })

// Dashboard 概览接口
export const getRecentActivities = (params) =>
  api.get('/database/recent-activities', { params })

export const getTopContributors = (params) =>
  api.get('/database/contributors/top', { params })

export const getBatchHealth = () =>
  api.get('/analysis/health/batch', { timeout: 60000 })

// ====================
// 通知管理
// ====================
export const getNotificationConfigs = () => api.get('/notifications/config')
export const createNotificationConfig = (data) => api.post('/notifications/config', data)
export const updateNotificationConfig = (configId, data) => api.put(`/notifications/config/${configId}`, data)
export const deleteNotificationConfig = (configId) => api.delete(`/notifications/config/${configId}`)
export const testNotificationConfig = (configId) =>
  api.post(`/notifications/config/${configId}/test`, null, { timeout: 30000 })
export const getNotificationHistory = (params) => api.get('/notifications/history', { params })

// ====================
// 数据导出
// ====================
export const exportReport = (owner, repo, params) =>
  api.get(`/export/report/${owner}/${repo}`, { params, responseType: 'blob', timeout: 120000 })
export const exportData = (owner, repo, params) =>
  api.get(`/export/data/${owner}/${repo}`, { params, responseType: 'blob', timeout: 120000 })

// ====================
// Webhook 管理
// ====================
export const getWebhookConfig = () => api.get('/webhooks/config')
export const updateWebhookConfig = (data) => api.put('/webhooks/config', data)
export const getWebhookEvents = (params) => api.get('/webhooks/events', { params })

// ====================
// 多仓库对比
// ====================
export const compareProjects = (data) => api.post('/analysis/compare', data, { timeout: 120000 })
export const getContributorsOverlap = (params) => api.get('/analysis/compare/contributors-overlap', { params })

// ====================
// 数据完整性 — GitHub 统计刷新
// ====================
export const refreshProjectStats = (owner, repo) =>
  api.post(`/database/projects/${owner}/${repo}/refresh-stats`)
export const refreshAllProjectStats = () =>
  api.post('/database/projects/refresh-all-stats', null, { timeout: 120000 })

// ====================
// 系统配置
// ====================
export const getProxyConfig = () => api.get('/config/proxy')
export const updateProxyConfig = (proxy) => api.put('/config/proxy', null, { params: { proxy } })
export const getAppConfig = () => api.get('/config')
export const getGithubTokens = () => api.get('/config/tokens/github')
export const updateGithubTokens = (payload) => api.put('/config/tokens/github', payload)
export const checkGithubTokens = () => api.get('/config/tokens/github/check')
export const getAtomgitTokens = () => api.get('/config/tokens/atomgit')
export const updateAtomgitTokens = (payload) => api.put('/config/tokens/atomgit', payload)
export const checkAtomgitTokens = () => api.get('/config/tokens/atomgit/check')

// ====================
// GitCode 平台 (gitcode.net)
// ====================
export const getGitCodeMrs = (owner, repo, params) =>
  api.get(`/gitcode/mrs/${owner}/${repo}`, { params })
export const getGitCodeMrComments = (owner, repo, mrIid) =>
  api.get(`/gitcode/mrs/${owner}/${repo}/${mrIid}/comments`)
export const getGitCodeMrDetail = (owner, repo, mrIid) =>
  api.get(`/gitcode/mrs/${owner}/${repo}/${mrIid}/detail`)
export const getGitCodeMrChanges = (owner, repo, mrIid) =>
  api.get(`/gitcode/mrs/${owner}/${repo}/${mrIid}/changes`)
export const getGitCodeBatchComments = (owner, repo, params) =>
  api.get(`/gitcode/mrs/${owner}/${repo}/comments`, { params })
export const getGitCodeBatchDetails = (owner, repo, params) =>
  api.get(`/gitcode/mrs/${owner}/${repo}/details`, { params })

// ====================
// AtomGit 平台 (atomgit.com)
// ====================
export const getAtomGitPulls = (owner, repo, params) =>
  api.get(`/atomgit/pulls/${owner}/${repo}`, { params })
export const getAtomGitPullDetail = (owner, repo, pullNumber) =>
  api.get(`/atomgit/pulls/${owner}/${repo}/${pullNumber}/detail`)
export const getAtomGitPullComments = (owner, repo, pullNumber) =>
  api.get(`/atomgit/pulls/${owner}/${repo}/${pullNumber}/comments`)
export const getAtomGitPullReviews = (owner, repo, pullNumber) =>
  api.get(`/atomgit/pulls/${owner}/${repo}/${pullNumber}/reviews`)
export const getAtomGitPullCommits = (owner, repo, pullNumber) =>
  api.get(`/atomgit/pulls/${owner}/${repo}/${pullNumber}/commits`)
export const getAtomGitPullFiles = (owner, repo, pullNumber) =>
  api.get(`/atomgit/pulls/${owner}/${repo}/${pullNumber}/files`)
export const getAtomGitPullTimeline = (owner, repo, pullNumber) =>
  api.get(`/atomgit/pulls/${owner}/${repo}/${pullNumber}/timeline`)
export const getAtomGitBatchComments = (owner, repo, params) =>
  api.get(`/atomgit/pulls/${owner}/${repo}/comments`, { params })
export const getAtomGitAllComments = (owner, repo, params) =>
  api.get(`/atomgit/pulls/${owner}/${repo}/comments/all`, { params })
export const getAtomGitBatchDetails = (owner, repo, prNumbers) =>
  api.get(`/atomgit/pulls/${owner}/${repo}/details`, { params: { pr_numbers: prNumbers } })
export const getAtomGitBatchReviews = (owner, repo, prNumbers) =>
  api.get(`/atomgit/pulls/${owner}/${repo}/reviews`, { params: { pr_numbers: prNumbers } })
export const getAtomGitBatchCommits = (owner, repo, prNumbers) =>
  api.get(`/atomgit/pulls/${owner}/${repo}/commits`, { params: { pr_numbers: prNumbers } })
export const getAtomGitBatchFiles = (owner, repo, prNumbers) =>
  api.get(`/atomgit/pulls/${owner}/${repo}/files`, { params: { pr_numbers: prNumbers } })
export const getAtomGitBatchTimelines = (owner, repo, prNumbers) =>
  api.get(`/atomgit/pulls/${owner}/${repo}/timelines`, { params: { pr_numbers: prNumbers } })
export const getAtomGitIssues = (owner, repo, params) =>
  api.get(`/atomgit/issues/${owner}/${repo}`, { params })
export const getAtomGitIssueDetail = (owner, repo, issueNumber) =>
  api.get(`/atomgit/issues/${owner}/${repo}/${issueNumber}`)

// ====================
// CANNBot Skills
// ====================
export const getCannbotStatus = () => api.get('/cannbot/status')
export const getCannbotSkills = () => api.get('/cannbot/skills')
export const getCannbotSkillDetail = (skillPath) =>
  api.get(`/cannbot/skills/${skillPath}`)
export const getCannbotSkillFile = (filePath) =>
  api.get(`/cannbot/skill-file/${filePath}`)
export const cloneCannbotSkills = () =>
  api.post('/cannbot/clone', null, { timeout: 120000 })
export const updateCannbotSkills = () =>
  api.post('/cannbot/update', null, { timeout: 120000 })
export const getCannbotStats = () => api.get('/cannbot/stats')
export const getCannbotEvaluation = () =>
  api.get('/cannbot/evaluation', { timeout: 120000 })
export const getCannbotChangelog = () => api.get('/cannbot/changelog')
export const getCannbotScenarios = () => api.get('/cannbot/scenarios')
export const installCannbotScenario = (data) =>
  api.post('/cannbot/install-scenario', data, { timeout: 120000 })
export const checkCannbotInstall = (scenarioPath) =>
  api.get(`/cannbot/install-check/${scenarioPath}`)
export const verifyCannbotInstall = (scenarioPath, tool = 'claude') =>
  api.get(`/cannbot/install-verify/${scenarioPath}`, { params: { tool } })
export const uninstallCannbotScenario = (data) =>
  api.post('/cannbot/uninstall-scenario', data, { timeout: 60000 })

// ====================
// CANNBot Workflow Simulation
// ====================
export const getWorkflowDefinitions = () =>
  api.get('/cannbot/workflow/definitions')
export const getWorkflowDefinition = (pluginId) =>
  api.get(`/cannbot/workflow/${pluginId}/definition`)
export const simulateWorkflow = (data) =>
  api.post('/cannbot/workflow/simulate', data, { timeout: 300000 })
export const simulateWorkflowStream = (pluginId, persona) =>
  // SSE 实时仿真流，返回 EventSource
  new EventSource(`/api/cannbot/workflow/simulate-stream?plugin_id=${encodeURIComponent(pluginId)}&persona=${encodeURIComponent(persona)}`)
export const simulateWorkflowBatch = () =>
  api.post('/cannbot/workflow/simulate-batch', null, { timeout: 600000 })
export const getWorkflowSimulation = (simId) =>
  api.get(`/cannbot/workflow/simulation/${simId}`)
export const getWorkflowSimulations = (params) =>
  api.get('/cannbot/workflow/simulations', { params })
export const getWorkflowComparison = () =>
  api.get('/cannbot/workflow/comparison')
export const getWorkflowAntipatterns = () =>
  api.get('/cannbot/workflow/antipatterns')
export const exportWorkflowReport = (data) =>
  api.post('/cannbot/workflow/export', data, { responseType: 'blob', timeout: 60000 })

// ====================
// 算子辅助开发 V2
// ====================
export const createOpsDevSession = (data) => api.post('/cannbot/ops-dev/sessions', data)
export const getOpsDevSessions = (params) => api.get('/cannbot/ops-dev/sessions', { params })
export const getOpsDevSession = (id) => api.get(`/cannbot/ops-dev/sessions/${id}`)
export const deleteOpsDevSession = (id) => api.delete(`/cannbot/ops-dev/sessions/${id}`)
export const executeOpsDevStep = (id, stepId) =>
  api.post(`/cannbot/ops-dev/sessions/${id}/steps/${stepId}/execute`, null, { timeout: 300000 })
export const stopOpsDevStep = (id, stepId) =>
  api.post(`/cannbot/ops-dev/sessions/${id}/steps/${stepId}/stop`)
export const exportOpsDevSession = (id, format = 'markdown') =>
  api.get(`/cannbot/ops-dev/sessions/${id}/export`, { params: { format }, responseType: 'blob', timeout: 60000 })
export const superviseOpsDevSession = (id) =>
  api.post(`/cannbot/ops-dev/sessions/${id}/supervise`, null, { timeout: 120000 })
export const streamOpsDevSession = (id) =>
  new EventSource(`/api/cannbot/ops-dev/sessions/${id}/stream`)

export default api
