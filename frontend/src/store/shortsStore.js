import { useState, useEffect } from 'react'

let state = {
  file: null,
  fileUrl: null,
  shortsCount: 3,
  clipDur: 60,
  mode: 'GUIDED',
  analyzing: false,
  cutting: false,
  autoSegments: [],
  autoClips: [],
  guidedSegments: [],
  guidedClips: [],
  manualSegments: [],
  manualClips: [],
  jobId: null,
  totalDur: 0,
  curTime: 0,
  playing: false,
  activeSeg: null,
  phase: 'upload',
  downloadingIdx: null,
}

const listeners = new Set()

export const shortsStore = {
  getState() {
    return state
  },
  setState(nextState) {
    if (typeof nextState === 'function') {
      state = { ...state, ...nextState(state) }
    } else {
      state = { ...state, ...nextState }
    }
    listeners.forEach(l => l(state))
  },
  subscribe(listener) {
    listeners.add(listener)
    return () => listeners.delete(listener)
  }
}

export function useShortsStore() {
  const [value, setValue] = useState(state)
  useEffect(() => {
    return shortsStore.subscribe(setValue)
  }, [])
  return [value, shortsStore.setState]
}
