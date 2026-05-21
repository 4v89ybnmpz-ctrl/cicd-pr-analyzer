import { useState, useEffect } from 'react'
import { Table, Input, Tag, Space, Button, Avatar, message, Modal } from 'antd'
import { UserOutlined, SearchOutlined, DownloadOutlined, ReloadOutlined, FolderOutlined } from '@ant-design/icons'
import * as api from '../api'

export default function Profiles({ onNavigate }) {

const REGION_RULES = [
  { test: s => /china|中国|香港|hong kong|taiwan|台湾|北京|上海|深圳|广州|杭州|成都|南京|武汉|西安|beijing|shanghai|shenzhen|guangzhou|hangzhou|chengdu|nanjing|wuhan|xian|\.cn\b|[一-龥]/i.test(s), region: '中国', color: 'red' },
  { test: s => /usa|united states|america|new york|california|san francisco|seattle|boston|chicago|austin|texas|oregon|washington|colorado|michigan|pennsylvania|massachusetts|illinois|north carolina|georgia|virginia|maryland|minnesota|utah|arizona|florida|\.us\b/i.test(s), region: '北美', color: 'blue' },
  { test: s => /canada|toronto|vancouver|montreal|ontario|british columbia|\.ca\b/i.test(s), region: '北美', color: 'blue' },
  { test: s => /russia|москва|moscow|saint petersburg|novosibirsk|россия|\.ru\b/i.test(s), region: '俄罗斯', color: 'volcano' },
  { test: s => /germany|berlin|munich|deutschland|frankfurt|hamburg|köln|\.de\b/i.test(s), region: '欧洲', color: 'geekblue' },
  { test: s => /united kingdom|london|england|scotland|wales|ireland|dublin|cambridge|oxford|britain|\.uk\b|\.ie\b/i.test(s), region: '欧洲', color: 'geekblue' },
  { test: s => /france|paris|lyon|toulouse|marseille|\.fr\b/i.test(s), region: '欧洲', color: 'geekblue' },
  { test: s => /netherlands|amsterdam|utrecht|rotterdam|holland|\.nl\b/i.test(s), region: '欧洲', color: 'geekblue' },
  { test: s => /sweden|stockholm|gothenburg|\.se\b/i.test(s), region: '欧洲', color: 'geekblue' },
  { test: s => /switzerland|zurich|bern|geneva|basel|\.ch\b/i.test(s), region: '欧洲', color: 'geekblue' },
  { test: s => /spain|madrid|barcelona|valencia|\.es\b/i.test(s), region: '欧洲', color: 'geekblue' },
  { test: s => /italy|rome|milan|turin|italia|\.it\b/i.test(s), region: '欧洲', color: 'geekblue' },
  { test: s => /poland|warsaw|krakow|polska|\.pl\b/i.test(s), region: '欧洲', color: 'geekblue' },
  { test: s => /czech|prague|czechia|czech republic/i.test(s), region: '欧洲', color: 'geekblue' },
  { test: s => /austria|vienna|wien|\.at\b/i.test(s), region: '欧洲', color: 'geekblue' },
  { test: s => /finland|helsinki|suomi|\.fi\b/i.test(s), region: '欧洲', color: 'geekblue' },
  { test: s => /norway|oslo|bergen|norge|\.no\b/i.test(s), region: '欧洲', color: 'geekblue' },
  { test: s => /denmark|copenhagen|danmark|\.dk\b/i.test(s), region: '欧洲', color: 'geekblue' },
  { test: s => /belgium|brussels|bruges|belgië|\.be\b/i.test(s), region: '欧洲', color: 'geekblue' },
  { test: s => /portugal|lisbon|porto|\.pt\b/i.test(s), region: '欧洲', color: 'geekblue' },
  { test: s => /greece|athens|thessaloniki/i.test(s), region: '欧洲', color: 'geekblue' },
  { test: s => /serbia|belgrade|srbija/i.test(s), region: '欧洲', color: 'geekblue' },
  { test: s => /croatia|zagreb|hrvatska/i.test(s), region: '欧洲', color: 'geekblue' },
  { test: s => /romania|bucharest|românia/i.test(s), region: '欧洲', color: 'geekblue' },
  { test: s => /hungary|budapest|magyarország/i.test(s), region: '欧洲', color: 'geekblue' },
  { test: s => /ukraine|kyiv|Україна/i.test(s), region: '欧洲', color: 'geekblue' },
  { test: s => /estonia|latvia|lithuania|tallinn|riga|vilnius/i.test(s), region: '欧洲', color: 'geekblue' },
  { test: s => /australia|sydney|melbourne|brisbane|perth|adelaide|canberra|hobart|tasmania|\.au\b/i.test(s), region: '大洋洲', color: 'cyan' },
  { test: s => /new zealand|auckland|wellington/i.test(s), region: '大洋洲', color: 'cyan' },
  { test: s => /japan|tokyo|osaka|日本|\.jp\b/i.test(s), region: '日韩', color: 'purple' },
  { test: s => /korea|seoul|south korea|busan|한국|서울|\.kr\b/i.test(s), region: '日韩', color: 'purple' },
  { test: s => /india|bangalore|mumbai|delhi|hyderabad|pune|chennai|kolkata|\.in\b/i.test(s), region: '南亚', color: 'orange' },
  { test: s => /singapore/i.test(s), region: '东南亚', color: 'gold' },
  { test: s => /vietnam|hanoi|ho chi minh/i.test(s), region: '东南亚', color: 'gold' },
  { test: s => /thailand|bangkok/i.test(s), region: '东南亚', color: 'gold' },
  { test: s => /indonesia|jakarta/i.test(s), region: '东南亚', color: 'gold' },
  { test: s => /philippines|manila/i.test(s), region: '东南亚', color: 'gold' },
  { test: s => /malaysia|kuala lumpur/i.test(s), region: '东南亚', color: 'gold' },
  { test: s => /brazil|são paulo|rio de janeiro|brasil|\.br\b/i.test(s), region: '南美', color: 'lime' },
  { test: s => /argentina|buenos aires|\.ar\b/i.test(s), region: '南美', color: 'lime' },
  { test: s => /colombia|bogota|\.co\b/i.test(s), region: '南美', color: 'lime' },
  { test: s => /mexico|mexico city|guadalajara|méxico|\.mx\b/i.test(s), region: '南美', color: 'lime' },
  { test: s => /chile|santiago|\.cl\b/i.test(s), region: '南美', color: 'lime' },
  { test: s => /nigeria|lagos|abuja|\.ng\b/i.test(s), region: '非洲', color: 'default' },
  { test: s => /south africa|cape town|johannesburg|durban|\.za\b/i.test(s), region: '非洲', color: 'default' },
  { test: s => /kenya|nairobi|\.ke\b/i.test(s), region: '非洲', color: 'default' },
  { test: s => /egypt|cairo|\.eg\b/i.test(s), region: '非洲', color: 'default' },
  { test: s => /morocco|casablanca|rabat/i.test(s), region: '非洲', color: 'default' },
  { test: s => /ghana|accra|\.gh\b/i.test(s), region: '非洲', color: 'default' },
  { test: s => /tanzania|dar es salaam/i.test(s), region: '非洲', color: 'default' },
  { test: s => /ethiopia|addis ababa/i.test(s), region: '非洲', color: 'default' },
  { test: s => /israel|tel aviv/i.test(s), region: '中东', color: 'magenta' },
  { test: s => /dubai|uae|united arab emirates|abu dhabi/i.test(s), region: '中东', color: 'magenta' },
  { test: s => /saudi arabia|riyadh/i.test(s), region: '中东', color: 'magenta' },
  { test: s => /iran|tehran/i.test(s), region: '中东', color: 'magenta' },
  { test: s => /turkey|istanbul|ankara|türkiye/i.test(s), region: '中东', color: 'magenta' },
]

function guessRegion(profile) {
  const location = (profile.location || '').toLowerCase().trim()
  const blog = (profile.blog || '').toLowerCase().trim()
  const company = (profile.company || '').toLowerCase().trim()
  const email = (profile.email || '').toLowerCase().trim()

  const texts = [location, blog, company, email].filter(Boolean)
  const joined = ' ' + texts.join(' ') + ' '

  for (const rule of REGION_RULES) {
    if (rule.test(joined)) return { region: rule.region, color: rule.color }
  }
  return { region: '未知', color: 'default' }
}
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [owner, setOwner] = useState('')
  const [repo, setRepo] = useState('')
  const [fetchLimit, setFetchLimit] = useState(20)

  const fetchFromDB = async (p = page) => {
    setLoading(true)
    try {
      const res = await api.getUserProfiles({ page: p, size: 20, sort_by: 'followers', sort_order: 'desc' })
      const items = (res.data.data || []).map((item, i) => ({ key: item.login || i, ...item }))
      setData(items)
      setTotal(res.data.total || 0)
    } catch (e) {
      message.error('获取数据失败: ' + e.message)
    }
    setLoading(false)
  }

  useEffect(() => { fetchFromDB(1) }, [])

  const fetchFromGithub = async () => {
    if (!owner || !repo) {
      message.warning('请输入 owner 和 repo')
      return
    }
    Modal.confirm({
      title: '确认获取 Profile',
      content: `将从 ${owner}/${repo} 的 Timeline 触发者中获取用户 Profile。请确保已先获取该项目的 PR/Issues/Timeline 数据，否则将返回空结果。`,
      okText: '确认获取',
      cancelText: '取消',
      onOk: async () => {
        try {
          const res = await api.asyncFetchProfiles(owner, repo, { limit: fetchLimit })
          message.success('任务已创建，正在跳转到任务监控...')
          setTimeout(() => { if (onNavigate) onNavigate('tasks') }, 300)
        } catch (e) {
          message.error('创建任务失败: ' + e.message)
        }
      },
    })
  }

  const columns = [
    {
      title: '头像', dataIndex: 'avatar_url', key: 'avatar', width: 60,
      render: v => v ? <Avatar src={v} size={32} /> : <Avatar icon={<UserOutlined />} size={32} />,
    },
    {
      title: '用户名', dataIndex: 'login', key: 'login',
      render: (v) => (
        <Space size="small">
          <a href={`https://github.com/${v}`} target="_blank" rel="noreferrer">{v}</a>
        </Space>
      ),
    },
    { title: '名称', dataIndex: 'name', key: 'name', render: v => v || '-' },
    {
      title: '类型', dataIndex: 'type', key: 'type', width: 80,
      render: v => <Tag color={v === 'Bot' ? 'orange' : 'blue'}>{v}</Tag>,
    },
    { title: '公司', dataIndex: 'company', key: 'company', render: v => v || '-', ellipsis: true },
    { title: '位置', dataIndex: 'location', key: 'location', render: v => v || '-' },
    {
      title: '区域', key: 'region', width: 90,
      render: (_, r) => {
        const { region, color, source } = guessRegion(r)
        return <Tag color={color}>{region}</Tag>
      },
    },
    { title: 'Bio', dataIndex: 'bio', key: 'bio', ellipsis: true, render: v => v || '-' },
    { title: '公开仓库', dataIndex: 'public_repos', key: 'public_repos', width: 90 },
    { title: '关注者', dataIndex: 'followers', key: 'followers', width: 80, render: v => v || 0 },
    { title: '关注中', dataIndex: 'following', key: 'following', width: 80, render: v => v || 0 },
    {
      title: '操作', key: 'action', width: 80,
      render: (_, r) => (
        <Button size="small" type="link" icon={<FolderOutlined />}
          onClick={() => { if (onNavigate) { onNavigate('user-repos', r.login) } }}>
          项目
        </Button>
      ),
    },
  ]

  return (
    <div>
      <h2 style={{ marginBottom: 24 }}>评论者 Profile</h2>
      <Space style={{ marginBottom: 16 }} wrap>
        <Input placeholder="Owner" value={owner} onChange={e => setOwner(e.target.value)} style={{ width: 130 }} />
        <Input placeholder="Repo" value={repo} onChange={e => setRepo(e.target.value)} style={{ width: 130 }} />
        <Input placeholder="数量" type="number" value={fetchLimit} onChange={e => setFetchLimit(Number(e.target.value))} style={{ width: 70 }} />
        <Button type="primary" icon={<DownloadOutlined />} onClick={fetchFromGithub} loading={loading}>
          从 GitHub 获取
        </Button>
        <Button icon={<ReloadOutlined />} onClick={() => fetchFromDB()}>刷新</Button>
      </Space>
      <Table
        columns={columns}
        dataSource={data}
        loading={loading}
        pagination={{
          current: page, total, pageSize: 20,
          onChange: (p) => { setPage(p); fetchFromDB(p) },
          showTotal: (t) => `共 ${t} 个用户`,
        }}
        scroll={{ x: 1000 }}
      />
    </div>
  )
}
