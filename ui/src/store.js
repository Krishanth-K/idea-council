import { create } from 'zustand'

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
    completed_at: null
  },

  // Sources
  sources: {},

  // Signals
  signals: [],

  // Active cycle
  activeCycle: null,

  // Completed cycles (verdicts)
  savedIdeas: [],
  rejectedIdeas: [],
  skippedSignals: [],
  errors: [],

  // WebSocket connection
  ws: null,
  connected: false,

  // Connect to WebSocket
  connect: () => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/ws`
    const ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      console.log('Connected to server')
      set({ connected: true, ws })
    }

    ws.onclose = () => {
      console.log('Disconnected from server')
      set({ connected: false, ws: null })
    }

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      get().handleEvent(data)
    }
  },

  disconnect: () => {
    const { ws } = get()
    if (ws) {
      ws.close()
    }
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
            error_count: 0
          },
          signals: [],
          savedIdeas: [],
          rejectedIdeas: [],
          skippedSignals: [],
          errors: []
        })
        break

      case 'source_scrape_started':
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

      case 'source_scrape_completed':
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
            status: 'queued',
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
              ? { ...s, status: 'processing' }
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

      case 'ideator_completed':
        if (state.activeCycle) {
          set({
            activeCycle: {
              ...state.activeCycle,
              ideator: {
                status: 'complete',
                idea: event.payload.idea,
                completed_at: event.timestamp
              }
            }
          })
        }
        break

      case 'ideator_skipped':
        if (state.activeCycle) {
          set({
            activeCycle: {
              ...state.activeCycle,
              ideator: {
                status: 'skipped',
                skip_reason: event.payload.reason,
                completed_at: event.timestamp
              }
            },
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
          })
        }
        break

      case 'round_started':
        if (state.activeCycle) {
          const round = event.payload.round === 1 ? 'round1' : 'round2'
          set({
            activeCycle: {
              ...state.activeCycle,
              [round]: {
                status: 'running',
                lawyers: {},
                started_at: event.timestamp
              }
            }
          })
        }
        break

      case 'lawyer_completed':
        if (state.activeCycle) {
          const round = event.payload.round === 1 ? 'round1' : 'round2'
          const currentRound = state.activeCycle[round]

          if (currentRound) {
            set({
              activeCycle: {
                ...state.activeCycle,
                [round]: {
                  ...currentRound,
                  lawyers: {
                    ...currentRound.lawyers,
                    [event.payload.dimension]: {
                      ...(round === 'round1'
                        ? {
                            score: event.payload.score,
                            argument: event.payload.argument,
                            key_points: event.payload.key_points || []
                          }
                        : {
                            original_score: event.payload.original_score,
                            updated_score: event.payload.updated_score,
                            rebuttal: event.payload.rebuttal
                          }),
                      status: 'complete'
                    }
                  }
                }
              }
            })
          }
        }
        break

      case 'judge_completed':
        if (state.activeCycle) {
          set({
            activeCycle: {
              ...state.activeCycle,
              judge: {
                status: 'complete',
                verdict: event.payload.verdict,
                completed_at: event.timestamp
              }
            }
          })
        }
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
              ? { ...s, status: 'saved' }
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
              ? { ...s, status: 'rejected' }
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

      case 'run_failed':
        set({
          run: {
            ...state.run,
            status: 'failed',
            completed_at: event.timestamp
          }
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
    const data = await response.json()
    await get().fetchState()
    return data
  },

  fetchState: async () => {
    const response = await fetch('/api/state')
    const data = await response.json()
    set(data)
  }
}))

export default useStore
