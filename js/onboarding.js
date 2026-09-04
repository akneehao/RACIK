// onboarding.js
// Screen 1 (location) and Screen 2 (menu duration / budget / people / notes).
// Exposes initOnboarding(onGenerate) — the callback fires once the person
// clicks "Generate Meal Plan", after the real backend plan comes back (or
// shows an error and stays on screen 2 if the request fails).

import { state } from './state.js';
import { api } from './api.js';
import { showScreen, setOnboardingStep, toast } from './utils.js';

// The mockup's four suggestion chips are English city/region names; the
// backend's corpus provinces are Indonesian. This is the one translation
// table needed to resolve the shipped suggestions to a real province —
// arbitrary free-typed text is matched directly against the live province
// list instead (see resolveProvince below), so nothing else needs a lookup.
const SUGGESTION_PROVINCE_HINTS = {
  'bandung, west java': 'jawa barat',
  'makassar, south sulawesi': 'sulawesi selatan',
  'medan, north sumatra': 'sumatera utara',
  'yogyakarta, d.i. yogyakarta': 'yogyakarta',
};

/** Resolve free-typed or suggestion-picked location text to a corpus province,
 * or '' if nothing matches (the backend then plans with no regional preference). */
function resolveProvince(text) {
  const low = (text || '').trim().toLowerCase();
  if (!low) return '';
  const hint = SUGGESTION_PROVINCE_HINTS[low];
  const needle = hint || low;
  const found = state.provinces.find((p) => p.province.toLowerCase().includes(needle))
    || state.provinces.find((p) => needle.includes(p.province.toLowerCase()));
  return found ? found.province : '';
}

function summarizeCustom() {
  const n = state.customSelectedDays.size;
  return `${n} day${n === 1 ? '' : 's'}/wk × ${state.customWeeks} wk${state.customWeeks === 1 ? '' : 's'}`;
}

function initLocationScreen() {
  const locInput = document.getElementById('locationInput');
  const locSuggestions = document.getElementById('locSuggestions');

  locInput.addEventListener('focus', () => locSuggestions.classList.add('show'));
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.loc-field')) locSuggestions.classList.remove('show');
  });
  locSuggestions.querySelectorAll('button').forEach((b) => {
    b.addEventListener('click', () => {
      locInput.value = b.textContent;
      locSuggestions.classList.remove('show');
    });
  });

  document.getElementById('startBtn').addEventListener('click', () => {
    state.location = locInput.value || 'Bandung, West Java';
    state.province = resolveProvince(state.location);
    document.getElementById('sumLocation').textContent = state.location;
    showScreen('screen-2');
    setOnboardingStep(2);
  });
}

function initDurationControls() {
  document.getElementById('durationChips').addEventListener('click', (e) => {
    const chip = e.target.closest('.chip');
    if (!chip) return;
    document.querySelectorAll('#durationChips .chip').forEach((c) => c.classList.remove('selected'));
    chip.classList.add('selected');
    state.selectedDuration = chip.dataset.val;

    const customPanel = document.getElementById('customRecurrence');
    if (state.selectedDuration === 'custom') {
      customPanel.classList.add('show');
      document.getElementById('sumDuration').textContent = summarizeCustom();
    } else {
      customPanel.classList.remove('show');
      document.getElementById('sumDuration').textContent = `${state.selectedDuration} days`;
    }
  });

  // weeks stepper
  document.getElementById('crWeeksInc').addEventListener('click', () => {
    state.customWeeks = Math.min(12, state.customWeeks + 1);
    document.getElementById('crWeeksCount').textContent = state.customWeeks;
    if (state.selectedDuration === 'custom') {
      document.getElementById('sumDuration').textContent = summarizeCustom();
    }
  });
  document.getElementById('crWeeksDec').addEventListener('click', () => {
    state.customWeeks = Math.max(1, state.customWeeks - 1);
    document.getElementById('crWeeksCount').textContent = state.customWeeks;
    if (state.selectedDuration === 'custom') {
      document.getElementById('sumDuration').textContent = summarizeCustom();
    }
  });

  // day-of-week picker
  document.querySelectorAll('#dayPicker .dp-day').forEach((btn) => {
    if (state.customSelectedDays.has(btn.dataset.day)) btn.classList.add('on');
    btn.addEventListener('click', () => {
      const day = btn.dataset.day;
      if (state.customSelectedDays.has(day)) {
        if (state.customSelectedDays.size === 1) return; // keep at least one day selected
        state.customSelectedDays.delete(day);
        btn.classList.remove('on');
      } else {
        state.customSelectedDays.add(day);
        btn.classList.add('on');
      }
      if (state.selectedDuration === 'custom') {
        document.getElementById('sumDuration').textContent = summarizeCustom();
      }
    });
  });
}

