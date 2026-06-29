import { useState, useEffect } from 'react'
import useStore from '../store'

function ScoreBar({ score, max = 10 }) {
  const pct = Math.min(100, (score / max) * 100)
  const color = score >= 7 ? '#4ade80' : score >= 5 ? '#facc15' : '#f87171'
  return (
    <div className="score-bar-wrap">
      <div
        className="score-bar-fill"
        style={{ width: `${pct}%`, background: color }}
      />
    </div>
  )
}

function ArchiveTab() {
  const { archive, fetchArchive, fetchArchiveDetail } = useStore()
  const [filter, setFilter] = useState('saved')
  const [selectedId, setSelectedId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [showTranscript, setShowTranscript] = useState(false)

  useEffect(() => {
    fetchArchive()
  }, [])

  const handleSelect = async (item) => {
    if (selectedId === item.id) return
    setSelectedId(item.id)
    setDetail(null)
    setShowTranscript(false)
    setLoadingDetail(true)
    try {
      const data = await fetchArchiveDetail(item.id)
      setDetail(data)
    } finally {
      setLoadingDetail(false)
    }
  }

  const filteredItems = filter === 'all'
    ? [...archive.saved, ...archive.rejected]
    : filter === 'saved'
      ? archive.saved
      : archive.rejected

  const sortedItems = [...filteredItems].sort((a, b) =>
    (b.weighted_score ?? 0) - (a.weighted_score ?? 0)
  )

  const formatDate = (str) => {
    if (!str) return ''
    return new Date(str).toLocaleString('en-IN', {
      day: 'numeric', month: 'short', year: 'numeric',
      hour: '2-digit', minute: '2-digit'
    })
  }

  const scoreColor = (score) => {
    if (score >= 7) return '#4ade80'
    if (score >= 5) return '#facc15'
    return '#f87171'
  }

  if (archive.loading) {
    return (
      <div className="archive-tab">
        <div className="loading">Loading archive…</div>
      </div>
    )
  }

  return (
    <div className="archive-tab">
      {/* Filter bar */}
      <div className="archive-filters">
        <button
          className={`filter-btn ${filter === 'all' ? 'active' : ''}`}
          onClick={() => setFilter('all')}
        >
          All ({archive.saved.length + archive.rejected.length})
        </button>
        <button
          className={`filter-btn saved ${filter === 'saved' ? 'active' : ''}`}
          onClick={() => setFilter('saved')}
        >
          ✓ Saved ({archive.saved.length})
        </button>
        <button
          className={`filter-btn rejected ${filter === 'rejected' ? 'active' : ''}`}
          onClick={() => setFilter('rejected')}
        >
          ✕ Rejected ({archive.rejected.length})
        </button>
        <button
          className="filter-btn"
          onClick={fetchArchive}
          title="Refresh archive from DB"
          style={{ marginLeft: 'auto' }}
        >
          ↻ Refresh
        </button>
      </div>

      <div className="archive-content">
        {/* Left: idea list */}
        <div className="archive-list">
          {sortedItems.length === 0 ? (
            <div className="empty-state">
              <p>No ideas in archive yet</p>
              <p className="hint">Run a full debate cycle to populate this view</p>
            </div>
          ) : (
            sortedItems.map(item => (
              <div
                key={item.id}
                className={`archive-item ${item.saved ? 'saved' : 'rejected'} ${selectedId === item.id ? 'selected' : ''}`}
                onClick={() => handleSelect(item)}
              >
                <div className="archive-item-header">
                  <span className="archive-title">{item.title}</span>
                  <span
                    className="archive-score"
                    style={{ color: scoreColor(item.weighted_score ?? 0) }}
                  >
                    {item.weighted_score != null ? item.weighted_score.toFixed(1) : '—'}
                  </span>
                </div>
                <div className="archive-liner">{item.one_liner}</div>
                <div className="archive-meta">
                  <span className={`archive-badge ${item.saved ? 'saved' : 'rejected'}`}>
                    {item.saved ? '✓ Saved' : '✕ Rejected'}
                  </span>
                  <span className="archive-date">{formatDate(item.created_at)}</span>
                </div>

                {/* Compact score pills */}
                {item.scores && Object.keys(item.scores).length > 0 && (
                  <div className="archive-score-pills">
                    {Object.entries(item.scores).map(([dim, score]) => (
                      <span
                        key={dim}
                        className="score-pill"
                        style={{ borderColor: scoreColor(score), color: scoreColor(score) }}
                        title={`${dim}: ${score}`}
                      >
                        {dim.replace(/_/g, ' ').slice(0, 3).toUpperCase()} {score.toFixed(0)}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))
          )}
        </div>

        {/* Right: detail panel */}
        <div className="archive-detail">
          {loadingDetail ? (
            <div className="loading">Loading details…</div>
          ) : detail ? (
            <div className="detail-content">
              <div className="detail-header">
                <h2>{detail.title}</h2>
                <span
                  className={`detail-badge ${detail.saved ? 'saved' : 'rejected'}`}
                >
                  {detail.saved ? '✓ Saved by Council' : '✕ Rejected by Council'}
                </span>
              </div>

              {detail.one_liner && (
                <p className="detail-liner">"{detail.one_liner}"</p>
              )}

              {detail.summary && (
                <div className="detail-section">
                  <h4>Judge Summary</h4>
                  <p className="detail-summary">{detail.summary}</p>
                </div>
              )}

              {detail.scores && Object.keys(detail.scores).length > 0 && (
                <div className="detail-section">
                  <h4>Score Breakdown</h4>
                  <div className="scores-grid">
                    {Object.entries(detail.scores).map(([dim, score]) => (
                      <div key={dim} className="score-row">
                        <span className="score-dim">{dim.replace(/_/g, ' ')}</span>
                        <ScoreBar score={score} />
                        <span
                          className="score-val"
                          style={{ color: scoreColor(score) }}
                        >
                          {score.toFixed(1)}
                        </span>
                      </div>
                    ))}
                    <div className="score-row weighted">
                      <span className="score-dim">Weighted Total</span>
                      <ScoreBar score={detail.weighted_score ?? 0} />
                      <span
                        className="score-val"
                        style={{ color: scoreColor(detail.weighted_score ?? 0), fontWeight: 700 }}
                      >
                        {detail.weighted_score?.toFixed(1) ?? '—'}
                      </span>
                    </div>
                  </div>
                </div>
              )}

              {detail.transcript && (
                <div className="detail-section">
                  <button
                    className="transcript-toggle"
                    onClick={() => setShowTranscript(v => !v)}
                  >
                    {showTranscript ? '▲ Hide Debate Transcript' : '▼ Show Debate Transcript'}
                  </button>
                  {showTranscript && (
                    <pre className="transcript">{detail.transcript}</pre>
                  )}
                </div>
              )}

              <div className="detail-meta">
                Saved on {formatDate(detail.created_at)}
                {detail.idea_id && (
                  <span className="detail-id"> · idea #{detail.idea_id}</span>
                )}
              </div>
            </div>
          ) : (
            <div className="no-selection">
              <div className="no-selection-icon">📋</div>
              <p>Select an idea to view full details</p>
              <p className="hint">Scores, judge summary, and full debate transcript</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default ArchiveTab