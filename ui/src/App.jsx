import { useEffect } from 'react'
import useStore from './store'
import RunHeader from './components/RunHeader'
import LiveRunBoard from './components/LiveRunBoard'
import ArchiveTab from './components/ArchiveTab'
import DetailDrawer from './components/DetailDrawer'

function App() {
  const { connect, disconnect, activeTab, setActiveTab, fetchArchive } = useStore()

  useEffect(() => {
    useStore.setState({ intentionalDisconnect: false })
    connect()

    return () => disconnect()
  }, [])

  // Fetch archive when switching to archive tab
  useEffect(() => {
    if (activeTab === 'archive') {
      fetchArchive()
    }
  }, [activeTab])

  return (
    <div className="app">
      <RunHeader />

      <div className="tab-bar">
        <button
          className={`tab-btn ${activeTab === 'live-run' ? 'active' : ''}`}
          onClick={() => setActiveTab('live-run')}
        >
          Live Run
        </button>
        <button
          className={`tab-btn ${activeTab === 'archive' ? 'active' : ''}`}
          onClick={() => setActiveTab('archive')}
        >
          Archive
        </button>
      </div>

      <div className="main-content">
        {activeTab === 'live-run' ? <LiveRunBoard /> : <ArchiveTab />}
      </div>

      <DetailDrawer />
    </div>
  )
}

export default App