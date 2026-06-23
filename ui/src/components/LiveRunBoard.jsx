import useStore, { SIGNAL_STATUS } from '../store'
import ActiveDebate from './ActiveDebate'

function LiveRunBoard() {
  const { sources, signals, activeCycle, ideationQueue, debateQueue } = useStore()

  // Filter signals by status for each column
  const scrapedSignals = signals.filter(s => s.status === SIGNAL_STATUS.SCRAPED)
  const ideatingSignals = signals.filter(s => s.status === SIGNAL_STATUS.IDEATING)
  const ideaGeneratedSignals = signals.filter(s => s.status === SIGNAL_STATUS.IDEA_GENERATED)
  const debatingSignals = signals.filter(s => s.status === SIGNAL_STATUS.DEBATING)
  const resolvedSignals = signals.filter(s => s.status === SIGNAL_STATUS.RESOLVED)

  // Signals for Column A (all signals that haven't been saved/rejected)
  const columnASignals = signals.filter(s => s.status !== SIGNAL_STATUS.RESOLVED)

  // Ideas for Column B (signals with ideas generated)
  const columnBIdeas = signals.filter(s =>
    s.status === SIGNAL_STATUS.IDEA_GENERATED ||
    s.status === SIGNAL_STATUS.DEBATING ||
    s.status === SIGNAL_STATUS.RESOLVED
  )

  return (
    <div className="live-run-board">
      {/* Source Cards Row */}
      <SourceCards sources={sources} />

      {/* Three Column Board */}
      <div className="three-column-board">
        {/* Column A - Signals */}
        <div className="column column-signals">
          <div className="column-header">
            <h3>Signals</h3>
            <span className="count">{columnASignals.length}</span>
          </div>
          <div className="column-content">
            {columnASignals.length === 0 ? (
              <div className="empty-state">
                <p>No signals yet</p>
                <p className="hint">Run scrape to collect signals</p>
              </div>
            ) : (
              columnASignals.map(signal => (
                <SignalCard
                  key={signal.signal_id}
                  signal={signal}
                  isActive={activeCycle?.signal_id === signal.signal_id}
                  isIdeating={ideationQueue.includes(signal.signal_id)}
                />
              ))
            )}
          </div>
        </div>

        {/* Column B - Ideas */}
        <div className="column column-ideas">
          <div className="column-header">
            <h3>Ideas</h3>
            <span className="count">{columnBIdeas.length}</span>
          </div>
          <div className="column-content">
            {columnBIdeas.length === 0 ? (
              <div className="empty-state">
                <p>No ideas yet</p>
                <p className="hint">Run ideator to generate ideas</p>
              </div>
            ) : (
              columnBIdeas.map(signal => (
                <IdeaCard
                  key={signal.signal_id}
                  signal={signal}
                  isActive={activeCycle?.signal_id === signal.signal_id}
                />
              ))
            )}
          </div>
        </div>

        {/* Column C - Active Debate */}
        <div className="column column-debate">
          <div className="column-header">
            <h3>Active Debate</h3>
          </div>
          <div className="column-content">
            <ActiveDebate />
          </div>
        </div>
      </div>
    </div>
  )
}

function SourceCards({ sources }) {
  const SOURCE_CONFIG = {
    github: { label: 'GitHub', color: '#24292e' },
    hacker_news: { label: 'Hacker News', color: '#ff6600' },
    arxiv: { label: 'arXiv', color: '#b31b1b' },
    devto: { label: 'DEV.to', color: '#0a0a0a' },
    lobsters: { label: 'Lobste.rs', color: '#ac130d' }
  }

  const sourcesList = Object.values(sources)

  return (
    <div className="source-cards">
      {sourcesList.length === 0 ? (
        <div className="source-placeholder">Click "Start Scrape" to begin</div>
      ) : (
        sourcesList.map(source => {
          const config = SOURCE_CONFIG[source.source] || { label: source.source, color: '#666' }
          return (
            <div
              key={source.source}
              className={`source-card ${source.status}`}
              style={{ borderColor: config.color }}
            >
              <div className="source-name" style={{ color: config.color }}>
                {config.label}
              </div>
              <div className="source-status">
                {source.status === 'scraping' && (
                  <div className="thinking-indicator">
                    <span></span><span></span><span></span>
                  </div>
                )}
                {source.status === 'complete' && (
                  <span className="badge success">{source.fresh_count} new</span>
                )}
                {source.status === 'error' && (
                  <span className="badge error">error</span>
                )}
                {source.status === 'waiting' && (
                  <span className="badge waiting">waiting</span>
                )}
              </div>
            </div>
          )
        })
      )}
    </div>
  )
}

function SignalCard({ signal, isActive, isIdeating }) {
  const { openDrawer } = useStore()

  const handleClick = () => {
    openDrawer('signal', signal)
  }

  return (
    <div
      className={`card signal-card ${isActive ? 'active' : ''} ${isIdeating ? 'ideating' : ''}`}
      onClick={handleClick}
    >
      <div className="card-source" data-source={signal.source}>
        {signal.source}
      </div>
      <div className="card-title">{signal.title}</div>
      <div className="card-status">
        <span className={`badge ${signal.status}`}>
          {signal.status.replace('_', ' ')}
        </span>
        {isIdeating && <span className="thinking-dot"></span>}
      </div>
    </div>
  )
}

function IdeaCard({ signal, isActive }) {
  const { openDrawer } = useStore()

  const handleClick = () => {
    openDrawer('idea', signal)
  }

  const status = signal.status === SIGNAL_STATUS.IDEA_GENERATED ? 'pending' :
                signal.status === SIGNAL_STATUS.DEBATING ? 'debating' : 'resolved'

  return (
    <div
      className={`card idea-card ${isActive ? 'active' : ''}`}
      onClick={handleClick}
    >
      <div className="card-source" data-source={signal.source}>
        {signal.source}
      </div>
      <div className="card-title">
        {signal.idea?.title || 'Untitled Idea'}
      </div>
      <div className="card-liner">
        {signal.idea?.one_liner || signal.idea?.title || '...'}
      </div>
      <div className="card-status">
        <span className={`badge ${status}`}>
          {status}
        </span>
      </div>
    </div>
  )
}

export default LiveRunBoard