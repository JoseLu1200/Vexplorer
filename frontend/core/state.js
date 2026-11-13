const EMPTY_STATE = Object.freeze({
  phase: "empty",
  runId: null,
  snapshot: null,
  selection: {},
  error: null,
  events: [],
});

function reduce(state, action) {
  switch (action.type) {
    case "RUN_LOADING":
      return { ...EMPTY_STATE, phase: "loading", runId: action.runId };
    case "SNAPSHOT_RECEIVED": {
      const snapshot = action.snapshot;
      const reviewStates = new Set(["needs_review", "completed"]);
      return {
        ...state,
        phase: reviewStates.has(snapshot.state) ? "review" : "loading",
        snapshot,
        error: null,
      };
    }
    case "SELECTION_CHANGED":
      return { ...state, selection: { ...action.selection } };
    case "ERROR_RECEIVED":
      return { ...state, phase: "error", error: action.error };
    case "EVENTS_CHANGED":
      return { ...state, events: [...action.events] };
    default:
      return state;
  }
}

export function createStore(initialState = {}) {
  let state = { ...EMPTY_STATE, ...initialState };
  const listeners = new Set();
  return {
    getState: () => state,
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    dispatch(action) {
      state = reduce(state, action);
      listeners.forEach((listener) => listener(state));
      return action;
    },
  };
}
