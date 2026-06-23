import useStore from '../store'

const DIMENSIONS = [
  { key: 'novelty', label: 'Novelty' },
  { key: 'feasibility', label: 'Feasibility' },
  { key: 'technical_depth', label: 'Technical Depth' },
  { key: 'resume_value', label: 'Resume Value' },
  { key: 'real_use_case', label: 'Real Use Case' }
]

function ActiveDebate() {
  const { activeCycle, signals, debateQueue } = useStore()

  // Get current debating signal
  const currentSignal = signals.find(s => s.status === 'debating')

  if (!currentSignal && !activeCycle) {
    return (
      <div className="debate-empty">
        <div className="gavel-icon">⚖️</div>
        <p>No debate in progress</p>
        <p className="hint">Start debate to see the courtroom</p>
      </div>
    )
  }

  const idea = currentSignal?.idea || activeCycle?.ideator?.idea
  const round1 = currentSignal?.round1 || activeCycle?.round1
  const round2 = currentSignal?.round2 || activeCycle?.round2
  const judge = activeCycle?.judge

  return (
    <div className="active-debate">
      {/* Current Idea */}
      <div className="debate-idea">
        <h4>Current Idea</h4>
        <p className="idea-title">{idea?.title || 'Loading...'}</p>
        <p className="idea-liner">{idea?.one_liner}</p>
      </div>

      {/* Round 1 - Lawyers */}
      <div className="debate-round">
        <h4>Round 1 - Opening Arguments</h4>
        <div className="lawyer-cards">
          {DIMENSIONS.map(dim => {
            const lawyer = round1?.lawyers?.[dim.key]
            const isActive = round1?.status === 'running' && !lawyer
            const isComplete = lawyer?.status === 'complete'

            return (
              <div
                key={dim.key}
                className={`lawyer-card ${isActive ? 'active thinking' : ''} ${isComplete ? 'complete' : ''}`}
              >
                <div className="lawyer-dimension">{dim.label}</div>
                {isActive && (
                  <div className="thinking-indicator">
                    <span></span><span></span><span></span>
                  </div>
                )}
                {isComplete && (
                  <>
                    <div className={`lawyer-score ${getScoreClass(lawyer?.score)}`}>
                      {lawyer?.score}
                    </div>
                    <p className="lawyer-argument">{lawyer?.argument}</p>
                  </>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* Round 2 - Rebuttals */}
      {round2 && (
        <div className="debate-round">
          <h4>Round 2 - Rebuttals</h4>
          <div className="lawyer-cards">
            {DIMENSIONS.map(dim => {
              const lawyer = round2?.lawyers?.[dim.key]
              const isComplete = lawyer?.status === 'complete'

              return (
                <div
                  key={dim.key}
                  className={`lawyer-card ${isComplete ? 'complete' : ''}`}
                >
                  <div className="lawyer-dimension">{dim.label}</div>
                  {isComplete && (
                    <>
                      <div className="score-change">
                        {lawyer?.original_score} → {lawyer?.updated_score}
                      </div>
                      <p className="lawyer-rebuttal">{lawyer?.rebuttal}</p>
                    </>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Judge */}
      {judge?.status === 'complete' && (
        <div className="debate-judge">
          <h4>Judge's Verdict</h4>
          <div className={`verdict-stamp ${judge.verdict?.save ? 'saved' : 'rejected'}`}>
            {judge.verdict?.save ? 'SAVED' : 'REJECTED'}
          </div>
          <div className="judge-scores">
            {judge.verdict?.scores && Object.entries(judge.verdict.scores).map(([dim, score]) => (
              <div key={dim} className="score-bar">
                <span className="score-label">{dim.replace('_', ' ')}</span>
                <div className="score-track">
                  <div className="score-fill" style={{ width: `${score * 10}%` }}></div>
                </div>
                <span className="score-value">{score}</span>
              </div>
            ))}
          </div>
          <p className="verdict-summary">{judge.verdict?.summary}</p>
        </div>
      )}

      {judge?.status === 'connecting' || judge?.status === 'thinking' ? (
        <div className="debate-judge thinking">
          <h4>Judge is thinking...</h4>
          <div className="thinking-indicator">
            <span></span><span></span><span></span>
          </div>
        </div>
      ) : null}
    </div>
  )
}

function getScoreClass(score) {
  if (score >= 7) return 'high'
  if (score >= 5) return 'medium'
  return 'low'
}

export default ActiveDebate