import useStore from '../store'

const SOURCE_LABELS = {
  github: 'GitHub',
  hacker_news: 'Hacker News',
  arxiv: 'arXiv',
  devto: 'DEV.to',
  lobsters: 'Lobste.rs'
}

function SignalSidebar() {
  const { sources, signals, activeCycle } = useStore()

  return (
    <div className="sidebar">
      <div className="sidebar-section">
        <h3>Sources</h3>
        {Object.values(sources).length === 0 ? (
          <div className="empty-state" style={{ padding: '10px', fontSize: '13px' }}>
            Waiting for scrape...
          </div>
        ) : (
          Object.values(sources).map(source => (
            <div key={source.source} className="source-status">
              <span className="name">{SOURCE_LABELS[source.source] || source.source}</span>
              <span className="count">
                {source.fresh_count}/{source.raw_count}
              </span>
            </div>
          ))
        )}
      </div>

      <div className="sidebar-section">
        <h3>Signal Queue</h3>
      </div>

      <div className="signal-list">
        {signals.length === 0 ? (
          <div className="empty-state">
            No signals queued
          </div>
        ) : (
          signals.map(signal => (
            <div
              key={signal.signal_id}
              className={`signal-item ${activeCycle?.signal_id === signal.signal_id ? 'active' : ''}`}
            >
              <div className="source">{signal.source}</div>
              <div className="title">{signal.title}</div>
              <div className="status">{signal.status}</div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

export default SignalSidebar