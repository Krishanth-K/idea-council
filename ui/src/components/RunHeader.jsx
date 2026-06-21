import useStore from '../store'

function RunHeader() {
  const { run, connected, startRun } = useStore()

  const handleStart = async () => {
    await startRun(10)
  }

  return (
    <div className="run-header">
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <h1>IdeaCouncil</h1>
        <span className={`status-badge ${connected ? 'complete' : 'error'}`}>
          {connected ? 'Connected' : 'Disconnected'}
        </span>
      </div>

      <div className="run-stats">
        <span>Status: <span className="count">{run.status}</span></span>
        <span>Signals: <span className="count">{run.signals_processed}/{run.total_signals}</span></span>
        <span>Saved: <span className="count">{run.saved_count}</span></span>
        <span>Rejected: <span className="count">{run.rejected_count}</span></span>
        <span>Skipped: <span className="count">{run.skipped_count}</span></span>
      </div>

      <button className="btn btn-primary" onClick={handleStart}>
        Start Run
      </button>
    </div>
  )
}

export default RunHeader