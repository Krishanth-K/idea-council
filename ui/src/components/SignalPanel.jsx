function SignalPanel({ signal }) {
  if (!signal) return null

  return (
    <div className="cycle-panel signal-panel">
      <div className="cycle-panel-header">Active Signal</div>
      <div className="cycle-panel-content">
        <span className="source">{signal.source}</span>
        <div className="title">{signal.title}</div>
        <div className="url">
          <a href={signal.url} target="_blank" rel="noopener noreferrer">
            {signal.url}
          </a>
        </div>
        <div className="blurb">{signal.blurb}</div>
      </div>
    </div>
  )
}

export default SignalPanel