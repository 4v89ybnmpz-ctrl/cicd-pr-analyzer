import { useState, useEffect, useCallback } from 'react'
import {
  Card, Row, Col, Spin, Alert, Tag, Space, Select, InputNumber,
  Table, Tooltip, Tabs, Statistic, Button, message, DatePicker,
} from 'antd'
import {
  HeatMapOutlined, FileTextOutlined, FolderOutlined,
  ThunderboltOutlined, QuestionCircleOutlined,
} from '@ant-design/icons'
import * as api from '../api'

const HEATMAP_RULES = (
  <div style={{ maxWidth: 480, fontSize: 12, lineHeight: 1.8 }}>
    <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 6 }}>热力图计算规则</div>
    <div style={{ color: '#999', marginBottom: 8 }}>基于 PR 变更文件数据，按文件和目录聚合变更统计</div>
    <div style={{ fontWeight: 600, marginTop: 8 }}>数据来源</div>
    <div>GitHub API <code>/repos/{'{owner}'}/{'{repo}'}/pulls/{'{pr}'}/files</code></div>
    <div>存储在 <code>pr_files</code> 集合，每个 PR 一个文档</div>
    <div style={{ fontWeight: 600, marginTop: 8 }}>文件级聚合</div>
    <div>对每个文件统计：变更次数（出现在多少个 PR 中）、累计 additions/deletions/changes</div>
    <div>热度值 = 变更次数 / 最大变更次数 × 100（归一化到 0-100）</div>
    <div style={{ fontWeight: 600, marginTop: 8 }}>目录级聚合</div>
    <div>对每级目录递归聚合子文件的变更统计</div>
    <div>热度值同上归一化</div>
    <div style={{ fontWeight: 600, marginTop: 8 }}>颜色映射</div>
    <div>
      <span style={{ color: '#52c41a' }}>■</span> 0-20 &nbsp;
      <span style={{ color: '#faad14' }}>■</span> 20-40 &nbsp;
      <span style={{ color: '#fa8c16' }}>■</span> 40-60 &nbsp;
      <span style={{ color: '#ff4d4f' }}>■</span> 60-80 &nbsp;
      <span style={{ color: '#cf1322' }}>■</span> 80-100
    </div>
  </div>
)

function heatColor(heat) {
  if (heat >= 80) return '#cf1322'
  if (heat >= 60) return '#ff4d4f'
  if (heat >= 40) return '#fa8c16'
  if (heat >= 20) return '#faad14'
  return '#52c41a'
}