/** Days-per-week implied by the current duration setting (used for the budget estimate). */
function daysPerWeek() {
  if (state.selectedDuration === 'custom') return state.customSelectedDays.size;
  return parseInt(state.selectedDuration, 10) || 5;
}

function updateBudgetSummary() {
  const perPortion = state.budgetMode === 'total'
    ? state.budgetValue / Math.max(state.people * daysPerWeek(), 1)
    : state.budgetValue;
  document.getElementById('sumPerPortion').textContent =
    `≈ Rp ${Math.round(perPortion).toLocaleString('en-US')}`;
}

function initBudgetControls() {
  const input = document.getElementById('budgetInput');
  input.addEventListener('input', () => {
    const raw = parseFloat(input.value.replace(/[^\d.]/g, ''));
    state.budgetValue = Number.isFinite(raw) ? raw : state.budgetValue;
    updateBudgetSummary();
  });

  document.querySelectorAll('.toggle-pair button').forEach((b) => {
    b.addEventListener('click', () => {
      b.parentElement.querySelectorAll('button').forEach((x) => x.classList.remove('active'));
      b.classList.add('active');
      state.budgetMode = b.dataset.mode === 'per' ? 'per_portion' : 'total';
      updateBudgetSummary();
    });
  });

  updateBudgetSummary();
}

function updatePeopleDisplay() {
  document.getElementById('peopleCount').textContent = state.people;
  document.getElementById('sumPeople').textContent = state.people;
  updateBudgetSummary();
}

function initPeopleStepper() {
  document.getElementById('incPeople').addEventListener('click', () => {
    state.people += 10;
    updatePeopleDisplay();
  });
  document.getElementById('decPeople').addEventListener('click', () => {
    state.people = Math.max(10, state.people - 10);
    updatePeopleDisplay();
  });
}

function initNotesField() {
  const el = document.getElementById('notesInput');
  if (!el) return;
  el.addEventListener('input', () => { state.notes = el.value; });
}

function initGenerateButton(onGenerate) {
  const btn = document.getElementById('generateBtn');
  btn.addEventListener('click', async () => {
    document.getElementById('loadingPanel').classList.add('show');
    btn.disabled = true;
    try {
      await onGenerate();
    } catch (err) {
      toast(`Couldn't generate a plan: ${err.message || err}`);
    } finally {
      document.getElementById('loadingPanel').classList.remove('show');
      btn.disabled = false;
    }
  });
}

/** Fetch corpus metadata once at startup — provinces (for location resolution)
 * and stages, used throughout the app. */
async function loadMeta() {
  try {
    const meta = await api.meta();
    state.provinces = meta.provinces;
  } catch (err) {
    // The app still works with no regional preference if /api/meta is
    // briefly unreachable; onboarding.js doesn't need to block on it.
    console.warn('Could not load /api/meta:', err);
  }
}

/** Wire up every control on the two onboarding screens. */
export function initOnboarding(onGenerate) {
  loadMeta();
  initLocationScreen();
  initDurationControls();
  initBudgetControls();
  initPeopleStepper();
  initNotesField();
  initGenerateButton(onGenerate);

  // clicking the onboarding stepper labels jumps between screens (handy while demoing)
  document.querySelectorAll('#onboardingStepper .step').forEach((s) => {
    s.style.cursor = 'pointer';
    s.addEventListener('click', () => {
      const n = parseInt(s.dataset.step, 10);
      showScreen(n === 1 ? 'screen-1' : 'screen-2');
      setOnboardingStep(n);
    });
  });
}
