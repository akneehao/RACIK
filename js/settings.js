// settings.js
// Program parameters recap, the feedback log fed by rejected tray days,
// and the export options (also reachable here since Screen 5 was folded
// into Settings rather than kept as its own wizard step).

import { state, resetForRegenerate } from './state.js';
import { toast } from './utils.js';

/** Populate the read-only/editable parameter fields and the feedback log. */
export function renderSettingsTab() {
  document.getElementById('setLocation').value = document.getElementById('sumLocation').textContent || '';
  document.getElementById('setPeople').value = state.people;
  document.getElementById('setBudget').value = state.weeklyBudget.toLocaleString('en-US');
  document.getElementById('setDuration').value = document.getElementById('sumDuration').textContent || '';

  const list = document.getElementById('settingsFeedbackList');
  if (state.rejectionLog.length === 0) {
    list.innerHTML = '<p class="empty-note">No rejections recorded yet in this session.</p>';
  } else {
    list.innerHTML = state.rejectionLog
      .map((r) => `<div class="fb-item"><span class="fb-day">${r.day}</span><span class="fb-reason">${r.reason}</span></div>`)
      .join('');
  }
}

/**
 * Wire up the Settings tab. `callbacks` lets this module trigger a full
 * re-render of the other tabs after "Regenerate Plan" without importing
 * them directly (keeps the module graph a simple tree, not a web).
 *
 * @param {{
 *   updatePeopleDisplay: () => void,
 *   buildTray: () => void,
 *   refreshProcurement: () => void,
 *   refreshInventory: () => void,
 *   updateSidebarFooter: () => void,
 *   goToPlanTab: () => void,
 * }} callbacks
 */
export function initSettingsTab(callbacks) {
  document.querySelectorAll('.export-option').forEach((opt) => {
    opt.addEventListener('click', () => {
      opt.classList.add('done');
      const type = opt.dataset.type;
      const label = type === 'pdf' ? 'PDF' : type === 'image' ? 'an image' : 'Excel/CSV';
      toast(`Meal plan successfully exported as ${label}.`);
    });
  });

  document.getElementById('settingsRegenerate').addEventListener('click', () => {
    const newPeople = parseInt(document.getElementById('setPeople').value, 10);
    if (newPeople) state.people = newPeople;
    callbacks.updatePeopleDisplay();

    callbacks.buildTray();
    resetForRegenerate();
    callbacks.refreshProcurement();
    callbacks.refreshInventory();
    callbacks.updateSidebarFooter();
    callbacks.goToPlanTab();

    toast('Plan regenerated with updated settings.');
  });
}
