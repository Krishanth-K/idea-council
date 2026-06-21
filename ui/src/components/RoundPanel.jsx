const DIMENSION_LABELS = {
  novelty: 'Novelty',
  solo_feasibility: 'Solo Feasibility',
  technical_depth: 'Technical Depth',
  resume_value: 'Resume Value',
  real_use_case: 'Real Use Case'
}

function getScoreClass(score) {
  if (score >= 7) return 'high'
  if (score >= 5) return 'medium'
  return 'low'
}

function RoundPanel({ round, data }) {
  const isRound1 = round === 'round1'
  const title = isRound1 ? 'Round 1: Opening Arguments' : 'Round 2: Cross Examination'

  if (!data || !data.lawyers) {
    return (
      <div className="cycle-panel">
        <div className="cycle-panel-header">{title}</div>
        <div className="cycle-panel-content">
          <span className="status-badge waiting">Waiting</span>
        </div>
      </div>
    )
  }

  const lawyers = Object.entries(data.lawyers)

  return (
    <div className="cycle-panel">
      <div className="cycle-panel-header">{title}</div>
      <div className="cycle-panel-content">
        <div className="lawyer-grid">
          {lawyers.map(([dimension, lawyer]) => (
            <div key={dimension} className="lawyer-card">
              <div className="dimension">{DIMENSION_LABELS[dimension] || dimension}</div>

              {isRound1 ? (
                <>
                  <div className={`score ${getScoreClass(lawyer.score)}`}>
                    {lawyer.score}/10
                  </div>
                  <div className="argument">{lawyer.argument}</div>
                </>
              ) : (
                <>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px' }}>
                    <span style={{ fontSize: '14px', color: '#888' }}>
                      {lawyer.original_score}
                    </span>
                    <span style={{ fontSize: '20px' }}>→</span>
                    <div className={`score ${getScoreClass(lawyer.updated_score)}`}>
                      {lawyer.updated_score}/10
                    </div>
                  </div>
                  <div className="argument">{lawyer.rebuttal}</div>
                </>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default RoundPanel