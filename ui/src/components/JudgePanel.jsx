const DIMENSION_LABELS = {
  novelty: 'Novelty',
  solo_feasibility: 'Solo Feasibility',
  technical_depth: 'Technical Depth',
  resume_value: 'Resume Value',
  real_use_case: 'Real Use Case'
}

function JudgePanel({ judge }) {
  if (!judge) {
    return (
      <div className="cycle-panel">
        <div className="cycle-panel-header">Judge</div>
        <div className="cycle-panel-content">
          <span className="status-badge waiting">Waiting</span>
        </div>
      </div>
    )
  }

  const verdict = judge.verdict

  if (!verdict) {
    return (
      <div className="cycle-panel">
        <div className="cycle-panel-header">Judge</div>
        <div className="cycle-panel-content">
          <span className="status-badge thinking">Thinking...</span>
        </div>
      </div>
    )
  }

  return (
    <div className="cycle-panel">
      <div className="cycle-panel-header">Judge Verdict</div>
      <div className="cycle-panel-content">
        <div className={`verdict-save ${verdict.save ? 'saved' : 'rejected'}`}>
          {verdict.save ? '✓ SAVED' : '✗ REJECTED'}
        </div>

        <div className="idea-field">
          <div className="label">Weighted Score</div>
          <div className="value" style={{ fontSize: '20px', fontWeight: 600 }}>
            {verdict.weighted_score}/10
          </div>
        </div>

        <div className="idea-field">
          <div className="label">Dimension Scores</div>
          <div style={{ marginTop: '4px' }}>
            {Object.entries(verdict.scores || {}).map(([dim, score]) => (
              <span key={dim} style={{ marginRight: '12px', fontSize: '13px' }}>
                {DIMENSION_LABELS[dim] || dim}: {score}
              </span>
            ))}
          </div>
        </div>

        <div className="idea-field">
          <div className="label">Summary</div>
          <div className="judge-summary">{verdict.summary}</div>
        </div>

        {verdict.hard_discard_reason && (
          <div className="idea-field">
            <div className="label">Hard Discard Reason</div>
            <div className="value" style={{ color: '#c62828' }}>
              {verdict.hard_discard_reason}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default JudgePanel