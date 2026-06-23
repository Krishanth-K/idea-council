import useStore from '../store'

function DetailDrawer() {
  const { drawerOpen, closeDrawer, selectedSignal, selectedIdea } = useStore()

  if (!drawerOpen) return null

  const data = selectedSignal || selectedIdea

  return (
    <div className="detail-drawer-overlay" onClick={closeDrawer}>
      <div className="detail-drawer" onClick={e => e.stopPropagation()}>
        <div className="drawer-header">
          <h3>{selectedSignal ? 'Signal Details' : 'Idea Details'}</h3>
          <button className="close-btn" onClick={closeDrawer}>&times;</button>
        </div>

        <div className="drawer-content">
          {selectedSignal && (
            <>
              <div className="detail-section">
                <label>Source</label>
                <span className="source-badge" data-source={selectedSignal.source}>
                  {selectedSignal.source}
                </span>
              </div>

              <div className="detail-section">
                <label>Title</label>
                <p className="detail-value">{selectedSignal.title}</p>
              </div>

              <div className="detail-section">
                <label>URL</label>
                <a href={selectedSignal.url} target="_blank" rel="noopener noreferrer" className="detail-link">
                  {selectedSignal.url}
                </a>
              </div>

              <div className="detail-section">
                <label>Blurb</label>
                <p className="detail-value">{selectedSignal.blurb}</p>
              </div>

              <div className="detail-section">
                <label>Status</label>
                <span className={`badge ${selectedSignal.status}`}>
                  {selectedSignal.status.replace('_', ' ')}
                </span>
              </div>

              <div className="detail-section">
                <label>Scraped At</label>
                <p className="detail-value timestamp">
                  {new Date(selectedSignal.scraped_at).toLocaleString()}
                </p>
              </div>
            </>
          )}

          {selectedIdea && (
            <>
              <div className="detail-section">
                <label>Source</label>
                <span className="source-badge" data-source={selectedIdea.source}>
                  {selectedIdea.source}
                </span>
              </div>

              <div className="detail-section">
                <label>Title</label>
                <p className="detail-value">{selectedIdea.idea?.title || 'Untitled'}</p>
              </div>

              <div className="detail-section">
                <label>One-Liner</label>
                <p className="detail-value liner">{selectedIdea.idea?.one_liner}</p>
              </div>

              <div className="detail-section">
                <label>Description</label>
                <p className="detail-value">{selectedIdea.idea?.description}</p>
              </div>

              <div className="detail-section">
                <label>Tech Stack</label>
                <p className="detail-value">{selectedIdea.idea?.tech_stack}</p>
              </div>

              <div className="detail-section">
                <label>Status</label>
                <span className={`badge ${selectedIdea.status}`}>
                  {selectedIdea.status.replace('_', ' ')}
                </span>
              </div>

              {/* Round 1 Results */}
              {selectedIdea.round1 && (
                <div className="detail-section round-results">
                  <label>Round 1 - Opening Arguments</label>
                  <div className="lawyers-grid">
                    {Object.entries(selectedIdea.round1.lawyers || {}).map(([dim, data]) => (
                      <div key={dim} className="lawyer-result">
                        <span className="dimension">{dim.replace('_', ' ')}</span>
                        <span className={`score ${getScoreClass(data.score)}`}>{data.score}</span>
                        <p className="argument">{data.argument}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Round 2 Results */}
              {selectedIdea.round2 && (
                <div className="detail-section round-results">
                  <label>Round 2 - Rebuttals</label>
                  <div className="lawyers-grid">
                    {Object.entries(selectedIdea.round2.lawyers || {}).map(([dim, data]) => (
                      <div key={dim} className="lawyer-result">
                        <span className="dimension">{dim.replace('_', ' ')}</span>
                        <span className="score-change">
                          {data.original_score} → {data.updated_score}
                        </span>
                        <p className="rebuttal">{data.rebuttal}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Verdict */}
              {selectedIdea.verdict && (
                <div className="detail-section verdict-section">
                  <label>Verdict</label>
                  <div className={`verdict-badge ${selectedIdea.verdict.save ? 'saved' : 'rejected'}`}>
                    {selectedIdea.verdict.save ? 'SAVED' : 'REJECTED'}
                  </div>
                  <p className="verdict-summary">{selectedIdea.verdict.summary}</p>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function getScoreClass(score) {
  if (score >= 7) return 'high'
  if (score >= 5) return 'medium'
  return 'low'
}

export default DetailDrawer