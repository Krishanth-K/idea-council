import useStore from '../store'

function VerdictSidebar() {
  const { savedIdeas, rejectedIdeas, skippedSignals, errors } = useStore()

  return (
    <div className="sidebar sidebar-right">
      <div className="sidebar-section">
        <h3>Saved ({savedIdeas.length})</h3>
      </div>
      <div className="verdict-list">
        {savedIdeas.length === 0 ? (
          <div className="empty-state" style={{ padding: '10px', fontSize: '13px' }}>
            No saved ideas
          </div>
        ) : (
          savedIdeas.map(item => (
            <div key={item.cycle_id} className="verdict-item saved">
              <div className="title">{item.verdict?.idea_title || 'Unknown'}</div>
              <div className="score">Score: {item.verdict?.weighted_score || '?'}</div>
            </div>
          ))
        )}
      </div>

      <div className="sidebar-section">
        <h3>Rejected ({rejectedIdeas.length})</h3>
      </div>
      <div className="verdict-list">
        {rejectedIdeas.length === 0 ? (
          <div className="empty-state" style={{ padding: '10px', fontSize: '13px' }}>
            No rejected ideas
          </div>
        ) : (
          rejectedIdeas.map(item => (
            <div key={item.cycle_id} className="verdict-item rejected">
              <div className="title">{item.verdict?.idea_title || 'Unknown'}</div>
              <div className="score">Score: {item.verdict?.weighted_score || '?'}</div>
            </div>
          ))
        )}
      </div>

      {skippedSignals.length > 0 && (
        <>
          <div className="sidebar-section">
            <h3>Skipped ({skippedSignals.length})</h3>
          </div>
          <div className="verdict-list">
            {skippedSignals.map(item => (
              <div key={item.signal_id} className="verdict-item">
                <div className="title">{item.signal?.title || 'Unknown'}</div>
              </div>
            ))}
          </div>
        </>
      )}

      {errors.length > 0 && (
        <>
          <div className="sidebar-section">
            <h3>Errors ({errors.length})</h3>
          </div>
          <div className="verdict-list">
            {errors.map(error => (
              <div key={error.error_id} className="verdict-item" style={{ background: '#ffebee' }}>
                <div className="title">{error.message}</div>
                <div className="score">{error.stage}</div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

export default VerdictSidebar