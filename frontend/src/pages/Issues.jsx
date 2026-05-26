import { useState, useEffect, useCallback, useMemo } from 'react'
import { Table, Input, Tag, Space, Button, message, AutoComplete, Select } from 'antd'
import { ReloadOutlined, SearchOutlined, SyncOutlined } from '@ant-design/icons'
import * as api from '../api'

export default function Issues({ onNavigate }) {
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [stateFilter, setStateFilter] = useState('')
  const [projects, setProjects] = useState([])
  const [searchText, setSearchText] = useState('')
  const [queryOwner, setQueryOwner] = useState('')
  const [queryRepo, setQueryRepo] = useState('')

  useEffect(() => {
    api.getIssueProjects().then(res => {
      setProjects(res.data.projects || [])
    }).catch(() => {})
  }, [])

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
            <Tag>{p.count} issues</Tag>
          </div>
        ),
      }))
  }, [projects, searchText])

  const fetchFromDB = useCallback(async (p = page, owner = queryOwner, repo = queryRepo) => {
    setLoading(true)
    try {
      const params = { page: p, size: 20, sort_by: 'created_at', sort_order: 'desc' }
      if (owner) params.owner = owner
      if (repo) params.repo = repo
      if (stateFilter) params.state = stateFilter
      const res = await api.getIssues(params)
      const items = (res.data.data || []).map((item, i) => ({ key: item.number || i, ...item }))
      setData(items)
      setTotal(res.data.total || 0)
    } catch (e) {
      message.error('获取数据失败: ' + e.message)
    }
    setLoading(false)
  }, [page, stateFilter, queryOwner, queryRepo])

  useEffect(() => { fetchFromDB(1) }, [fetchFromDB])

  const handleSelect = (value) => {
    const [o, r] = value.split('/')
    setQueryOwner(o)
    setQueryRepo(r)
    setSearchText(value)
    setPage(1)
    fetchFromDB(1, o, r)
  }

  const handleSearch = () => {
    setPage(1)
    fetchFromDB(1)
  }

  const handleUpdate = async () => {
    if (!queryOwner || !queryRepo) {
      message.warning('请先选择一个项目')
      return
    }
    setLoading(true)
    try {
      const res = await api.updateIssues(queryOwner, queryRepo)
      message.success(`更新完成: 更新=${res.data.updated}, 新增=${res.data.added}, 未变=${res.data.unchanged}`)
      fetchFromDB(1)
    } catch (e) {
      message.error('更新失败: ' + e.message)
    }
    setLoading(false)
  }

  const columns = [
    {
      title: '项目', key: 'project', width: 180, fixed: 'left',
      render: (_, r) => (
        <a href={`https://github.com/${r.owner}/${r.repo}`} target="_blank" rel="noreferrer" style={{ fontWeight: 500 }}>
          {r.owner}/{r.repo}
        </a>
      ),
    },
    {
      title: 'Issue#', dataIndex: 'number', key: 'number', width: 80,
      render: (v, r) => <a href={r.url} target="_blank" rel="noreferrer">#{v}</a>,
    },
    { title: '标题', dataIndex: 'title', key: 'title', ellipsis: true },
    {
      title: '状态', dataIndex: 'state', key: 'state', width: 70,
      render: v => <Tag color={v === 'open' ? 'green' : 'red'}>{v}</Tag>,
    },
    { title: '作者', dataIndex: 'user', key: 'user', width: 120 },
    {
      title: '标签', dataIndex: 'labels', key: 'labels', width: 200,
      render: v => (v || []).slice(0, 3).map((l, i) => <Tag key={i}>{l}</Tag>),
    },
    {
      title: '评论', dataIndex: 'comments_count', key: 'comments_count', width: 60,
      render: v => v || 0,
    },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 170 },
  ]

  return (
    <div>
      <h2 style={{ marginBottom: 24 }}>Issues</h2>

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
        <Select
          placeholder="状态"
          value={stateFilter || undefined}
          onChange={v => { setStateFilter(v || '') }}
          allowClear
          style={{ width: 120 }}
          options={[
            { value: 'open', label: 'Open' },
            { value: 'closed', label: 'Closed' },
          ]}
        />
        <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch} loading={loading}>搜索</Button>
        <Button icon={<SyncOutlined />} onClick={handleUpdate} loading={loading}>更新数据</Button>
        <Button icon={<ReloadOutlined />} onClick={() => fetchFromDB()}>刷新</Button>
      </Space>

      <Table
        columns={columns}
        dataSource={data}
        loading={loading}
        pagination={{
          current: page, total, pageSize: 20,
          onChange: (p) => { setPage(p); fetchFromDB(p) },
          showTotal: (t) => `共 ${t} 条`,
        }}
        scroll={{ x: 1100 }}
      />
    </div>
  )
}
