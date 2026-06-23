import { useState, useEffect } from 'react'
import useStore, { SIGNAL_STATUS } from '../store'

function RunHeader() {
  const {
    run,
    connected,
    signals,
    sources,
    startRun,
    stopRun,
    startScraping,
    startIdeator,
    startDebate
  } = useStore()

  const isRunning = run.status === 'scraping' || run.status === 'processing'
  const isIdle = run.status === 'idle'

  // Count signals by status for button gating
  const newSignals = signals.filter(s => s.status === SIGNAL_STATUS.SCRAPED).length
  const pendingDebateIdeas = signals.filter(s => s.status === SIGNAL_STATUS.IDEA_GENERATED).length
  const hasScrapedSignals = Object.values(sources).some(s => s.status === 'complete')

  const handleStartScraping = async () => {
    await startScraping(10)
  }

  const handleStartIdeator = async () => {
    await startIdeator()
  }

  const handleStartDebate = async () => {
    await startDebate()
  }

  const handleStart = async () => {
    await startRun(10)
  }

  const handleStop = async () => {
    await stopRun()
  }

  // Calculate elapsed time
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    if (run.started_at && run.status !== 'idle' && run.status !== 'complete') {
      const interval = setInterval(() => {
        const start = new Date(run.started_at).getTime()
        const now = Date.now()
        setElapsed(Math.floor((now - start) / 1000))
      }, 1000)
      return () => clearInterval(interval)
    } else {
      setElapsed(0)
    }
  }, [run.started_at, run.status])

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${mins}:${secs.toString().padStart(2, '0')}`
  }

  return (
    <div className="run-header">
      <div className="header-left">
        <h1>IdeaCouncil</h1>
        <span className={`status-badge ${connected ? 'complete' : 'error'}`}>
          {connected ? 'Connected' : 'Disconnected'}
        </span>
      </div>

      <div className="header-controls">
        <div className="control-buttons">
          <button
            className="btn btn-primary"
            onClick={handleStartScraping}
            disabled={isRunning || !isIdle}
          >
            Start Scrape
          </button>
          <button
            className="btn btn-primary"
            onClick={handleStartIdeator}
            disabled={isRunning || newSignals === 0}
            title={newSignals === 0 ? 'No new signals to ideate' : ''}
          >
            Run Ideator {newSignals > 0 && `(${newSignals})`}
          </button>
          <button
            className="btn btn-primary"
            onClick={handleStartDebate}
            disabled={isRunning || pendingDebateIdeas === 0}
            title={pendingDebateIdeas === 0 ? 'No ideas pending debate' : ''}
          >
            Start Debate {pendingDebateIdeas > 0 && `(${pendingDebateIdeas})`}
          </button>
        </div>

        <div className="run-actions">
          <button
            className="btn btn-full-run"
            onClick={handleStart}
            disabled={isRunning}
          >
            Full Run
          </button>
          <button
            className="btn btn-stop"
            onClick={handleStop}
            disabled={!isRunning}
          >
            Stop
          </button>
        </div>
      </div>

      <div className="header-status">
        <div className="status-strip">
          {run.run_id && <span className="run-id">Run: {run.run_id.slice(0, 8)}</span>}
          <span className={`stage-badge ${run.status}`}>
            {run.stage || run.status}
          </span>
          {elapsed > 0 && <span className="elapsed">{formatTime(elapsed)}</span>}
        </div>
        <div className="stats-strip">
          <span>Signals: <span className="count">{run.signals_processed}/{run.total_signals}</span></span>
          <span className="saved">Saved: <span className="count">{run.saved_count}</span></span>
          <span className="rejected">Rejected: <span className="count">{run.rejected_count}</span></span>
        </div>
      </div>
    </div>
  )
}

export default RunHeader