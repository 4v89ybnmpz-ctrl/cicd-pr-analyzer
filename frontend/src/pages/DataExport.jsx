import { useState, useEffect } from 'react'
import {
  Card, Row, Col, Select, Radio, Button, DatePicker, Space, Spin, Alert, message, Divider, Tag,
} from 'antd'
import {
  DownloadOutlined, FileExcelOutlined, FilePdfOutlined, FileTextOutlined, RocketOutlined,
} from '@ant-design/icons'
import * as api from '../api'

const { RangePicker } = DatePicker

// 报告类型选项
const REPORT_TYPES = [
  { value: 'all', label: '综合报告' },
  { value: 'project_health', label: '项目健康度' },
  { value: 'review_quality', label: 'Review 质量' },
  { value: 'trend_alerts', label: '趋势预警' },
  { value: 'cicd', label: 'CI/CD 洞察' },
]

// 数据集合选项
const COLLECTION_OPTIONS = [
  { value: 'pr_data', label: 'PR 列表' },
  { value: 'pr_details', label: 'PR 详情' },
  { value: 'pr_comments', label: 'PR 评论' },
  { value: 'pr_reviews', label: 'PR Reviews' },
  { value: 'pr_commits', label: 'PR Commits' },
  { value: 'pr_files', label: 'PR 变更文件' },
  { value: 'issues', label: 'Issues' },
  { value: 'cicd_results', label: 'CI/CD 结果' },
]

