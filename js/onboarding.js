// onboarding.js
// Screen 1 (location) and Screen 2 (menu duration / budget / people / notes).
// Exposes initOnboarding(onGenerate) — the callback fires once the person
// clicks "Generate Meal Plan", after the real backend plan comes back (or
// shows an error and stays on screen 2 if the request fails).

import { state } from './state.js';
import { api } from './api.js';
import { showScreen, setOnboardingStep, toast, glossProvince, resolveProvince } from './utils.js';

/** Render the location suggestion dropdown from the real corpus province
 * list (33 provinces, from /api/meta) filtered by whatever's typed so far —
 * replaces four hardcoded example cities that made the location picker
 * look far more limited than the backend actually is. Shown in English
 * (clicking one fills the input with the English name too); resolveProvince()
 * matches either language back to the real corpus record. */
function renderLocationSuggestions(filterText) {
  const box = document.getElementById('locSuggestions');
  const low = (filterText || '').trim().toLowerCase();
  // Filter against both the raw Indonesian corpus name and its English gloss
  // — the operator may type either ("jawa barat" or "west java") — but always
  // display the English gloss, so the shown label is consistent either way.
  const matches = state.provinces
    .filter((p) => !low || p.province.toLowerCase().includes(low)
      || glossProvince(p.province).toLowerCase().includes(low))
    .map((p) => glossProvince(p.province))
    .sort((a, b) => a.localeCompare(b));
  box.innerHTML = matches.length
    ? matches.map((name) => `<button type="button">${name}</button>`).join('')
    : '<button type="button" disabled>No matching province</button>';
}

function summarizeCustom() {
  const n = state.customSelectedDays.size;
  return `${n} day${n === 1 ? '' : 's'}/wk × ${state.customWeeks} wk${state.customWeeks === 1 ? '' : 's'}`;
}

