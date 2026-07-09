import { ConfigProvider, theme } from 'antd'
import { ExperimentOutlined } from '@ant-design/icons'
import WorkflowSimV2Tab from './pages/WorkflowSimV2Tab'

function App() {
  return (
    <ConfigProvider theme={{ algorithm: theme.defaultAlgorithm, token: { colorPrimary: '#1677ff' } }}>
      <div style={{ minHeight: '100vh', background: '#f5f5f5' }}>
        <div style={{
          background: '#fff', padding: '0 24px', borderBottom: '1px solid #f0f0f0',
          height: 56, display: 'flex', alignItems: 'center', gap: 10,
        }}>
          <ExperimentOutlined style={{ fontSize: 20, color: '#1677ff' }} />
          <h2 style={{ margin: 0, fontSize: 16, fontWeight: 600, color: '#1f1f1f' }}>
            CANNBot 工作流评估
          </h2>
        </div>
        <div style={{ padding: 20, minHeight: 'calc(100vh - 56px)' }}>
          <WorkflowSimV2Tab />
        </div>
      </div>
    </ConfigProvider>
  )
}

export default App
