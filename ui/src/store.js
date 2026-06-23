import { create } from 'zustand'

// Signal status enum: scraped → ideating → idea_generated → debating → resolved
const SIGNAL_STATUS = {
  SCRAPED: 'scraped',           // Signal discovered, no idea yet
  IDEATING: 'ideating',         // Ideator is running
  IDEA_GENERATED: 'idea_generated', // Idea created
  DEBATING: 'debating',         // Debate in progress
  RESOLVED: 'resolved'          // Saved or rejected
}

// Idea status enum
const IDEA_STATUS = {
  PENDING_DEBATE: 'pending_debate',
  DEBATING: 'debating',
  SAVED: 'saved',
  REJECTED: 'rejected'
}

function resolveActiveCycle(state, event) {
  if (state.activeCycle?.cycle_id === event.cycle_id) {
    return state.activeCycle
  }
  if (!event.cycle_id) {
    return state.activeCycle
  }
  const signal = state.signals.find(s => s.signal_id === event.signal_id)
  return {
    cycle_id: event.cycle_id,
    signal_id: event.signal_id,
    signal,
    ideator: { status: 'waiting' },
    round1: null,
    round2: null,
    judge: null
  }
}

function patchActiveCycle(state, event, patch) {
  const base = resolveActiveCycle(state, event)
  if (!base) return {}
  return {
    activeCycle: {
      ...base,
      ...patch
    }
  }
}

