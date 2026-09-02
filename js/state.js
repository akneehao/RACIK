// state.js
// Single shared source of truth for the app. Other modules import `state`
// and mutate it directly (or via the helpers below) rather than keeping
// their own copies, so every tab always reads consistent data.

export const state = {
  // onboarding
  location: '',
  people: 120,
  selectedDuration: '5',       // '3' | '5' | '7' | 'custom'
  customSelectedDays: new Set(['M', 'T1', 'W', 'T2', 'F']),
  customWeeks: 2,
  weeklyBudget: 3500000,       // illustrative, Rupiah

  // generated plan
  generatedDays: [],           // built by buildTray(); array of recipe objects with .key/.name
  statusMap: {},               // dayKey -> 'yes' | 'no'
  activeRejectDay: null,
  rejectionLog: [],            // [{ day, reason }] — feeds the Settings feedback log

  // inventory records, keyed as `${dayKey}::${ingredientName}`
  inventoryRecords: {},
};

export function resetForRegenerate() {
  state.inventoryRecords = {};
  state.statusMap = {};
}