export default function CodeHeatmap() {
  const [projects, setProjects] = useState([])
  const [selected, setSelected] = useState(null)
  const [topN, setTopN] = useState(50)
  const [dateRange, setDateRange] = useState(null)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [fetchingFiles, setFetchingFiles] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.getProjectsOverview()
      .then(res => {
        const list = res.data.projects || []
        setProjects(list)
        if (list.length > 0) setSelected(list[0])
      })
      .catch(() => {})
  }, [])

  const fetchData = useCallback(async () => {
    if (!selected) return
    setLoading(true)
    setError(null)
    try {
      const res = await api.getCodeHeatmap(selected.owner, selected.repo, {
        top_n: topN,
        ...(dateRange?.[0] ? { start_date: dateRange[0].format('YYYY-MM-DD') } : {}),
        ...(dateRange?.[1] ? { end_date: dateRange[1].format('YYYY-MM-DD') } : {}),
      })
      setData(res.data)
    } catch (e) {
      setError(e.message)
    }
    setLoading(false)
  }, [selected, topN, dateRange])

  useEffect(() => { fetchData() }, [fetchData])

  if (projects.length === 0 && !loading) {
    return <Alert type="info" message="暂无项目数据" />
  }

  const files = data?.files || []
  const directories = data?.directories || []

  const fetchFiles = async () => {
    if (!selected) return
    setFetchingFiles(true)
    try {
      const res = await api.fetchPrFiles(selected.owner, selected.repo, { limit: 30 })
      const d = res.data
      if (d.task) {
        message.success({ content: `任务已创建，请在「任务监控」中查看进度`, key: 'fetch' })
        // 轮询等待任务完成
        const taskId = d.task.task_id
        const poll = setInterval(async () => {
          try {
            const taskRes = await api.getTask(taskId)
            const status = taskRes.data.status
            if (status === 'completed') {
              clearInterval(poll)
              message.success({ content: `文件获取完成`, key: 'fetch' })
              setFetchingFiles(false)
              fetchData()
            } else if (status === 'failed') {
              clearInterval(poll)
              message.error({ content: `文件获取失败`, key: 'fetch' })
              setFetchingFiles(false)
            }
          } catch { clearInterval(poll); setFetchingFiles(false) }
        }, 3000)
      } else {
        message.info({ content: d.message || '任务已存在', key: 'fetch' })
        setFetchingFiles(false)
      }
    } catch (e) {
      message.error({ content: `创建任务失败: ${e.message}`, key: 'fetch' })
      setError(e.message)
      setFetchingFiles(false)
    }
  }

  const fileColumns = [
    {
      title: '文件路径', dataIndex: 'filename', key: 'filename', ellipsis: true,
      render: v => <Tooltip title={v}><code style={{ fontSize: 12 }}>{v}</code></Tooltip>,
    },
    { title: '变更次数', dataIndex: 'change_count', key: 'change_count', width: 90, sorter: (a, b) => a.change_count - b.change_count, defaultSortOrder: 'descend' },
    { title: 'Add', dataIndex: 'total_additions', key: 'total_additions', width: 80, render: v => <span style={{ color: '#52c41a' }}>+{v?.toLocaleString()}</span> },
    { title: 'Del', dataIndex: 'total_deletions', key: 'total_deletions', width: 80, render: v => <span style={{ color: '#ff4d4f' }}>-{v?.toLocaleString()}</span> },
    { title: '涉及 PR', dataIndex: 'pr_numbers', key: 'pr_numbers', width: 120, render: v => v?.length || 0 },
    {
      title: '热度', dataIndex: 'heat', key: 'heat', width: 100, sorter: (a, b) => a.heat - b.heat,
      render: v => (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{ width: 48, height: 16, borderRadius: 3, background: heatColor(v), opacity: 0.9 }} />
          <span style={{ fontSize: 12, fontWeight: 600, color: heatColor(v) }}>{v}</span>
        </div>
      ),
    },
  ]

  const dirColumns = [
    { title: '目录', dataIndex: 'directory', key: 'directory', ellipsis: true, render: v => <code style={{ fontSize: 12 }}>{v}</code> },
    { title: '变更次数', dataIndex: 'change_count', key: 'change_count', width: 90, sorter: (a, b) => a.change_count - b.change_count, defaultSortOrder: 'descend' },
    { title: 'Add', dataIndex: 'total_additions', key: 'total_additions', width: 80, render: v => <span style={{ color: '#52c41a' }}>+{v?.toLocaleString()}</span> },
    { title: 'Del', dataIndex: 'total_deletions', key: 'total_deletions', width: 80, render: v => <span style={{ color: '#ff4d4f' }}>-{v?.toLocaleString()}</span> },
    { title: '文件数', dataIndex: 'file_count', key: 'file_count', width: 80 },
    {
      title: '热度', dataIndex: 'heat', key: 'heat', width: 100, sorter: (a, b) => a.heat - b.heat,
      render: v => (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{ width: 48, height: 16, borderRadius: 3, background: heatColor(v), opacity: 0.9 }} />
          <span style={{ fontSize: 12, fontWeight: 600, color: heatColor(v) }}>{v}</span>
        </div>
      ),
    },
  ]

  return (
    <div>
      <Row gutter={[16, 16]} align="middle" style={{ marginBottom: 24 }}>
        <Col>
          <h2 style={{ margin: 0 }}><HeatMapOutlined style={{ marginRight: 8, color: '#fa541c' }} />代码变更热力图</h2>
        </Col>
        <Col>
          <Tooltip title={HEATMAP_RULES} placement="bottomLeft" overlayStyle={{ maxWidth: 520 }} color="#fff" overlayInnerStyle={{ color: '#333' }}>
            <Tag style={{ cursor: 'pointer', fontSize: 13, padding: '2px 10px' }}>
              <QuestionCircleOutlined /> 逻辑介绍
            </Tag>
          </Tooltip>
        </Col>
        <Col flex="auto" />
        <Col>
          <Space>
            <Select
              value={selected ? `${selected.owner}/${selected.repo}` : undefined}
              onChange={v => { const p = projects.find(x => `${x.owner}/${x.repo}` === v); if (p) setSelected(p) }}
              style={{ width: 240 }}
              placeholder="选择项目"
              showSearch
              options={projects.map(p => ({ value: `${p.owner}/${p.repo}`, label: `${p.owner}/${p.repo}` }))}
            />
            <InputNumber min={10} max={200} value={topN} onChange={v => setTopN(v || 50)} style={{ width: 70 }} addonAfter="条" />
            <DatePicker.RangePicker
              value={dateRange}
              onChange={setDateRange}
              placeholder={['开始日期', '结束日期']}
              style={{ width: 240 }}
            />
            <Button icon={<ThunderboltOutlined />} onClick={fetchFiles} loading={fetchingFiles}>获取文件数据</Button>
          </Space>
        </Col>
      </Row>

      {loading && <Spin size="large" style={{ display: 'block', margin: '60px auto' }} />}
      {error && <Alert type="error" message={error} style={{ marginBottom: 16 }} />}

      {!loading && data && (
        <>
          <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
            <Col span={6}>
              <Card bodyStyle={{ padding: '16px 20px', textAlign: 'center' }}>
                <Statistic title="涉及 PR" value={data.total_prs || 0} prefix={<FileTextOutlined />} valueStyle={{ color: '#1890ff' }} />
              </Card>
            </Col>
            <Col span={6}>
              <Card bodyStyle={{ padding: '16px 20px', textAlign: 'center' }}>
                <Statistic title="变更文件" value={data.total_files || 0} prefix={<FileTextOutlined />} valueStyle={{ color: '#fa541c' }} />
              </Card>
            </Col>
            <Col span={6}>
              <Card bodyStyle={{ padding: '16px 20px', textAlign: 'center' }}>
                <Statistic title="变更目录" value={data.total_dirs || 0} prefix={<FolderOutlined />} valueStyle={{ color: '#722ed1' }} />
              </Card>
            </Col>
            <Col span={6}>
              <Card bodyStyle={{ padding: '16px 20px', textAlign: 'center' }}>
                <Statistic title="Top N" value={topN} valueStyle={{ color: '#52c41a' }} />
              </Card>
            </Col>
          </Row>

          {files.length === 0 && directories.length === 0 ? (
            <Card style={{ textAlign: 'center', padding: 40 }}>
              <div style={{ fontSize: 48, color: '#d9d9d9', marginBottom: 12 }}>📊</div>
              <div style={{ fontSize: 16, fontWeight: 600, color: '#999' }}>暂无变更文件数据</div>
              <div style={{ fontSize: 13, color: '#999', marginTop: 4 }}>点击「获取文件数据」从 GitHub 拉取 PR 变更文件</div>
            </Card>
          ) : (
            <Tabs
              defaultActiveKey="files"
              items={[
                {
                  key: 'files',
                  label: <span><FileTextOutlined /> 文件热力图</span>,
                  children: (
                    <Table
                      size="small"
                      dataSource={files.map((f, i) => ({ key: i, ...f }))}
                      columns={fileColumns}
                      pagination={{ pageSize: 20, showTotal: t => `共 ${t} 个文件` }}
                      scroll={{ x: 600 }}
                    />
                  ),
                },
                {
                  key: 'dirs',
                  label: <span><FolderOutlined /> 目录热力图</span>,
                  children: (
                    <Table
                      size="small"
                      dataSource={directories.map((d, i) => ({ key: i, ...d }))}
                      columns={dirColumns}
                      pagination={{ pageSize: 20, showTotal: t => `共 ${t} 个目录` }}
                      scroll={{ x: 600 }}
                    />
                  ),
                },
              ]}
            />
          )}
        </>
      )}
    </div>
  )
}