function initLocationScreen() {
  const locInput = document.getElementById('locationInput');
  const locSuggestions = document.getElementById('locSuggestions');

  locInput.addEventListener('focus', () => {
    renderLocationSuggestions(locInput.value);
    locSuggestions.classList.add('show');
  });
  locInput.addEventListener('input', () => renderLocationSuggestions(locInput.value));
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.loc-field')) locSuggestions.classList.remove('show');
  });
  // Suggestions re-render on every keystroke, so bind clicks once via
  // delegation on the container rather than per-button.
  locSuggestions.addEventListener('click', (e) => {
    const b = e.target.closest('button:not([disabled])');
    if (!b) return;
    locInput.value = b.textContent;
    locSuggestions.classList.remove('show');
  });

  // A location silently defaulting to "Bandung, West Java" meant a plan
  // could be generated for the wrong region without the operator ever
  // choosing one — regional price index and dish preference both depend on
  // it, so it's required, not a convenience default.
  locInput.addEventListener('input', () => locInput.classList.remove('input-error'));

  document.getElementById('startBtn').addEventListener('click', () => {
    const typed = locInput.value.trim();
    if (!typed) {
      toast('Please enter a location first.');
      locInput.classList.add('input-error');
      locInput.focus();
      return;
    }
    const resolvedProvince = resolveProvince(typed);
    if (!resolvedProvince) {
      toast("Couldn't match that to a province, pick one from the list.");
      locInput.classList.add('input-error');
      renderLocationSuggestions(typed);
      locSuggestions.classList.add('show');
      return;
    }

    state.location = typed;
    state.province = resolvedProvince;
    // Show the resolved corpus province's English name — the canonical,
    // confirmed value — rather than echoing back whatever raw text was
    // typed (which could be any capitalization/language/city name that
    // happened to match).
    document.getElementById('sumLocation').textContent = glossProvince(state.province);
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
  const budgetLabel = state.budgetMode === 'total'
    ? `Rp ${Math.round(state.budgetValue).toLocaleString('en-US')} total`
    : `Rp ${Math.round(state.budgetValue).toLocaleString('en-US')} / portion`;
  document.getElementById('sumBudget').textContent = budgetLabel;
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

// Where the chip-built clause ends and anything the operator typed begins.
// Kept as a marker rather than parsed back out of the text, so a chip can be
// un-toggled without disturbing free text that happens to mention the same word.
const CHIP_CLAUSE = /^tanpa [^.\n]*\.\s*/;

/** Render the school-level chips and the AKG target editor beneath them.
 *
 * Called once /api/meta lands, because both are driven entirely by what the
 * backend says the stages and nutrients are — hardcoding either would let the
 * form drift from the engine's own AKG table, which is the one thing an
 * operator overriding a nutrition floor must be able to trust.
 *
 * Only BINDING nutrients are editable. The advisory ones (calcium, iron,
 * zinc, the vitamins) are not enforced by the solver at all — offering a box
 * that changes nothing would be worse than offering nothing.
 */
function updateStageSummary() {
  const stageEl = document.getElementById('sumStage');
  const targetsEl = document.getElementById('sumTargets');
  const found = state.stages.find((st) => st.key === state.stage);
  if (stageEl) stageEl.textContent = found ? found.label : state.stage.toUpperCase();
  if (!targetsEl) return;
  const n = Object.keys(state.targetOverrides).length;
  // Name the overridden nutrients rather than counting them: an operator who
  // set a protein floor needs to see that on the summary they check before
  // generating, not "2 overridden".
  targetsEl.textContent = n
    ? Object.keys(state.targetOverrides)
        .map((k) => {
          const meta = state.nutrients.find((x) => x.key === k);
          return `${meta ? meta.label_en : k} ${state.targetOverrides[k]}`;
        })
        .join(', ')
    : 'AKG default';
}

export function renderStageAndTargets() {
  const chips = document.getElementById('stageChips');
  if (!chips || !state.stages.length) return;

  chips.innerHTML = state.stages
    .map((st) => `<button type="button" class="chip${st.key === state.stage ? ' selected' : ''}"
                    data-stage="${st.key}">${st.label}</button>`)
    .join('');
  chips.querySelectorAll('.chip').forEach((chip) => {
    chip.addEventListener('click', () => {
      state.stage = chip.dataset.stage;
      // A target typed against SD's 616 kcal means nothing against SMA's 833,
      // so switching level clears the overrides rather than carrying numbers
      // across to a scale they were never chosen for.
      state.targetOverrides = {};
      renderStageAndTargets();
      updateStageSummary();
    });
  });

  renderTargetInputs();
}

function stageTargets() {
  const found = state.stages.find((st) => st.key === state.stage);
  return found ? found.targets : {};
}

function renderTargetInputs() {
  const grid = document.getElementById('targetsGrid');
  const reset = document.getElementById('targetsReset');
  if (!grid) return;

  const defaults = stageTargets();
  const binding = state.nutrients.filter((n) => n.binding && defaults[n.key] != null);

  grid.innerHTML = binding.map((n) => {
    const akg = defaults[n.key];
    const set = state.targetOverrides[n.key];
    const edited = set != null && Math.abs(set - akg) > 0.05;
    return `
      <label class="target-field${edited ? ' edited' : ''}">
        <span class="target-name">${n.label_en}</span>
        <span class="target-input">
          <input type="number" min="0" step="0.1" data-nutrient="${n.key}"
                 value="${set != null ? set : akg}" aria-label="${n.label_en} target">
          <span class="target-unit">${n.unit}</span>
        </span>
        <span class="target-akg">${edited ? `AKG ${akg}` : 'AKG default'}</span>
      </label>`;
  }).join('');

  grid.querySelectorAll('input[data-nutrient]').forEach((input) => {
    input.addEventListener('change', () => {
      const key = input.dataset.nutrient;
      const value = parseFloat(input.value);
      const akg = defaults[key];
      // Back at the AKG figure is not an override — drop it so the request
      // carries only what the operator actually changed.
      if (!Number.isFinite(value) || value <= 0 || Math.abs(value - akg) <= 0.05) {
        delete state.targetOverrides[key];
      } else {
        state.targetOverrides[key] = value;
      }
      renderTargetInputs();
      updateStageSummary();
    });
  });

  if (reset) reset.hidden = !Object.keys(state.targetOverrides).length;
}

function initTargetsPanel() {
  const toggle = document.getElementById('targetsToggle');
  const grid = document.getElementById('targetsGrid');
  const reset = document.getElementById('targetsReset');
  if (!toggle || !grid) return;

  toggle.addEventListener('click', () => {
    const open = grid.hidden;
    grid.hidden = !open;
    toggle.setAttribute('aria-expanded', String(open));
    toggle.textContent = open ? 'Hide targets' : 'Edit targets';
  });

  if (reset) {
    reset.addEventListener('click', () => {
      state.targetOverrides = {};
      renderTargetInputs();
      updateStageSummary();
    });
  }
}

function initNotesField() {
  const el = document.getElementById('notesInput');
  if (!el) return;
  el.addEventListener('input', () => { state.notes = el.value; });

  // Quick-pick restrictions. These write plain text into the same notes
  // field rather than a separate parameter, because the notes field is what
  // Agen Gizi actually reads — a chip is a shortcut for typing, not a second
  // input path that could disagree with what the operator sees.
  //
  // `data-term` is the Indonesian word on purpose: exclude_terms is a text
  // filter matched against Indonesian dish and ingredient names, so "shrimp"
  // would match nothing. The visible label stays English like the rest of
  // this screen. "tanpa" is the marker the rule-based fallback in agents.py
  // looks for, so the chips work with no model configured.
  const chips = document.getElementById('allergyChips');
  if (!chips) return;
  const chosen = new Set();
  chips.querySelectorAll('.chip').forEach((chip) => {
    chip.addEventListener('click', () => {
      const term = chip.dataset.term;
      if (chosen.has(term)) { chosen.delete(term); } else { chosen.add(term); }
      chip.classList.toggle('selected', chosen.has(term));

      const rest = el.value.replace(CHIP_CLAUSE, '');
      const clause = chosen.size ? `tanpa ${[...chosen].join(', ')}. ` : '';
      el.value = clause + rest;
      state.notes = el.value;
    });
  });
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
    state.stages = meta.stages || [];
    state.nutrients = meta.nutrients || [];
    renderStageAndTargets();
    // The summary ran once at startup with no stage labels to read from, so
    // it showed the bare key ("sd"). Refresh now that meta has the labels.
    updateStageSummary();
    renderLocationSuggestions(document.getElementById('locationInput').value);
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
  initTargetsPanel();
  updateStageSummary();
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
