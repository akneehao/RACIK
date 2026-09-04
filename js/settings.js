// settings.js
// Program parameters recap, the feedback log (real, persisted rejection
// reasons from /api/history — not just this session's in-memory pushes),
// and the export options.

import { state, resetForRegenerate, estimateTotalBudget } from './state.js';
import { api } from './api.js';
import { toast } from './utils.js';
import { exportAuditCsv } from './inventory.js';

function friendlyDayName(run_id, day_index) {
  const match = state.generatedDays.find((d) => d.runId === run_id && d.dayIndex === day_index);
  return match ? match.name : `Run #${run_id} · Day ${day_index + 1}`;
}

/** Populate the read-only/editable parameter fields and the feedback log. */
export async function renderSettingsTab() {
  document.getElementById('setLocation').value = document.getElementById('sumLocation').textContent || '';
  document.getElementById('setPeople').value = state.people;
  document.getElementById('setBudget').value = Math.round(
    estimateTotalBudget(state.generatedDays.length)).toLocaleString('en-US');
  document.getElementById('setDuration').value = document.getElementById('sumDuration').textContent || '';

  const list = document.getElementById('settingsFeedbackList');
  let rejections = [];
  try {
    const history = await api.history();
    rejections = history.rejections.map((r) => ({
      day: friendlyDayName(r.run_id, r.day_index), reason: r.reason,
    }));
  } catch (err) {
    // fall back to this session's optimistic log if the server is unreachable
    rejections = state.rejectionLog;
  }
  if (rejections.length === 0) {
    list.innerHTML = '<p class="empty-note">No rejections recorded yet.</p>';
  } else {
    list.innerHTML = rejections
      .map((r) => `<div class="fb-item"><span class="fb-day">${r.day}</span><span class="fb-reason">${r.reason}</span></div>`)
      .join('');
  }
}

/** Reconstruct a /api/report-shaped body from the first generated week's
 * resolved Agen Gizi / Agen Biaya parameters, so the printable report
 * matches what the operator actually saw on the Plan tab. */
function reportBodyForFirstWeek() {
  const week = state.weeks[0];
  if (!week) return null;
  const days = state.generatedDays.filter((d) => d.runId === week.runId).length;
  return {
    days, stage: week.resolved.stage, portions: state.people,
    province: week.resolved.province, island: week.resolved.island || '',
    budget_per_portion_idr: week.resolved.budget_per_portion_idr,
    ingredient_budget_share: week.resolved.ingredient_budget_share,
    regional_cost_index: week.resolved.regional_cost_index || 1.0,
    exclude_terms: week.resolved.exclude_terms || [],
    enforce_micronutrients: week.resolved.enforce_micronutrients || false,
    sppg_name: '', lang: 'en',
  };
}

async function handleExport(type) {
  if (type === 'csv') {
    await exportAuditCsv();
    toast('Audit CSV downloaded.');
    return;
  }
  if (type === 'pdf') {
    const body = reportBodyForFirstWeek();
    if (!body) { toast('Generate a plan first.'); return; }
    // Open the tab synchronously, in the same gesture as the click — opening
    // it after the `await` below is a same-origin no-op in most browsers,
    // but cross-origin/deployed contexts can treat it as an untrusted popup
    // and silently block it.
    const win = window.open('', '_blank');
    try {
      const html = await api.report(body);
      if (win) {
        win.document.write(html);
        win.document.close();
        toast('Report opened in a new tab — use your browser\'s Print to save as PDF.');
      } else {
        toast('Report generated, but the popup was blocked — allow popups for this site and try again.');
      }
    } catch (err) {
      if (win) win.close();
      toast(`Couldn't build the report: ${err.message}`);
    }
    return;
  }
  // "Save as image" needs a client-side rasteriser (e.g. html2canvas) that
  // this app deliberately doesn't depend on — point the operator at the
  // browser's own screenshot/print tools instead of faking success.
  toast('Use your browser\'s screenshot tool, or export to PDF and print to image.');
}

/**
 * Wire up the Settings tab. `callbacks` lets this module trigger a full
 * re-render of the other tabs after "Regenerate Plan" without importing
 * them directly (keeps the module graph a simple tree, not a web).
 *
 * @param {{
 *   updatePeopleDisplay: () => void,
 *   buildTray: () => Promise<void>,
 *   refreshProcurement: () => void,
 *   refreshInventory: () => void,
 *   updateSidebarFooter: () => void,
 *   goToPlanTab: () => void,
 * }} callbacks
 */
export function initSettingsTab(callbacks) {
  document.querySelectorAll('.export-option').forEach((opt) => {
    opt.addEventListener('click', async () => {
      await handleExport(opt.dataset.type);
      opt.classList.add('done');
    });
  });

  document.getElementById('settingsRegenerate').addEventListener('click', async () => {
    const newPeople = parseInt(document.getElementById('setPeople').value, 10);
    if (newPeople) state.people = newPeople;
    callbacks.updatePeopleDisplay();

    resetForRegenerate();
    try {
      await callbacks.buildTray();
      callbacks.refreshProcurement();
      callbacks.refreshInventory();
      callbacks.updateSidebarFooter();
      callbacks.goToPlanTab();
      toast('Plan regenerated with updated settings.');
    } catch (err) {
      toast(`Couldn't regenerate: ${err.message}`);
    }
  });
}
