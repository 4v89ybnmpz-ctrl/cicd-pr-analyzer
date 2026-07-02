import { useState, useEffect } from 'react'
import {
  Card,
  Tag,
  Row,
  Col,
  Button,
  Spin,
  Input,
  Select,
  Steps,
  message,
  Space,
  Typography,
} from 'antd'
import {
  StopOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
  DownOutlined,
  UpOutlined,
  ThunderboltOutlined,
  RocketOutlined,
} from '@ant-design/icons'
import {
  getNpuHosts,
} from '../../api'
import '@xyflow/react/dist/style.css'

const { Text } = Typography

const NPU_DEFAULT_BUILD_CMD = 'source /usr/local/Ascend/ascend-toolkit/set_env.sh 2>/dev/null; cd {remote_dir} && bash build.sh 2>&1'
const NPU_DEFAULT_TEST_CMD = 'source /usr/local/Ascend/ascend-toolkit/set_env.sh 2>/dev/null; cd {remote_dir}/tests/st && bash run.sh {op_name} ascend910b1 st 2>&1'

export default function NpuTestPanel({ npuTest, logs, sessionId, sessionStatus, logEndRef, boxRef, onBoxScroll, onTrigger, onCancel, onTriggerClaude }) {
  const [hosts, setHosts] = useState([])
  const [hostsLoading, setHostsLoading] = useState(false)
  const [hostsError, setHostsError] = useState('')
  const [host, setHost] = useState('')
  const [remoteDir, setRemoteDir] = useState('')
  const [buildCmd, setBuildCmd] = useState('')
  const [testCmd, setTestCmd] = useState('')
  const [showAdvanced, setShowAdvanced] = useState(false)

  useEffect(() => {
    setHostsLoading(true)
    getNpuHosts()
      .then(res => {
        setHosts(res.data?.hosts || [])
        setHostsError(res.data?.error || '')
      })
      .catch(() => setHostsError('获取 ssh host 列表失败'))
      .finally(() => setHostsLoading(false))
  }, [])

  const status = npuTest?.status || 'pending'
  const steps = npuTest?.steps || []
  const hasRun = steps.length > 0
  const isRunning = status === 'running'
  const canTrigger = !!onTrigger && (sessionStatus === 'completed' || sessionStatus === 'stopped') && !isRunning

  const handleTrigger = () => {
    if (!host) { message.warning('请选择 SSH Host'); return }
    onTrigger({
      host,
      remote_dir: remoteDir.trim(),
      build_cmd: buildCmd.trim(),
      test_cmd: testCmd.trim(),
      env_check: true,
      cleanup: true,
    })
  }

  const statusTag = {
    pending:   <Tag>未测试</Tag>,
    running:   <Tag color="processing" icon={<LoadingOutlined />}>测试中</Tag>,
    success:   <Tag color="success" icon={<CheckCircleOutlined />}>通过</Tag>,
    failed:    <Tag color="error" icon={<CloseCircleOutlined />}>失败</Tag>,
    cancelled: <Tag color="default">已取消</Tag>,
    timeout:   <Tag color="warning">超时</Tag>,
  }[status] || <Tag>{status}</Tag>

  const summary = npuTest?.summary

  return (
    <Card size="small" title={
      <Space>
        <RocketOutlined style={{ color: '#722ed1' }} />
        <span>真机 NPU 远程测试</span>
        {statusTag}
        {isRunning && <Spin size="small" />}
      </Space>
    } extra={
      <Space>
        {isRunning && onCancel && (
          <Button size="small" danger icon={<StopOutlined />} onClick={onCancel}>取消测试</Button>
        )}
        {!hasRun && canTrigger && (
          <Button size="small" type="primary" icon={<RocketOutlined />}
            disabled={!host || hostsLoading}
            onClick={handleTrigger}
          >发起真机测试</Button>
        )}
        {canTrigger && (
          <Button size="small" icon={<ThunderboltOutlined />}
            disabled={!host}
            onClick={() => {
              const cfg = {
                ssh_host: host,
                remote_dir: remoteDir || `/tmp/cannbot-npu-${sessionId}`,
                build_cmd: buildCmd || '',
                test_cmd: testCmd || '',
              }
              onTriggerClaude && onTriggerClaude(cfg)
            }}
          >Claude 真机测试</Button>
        )}
      </Space>
    }>
      {/* 配置区：未触发或可重新发起时展示 */}
      {(!hasRun || !isRunning) && (
        <div style={{ marginBottom: hasRun ? 12 : 0 }}>
          <Row gutter={8} align="middle" style={{ marginBottom: 6 }}>
            <Col><Text strong style={{ fontSize: 12 }}>SSH Host:</Text></Col>
            <Col flex="auto">
              <Select
                style={{ width: '100%' }}
                placeholder="选择 ~/.ssh/config 中的 Host"
                value={host || undefined}
                loading={hostsLoading}
                onChange={setHost}
                notFoundContent={hostsError || '未找到 ssh Host'}
                options={hosts.map(h => ({ value: h, label: h }))}
                popupMatchSelectWidth={false}
              />
            </Col>
            {hostsError && <Col><Text type="danger" style={{ fontSize: 11 }}>{hostsError}</Text></Col>}
          </Row>
          <Row gutter={8} align="middle" style={{ marginBottom: 6 }}>
            <Col><Text strong style={{ fontSize: 12 }}>远程目录:</Text></Col>
            <Col flex="auto">
              <Input
                placeholder={sessionId ? `/tmp/cannbot-npu-${sessionId}` : '/tmp/cannbot-npu-{session}'}
                value={remoteDir}
                onChange={e => setRemoteDir(e.target.value)}
                style={{ width: '100%' }}
              />
            </Col>
            <Col>
              <Button size="small" type="link" icon={showAdvanced ? <UpOutlined /> : <DownOutlined />}
                onClick={() => setShowAdvanced(v => !v)}
              >{showAdvanced ? '收起命令' : '自定义命令'}</Button>
            </Col>
          </Row>
          {showAdvanced && (
            <div style={{ padding: 8, background: '#fafafa', borderRadius: 4, marginBottom: 6 }}>
              <Text type="secondary" style={{ fontSize: 11 }}>编译命令（占位符 {`{remote_dir}/{op_name}`}）:</Text>
              <Input.TextArea
                value={buildCmd}
                onChange={e => setBuildCmd(e.target.value)}
                placeholder={NPU_DEFAULT_BUILD_CMD}
                autoSize={{ minRows: 2, maxRows: 4 }}
                style={{ marginTop: 4, marginBottom: 8, fontFamily: 'Menlo, Monaco, monospace', fontSize: 11 }}
              />
              <Text type="secondary" style={{ fontSize: 11 }}>测试命令:</Text>
              <Input.TextArea
                value={testCmd}
                onChange={e => setTestCmd(e.target.value)}
                placeholder={NPU_DEFAULT_TEST_CMD}
                autoSize={{ minRows: 2, maxRows: 4 }}
                style={{ marginTop: 4, fontFamily: 'Menlo, Monaco, monospace', fontSize: 11 }}
              />
            </div>
          )}
        </div>
      )}

      {/* 步骤进度 */}
      {hasRun && (
        <>
          {npuTest?.host && (
            <div style={{ marginBottom: 8 }}>
              <Space size={6} wrap>
                <Tag color="purple" style={{ fontSize: 10 }}>Host: {npuTest.host}</Tag>
                {npuTest.remote_dir && <Tag style={{ fontSize: 10 }}>{npuTest.remote_dir}</Tag>}
                {npuTest.triggered_at && <Text type="secondary" style={{ fontSize: 11 }}>{npuTest.triggered_at}</Text>}
              </Space>
            </div>
          )}
          <Steps
            size="small"
            current={steps.findIndex(s => s.status === 'running')}
            style={{ marginBottom: 12 }}
            items={steps.map(s => {
              const st = s.status
              return {
                title: <span style={{ fontSize: 11 }}>{s.name}</span>,
                status: st === 'running' ? 'process' : st === 'success' ? 'finish'
                  : st === 'failed' || st === 'cancelled' ? 'error' : 'wait',
                icon: st === 'success' ? <CheckCircleOutlined style={{ color: '#52c41a' }} />
                  : st === 'failed' || st === 'cancelled' ? <CloseCircleOutlined style={{ color: '#ff4d4f' }} />
                  : st === 'running' ? <LoadingOutlined /> : null,
              }
            })}
          />

          {/* 错误详情 */}
          {npuTest?.error_detail && (
            <div style={{ marginBottom: 8, padding: 8, borderRadius: 6, background: '#fff1f0', borderLeft: '3px solid #ff4d4f' }}>
              <Space size={6} style={{ marginBottom: 4 }}>
                <Tag color="red" style={{ fontSize: 10 }}>{npuTest.error_detail.category}</Tag>
                <Text strong style={{ fontSize: 12 }}>真机测试错误</Text>
              </Space>
              <div style={{ fontSize: 11, lineHeight: 1.8 }}>
                <div><Text type="secondary">根因：</Text><Text type="danger">{npuTest.error_detail.root_cause}</Text></div>
                {npuTest.error_detail.original_error && (
                  <div><Text type="secondary">原始：</Text><Text code style={{ fontSize: 10 }}>{String(npuTest.error_detail.original_error).slice(0, 200)}</Text></div>
                )}
                <div style={{ marginTop: 4, padding: '4px 8px', background: '#fff', borderRadius: 4 }}>
                  <Text type="secondary">建议：</Text><Text style={{ color: '#1677ff' }}>{npuTest.error_detail.suggestion}</Text>
                </div>
              </div>
            </div>
          )}

          {/* 结果摘要 */}
          {summary && (
            <div style={{ marginBottom: 8, padding: 8, borderRadius: 6,
              background: summary.passed ? '#f6ffed' : '#fff1f0',
              borderLeft: `3px solid ${summary.passed ? '#52c41a' : '#ff4d4f'}` }}>
              <Space size={8} wrap>
                <Tag color={summary.passed ? 'success' : 'error'}>
                  {summary.passed ? '✅ 全部通过' : '❌ 存在失败'}
                </Tag>
                <Text style={{ fontSize: 12 }}>通过 <Text strong style={{ color: '#52c41a' }}>{summary.passed_count}</Text></Text>
                <Text style={{ fontSize: 12 }}>失败 <Text strong style={{ color: '#ff4d4f' }}>{summary.failed_count}</Text></Text>
                <Text style={{ fontSize: 12 }}>共 {summary.total}</Text>
              </Space>
            </div>
          )}
        </>
      )}

      {/* 远程日志流 */}
      {logs.length > 0 && (
        <div>
          <div style={{ marginBottom: 4 }}>
            <Text strong style={{ fontSize: 12 }}>远程日志</Text>
            <Tag style={{ fontSize: 10, marginLeft: 8 }}>{logs.length} 行</Tag>
          </div>
          <div ref={boxRef} onScroll={onBoxScroll} style={{
            background: '#1e1e1e', borderRadius: 6, padding: 8,
            maxHeight: 360, overflowY: 'auto',
            fontFamily: 'Menlo, Monaco, monospace', fontSize: 12,
          }}>
            {logs.map((l, i) => {
              const color = l.stream === 'stderr' ? '#ff6b6b'
                : l.stream === 'stdout' ? '#d4d4d4' : '#999'
              return (
                <div key={i} style={{ color, lineHeight: '18px', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                  {l.line}
                </div>
              )
            })}
            <div ref={logEndRef} />
          </div>
        </div>
      )}
    </Card>
  )
}

