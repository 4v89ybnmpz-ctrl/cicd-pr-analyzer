import { useState, useEffect, useCallback, useMemo } from 'react'
import { Table, Input, Tag, Space, Button, message, Tooltip, AutoComplete } from 'antd'
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import * as api from '../api'

const EVENT_COLORS = {
  labeled: 'blue', unlabeled: 'default', commented: 'green',
  closed: 'red', reopened: 'orange', merged: 'purple',
  assigned: 'cyan', unassigned: 'default', referenced: 'geekblue',
  subscribed: 'default', mentioned: 'gold', milestoned: 'lime',
  demilestoned: 'volcano', renamed: 'blue', cross_referenced: 'geekblue',
  head_ref_deleted: 'red', head_ref_restored: 'green',
}

export default function IssueTimelines({ onNavigate }) {
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [issueNumber, setIssueNumber] = useState('')
  const [projects, setProjects] = useState([])
  const [searchText, setSearchText] = useState('')
  const [queryOwner, setQueryOwner] = useState('')
  const [queryRepo, setQueryRepo] = useState('')

  useEffect(() => {
    api.getIssueTimelineProjects().then(res => {
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
            <Tag>{p.count} events</Tag>
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
      if (issueNumber) params.issue_number = issueNumber
      const res = await api.getIssueTimelines(params)
      const items = (res.data.data || []).map((item, i) => ({ key: item.event_id || i, ...item }))
      setData(items)
      setTotal(res.data.total || 0)
    } catch (e) {
      message.error('获取数据失败: ' + e.message)
    }
    setLoading(false)
  }, [page, issueNumber, queryOwner, queryRepo])

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
      title: 'Issue#', dataIndex: 'issue_number', key: 'issue_number', width: 70,
      render: (v, r) => <a href={`https://github.com/${r.owner}/${r.repo}/issues/${v}`} target="_blank" rel="noreferrer">#{v}</a>,
    },
    {
      title: '类型', dataIndex: 'is_pr', key: 'is_pr', width: 65,
      render: v => v ? <Tag color="purple">PR</Tag> : <Tag color="blue">Issue</Tag>,
    },
    {
      title: '事件类型', dataIndex: 'event_type', key: 'event_type', width: 110,
      render: v => <Tag color={EVENT_COLORS[v] || 'default'}>{v}</Tag>,
    },
    {
      title: '触发者', dataIndex: 'actor', key: 'actor', width: 120,
      render: v => v ? <a href={`https://github.com/${v}`} target="_blank" rel="noreferrer">{v}</a> : '-',
    },
    {
      title: '标签', dataIndex: 'label', key: 'label', width: 130,
      render: (v, r) => v ? <Tag color={`#${r.label_color || '1677ff'}`}>{v}</Tag> : '-',
    },
    {
      title: '指派给', dataIndex: 'assignee', key: 'assignee', width: 110,
      render: v => v || '-',
    },
    {
      title: '里程碑', dataIndex: 'milestone', key: 'milestone', width: 110,
      render: v => v || '-',
    },
    {
      title: '内容/评论', dataIndex: 'body', key: 'body', width: 200, ellipsis: true,
      render: v => v ? <Tooltip title={v}><span>{v.substring(0, 80)}</span></Tooltip> : '-',
    },
    {
      title: '状态', dataIndex: 'state', key: 'state', width: 70,
      render: v => v ? <Tag color={v === 'open' ? 'green' : 'red'}>{v}</Tag> : '-',
    },
    {
      title: '来源', dataIndex: 'source_issue_url', key: 'source', width: 100,
      render: v => v ? <a href={v} target="_blank" rel="noreferrer">链接</a> : '-',
    },
    {
      title: 'Commit', dataIndex: 'commit_id', key: 'commit_id', width: 80,
      render: v => v ? <Tooltip title={v}><code style={{ fontSize: 12 }}>{v.substring(0, 7)}</code></Tooltip> : '-',
    },
    { title: '时间', dataIndex: 'created_at', key: 'created_at', width: 170 },
  ]

  return (
    <div>
      <h2 style={{ marginBottom: 24 }}>Issue Timelines</h2>

      <Space style={{ marginBottom: 12 }} wrap>
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
        <Input placeholder="Issue# 筛选" value={issueNumber} onChange={e => setIssueNumber(e.target.value)}
          onPressEnter={handleSearch} style={{ width: 100 }} allowClear />
        <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch} loading={loading}>搜索</Button>
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
        scroll={{ x: 1400 }}
      />
    </div>
  )
}
