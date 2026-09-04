// state.js
// Single shared source of truth for the app. Other modules import `state`
// and mutate it directly (or via the helpers below) rather than keeping
// their own copies, so every tab always reads consistent data.
//
// `generatedDays` now holds real backend day objects (one /api/generate call
// per calendar week — see plan.js's buildTray()), each carrying `runId` +
// `dayIndex` so accept/reject and stock edits can be posted back to the
// exact run/day they belong to.

export const state = {
  // onboarding
  location: '',
  province: '',                 // resolved backend province name, '' = no regional preference
  provinces: [],                 // [{province, island, dishes}] from /api/meta
  people: 120,
  selectedDuration: '5',        // '3' | '5' | '7' | 'custom'
  customSelectedDays: new Set(['M', 'T1', 'W', 'T2', 'F']),
  customWeeks: 2,
  budgetMode: 'total',           // 'total' | 'per_portion'
  budgetValue: 3500000,
  notes: '',

  // generated plan — one entry per calendar week, in onboarding order
  weeks: [],                     // [{ runId, resolved, trace }]
  generatedDays: [],             // flattened day-view objects, see plan.js buildDayView()
  statusMap: {},                  // dayKey -> 'yes' | 'no'
  activeRejectDay: null,
  rejectionLog: [],               // [{ day, reason }], seeded from /api/history + optimistic pushes
};

export function resetForRegenerate() {
  state.weeks = [];
  state.generatedDays = [];
  state.statusMap = {};
}

/** Estimated total Rupiah budget for `totalDays` days at the current
 * onboarding budget setting — used for display only (the real per-portion
 * figure the solver enforces is Agen Biaya's resolved value, per run). */
export function estimateTotalBudget(totalDays) {
  if (state.budgetMode === 'total') return state.budgetValue;
  return state.budgetValue * state.people * Math.max(totalDays, 1);
}
