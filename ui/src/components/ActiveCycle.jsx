import useStore from '../store'
import SignalPanel from './SignalPanel'
import IdeatorPanel from './IdeatorPanel'
import RoundPanel from './RoundPanel'
import JudgePanel from './JudgePanel'

function ActiveCycle() {
  const { activeCycle, run } = useStore()

  if (!activeCycle) {
    return (
      <div className="main-content">
        <div className="empty-state">
          <h2>No Active Cycle</h2>
          <p>Start a run to see the council in action</p>
        </div>
      </div>
    )
  }

  return (
    <div className="main-content">
      <SignalPanel signal={activeCycle.signal} />
      <IdeatorPanel ideator={activeCycle.ideator} />
      {activeCycle.round1 && <RoundPanel round="round1" data={activeCycle.round1} />}
      {activeCycle.round2 && <RoundPanel round="round2" data={activeCycle.round2} />}
      {activeCycle.judge && <JudgePanel judge={activeCycle.judge} />}
    </div>
  )
}

export default ActiveCycle