/**
 * NewSessionModal — 新建评估弹窗
 * 含算子库 clone（Step1）+ 装插件（Step2）+ 启动参数（Step3）全部准备步骤。
 * 表单输入态（9 个）由父组件受控（保留 sessionStorage 持久化单一数据源），
 * 操作态（fork/clone/install/分支）封在组件内部。
 * 点「开始评估」组装 formData 调 onStart，成功后关闭。
 */
import { useState, useEffect, useCallback } from 'react'
import { Modal, Card, Space, Tag, Input, Select, Button, Switch, Row, Col, Tooltip, Typography, message } from 'antd'
import {
  GithubOutlined, DownloadOutlined, ToolOutlined, BranchesOutlined, PlusOutlined,
  ReloadOutlined, ExperimentOutlined, PlayCircleOutlined, ApartmentOutlined,
  LoadingOutlined, WarningOutlined,
} from '@ant-design/icons'
import {
  forkWorkflowV2Repo, checkWorkflowV2Fork, cloneWorkflowV2Repo, checkWorkflowV2Repo,
  checkWorkflowV2Base,
  installCannbotScenario, checkCannbotInstallWorkdir,
  listWorkflowV2Branches, createWorkflowV2Branch, switchWorkflowV2Branch,
} from '../../api'

const { Text } = Typography

