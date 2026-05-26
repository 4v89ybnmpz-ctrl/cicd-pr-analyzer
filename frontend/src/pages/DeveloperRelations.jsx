import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { Space, Button, AutoComplete, Tag, Card, Row, Col, Statistic, message, Tooltip, Drawer, Table } from 'antd'
import { SearchOutlined, TeamOutlined, InfoCircleOutlined, ReloadOutlined } from '@ant-design/icons'
import ForceGraph from 'react-force-graph-2d'
import * as api from '../api'

const NODE_COLORS = [
  '#1890ff', '#52c41a', '#faad14', '#eb2f96', '#722ed1',
  '#13c2c2', '#fa541c', '#2f54eb', '#a0d911', '#f5222d',
]

export default function DeveloperRelations() {
  const [projects, setProjects] = useState([])
  const [searchText, setSearchText] = useState('')
  const [queryOwner, setQueryOwner] = useState('')
  const [queryRepo, setQueryRepo] = useState('')
  const [graphData, setGraphData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [selectedNode, setSelectedNode] = useState(null)
  const [highlightNodes, setHighlightNodes] = useState(new Set())
  const [drawerOpen, setDrawerOpen] = useState(false)
  const fgRef = useRef()

  useEffect(() => {
    api.getComments().then(() => {}).catch(() => {})
    // 用所有有评论数据的项目做提示
    fetchProjects()
  }, [])

  const fetchProjects = async () => {
    try {
      const res = await api.getComments({ size: 1 })
      // 用各已有 projects API 组合
      const [commentsP, issuesP, timelinesP] = await Promise.all([
        fetch('/api/database/comments/projects').then(r => r.json()).catch(() => ({ projects: [] })),
        fetch('/api/database/issues/projects').then(r => r.json()).catch(() => ({ projects: [] })),
        fetch('/api/database/issue-timelines/projects').then(r => r.json()).catch(() => ({ projects: [] })),
      ])
      const allMap = {}
      ;[commentsP, issuesP, timelinesP].forEach(d => {
        for (const p of (d.projects || [])) {
          const k = `${p.owner}/${p.repo}`
          if (!allMap[k]) allMap[k] = { owner: p.owner, repo: p.repo, count: 0 }
          allMap[k].count += p.count
        }
      })
      // 也加入 overview 的项目
      const overviewRes = await api.getProjectsOverview()
      for (const p of (overviewRes.data.projects || [])) {
        const k = `${p.owner}/${p.repo}`
        if (!allMap[k]) allMap[k] = { owner: p.owner, repo: p.repo, count: 0 }
      }
      setProjects(Object.values(allMap).sort((a, b) => b.count - a.count))
    } catch {
      setProjects([])
    }
  }

  const projectOptions = useMemo(() => {
    const q = searchText.toLowerCase().trim()
    return projects
      .filter(p => {
        if (!q) return true
        return p.owner.toLowerCase().startsWith(q) ||
               p.repo.toLowerCase().startsWith(q) ||
               `${p.owner}/${p.repo}`.toLowerCase().includes(q)
      })
      .slice(0, 15)
      .map(p => ({
        value: `${p.owner}/${p.repo}`,
        label: (
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span><b>{p.owner}</b>/{p.repo}</span>
            {p.count > 0 && <Tag>{p.count}</Tag>}
          </div>
        ),
      }))
  }, [projects, searchText])

  const fetchRelations = useCallback(async (owner, repo) => {
    if (!owner || !repo) return
    setLoading(true)
    setSelectedNode(null)
    setHighlightNodes(new Set())
    try {
      const res = await api.getDeveloperRelations(owner, repo)
      const data = res.data
      // 给节点分配颜色和大小
      const maxComments = Math.max(...data.nodes.map(n => n.comments), 1)
      data.nodes.forEach((n, i) => {
        n.color = NODE_COLORS[i % NODE_COLORS.length]
        n.val = Math.max(3, (n.comments / maxComments) * 12)
      })
      setGraphData(data)
    } catch (e) {
      message.error('获取关系数据失败: ' + e.message)
    }
    setLoading(false)
  }, [])

  const handleSelect = (value) => {
    const [o, r] = value.split('/')
    setQueryOwner(o)
    setQueryRepo(r)
    setSearchText(value)
    fetchRelations(o, r)
  }

  const handleSearch = () => {
    if (!queryOwner || !queryRepo) {
      message.warning('请选择一个项目')
      return
    }
    fetchRelations(queryOwner, queryRepo)
  }

  const handleNodeClick = (node) => {
    if (selectedNode?.id === node.id) {
      setSelectedNode(null)
      setHighlightNodes(new Set())
      return
    }
    setSelectedNode(node)
    const connected = new Set([node.id])
    graphData.edges.forEach(e => {
      if (e.source.id === node.id || e.source === node.id) {
        connected.add(typeof e.target === 'object' ? e.target.id : e.target)
      }
      if (e.target.id === node.id || e.target === node.id) {
        connected.add(typeof e.source === 'object' ? e.source.id : e.source)
      }
    })
    setHighlightNodes(connected)
  }

  const handleNodeHover = (node) => {
    if (fgRef.current?.container) {
      fgRef.current.container.style.cursor = node ? 'pointer' : 'default'
    }
  }

  // 选中节点的关联边
  const selectedEdges = useMemo(() => {
    if (!selectedNode || !graphData) return []
    return graphData.edges.filter(e => {
      const sId = typeof e.source === 'object' ? e.source.id : e.source
      const tId = typeof e.target === 'object' ? e.target.id : e.target
      return sId === selectedNode.id || tId === selectedNode.id
    }).map(e => {
      const sId = typeof e.source === 'object' ? e.source.id : e.source
      const tId = typeof e.target === 'object' ? e.target.id : e.target
      return {
        key: `${sId}-${tId}`,
        developer: tId === selectedNode.id ? sId : tId,
        ...e,
      }
    }).sort((a, b) => b.weight - a.weight)
  }, [selectedNode, graphData])

  const fgData = useMemo(() => {
    if (!graphData) return { nodes: [], links: [] }
    return {
      nodes: graphData.nodes.map(n => ({ ...n })),
      links: graphData.edges.map(e => ({
        source: e.source,
        target: e.target,
        value: e.weight,
        co_pr: e.co_pr,
        mentions: e.mentions,
      })),
    }
  }, [graphData])

  return (
    <div>
      <h2 style={{ marginBottom: 24 }}><TeamOutlined style={{ marginRight: 8 }} />开发者关系图</h2>

      <Space style={{ marginBottom: 16 }} wrap>
        <AutoComplete
          options={projectOptions}
          onSelect={handleSelect}
          value={searchText}
          onChange={(v) => {
            setSearchText(v || '')
            if (!v) { setQueryOwner(''); setQueryRepo(''); return }
            const idx = v.indexOf('/')
            if (idx >= 0) { setQueryOwner(v.substring(0, idx)); setQueryRepo(v.substring(idx + 1)) }
            else { setQueryOwner(v); setQueryRepo('') }
          }}
          style={{ width: 300 }}
          placeholder="输入项目名称 (owner/repo)"
          filterOption={false}
          allowClear
        />
        <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch} loading={loading}>生成关系图</Button>
        <Button icon={<ReloadOutlined />} onClick={() => { if (queryOwner && queryRepo) fetchRelations(queryOwner, queryRepo) }}>刷新</Button>
        {selectedNode && (
          <Button icon={<InfoCircleOutlined />} onClick={() => setDrawerOpen(true)}>
            {selectedNode.id} 的关系详情
          </Button>
        )}
      </Space>

      {graphData && (
        <Row gutter={[16, 12]} style={{ marginBottom: 16 }}>
          <Col span={4}>
            <Card size="small"><Statistic title="开发者" value={graphData.stats.total_users} valueStyle={{ color: '#1890ff' }} /></Card>
          </Col>
          <Col span={4}>
            <Card size="small"><Statistic title="关系连接" value={graphData.stats.total_connections} valueStyle={{ color: '#52c41a' }} /></Card>
          </Col>
          <Col span={4}>
            <Card size="small"><Statistic title="评论总数" value={graphData.stats.total_comments} /></Card>
          </Col>
          <Col span={12}>
            <Card size="small">
              <div style={{ fontSize: 12, color: '#999', marginBottom: 4 }}>图例</div>
              <Space size={12}>
                <span><span style={{ display: 'inline-block', width: 20, height: 3, background: '#1890ff', verticalAlign: 'middle', marginRight: 4, borderRadius: 2 }} />同 PR 互动</span>
                <span><span style={{ display: 'inline-block', width: 20, height: 3, background: '#ff4d4f', verticalAlign: 'middle', marginRight: 4, borderRadius: 2, borderTop: '2px dashed #ff4d4f' }} />@提及</span>
                <span>节点大小 = 评论数</span>
                <span>线粗细 = 互动频率</span>
              </Space>
            </Card>
          </Col>
        </Row>
      )}

      <div style={{ border: '1px solid #f0f0f0', borderRadius: 8, overflow: 'hidden', background: '#fafafa' }}>
        {graphData ? (
          <ForceGraph
            ref={fgRef}
            graphData={fgData}
            nodeLabel="id"
            nodeVal="val"
            nodeColor={n => highlightNodes.size > 0 ? (highlightNodes.has(n.id) ? n.color : 'rgba(200,200,200,0.3)') : n.color}
            nodeRelSize={4}
            nodeCanvasObjectMode={() => 'replace'}
            nodeCanvasObject={(node, ctx, globalScale) => {
              const label = node.id
              const fontSize = 12 / globalScale
              ctx.font = `${fontSize}px Sans-Serif`
              const isHighlighted = highlightNodes.size === 0 || highlightNodes.has(node.id)
              const [x, y] = [node.x, node.y]
              const radius = Math.max(node.val * 0.5, 2 / globalScale)

              ctx.beginPath()
              ctx.arc(x, y, radius, 0, 2 * Math.PI)
              ctx.fillStyle = isHighlighted ? node.color : 'rgba(200,200,200,0.3)'
              ctx.fill()

              if (isHighlighted && globalScale > 0.4) {
                ctx.textAlign = 'center'
                ctx.textBaseline = 'bottom'
                ctx.fillStyle = '#333'
                ctx.fillText(label, x, y - radius - 2)
              }
            }}
            linkWidth={l => Math.min(l.value * 1.2, 5)}
            linkColor={l => {
              if (highlightNodes.size > 0) {
                const sId = typeof l.source === 'object' ? l.source.id : l.source
                const tId = typeof l.target === 'object' ? l.target.id : l.target
                if (highlightNodes.has(sId) && highlightNodes.has(tId)) {
                  return l.mentions > 0 ? '#ff4d4f' : '#1890ff'
                }
                return 'rgba(200,200,200,0.1)'
              }
              return l.mentions > 0 ? 'rgba(255,77,79,0.35)' : 'rgba(24,144,255,0.25)'
            }}
            linkLineDash={l => l.mentions > 0 ? [4, 3] : null}
            onNodeClick={handleNodeClick}
            onNodeHover={handleNodeHover}
            onBackgroundClick={() => { setSelectedNode(null); setHighlightNodes(new Set()) }}
            cooldownTicks={300}
            cooldownTime={3000}
            enableNodeDrag={true}
            width={window.innerWidth - 320}
            height={600}
          />
        ) : (
          <div style={{ textAlign: 'center', padding: '120px 0', color: '#999' }}>
            <TeamOutlined style={{ fontSize: 48, marginBottom: 16, display: 'block' }} />
            <div>选择一个项目，生成开发者关系图</div>
            <div style={{ fontSize: 12, marginTop: 8 }}>提示：需要该项目有 PR 评论数据</div>
          </div>
        )}
      </div>

      <Drawer
        title={<span><InfoCircleOutlined style={{ marginRight: 8 }} />{selectedNode?.id} 的关系详情</span>}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={500}
      >
        {selectedNode && (
          <div>
            <Card size="small" style={{ marginBottom: 16 }}>
              <Statistic title="评论数" value={selectedNode.comments} />
            </Card>
            <h4>关联开发者 ({selectedEdges.length})</h4>
            {selectedEdges.length > 0 ? (
              <Table
                size="small"
                dataSource={selectedEdges}
                pagination={false}
                columns={[
                  { title: '开发者', dataIndex: 'developer', render: v => <Tag color="blue">{v}</Tag> },
                  { title: '互动强度', dataIndex: 'weight', width: 80, sorter: (a, b) => a.weight - b.weight },
                  {
                    title: '关系', width: 200,
                    render: (_, r) => (
                      <Space size={4}>
                        {r.co_pr > 0 && <Tag color="blue">共同PR ×{r.co_pr}</Tag>}
                        {r.mentions > 0 && <Tag color="red">@提及 ×{r.mentions}</Tag>}
                      </Space>
                    ),
                  },
                ]}
              />
            ) : (
              <div style={{ color: '#999' }}>无关联关系</div>
            )}
          </div>
        )}
      </Drawer>
    </div>
  )
}
