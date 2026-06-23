import { useState, useEffect } from 'react'
import useStore from '../store'

function ArchiveTab() {
  const { archive, fetchArchive, fetchArchiveDetail, openDrawer } = useStore()
  const [filter, setFilter] = useState('all')
  const [selectedId, setSelectedId] = useState(null)
  const [detail, setDetail] = useState(null)

  useEffect(() => {
    fetchArchive()
  }, [])

  const handleSelect = async (item) => {
    setSelectedId(item.id)
    const data = await fetchArchiveDetail(item.id)
    setDetail(data)
  }

  const filteredItems = filter === 'all'
    ? [...archive.saved, ...archive.rejected]
    : filter === 'saved'
      ? archive.saved
      : archive.rejected

  const sortedItems = [...filteredItems].sort((a, b) =>
    new Date(b.created_at) - new Date(a.created_at)
  )

  if (archive.loading) {
    return (
      <div className="archive-tab">
        <div className="loading">Loading archive...</div>
      </div>
    )
  }

  return (
    <div className="archive-tab">
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
          Saved ({archive.saved.length})
        </button>
        <button
          className={`filter-btn rejected ${filter === 'rejected' ? 'active' : ''}`}
          onClick={() => setFilter('rejected')}
        >
          Rejected ({archive.rejected.length})
        </button>
      </div>

      <div className="archive-content">
        <div className="archive-list">
          {sortedItems.length === 0 ? (
            <div className="empty-state">
              <p>No archived ideas yet</p>
              <p className="hint">Run a debate to save or reject ideas</p>
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
                  <span className={`archive-score ${item.saved ? 'saved' : 'rejected'}`}>
                    {item.weighted_score?.toFixed(1)}
                  </span>
                </div>
                <div className="archive-liner">{item.one_liner}</div>
                <div className="archive-date">
                  {new Date(item.created_at).toLocaleDateString()}
                </div>
              </div>
            ))
          )}
        </div>

        <div className="archive-detail">
          {detail ? (
            <div className="detail-content">
              <h2>{detail.title}</h2>
              <p className="liner">{detail.one_liner}</p>

              <div className="score-breakdown">
                <h4>Scores</h4>
                <div className="scores-grid">
                  {detail.scores && Object.entries(detail.scores).map(([dim, score]) => (
                    <div key={dim} className="score-item">
                      <span className="score-dim">{dim.replace('_', ' ')}</span>
                      <span className="score-val">{score.toFixed(1)}</span>
                    </div>
                  ))}
                </div>
                <div className="weighted-score">
                  Weighted: <strong>{detail.weighted_score?.toFixed(1)}</strong>
                </div>
              </div>

              <div className="transcript-section">
                <h4>Transcript</h4>
                <pre className="transcript">{detail.transcript}</pre>
              </div>
            </div>
          ) : (
            <div className="no-selection">
              Select an idea to view details
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default ArchiveTab