export default function NewSessionModal({
  visible, onCancel,
  // 受控表单字段
  selectedPlugin, onSelectedPluginChange,
  opName, onOpNameChange,
  opSpec, onOpSpecChange,
  workDir, onWorkDirChange,
  repoUrl, onRepoUrlChange,
  gitcodeToken, onGitcodeTokenChange,
  selectedTool, onSelectedToolChange,
  stepTimeout, onStepTimeoutChange,
  autoPipeline, onAutoPipelineChange,
  // 透传
  plugins, pluginsLoading,
  onViewArch,
  // 启动回调 (formData) => Promise；reject 或 resolve(false) 时不关闭
  onStart,
}) {
  // ===== 内部操作态 =====
  const [baseReady, setBaseReady] = useState(false)  // base_repo 母本是否就绪（决定 Clone/派生按钮）
  const [forkStatus, setForkStatus] = useState('idle')
  const [forkInfo, setForkInfo] = useState(null)
  const [cloneStatus, setCloneStatus] = useState('idle')
  const [cloneInfo, setCloneInfo] = useState(null)
  const [installStatus, setInstallStatus] = useState('idle')
  const [installInfo, setInstallInfo] = useState(null)
  const [branches, setBranches] = useState([])
  const [currentBranch, setCurrentBranch] = useState('')
  const [branchesLoading, setBranchesLoading] = useState(false)
  const [newBranchName, setNewBranchName] = useState('')
  const [baseBranch, setBaseBranch] = useState('')
  const [branchCreating, setBranchCreating] = useState(false)
  const [branchSwitching, setBranchSwitching] = useState(false)
  const [selectedBranchToSwitch, setSelectedBranchToSwitch] = useState(null)
  const [starting, setStarting] = useState(false)

  // ===== 4 个自动检测 effect（监听受控 props） =====
  useEffect(() => {
    if (!workDir?.trim()) { setCloneStatus('idle'); setCloneInfo(null); return }
    setCloneStatus('checking')
    checkWorkflowV2Repo(workDir.trim())
      .then(res => {
        if (res.data?.is_git) {
          setCloneStatus('cloned')
          setCloneInfo({ branch: res.data.branch, path: res.data.path, is_clean: res.data.is_clean, modified_count: res.data.modified_count })
        } else { setCloneStatus('idle'); setCloneInfo(null) }  // 方案一：workDir 可能是根目录（非 git，合法），不报错
      })
      .catch(() => setCloneStatus('idle'))
    // 定期轮询刷新文件改动状态（30s），让"全新/已修改"实时更新
    const timer = setInterval(() => {
      const wd = workDir?.trim()
      if (!wd) return
      checkWorkflowV2Repo(wd).then(res => {
        if (res.data?.is_git) {
          setCloneInfo(prev => prev ? { ...prev, is_clean: res.data.is_clean, modified_count: res.data.modified_count } : prev)
        }
      }).catch(() => {})
    }, 30000)
    return () => clearInterval(timer)
  }, [workDir])

  useEffect(() => {
    if (!workDir?.trim() || !selectedPlugin) { if (installStatus !== 'installing') setInstallStatus('idle'); return }
    setInstallStatus('checking')
    checkCannbotInstallWorkdir(workDir.trim(), selectedPlugin, selectedTool)
      .then(res => {
        if (res.data?.installed) { setInstallStatus('installed'); setInstallInfo(res.data) }
        else { setInstallStatus('idle'); setInstallInfo(null) }
      })
      .catch(() => setInstallStatus('idle'))
  }, [workDir, selectedPlugin, selectedTool])

  useEffect(() => {
    if (!repoUrl?.trim() || !gitcodeToken?.trim()) return
    setForkStatus('checking')
    checkWorkflowV2Fork(repoUrl.trim(), gitcodeToken.trim())
      .then(res => {
        if (res.data?.forked) {
          setForkStatus('forked')
          setForkInfo({ fork_url: res.data.fork_url, fork_ssh: res.data.fork_ssh, fork_path: res.data.fork_path })
        } else { setForkStatus('idle'); setForkInfo(null) }
      })
      .catch(() => setForkStatus('idle'))
  }, [repoUrl, gitcodeToken])

  const loadBranches = useCallback(async () => {
    if (!workDir?.trim()) return
    setBranchesLoading(true)
    try {
      const res = await listWorkflowV2Branches(workDir.trim())
      if (res.data.error) { message.error(res.data.error); return }
      setBranches(res.data.branches || [])
      setCurrentBranch(res.data.current_branch || '')
    } catch (e) { message.error(e._friendlyMsg || '获取分支失败') }
    finally { setBranchesLoading(false) }
  }, [workDir])

  useEffect(() => { if (cloneStatus === 'cloned') loadBranches() }, [cloneStatus, loadBranches])

  // 检测母本是否就绪（决定显示 Clone 还是派生按钮；根目录 = workDir 或 config 默认）
  useEffect(() => {
    const cloneUrl = forkInfo?.fork_url || repoUrl?.trim()
    if (!cloneUrl) { setBaseReady(false); return }
    let cancelled = false
    checkWorkflowV2Base(cloneUrl, workDir?.trim())
      .then(res => { if (!cancelled) setBaseReady(!!res.data?.base_ready) })
      .catch(() => { if (!cancelled) setBaseReady(false) })
    return () => { cancelled = true }
  }, [repoUrl, forkInfo, workDir])

  // ===== handler =====
  const handleFork = useCallback(async () => {
    if (!repoUrl?.trim()) { message.warning('请输入算子库地址'); return }
    if (!gitcodeToken?.trim()) { message.warning('请输入 GitCode Token'); return }
    setForkStatus('forking')
    try {
      const res = await forkWorkflowV2Repo({ repo_url: repoUrl.trim(), token: gitcodeToken.trim() })
      if (res.data.error) { setForkStatus('error'); message.error(res.data.error); return }
      setForkStatus('forked'); setForkInfo(res.data)
      message.success(res.data.status === 'already_forked' ? '仓库已存在于您的账号' : 'Fork 成功')
    } catch (e) { setForkStatus('error'); message.error(e._friendlyMsg || 'Fork 失败') }
  }, [repoUrl, gitcodeToken])

  const handleClone = useCallback(async () => {
    const cloneUrl = forkInfo?.fork_url || repoUrl?.trim()
    if (!cloneUrl) { message.warning('请先 Fork 或输入仓库地址'); return }
    setCloneStatus('cloning')
    try {
      // 方案一：workDir 留空 → 后端自动生成隔离目录（base_repo + --shared）；填写则用指定目录
      const payload = { repo_url: cloneUrl }
      if (workDir?.trim()) payload.target_dir = workDir.trim()
      if (opName?.trim()) payload.op_name = opName.trim()
      const res = await cloneWorkflowV2Repo(payload)
      if (res.data.error) { setCloneStatus('error'); message.error(res.data.error); return }
      setCloneStatus('cloned'); setCloneInfo({ branch: res.data.branch, path: res.data.path })
      if (res.data.path) onWorkDirChange({ target: { value: res.data.path } })  // 模拟 Input.onChange 事件回填 workDir
      const msg = res.data.isolated
        ? `已派生隔离工作区${res.data.auto_branch ? '（分支 ' + res.data.branch + '）' : ''}`
        : (res.data.status === 'already_exists' ? '仓库已存在' : 'Clone 成功')
      message.success(msg)
    } catch (e) { setCloneStatus('error'); message.error(e._friendlyMsg || 'Clone 失败') }
  }, [repoUrl, workDir, forkInfo, opName, onWorkDirChange])

  const handleInstall = useCallback(async () => {
    if (!selectedPlugin) { message.warning('请先选择插件'); return }
    if (!workDir?.trim()) { message.warning('请先设置工作目录'); return }
    setInstallStatus('installing')
    try {
      const plugin = (plugins || []).find(p => p.plugin_id === selectedPlugin)
      const scenarioPath = plugin?.plugin_id ? `plugins-official/${plugin.plugin_id}` : ''
      if (!scenarioPath) { message.error('无法确定插件路径'); setInstallStatus('error'); return }
      const res = await installCannbotScenario({
        scenario_path: scenarioPath, tool: selectedTool, level: 'project', install_path: workDir.trim(),
      })
      if (res.data?.success) { setInstallStatus('installed'); setInstallInfo(res.data); message.success('插件安装成功') }
      else { setInstallStatus('error'); message.error(res.data?.errors || '安装失败') }
    } catch (e) { setInstallStatus('error'); message.error(e._friendlyMsg || '安装失败') }
  }, [selectedPlugin, selectedTool, workDir, plugins])

  const handleCreateBranch = useCallback(async () => {
    if (!newBranchName.trim()) { message.warning('请输入分支名称'); return }
    if (!workDir?.trim()) { message.warning('请先设置工作目录'); return }
    setBranchCreating(true)
    try {
      const res = await createWorkflowV2Branch({ work_dir: workDir.trim(), branch_name: newBranchName.trim(), base_branch: baseBranch || '' })
      if (res.data.error) { message.error(res.data.error); return }
      message.success(res.data.message)
      setNewBranchName(''); setCurrentBranch(newBranchName.trim())
      setCloneInfo(prev => prev ? { ...prev, branch: newBranchName.trim() } : null)
      loadBranches()
    } catch (e) { message.error(e._friendlyMsg || '创建分支失败') }
    finally { setBranchCreating(false) }
  }, [workDir, newBranchName, baseBranch, loadBranches])

  const handleSwitchBranch = useCallback(async (branchName) => {
    if (!branchName || !workDir?.trim()) return
    setBranchSwitching(true)
    try {
      const res = await switchWorkflowV2Branch({ work_dir: workDir.trim(), branch_name: branchName })
      if (res.data.error) { message.error(res.data.error); return }
      message.success(res.data.message)
      setCurrentBranch(branchName)
      setCloneInfo(prev => prev ? { ...prev, branch: branchName } : null)
      loadBranches()
    } catch (e) { message.error(e._friendlyMsg || '切换分支失败') }
    finally { setBranchSwitching(false) }
  }, [workDir, loadBranches])

  // ===== 提交：组装 formData 调 onStart =====
  const handleSubmit = async () => {
    if (!selectedPlugin) { message.warning('请选择插件'); return }
    if (!opName?.trim()) { message.warning('请输入算子名称'); return }
    const formData = {
      plugin_id: selectedPlugin,
      op_name: opName.trim(),
      op_spec: (opSpec || '').trim(),
      work_dir: (workDir || '').trim(),
      step_timeout: stepTimeout,
      auto_pipeline: autoPipeline,
      gitcode_token: (gitcodeToken || '').trim(),
      repo_url: (repoUrl || '').trim(),
      fork_info: forkInfo,
      clone_status: cloneStatus === 'cloned' ? 'cloned' : cloneStatus === 'error' ? 'failed' : 'pending',
    }
    setStarting(true)
    try {
      const ok = await onStart(formData)
      if (ok !== false) onCancel()
    } catch { /* onStart 自身已提示，保持 Modal 打开 */ }
    finally { setStarting(false) }
  }

  return (
    <Modal
      open={visible}
      onCancel={onCancel}
      title={<Space><ExperimentOutlined /> 新建评估</Space>}
      width={760}
      footer={null}
      destroyOnClose={false}
    >
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        {/* Step 1: 算子库 */}
        <Card size="small" title={
          <Space>
            <GithubOutlined />
            <span>Step 1: 算子库</span>
            {forkStatus === 'forked' && <Tag color="cyan" style={{ fontSize: 10 }}>已 Fork</Tag>}
            {cloneStatus === 'cloned' && <Tag color="green" style={{ fontSize: 10 }}>已克隆</Tag>}
            {cloneStatus === 'cloning' && <Tag color="blue" style={{ fontSize: 10 }}><LoadingOutlined /> 克隆中</Tag>}
            {forkStatus === 'forking' && <Tag color="blue" style={{ fontSize: 10 }}><LoadingOutlined /> Fork 中</Tag>}
            {(forkStatus === 'checking' || cloneStatus === 'checking') && <Tag style={{ fontSize: 10 }}><LoadingOutlined /> 检查中</Tag>}
          </Space>
        }>
          <Space direction="vertical" size={6} style={{ width: '100%' }}>
            <Row gutter={8} align="middle">
              <Col><Text strong style={{ fontSize: 12 }}>上游仓库:</Text></Col>
              <Col flex="auto">
                <Input placeholder="如 https://atomgit.com/cann/ops-math" value={repoUrl} onChange={onRepoUrlChange} style={{ width: '100%' }} />
              </Col>
            </Row>
            <Row gutter={8} align="middle">
              <Col><Text strong style={{ fontSize: 12 }}>GitCode Token:</Text></Col>
              <Col flex="auto">
                <Input.Password placeholder="输入 GitCode API Token（用于 Fork 操作）" value={gitcodeToken} onChange={onGitcodeTokenChange} style={{ width: '100%' }} />
              </Col>
              <Col>
                <Button
                  icon={<GithubOutlined />}
                  onClick={handleFork}
                  loading={forkStatus === 'forking' || forkStatus === 'checking'}
                  disabled={!repoUrl?.trim() || !gitcodeToken?.trim() || forkStatus === 'forking' || forkStatus === 'forked' || forkStatus === 'checking'}
                  type={forkStatus === 'forked' ? 'default' : 'primary'}
                >
                  {forkStatus === 'forked' ? '已 Fork' : forkStatus === 'forking' ? 'Fork 中...' : forkStatus === 'checking' ? '检测中...' : 'Fork 到我的账号'}
                </Button>
              </Col>
            </Row>
            {forkInfo && (
              <div style={{ padding: '4px 0' }}>
                <Space size={8}>
                  <Tag color="cyan" style={{ fontSize: 10 }}>Fork: {forkInfo.fork_path || ''}</Tag>
                  {forkInfo.fork_url && <a href={forkInfo.fork_url.replace('.git', '')} target="_blank" rel="noopener noreferrer" style={{ fontSize: 11 }}>查看仓库</a>}
                </Space>
              </div>
            )}
            <Row gutter={8} align="middle">
              <Col><Text strong style={{ fontSize: 12 }}>工作目录:</Text></Col>
              <Col flex="auto">
                <Input placeholder="留空则自动创建隔离工作区（推荐，每次评估独立）；或手动指定目录" value={workDir} onChange={onWorkDirChange} style={{ width: '100%' }} />
              </Col>
              <Col>
                <Button
                  icon={<DownloadOutlined />}
                  onClick={handleClone}
                  loading={cloneStatus === 'cloning'}
                  disabled={(!forkInfo?.fork_url && !repoUrl?.trim()) || cloneStatus === 'cloning' || cloneStatus === 'cloned'}
                  type={cloneStatus === 'cloned' ? 'default' : 'primary'}
                >
                  {cloneStatus === 'cloned' ? '已派生' : cloneStatus === 'cloning' ? (baseReady ? '派生中...' : '克隆中...') : (baseReady ? '派生新工作区' : 'Clone 算子库')}
                </Button>
              </Col>
            </Row>
            {cloneInfo && (
              <div>
                <Space size={8}>
                  <Text type="secondary" style={{ fontSize: 11 }}>路径: {cloneInfo.path}</Text>
                  {currentBranch && <Tag color="blue" style={{ fontSize: 10 }}>当前分支: {currentBranch}</Tag>}
                  {cloneInfo.is_clean
                    ? <Tag color="success" style={{ fontSize: 10 }}>✨ 全新（未改动）</Tag>
                    : <Tag color="warning" style={{ fontSize: 10 }}>📝 已修改 {cloneInfo.modified_count} 个文件</Tag>}
                </Space>
              </div>
            )}
            {cloneStatus === 'cloned' && (
              <div style={{ borderTop: '1px dashed #e8e8e8', paddingTop: 8, marginTop: 4 }}>
                <Row gutter={8} align="middle" style={{ marginBottom: 6 }}>
                  <Col><BranchesOutlined style={{ color: '#1677ff' }} /> <Text strong style={{ fontSize: 12 }}>分支:</Text></Col>
                  <Col flex="auto">
                    <Select
                      style={{ width: '100%' }}
                      placeholder="选择分支切换"
                      value={currentBranch || undefined}
                      loading={branchesLoading}
                      onChange={(val) => { setSelectedBranchToSwitch(val); handleSwitchBranch(val) }}
                      options={branches.map(b => ({
                        value: b.name,
                        label: (
                          <span>
                            {b.is_current ? <Tag color="blue" style={{ fontSize: 9, lineHeight: '14px', padding: '0 3px', marginRight: 4 }}>当前</Tag> : null}
                            {b.name}
                            {b.is_remote && !b.is_current && <Tag style={{ fontSize: 9, lineHeight: '14px', padding: '0 3px', marginLeft: 4 }}>远程</Tag>}
                          </span>
                        ),
                      }))}
                      popupMatchSelectWidth={false}
                    />
                  </Col>
                  <Col>
                    <Button size="small" icon={<ReloadOutlined />} onClick={loadBranches} loading={branchesLoading} />
                  </Col>
                </Row>
                <Row gutter={8} align="middle">
                  <Col><Text strong style={{ fontSize: 12 }}>基于:</Text></Col>
                  <Col>
                    <Select
                      style={{ width: 200 }}
                      placeholder="自动检测主分支"
                      value={baseBranch || undefined}
                      onChange={setBaseBranch}
                      allowClear
                      options={[
                        { value: '', label: '自动检测 (origin/main 或 master)' },
                        ...branches.map(b => ({
                          value: b.name,
                          label: `${b.is_current ? '★ ' : ''}${b.name}${b.is_remote ? ' (远程)' : ''}`,
                        })),
                      ]}
                    />
                  </Col>
                </Row>
                <Row gutter={8} align="middle">
                  <Col><Text strong style={{ fontSize: 12 }}>新分支:</Text></Col>
                  <Col flex="auto">
                    <Input
                      placeholder="输入新分支名称，如 feature/add-op"
                      value={newBranchName}
                      onChange={e => setNewBranchName(e.target.value)}
                      onPressEnter={handleCreateBranch}
                      style={{ width: '100%' }}
                      suffix={
                        <Button type="link" size="small" icon={<PlusOutlined />} onClick={handleCreateBranch} loading={branchCreating} disabled={!newBranchName.trim()} style={{ padding: 0 }}>
                          创建并切换
                        </Button>
                      }
                    />
                  </Col>
                </Row>
              </div>
            )}
          </Space>
        </Card>

        {/* Step 2: 安装插件 */}
        <Card size="small" title={
          <Space>
            <ToolOutlined />
            <span>Step 2: 安装插件</span>
            {installStatus === 'installed' && <Tag color="green" style={{ fontSize: 10 }}>已安装</Tag>}
            {installStatus === 'installing' && <Tag color="blue" style={{ fontSize: 10 }}><LoadingOutlined /> 安装中</Tag>}
            {installStatus === 'checking' && <Tag color="blue" style={{ fontSize: 10 }}><LoadingOutlined /> 检测中</Tag>}
          </Space>
        }>
          <Row gutter={12} align="middle">
            <Col>
              <Space>
                <Text strong style={{ fontSize: 12 }}>插件:</Text>
                <Select
                  style={{ width: 260 }}
                  placeholder="选择插件"
                  loading={pluginsLoading}
                  value={selectedPlugin}
                  onChange={onSelectedPluginChange}
                  options={(plugins || []).map(p => ({
                    value: p.plugin_id,
                    label: `${p.plugin_name}${p.agents_count ? ` (${p.agents_count} agents)` : ''}`,
                  }))}
                />
              </Space>
            </Col>
            <Col>
              <Space>
                <Text strong style={{ fontSize: 12 }}>工具:</Text>
                <Select
                  style={{ width: 120 }}
                  value={selectedTool}
                  onChange={onSelectedToolChange}
                  options={[
                    { value: 'claude', label: 'Claude' },
                    { value: 'cursor', label: 'Cursor' },
                    { value: 'trae', label: 'Trae' },
                    { value: 'opencode', label: 'OpenCode' },
                  ]}
                />
              </Space>
            </Col>
            <Col>
              <Button
                icon={<ToolOutlined />}
                onClick={handleInstall}
                loading={installStatus === 'installing' || installStatus === 'checking'}
                disabled={!selectedPlugin || !workDir?.trim() || installStatus === 'installing' || installStatus === 'installed' || installStatus === 'checking'}
                type={installStatus === 'installed' ? 'default' : 'primary'}
              >
                {installStatus === 'installed' ? '已安装' : installStatus === 'installing' ? '安装中...' : installStatus === 'checking' ? '检测中...' : '安装到工作目录'}
              </Button>
            </Col>
          </Row>
          {installInfo && (
            <div style={{ marginTop: 6 }}>
              <Space size={8}>
                <Tag style={{ fontSize: 10 }}>工具: {selectedTool}</Tag>
                {installInfo.skills?.length > 0 && <Tag color="green" style={{ fontSize: 10 }}>Skills: {installInfo.skills.length}</Tag>}
                {installInfo.agents?.length > 0 && <Tag color="blue" style={{ fontSize: 10 }}>Agents: {installInfo.agents.length}</Tag>}
              </Space>
            </div>
          )}
          {selectedPlugin && (
            <div style={{ marginTop: 8 }}>
              <Button size="small" type="link" icon={<ApartmentOutlined />} onClick={() => onViewArch && onViewArch(selectedPlugin)}>
                查看插件架构
              </Button>
            </div>
          )}
        </Card>

        {/* Step 3: 启动参数 */}
        <Card size="small" title={
          <Space><ExperimentOutlined /><span>Step 3: 启动参数</span></Space>
        }>
          <Space direction="vertical" size={6} style={{ width: '100%' }}>
            <Row gutter={8} align="middle">
              <Col><Text strong style={{ fontSize: 12 }}>算子名:</Text></Col>
              <Col>
                <Input style={{ width: 200 }} placeholder="如 Abs, Add, ScaledBesselI1" value={opName} onChange={onOpNameChange} />
              </Col>
            </Row>
            <Row gutter={8} align="middle">
              <Col><Text strong style={{ fontSize: 12 }}>需求描述:</Text></Col>
              <Col flex="auto">
                <Input.TextArea
                  placeholder="描述算子开发需求，如：指数缩放第一类修正贝塞尔函数 I₁(x)·exp(-|x|) 的 AscendC 实现，支持 float16/float32"
                  value={opSpec}
                  onChange={onOpSpecChange}
                  autoSize={{ minRows: 2, maxRows: 4 }}
                  style={{ width: '100%' }}
                />
              </Col>
            </Row>
            <Row gutter={8} align="middle">
              <Col><Text strong style={{ fontSize: 12 }}>步骤超时:</Text></Col>
              <Col>
                <Select
                  style={{ width: 160 }}
                  value={stepTimeout}
                  onChange={onStepTimeoutChange}
                  options={[
                    { value: 0, label: '不限制 (默认)' },
                    { value: 600, label: '10 分钟' },
                    { value: 1800, label: '30 分钟' },
                    { value: 3600, label: '60 分钟' },
                  ]}
                />
              </Col>
              <Col>
                <Tooltip title="步骤执行超时限制。默认不限制，长任务安全。">
                  <WarningOutlined style={{ color: '#faad14' }} />
                </Tooltip>
              </Col>
            </Row>
            <Row align="middle" gutter={8}>
              <Col>
                <Switch size="small" checked={autoPipeline} onChange={onAutoPipelineChange} disabled={!gitcodeToken?.trim()} />
              </Col>
              <Col><Text style={{ fontSize: 12 }}>自动触发 CI/CD 流水线</Text></Col>
              <Col>
                <Tooltip title="开启后，评估完成后将自动提交 PR、触发流水线编译测试，失败时自动修复（需填写 GitCode Token）">
                  <WarningOutlined style={{ color: autoPipeline ? '#1677ff' : '#d9d9d9', fontSize: 12 }} />
                </Tooltip>
              </Col>
            </Row>
          </Space>
        </Card>

        <div style={{ textAlign: 'right', marginTop: 4 }}>
          <Space>
            <Button onClick={onCancel}>取消</Button>
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              loading={starting}
              disabled={!selectedPlugin || !opName?.trim()}
              onClick={handleSubmit}
            >
              开始评估
            </Button>
          </Space>
        </div>
      </Space>
    </Modal>
  )
}
