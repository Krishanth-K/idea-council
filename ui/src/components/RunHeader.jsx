import useStore from '../store'

function RunHeader() {
  const { run, connected, startRun, stopRun, startScraping, startIdeator, startRound1, startRound2 } = useStore()

  const isRunning = run.status === 'scraping' || run.status === 'processing'
  const isIdle = run.status === 'idle'

  const handleStart = async () => {
    await startRun(10)
  }

  const handleStop = async () => {
    await stopRun()
  }

  const handleStartScraping = async () => {
    await startScraping(10)
  }

  const handleStartIdeator = async () => {
    await startIdeator()
  }

  const handleStartRound1 = async () => {
    await startRound1()
  }

  const handleStartRound2 = async () => {
    await startRound2()
  }

  const SectionButton = ({ section, label, onClick, disabled }) => (
    <div className="section-control">
      <span className="section-label">{label}</span>
      <button
        className="btn btn-small btn-primary"
        onClick={onClick}
        disabled={disabled || isRunning}
      >
        Start
      </button>
    </div>
  )

  return (
    <div className="run-header">
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <h1>IdeaCouncil</h1>
        <span className={`status-badge ${connected ? 'complete' : 'error'}`}>
          {connected ? 'Connected' : 'Disconnected'}
        </span>
      </div>

      <div className="section-controls">
        <SectionButton
          section="scraping"
          label="Scraping"
          onClick={handleStartScraping}
          disabled={!isIdle}
        />
        <SectionButton
          section="ideator"
          label="Signals → Ideas"
          onClick={handleStartIdeator}
          disabled={!isIdle}
        />
        <SectionButton
          section="round1"
          label="Ideas → Round 1"
          onClick={handleStartRound1}
          disabled={!isIdle}
        />
        <SectionButton
          section="round2"
          label="Round 1 → Round 2"
          onClick={handleStartRound2}
          disabled={!isIdle}
        />
      </div>

      <div className="run-stats">
        <span>Status: <span className="count">{run.status}</span></span>
        {run.stage && <span>Stage: <span className="count">{run.stage}</span></span>}
        <span>Signals: <span className="count">{run.signals_processed}/{run.total_signals}</span></span>
        <span>Saved: <span className="count">{run.saved_count}</span></span>
        <span>Rejected: <span className="count">{run.rejected_count}</span></span>
        <span>Skipped: <span className="count">{run.skipped_count}</span></span>
      </div>

      <div className="run-actions">
        <button className="btn btn-primary" onClick={handleStart} disabled={isRunning}>
          Start Full Run
        </button>
        <button className="btn btn-danger" onClick={handleStop} disabled={!isRunning}>
          Stop
        </button>
      </div>
    </div>
  )
}

export default RunHeader