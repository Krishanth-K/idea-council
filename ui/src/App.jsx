import { useEffect } from 'react'
import useStore from './store'
import RunHeader from './components/RunHeader'
import SignalSidebar from './components/SignalSidebar'
import ActiveCycle from './components/ActiveCycle'
import VerdictSidebar from './components/VerdictSidebar'

function App() {
  const { connect, disconnect, connected, fetchState } = useStore()

  useEffect(() => {
    connect()
    fetchState()

    return () => disconnect()
  }, [])

  return (
    <div className="app">
      <RunHeader />
      <div className="dashboard">
        <SignalSidebar />
        <ActiveCycle />
        <VerdictSidebar />
      </div>
    </div>
  )
}

export default App