export default function DataExport() {
  // 项目列表
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)

  // 报告导出状态
  const [reportProject, setReportProject] = useState(null)
  const [reportType, setReportType] = useState('all')
  const [reportFormat, setReportFormat] = useState('pdf')
  const [dateRange, setDateRange] = useState(null)
  const [exportingReport, setExportingReport] = useState(false)

  // 数据导出状态
  const [dataProject, setDataProject] = useState(null)
  const [dataCollection, setDataCollection] = useState('pr_data')
  const [dataFormat, setDataFormat] = useState('excel')
  const [exportingData, setExportingData] = useState(false)

  useEffect(() => {
    api.getProjectsOverview()
      .then(res => {
        const list = res.data.projects || []
        setProjects(list)
        if (list.length > 0) {
          setReportProject(list[0])
          setDataProject(list[0])
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  // 触发文件下载
  const triggerDownload = (blob, filename) => {
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  // 导出报告
  const handleExportReport = async () => {
    if (!reportProject) {
      message.warning('请先选择项目')
      return
    }
    setExportingReport(true)
    try {
      const params = { format: reportFormat, report_type: reportType }
      if (dateRange?.[0]) params.start_date = dateRange[0].format('YYYY-MM-DD')
      if (dateRange?.[1]) params.end_date = dateRange[1].format('YYYY-MM-DD')

      const res = await api.exportReport(reportProject.owner, reportProject.repo, params)
      const ext = reportFormat === 'pdf' ? 'pdf' : 'xlsx'
      const filename = `report_${reportProject.owner}_${reportProject.repo}_${reportType}.${ext}`
      triggerDownload(res.data, filename)
      message.success('报告导出成功')
    } catch (e) {
      message.error(`导出失败: ${e.message}`)
    } finally {
      setExportingReport(false)
    }
  }

  // 导出原始数据
  const handleExportData = async () => {
    if (!dataProject) {
      message.warning('请先选择项目')
      return
    }
    setExportingData(true)
    try {
      const params = { collection: dataCollection, format: dataFormat }
      const res = await api.exportData(dataProject.owner, dataProject.repo, params)
      const ext = dataFormat === 'csv' ? 'csv' : 'xlsx'
      const filename = `${dataProject.owner}_${dataProject.repo}_${dataCollection}.${ext}`
      triggerDownload(res.data, filename)
      message.success('数据导出成功')
    } catch (e) {
      message.error(`导出失败: ${e.message}`)
    } finally {
      setExportingData(false)
    }
  }

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />

  const projectOptions = projects.map(p => ({
    value: `${p.owner}/${p.repo}`,
    label: `${p.owner}/${p.repo}`,
  }))

  const selectProject = (val, setter) => {
    const p = projects.find(x => `${x.owner}/${x.repo}` === val)
    if (p) setter(p)
  }

  return (
    <div>
      <Row gutter={[16, 16]} align="middle" style={{ marginBottom: 24 }}>
        <Col><h2 style={{ margin: 0 }}><DownloadOutlined style={{ marginRight: 8, color: '#1890ff' }} />数据导出</h2></Col>
      </Row>

      {projects.length === 0 ? (
        <Alert type="warning" message="暂无已注册项目，请先在项目总览中添加项目" showIcon />
      ) : (
        <Row gutter={[16, 16]}>
          {/* 报告导出 */}
          <Col xs={24}>
            <Card
              title={<span><FilePdfOutlined style={{ marginRight: 8 }} />分析报告导出</span>}
              extra={<Tag color="blue">PDF / Excel</Tag>}
            >
              <Row gutter={[16, 16]} align="middle">
                <Col xs={24} md={6}>
                  <div style={{ marginBottom: 4, color: '#666', fontSize: 13 }}>选择项目</div>
                  <Select
                    value={reportProject ? `${reportProject.owner}/${reportProject.repo}` : undefined}
                    onChange={v => selectProject(v, setReportProject)}
                    options={projectOptions}
                    style={{ width: '100%' }}
                    showSearch
                    placeholder="选择项目"
                  />
                </Col>
                <Col xs={24} md={5}>
                  <div style={{ marginBottom: 4, color: '#666', fontSize: 13 }}>报告类型</div>
                  <Select
                    value={reportType}
                    onChange={setReportType}
                    options={REPORT_TYPES}
                    style={{ width: '100%' }}
                  />
                </Col>
                <Col xs={24} md={7}>
                  <div style={{ marginBottom: 4, color: '#666', fontSize: 13 }}>日期范围（可选）</div>
                  <RangePicker
                    value={dateRange}
                    onChange={setDateRange}
                    style={{ width: '100%' }}
                    placeholder={['开始日期', '结束日期']}
                  />
                </Col>
                <Col xs={24} md={3}>
                  <div style={{ marginBottom: 4, color: '#666', fontSize: 13 }}>格式</div>
                  <Radio.Group value={reportFormat} onChange={e => setReportFormat(e.target.value)}>
                    <Radio.Button value="pdf"><FilePdfOutlined /> PDF</Radio.Button>
                    <Radio.Button value="excel"><FileExcelOutlined /> Excel</Radio.Button>
                  </Radio.Group>
                </Col>
                <Col xs={24} md={3}>
                  <div style={{ marginBottom: 4, color: '#666', fontSize: 13 }}>&nbsp;</div>
                  <Button
                    type="primary"
                    icon={<DownloadOutlined />}
                    onClick={handleExportReport}
                    loading={exportingReport}
                    block
                  >
                    导出报告
                  </Button>
                </Col>
              </Row>
            </Card>
          </Col>

          {/* 原始数据导出 */}
          <Col xs={24}>
            <Card
              title={<span><FileTextOutlined style={{ marginRight: 8 }} />原始数据导出</span>}
              extra={<Tag color="green">Excel / CSV</Tag>}
            >
              <Row gutter={[16, 16]} align="middle">
                <Col xs={24} md={7}>
                  <div style={{ marginBottom: 4, color: '#666', fontSize: 13 }}>选择项目</div>
                  <Select
                    value={dataProject ? `${dataProject.owner}/${dataProject.repo}` : undefined}
                    onChange={v => selectProject(v, setDataProject)}
                    options={projectOptions}
                    style={{ width: '100%' }}
                    showSearch
                    placeholder="选择项目"
                  />
                </Col>
                <Col xs={24} md={6}>
                  <div style={{ marginBottom: 4, color: '#666', fontSize: 13 }}>数据集合</div>
                  <Select
                    value={dataCollection}
                    onChange={setDataCollection}
                    options={COLLECTION_OPTIONS}
                    style={{ width: '100%' }}
                  />
                </Col>
                <Col xs={24} md={5}>
                  <div style={{ marginBottom: 4, color: '#666', fontSize: 13 }}>格式</div>
                  <Radio.Group value={dataFormat} onChange={e => setDataFormat(e.target.value)}>
                    <Radio.Button value="excel"><FileExcelOutlined /> Excel</Radio.Button>
                    <Radio.Button value="csv"><FileTextOutlined /> CSV</Radio.Button>
                  </Radio.Group>
                </Col>
                <Col xs={24} md={3}>
                  <div style={{ marginBottom: 4, color: '#666', fontSize: 13 }}>&nbsp;</div>
                  <Button
                    type="primary"
                    icon={<DownloadOutlined />}
                    onClick={handleExportData}
                    loading={exportingData}
                    block
                  >
                    导出数据
                  </Button>
                </Col>
              </Row>
            </Card>
          </Col>
        </Row>
      )}
    </div>
  )
}