const useStore = create((set, get) => ({
  // Run state
  run: {
    run_id: null,
    status: 'idle',
    stage: null,
    current_signal_index: 0,
    total_signals: 0,
    signals_processed: 0,
    saved_count: 0,
    rejected_count: 0,
    skipped_count: 0,
    error_count: 0,
    started_at: null,
    completed_at: null,
    elapsed_seconds: 0
  },

  // Sources
  sources: {},

  // Signals
  signals: [],

  // Queue tracking for batch operations
  ideationQueue: [],
  debateQueue: [],

  // Active cycle
  activeCycle: null,

  // Archived ideas (loaded from API)
  archive: {
    saved: [],
    rejected: [],
    loading: false
  },

  // Completed cycles (verdicts)
  savedIdeas: [],
  rejectedIdeas: [],
  skippedSignals: [],
  errors: [],

  // Current tab
  activeTab: 'live-run',

  // Detail drawer
  selectedSignal: null,
  selectedIdea: null,
  drawerOpen: false,

  // WebSocket connection
  ws: null,
  connected: false,
  reconnectTimer: null,
  reconnectDelay: 1000,
  intentionalDisconnect: false,

  // Actions
  setActiveTab: (tab) => set({ activeTab: tab }),

  openDrawer: (type, data) => set({
    drawerOpen: true,
    selectedSignal: type === 'signal' ? data : null,
    selectedIdea: type === 'idea' ? data : null
  }),

  closeDrawer: () => set({
    drawerOpen: false,
    selectedSignal: null,
    selectedIdea: null
  }),

  // Connect to WebSocket
  connect: () => {
    const { ws, intentionalDisconnect } = get()
    if (intentionalDisconnect) return
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
      return
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/ws`
    const socket = new WebSocket(wsUrl)

    socket.onopen = () => {
      console.log('Connected to server')
      set({ connected: true, ws: socket, reconnectDelay: 1000 })
      get().fetchState()
    }

    socket.onclose = () => {
      console.log('Disconnected from server')
      set({ connected: false, ws: null })

      const { intentionalDisconnect: closedOnPurpose, reconnectDelay } = get()
      if (closedOnPurpose) return

      const timer = setTimeout(() => {
        set({ reconnectDelay: Math.min(reconnectDelay * 2, 30000) })
        get().connect()
      }, reconnectDelay)
      set({ reconnectTimer: timer })
    }

    socket.onmessage = (event) => {
      const data = JSON.parse(event.data)
      get().handleEvent(data)
    }

    set({ ws: socket })
  },

  disconnect: () => {
    const { ws, reconnectTimer } = get()
    if (reconnectTimer) clearTimeout(reconnectTimer)
    set({ intentionalDisconnect: true, reconnectTimer: null, reconnectDelay: 1000 })
    if (ws) ws.close()
    set({ connected: false, ws: null })
  },

  // Handle incoming events
  handleEvent: (event) => {
    const state = get()

    switch (event.type) {
      case 'run_started':
        set({
          run: {
            ...state.run,
            run_id: event.run_id,
            status: 'scraping',
            started_at: event.timestamp,
            total_signals: 0,
            signals_processed: 0,
            saved_count: 0,
            rejected_count: 0,
            skipped_count: 0,
            error_count: 0,
            elapsed_seconds: 0
          },
          signals: [],
          activeCycle: null,
          savedIdeas: [],
          rejectedIdeas: [],
          skippedSignals: [],
          errors: [],
          ideationQueue: [],
          debateQueue: []
        })
        break

      case 'source_started':
        set({
          sources: {
            ...state.sources,
            [event.payload.source]: {
              source: event.payload.source,
              status: 'scraping',
              raw_count: 0,
              fresh_count: 0,
              duplicate_count: 0,
              started_at: event.timestamp
            }
          }
        })
        break

      case 'source_completed':
        set({
          sources: {
            ...state.sources,
            [event.payload.source]: {
              ...state.sources[event.payload.source],
              status: 'complete',
              raw_count: event.payload.raw_count,
              fresh_count: event.payload.fresh_count,
              duplicate_count: event.payload.duplicate_count,
              completed_at: event.timestamp
            }
          }
        })
        break

      case 'source_error':
        set({
          sources: {
            ...state.sources,
            [event.payload.source]: {
              ...state.sources[event.payload.source],
              status: 'error',
              error: event.payload.error,
              completed_at: event.timestamp
            }
          }
        })
        break

      case 'signal_discovered':
        set({
          run: {
            ...state.run,
            total_signals: state.run.total_signals + 1
          }
        })
        break

      case 'signal_queued':
        set({
          signals: [...state.signals, {
            signal_id: event.signal_id,
            source: event.payload.source,
            title: event.payload.title,
            url: event.payload.url,
            blurb: event.payload.blurb,
            scraped_at: event.payload.scraped_at,
            status: SIGNAL_STATUS.SCRAPED,
            queue_index: event.payload.queue_index
          }],
          run: {
            ...state.run,
            total_signals: state.run.total_signals + 1
          }
        })
        break

      case 'signal_processing_started':
        set({
          signals: state.signals.map(s =>
            s.signal_id === event.signal_id
              ? { ...s, status: SIGNAL_STATUS.IDEATING }
              : s
          ),
          run: {
            ...state.run,
            status: 'processing',
            current_signal_index: event.payload.signal_index || 0
          },
          activeCycle: {
            cycle_id: event.cycle_id,
            signal_id: event.signal_id,
            signal: state.signals.find(s => s.signal_id === event.signal_id),
            ideator: { status: 'waiting' },
            round1: null,
            round2: null,
            judge: null
          }
        })
        break

      // New events for parallel ideation
      case 'ideation_started':
        set(state => ({
          ...patchActiveCycle(state, event, {
            ideator: {
              status: 'connecting',
              provider: event.payload.provider,
              host: event.payload.host,
              model: event.payload.model,
              started_at: event.timestamp
            }
          }),
          signals: state.signals.map(s =>
            s.signal_id === event.signal_id
              ? { ...s, status: SIGNAL_STATUS.IDEATING }
              : s
          ),
          ideationQueue: state.ideationQueue.includes(event.signal_id)
            ? state.ideationQueue
            : [...state.ideationQueue, event.signal_id]
        }))
        break

      case 'ideation_completed':
        set(state => ({
          ...patchActiveCycle(state, event, {
            ideator: {
              status: 'complete',
              idea: event.payload.idea,
              completed_at: event.timestamp
            }
          }),
          signals: state.signals.map(s =>
            s.signal_id === event.signal_id
              ? { ...s, status: SIGNAL_STATUS.IDEA_GENERATED, idea: event.payload.idea }
              : s
          ),
          ideationQueue: state.ideationQueue.filter(id => id !== event.signal_id)
        }))
        break

      case 'ideation_error':
        set(state => ({
          ...patchActiveCycle(state, event, {
            ideator: {
              status: 'failed',
              error: event.payload.error,
              completed_at: event.timestamp
            }
          }),
          signals: state.signals.map(s =>
            s.signal_id === event.signal_id
              ? { ...s, status: 'error' }
              : s
          ),
          ideationQueue: state.ideationQueue.filter(id => id !== event.signal_id),
          run: {
            ...state.run,
            error_count: state.run.error_count + 1
          },
          errors: [...state.errors, {
            error_id: `${event.cycle_id}-ideator`,
            stage: 'ideator',
            message: event.payload.error
          }]
        }))
        break

      // Legacy event handlers (keep for backward compatibility)
      case 'ideator_started':
        set(state => ({
          ...patchActiveCycle(state, event, {
            ideator: {
              status: 'connecting',
              provider: event.payload.provider,
              host: event.payload.host,
              model: event.payload.model,
              started_at: event.timestamp
            }
          }),
          signals: state.signals.map(s =>
            s.signal_id === event.signal_id
              ? { ...s, status: SIGNAL_STATUS.IDEATING }
              : s
          )
        }))
        break

      case 'ideator_thinking':
        set(state => {
          const base = resolveActiveCycle(state, event)
          if (!base) return {}
          return {
            activeCycle: {
              ...base,
              ideator: {
                status: 'thinking',
                provider: event.payload.provider,
                host: event.payload.host,
                model: event.payload.model,
                started_at: base.ideator?.started_at || event.timestamp
              }
            }
          }
        })
        break

      case 'ideator_completed':
        set(state => ({
          ...patchActiveCycle(state, event, {
            ideator: {
              status: 'complete',
              idea: event.payload.idea,
              completed_at: event.timestamp
            }
          }),
          signals: state.signals.map(s =>
            s.signal_id === event.signal_id
              ? { ...s, status: SIGNAL_STATUS.IDEA_GENERATED, idea: event.payload.idea }
              : s
          )
        }))
        break

      case 'ideator_failed':
        set(state => ({
          ...patchActiveCycle(state, event, {
            ideator: {
              status: 'failed',
              error: event.payload.error,
              completed_at: event.timestamp
            }
          }),
          signals: state.signals.map(s =>
            s.signal_id === event.signal_id
              ? { ...s, status: 'error' }
              : s
          ),
          run: {
            ...state.run,
            error_count: state.run.error_count + 1
          },
          errors: [...state.errors, {
            error_id: `${event.cycle_id}-ideator`,
            stage: 'ideator',
            message: event.payload.error
          }]
        }))
        break

      case 'ideator_skipped':
        set(state => ({
          ...patchActiveCycle(state, event, {
            ideator: {
              status: 'skipped',
              skip_reason: event.payload.reason,
              completed_at: event.timestamp
            }
          }),
          signals: state.signals.map(s =>
            s.signal_id === event.signal_id
              ? { ...s, status: 'skipped' }
              : s
          ),
          run: {
            ...state.run,
            signals_processed: state.run.signals_processed + 1,
            skipped_count: state.run.skipped_count + 1
          }
        }))
        break

      case 'round_started': {
        const round = event.payload.round === 1 ? 'round1' : 'round2'
        set(state => ({
          ...patchActiveCycle(state, event, {
            [round]: {
              status: 'running',
              lawyers: {},
              started_at: event.timestamp
            }
          }),
          signals: state.signals.map(s =>
            s.signal_id === event.signal_id
              ? { ...s, status: SIGNAL_STATUS.DEBATING }
              : s
          )
        }))
        break
      }

      case 'lawyer_completed': {
        const round = event.payload.round === 1 ? 'round1' : 'round2'
        set(state => {
          const base = resolveActiveCycle(state, event)
          if (!base) return {}
          const currentRound = base[round] || { status: 'running', lawyers: {} }

          const lawyerData = round === 'round1'
            ? {
                score: event.payload.score,
                argument: event.payload.argument,
                key_points: event.payload.key_points || []
              }
            : {
                original_score: event.payload.original_score,
                updated_score: event.payload.updated_score,
                rebuttal: event.payload.rebuttal
              }

          const updatedSignals = state.signals.map(s => {
            if (s.signal_id !== event.signal_id) return s
            const existingRound = s[round] || {}
            return {
              ...s,
              [round]: {
                ...existingRound,
                lawyers: {
                  ...existingRound.lawyers,
                  [event.payload.dimension]: { ...lawyerData, status: 'complete' }
                }
              }
            }
          })

          return {
            activeCycle: {
              ...base,
              [round]: {
                ...currentRound,
                lawyers: {
                  ...currentRound.lawyers,
                  [event.payload.dimension]: {
                    ...lawyerData,
                    status: 'complete'
                  }
                }
              }
            },
            signals: updatedSignals
          }
        })
        break
      }

      case 'judge_completed':
        set(state => ({
          ...patchActiveCycle(state, event, {
            judge: {
              status: 'complete',
              verdict: event.payload.verdict,
              completed_at: event.timestamp
            }
          })
        }))
        break

      case 'cycle_failed':
        set(state => ({
          signals: state.signals.map(s =>
            s.signal_id === event.signal_id
              ? { ...s, status: 'error' }
              : s
          ),
          run: {
            ...state.run,
            error_count: state.run.error_count + 1
          },
          errors: [...state.errors, {
            error_id: `${event.cycle_id}-${event.payload.stage}`,
            stage: event.payload.stage,
            message: event.payload.error
          }]
        }))
        break

      case 'verdict_saved':
        set({
          savedIdeas: [...state.savedIdeas, {
            cycle_id: event.cycle_id,
            signal_id: event.signal_id,
            idea: state.activeCycle?.ideator?.idea,
            verdict: event.payload.verdict
          }],
          signals: state.signals.map(s =>
            s.signal_id === event.signal_id
              ? { ...s, status: SIGNAL_STATUS.RESOLVED }
              : s
          ),
          run: {
            ...state.run,
            signals_processed: state.run.signals_processed + 1,
            saved_count: state.run.saved_count + 1
          }
        })
        break

      case 'verdict_rejected':
        set({
          rejectedIdeas: [...state.rejectedIdeas, {
            cycle_id: event.cycle_id,
            signal_id: event.signal_id,
            idea: state.activeCycle?.ideator?.idea,
            verdict: event.payload.verdict
          }],
          signals: state.signals.map(s =>
            s.signal_id === event.signal_id
              ? { ...s, status: SIGNAL_STATUS.RESOLVED }
              : s
          ),
          run: {
            ...state.run,
            signals_processed: state.run.signals_processed + 1,
            rejected_count: state.run.rejected_count + 1
          }
        })
        break

      case 'cycle_completed':
        set({
          run: {
            ...state.run,
            status: 'processing'
          }
        })
        break

      case 'run_completed':
        set({
          run: {
            ...state.run,
            status: 'complete',
            completed_at: event.timestamp
          }
        })
        break

      case 'section_started':
        set({
          run: {
            ...state.run,
            status: 'processing',
            stage: event.payload.section
          }
        })
        break

      case 'section_completed':
        set({
          run: {
            ...state.run,
            status: 'idle',
            stage: null
          }
        })
        break

      case 'run_stopped':
        set({
          run: {
            ...state.run,
            status: 'idle',
            stage: null
          }
        })
        break

      case 'run_failed':
        set({
          run: {
            ...state.run,
            status: 'failed',
            completed_at: event.timestamp
          },
          errors: [...state.errors, {
            error_id: `${event.run_id}-run`,
            stage: 'run',
            message: event.payload.error
          }]
        })
        break

      default:
        console.log('Unknown event:', event.type)
    }
  },

  // Actions
  startRun: async (maxSignals = 10) => {
    const response = await fetch('/api/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ max_signals: maxSignals })
    })
    return response.json()
  },

  stopRun: async () => {
    const response = await fetch('/api/run/stop', { method: 'POST' })
    return response.json()
  },

  startScraping: async (maxSignals = 10) => {
    const response = await fetch('/api/run/start-scraping', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ max_signals: maxSignals })
    })
    return response.json()
  },

  startIdeator: async () => {
    const response = await fetch('/api/run/start-ideator', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    })
    return response.json()
  },

  startDebate: async () => {
    // Start Round 1 - debate is batch triggered
    const response = await fetch('/api/run/start-round1', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    })
    return response.json()
  },

  fetchState: async () => {
    const response = await fetch('/api/state')
    const data = await response.json()
    set({
      run: data.run,
      sources: data.sources,
      signals: data.signals,
      activeCycle: data.activeCycle,
      savedIdeas: data.savedIdeas,
      rejectedIdeas: data.rejectedIdeas,
      skippedSignals: data.skippedSignals,
      errors: data.errors
    })
  },

  // Archive actions
  fetchArchive: async () => {
    set(state => ({ archive: { ...state.archive, loading: true } }))

    try {
      const response = await fetch('/api/archive')
      const data = await response.json()

      set({
        archive: {
          saved: data.saved || [],
          rejected: data.rejected || [],
          loading: false
        }
      })
    } catch (error) {
      console.error('Failed to fetch archive:', error)
      set(state => ({ archive: { ...state.archive, loading: false } }))
    }
  },

  fetchArchiveDetail: async (id) => {
    const response = await fetch(`/api/archive/${id}`)
    return response.json()
  }
}))

// Export constants for use in components
export { SIGNAL_STATUS, IDEA_STATUS }
export default useStore