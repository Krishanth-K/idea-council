function IdeatorPanel({ ideator }) {
  if (!ideator) {
    return (
      <div className="cycle-panel">
        <div className="cycle-panel-header">Ideator</div>
        <div className="cycle-panel-content">
          <span className="status-badge waiting">Waiting</span>
        </div>
      </div>
    )
  }

  if (ideator.status === 'skipped') {
    return (
      <div className="cycle-panel">
        <div className="cycle-panel-header">Ideator</div>
        <div className="cycle-panel-content">
          <span className="status-badge error">Skipped</span>
          <p style={{ marginTop: '8px', color: '#666' }}>
            Reason: {ideator.skip_reason}
          </p>
        </div>
      </div>
    )
  }

  if (ideator.status !== 'complete' || !ideator.idea) {
    return (
      <div className="cycle-panel">
        <div className="cycle-panel-header">Ideator</div>
        <div className="cycle-panel-content">
          <span className="status-badge thinking">Thinking...</span>
        </div>
      </div>
    )
  }

  const idea = ideator.idea

  return (
    <div className="cycle-panel">
      <div className="cycle-panel-header">Ideator</div>
      <div className="cycle-panel-content">
        <span className="status-badge complete">Complete</span>

        <div className="idea-field">
          <div className="label">Title</div>
          <div className="value" style={{ fontWeight: 600, fontSize: '16px' }}>
            {idea.title}
          </div>
        </div>

        <div className="idea-field">
          <div className="label">One-Liner</div>
          <div className="value">{idea.one_liner}</div>
        </div>

        <div className="idea-field">
          <div className="label">Target User</div>
          <div className="value">{idea.target_user}</div>
        </div>

        <div className="idea-field">
          <div className="label">Problem It Solves</div>
          <div className="value">{idea.problem_it_solves}</div>
        </div>

        <div className="idea-field">
          <div className="label">Core Technical Challenge</div>
          <div className="value">{idea.core_technical_challenge}</div>
        </div>

        <div className="idea-field">
          <div className="label">Estimated Scope</div>
          <div className="value">{idea.estimated_scope}</div>
        </div>
      </div>
    </div>
  )
}

export default IdeatorPanel