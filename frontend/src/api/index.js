import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 60000,
})

export const getDatabaseStats = () => api.get('/database/stats')

export const getProjectsOverview = () => api.get('/database/projects/overview')

export const getRepoStats = (owner, repo) => api.get(`/github/repos/${owner}/${repo}/stats`)

export const getGitRepoStatus = (owner, repo) => api.get(`/git/repos/${owner}/${repo}/status`)

export const getGitLogSummary = (owner, repo) => api.get(`/git/repos/${owner}/${repo}/log/summary`)

export const getGitLogCommits = (owner, repo, params) => api.get(`/git/repos/${owner}/${repo}/log/commits`, { params })

export const getGitProjects = () => api.get('/git/projects')

export const asyncGitClone = (owner, repo) => api.post(`/git/tasks/clone/${owner}/${repo}`)

export const asyncGitExtract = (owner, repo, maxCount) => api.post(`/git/tasks/extract/${owner}/${repo}`, null, { params: { max_count: maxCount } })

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

export const getCommenterProfiles = (owner, repo, limit = 20) =>
  api.get(`/github/prs/${owner}/${repo}/commenters/profiles?limit=${limit}`)

export const getUserProfiles = (params) => api.get('/database/profiles', { params })

export const getIssues = (params) => api.get('/database/issues', { params })

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

export default api
