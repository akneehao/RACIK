// onboarding.js
// Screen 1 (location) and Screen 2 (menu duration / budget / people / notes).
// Exposes initOnboarding(onGenerate) — the callback fires once the person
// clicks "Generate Meal Plan", after the loading animation completes.

import { state } from './state.js';
import { showScreen, setOnboardingStep } from './utils.js';

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

function initBudgetToggle() {
  document.querySelectorAll('.toggle-pair button').forEach((b) => {
    b.addEventListener('click', () => {
      b.parentElement.querySelectorAll('button').forEach((x) => x.classList.remove('active'));
      b.classList.add('active');
    });
  });
}

function updatePeopleDisplay() {
  document.getElementById('peopleCount').textContent = state.people;
  document.getElementById('sumPeople').textContent = state.people;
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

function initGenerateButton(onGenerate) {
  document.getElementById('generateBtn').addEventListener('click', () => {
    const btn = document.getElementById('generateBtn');
    document.getElementById('loadingPanel').classList.add('show');
    btn.disabled = true;
    setTimeout(() => {
      document.getElementById('loadingPanel').classList.remove('show');
      btn.disabled = false;
      onGenerate();
    }, 1400);
  });
}

/** Wire up every control on the two onboarding screens. */
export function initOnboarding(onGenerate) {
  initLocationScreen();
  initDurationControls();
  initBudgetToggle();
  initPeopleStepper();
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
