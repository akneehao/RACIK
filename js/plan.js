// plan.js
// Screen 3 (weekly tray) and Screen 4 (day detail) — the "Meal Plan" tab.
// buildTray() turns the onboarding parameters into one /api/generate call
// per calendar week (so each week's solve sees the previous week's served
// dishes via the backend's menu-history/rotation window), flattens the
// results into state.generatedDays, and renders the tray cards.

import { state } from './state.js';
import { api } from './api.js';
import { slotIcons, slotLabels } from './icons.js';
import { formatIDR, formatIDRDelta, toast, showScreen, setupStarRating } from './utils.js';

// Matches racik.racik.agents.validate_plan()'s meets_akg threshold exactly:
// a day only counts as meeting the standard when every binding nutrient
// reaches its full AKG target, not some partial-credit average.
export const MEETS_AKG_THRESHOLD = 0.999;

const WEEKDAY_ORDER = ['M', 'T1', 'W', 'T2', 'F', 'S1', 'S2'];
const WEEKDAY_NAMES = { M: 'Monday', T1: 'Tuesday', W: 'Wednesday', T2: 'Thursday',
                        F: 'Friday', S1: 'Saturday', S2: 'Sunday' };
// The five real Isi Piringku tray slots, in the visual order the mockup's
// card lays them out (vegetable, main/animal-protein, fruit, staple, then
// the "extra" box repurposed to show the real plant-protein dish).
const CARD_SLOT_ORDER = ['sayur', 'hewani', 'buah', 'staple', 'nabati'];
const CARD_SLOT_CSS = { sayur: 'slot-veg', hewani: 'slot-main', buah: 'slot-fruit',
                        staple: 'slot-staple', nabati: 'slot-extra' };

/** Weeks implied by the current onboarding duration settings, each as the
 * ordered list of weekday keys /api/generate's `days` count should cover. */
function weekPlans() {
  if (state.selectedDuration === 'custom') {
    const chosen = WEEKDAY_ORDER.filter((k) => state.customSelectedDays.has(k));
    const weeks = [];
    for (let w = 1; w <= state.customWeeks; w++) weeks.push({ week: w, dayKeys: chosen });
    return weeks;
  }
  const n = parseInt(state.selectedDuration, 10) || 5;
  return [{ week: 1, dayKeys: WEEKDAY_ORDER.slice(0, n) }];
}

/** Merge one backend day object into a UI-facing view: key/name for
 * rendering, runId/dayIndex for posting reviews and stock edits back. */
function buildDayView(runId, backendDay, dayKey, multiWeek, weekNum) {
  const name = multiWeek ? `${WEEKDAY_NAMES[dayKey]} (Wk ${weekNum})` : WEEKDAY_NAMES[dayKey];
  const key = multiWeek ? `${dayKey}-w${weekNum}` : dayKey;
  return { key, name, runId, dayIndex: backendDay.index, ...backendDay };
}

function slotDish(view, slot) {
  return view.slots ? view.slots[slot] : null;
}

function slotCardHtml(view, slot) {
  const dish = slotDish(view, slot);
  const label = slotLabels[slot];
  if (!dish) {
    return `
      <div class="slot ${CARD_SLOT_CSS[slot]} slot-empty">
        <span class="slot-eyebrow">${label}</span>
        <span class="slot-name">Not planned this day</span>
      </div>`;
  }
  return `
    <div class="slot ${CARD_SLOT_CSS[slot]}">
      <span class="slot-eyebrow">${label}</span>
      <span class="slot-name">${dish.name}</span>
      <div class="slot-foot">
        <span class="slot-tag">${dish.province || 'Nasional'}</span>
        <span class="slot-price">${formatIDR(dish.cost_per_portion_idr)}</span>
      </div>
    </div>`;
}

function dayCardHtml(view) {
  const main = slotDish(view, 'hewani');
  const pct = Math.round((view.adequacy || 0) * 100);
  return `
    <div class="hover-preview">
      <strong>${main ? main.name : view.name}</strong>
      <div class="nutri-row"><span>Calories</span><span>${Math.round(view.nutrients.energy_kcal)} kcal</span></div>
      <div class="nutri-row"><span>Protein</span><span>${view.nutrients.protein_g.toFixed(1)} g</span></div>
      <div class="nutri-row"><span>Nutrient adequacy</span><span>${pct}%</span></div>
    </div>
    <div class="day-top">
      <span class="day-name">${view.name}</span>
      <div class="status-btns">
        <button class="yes" data-key="${view.key}" aria-label="Accept menu for ${view.name}">✓</button>
        <button class="no" data-key="${view.key}" aria-label="Reject menu for ${view.name}">✕</button>
      </div>
    </div>
    <div class="meal-tray">
      <div class="slot-grid">
        ${CARD_SLOT_ORDER.map((slot) => slotCardHtml(view, slot)).join('')}
      </div>
    </div>
    <div class="day-foot">
      <span class="cost">${formatIDR(view.cost_total_idr)} total</span>
      ${pct >= 100 ? '<span class="tag">Meets AKG</span>' : '<span></span>'}
    </div>
  `;
}

function refreshStatus() {
  document.querySelectorAll('.day-cell').forEach((cell) => {
    const key = cell.dataset.key;
    const yBtn = cell.querySelector('.status-btns .yes');
    const nBtn = cell.querySelector('.status-btns .no');
    yBtn.classList.toggle('active', state.statusMap[key] === 'yes');
    nBtn.classList.toggle('active', state.statusMap[key] === 'no');
    cell.classList.toggle('rejected', state.statusMap[key] === 'no');
  });
}

function updateTraySubline(dayCount) {
  const loc = document.getElementById('sumLocation').textContent || state.location || '—';
  document.getElementById('traySubline').textContent =
    `${loc} · ${state.people} people · ${dayCount} day${dayCount === 1 ? '' : 's'}`;
}

function updateWeekMetrics() {
  const { generatedDays, people } = state;
  if (!generatedDays.length) return;
  const totalCost = generatedDays.reduce((sum, d) => sum + d.cost_total_idr, 0);
  const avgPortion = Math.round(totalCost / generatedDays.length / people);
  const daysMet = generatedDays.filter((d) => d.adequacy >= MEETS_AKG_THRESHOLD).length;

  document.getElementById('metricTotalCost').textContent = `Rp ${(totalCost / 1_000_000).toFixed(2)}M`;
  document.getElementById('metricAvgPortion').textContent = formatIDR(avgPortion);
  document.getElementById('metricPortionSub').textContent = `${people.toLocaleString('en-US')} people / day`;
  document.getElementById('metricBudgetSub').textContent =
    `across ${generatedDays.length} day${generatedDays.length === 1 ? '' : 's'}`;

  const badge = document.getElementById('metricNutritionBadge');
  const sub = document.getElementById('metricNutritionSub');
  // "Meets MBG Standard" means every day meets it — see MEETS_AKG_THRESHOLD
  // and the Daily nutrition compliance panel on each day's detail screen for
  // exactly how each day is judged.
  if (daysMet === generatedDays.length) {
    badge.textContent = '✓ Meets MBG Standard';
    badge.className = 'badge ok';
  } else {
    badge.textContent = '⚠ Below MBG Standard';
    badge.className = 'badge warn';
  }
  sub.textContent = `${daysMet} of ${generatedDays.length} days met`;
}

function findView(key) {
  return state.generatedDays.find((d) => d.key === key);
}

function bindDayCellEvents(row) {
  row.querySelectorAll('.day-cell').forEach((cell) => {
    cell.addEventListener('click', (e) => {
      if (e.target.closest('.status-btns')) return;
      const view = findView(cell.dataset.key);
      if (view) showDetail(view);
    });
    cell.addEventListener('keypress', (e) => {
      if (e.key === 'Enter' && !e.target.closest('.status-btns')) {
        const view = findView(cell.dataset.key);
        if (view) showDetail(view);
      }
    });
  });

  row.querySelectorAll('.status-btns .yes').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const view = findView(btn.dataset.key);
      state.statusMap[btn.dataset.key] = 'yes';
      refreshStatus();
      document.getElementById('rejectPanel').classList.remove('show');
      if (view) {
        api.review({ run_id: view.runId, day_index: view.dayIndex, decision: 'accept' })
          .catch((err) => toast(`Couldn't save the review: ${err.message}`));
      }
    });
  });
  row.querySelectorAll('.status-btns .no').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      state.statusMap[btn.dataset.key] = 'no';
      state.activeRejectDay = btn.dataset.key;
      refreshStatus();
      document.getElementById('rejectPanel').classList.add('show');
      document.querySelectorAll('#reasonChips button').forEach((c) => c.classList.remove('picked'));
    });
  });
}

function renderTray() {
  const row = document.getElementById('trayRow');
  row.innerHTML = '';
  state.generatedDays.forEach((d) => {
    const cell = document.createElement('div');
    cell.className = 'day-cell';
    cell.tabIndex = 0;
    cell.dataset.key = d.key;
    cell.innerHTML = dayCardHtml(d);
    row.appendChild(cell);
  });
  bindDayCellEvents(row);
  updateWeekMetrics();
  updateTraySubline(state.generatedDays.length);
  refreshStatus();
}

/** Regenerate state.generatedDays by calling /api/generate once per
 * calendar week (sequential, so each week's solve benefits from the
 * previous week's served-dish history), then render the tray. */
export async function buildTray() {
  const weeks = weekPlans();
  const multiWeek = weeks.length > 1;
  const generatedDays = [];
  const weekRuns = [];

  for (const w of weeks) {
    const body = {
      days: w.dayKeys.length,
      portions: state.people,
      province: state.province,
      budget_mode: state.budgetMode,
      budget_value: state.budgetValue,
      notes: state.notes,
      lang: 'en',
    };
    const result = await api.generate(body);
    weekRuns.push({
      runId: result.run_id, week: w.week, resolved: result.resolved,
      trace: result.trace, procurement: result.plan.procurement,
      complianceMethodology: result.plan.compliance_methodology,
    });
    result.plan.days.forEach((backendDay, i) => {
      const view = buildDayView(result.run_id, backendDay, w.dayKeys[i], multiWeek, w.week);
      view.relaxations = result.plan.relaxations.filter((r) => r.day === backendDay.index);
      view.procurement = result.plan.procurement.by_day[i];
      view.complianceMethodology = result.plan.compliance_methodology;
      generatedDays.push(view);
    });
  }

  state.weeks = weekRuns;
  state.generatedDays = generatedDays;
  renderTray();
}

// ---- Day detail (Screen 4) ----

function formatMass(grams) {
  return grams >= 1000 ? `${(grams / 1000).toFixed(2)} kg` : `${Math.round(grams)} g`;
}

async function renderIngredientList(elId, dish, portions) {
  const el = document.getElementById(elId);
  el.innerHTML = '<li><span>Loading…</span></li>';
  try {
    const detail = await api.dish(dish.dish_id);
    const scale = portions / Math.max(detail.servings_per_recipe || detail.servings || 1, 1);
    el.innerHTML = (detail.ingredients || [])
      .map((ing) => `<li><span>${ing.tkpi_name || ing.name || ing.raw}</span>` +
        `<span class="amt">${formatMass(ing.gross_g * scale)}</span></li>`)
      .join('') || '<li><span>No ingredient data</span></li>';
    return detail;
  } catch (err) {
    el.innerHTML = `<li><span>Couldn't load ingredients (${err.message})</span></li>`;
    return null;
  }
}

function renderStepsList(elId, detail) {
  const el = document.getElementById(elId);
  const steps = detail
    ? (detail.steps || '').split(/(?<=[.!?])\s+/).map((s) => s.trim()).filter(Boolean)
    : [];
  el.innerHTML = steps.length
    ? steps.map((s) => `<li>${s}</li>`).join('')
    : '<li>No preparation notes available for this dish.</li>';
}

// Per-dish panels show this dish's raw contribution only — no bars, no
// pass/fail badge. "Meets the standard" is a whole-day, multi-nutrient
// determination (see renderCompliancePanel below); showing a badge under a
// single dish implied otherwise, which is exactly the kind of unclear claim
// this screen should not make.
function renderNutritionPanel(elId, dish) {
  const n = dish.per_portion || {};
  const rows = [
    ['Calories', `${Math.round(n.energy_kcal || 0)} kcal`],
    ['Protein', `${(n.protein_g || 0).toFixed(1)} g`],
    ['Fat', `${(n.fat_g || 0).toFixed(1)} g`],
    ['Fibre', `${(n.fibre_g || 0).toFixed(1)} g`],
    ['Iron (info only)', `${(n.iron_mg || 0).toFixed(1)} mg`],
  ];
  const rowsHtml = rows.map(([label, val]) =>
    `<div class="nutri-item"><span>${label}</span><span>${val}</span></div>`).join('');
  document.getElementById(elId).innerHTML =
    `<h4>This dish's contribution (per portion)</h4>${rowsHtml}` +
    `<p class="data-card-sub" style="margin-top:10px; margin-bottom:0;">` +
    `See "Daily nutrition compliance" above for whether the full day meets AKG.</p>`;
}

/** The one place a day is actually judged against AKG — every binding
 * (enforced) and advisory (informational-only) nutrient, real target from
 * the resolved AKG stage, and the exact methodology in plain language. */
function complianceRowHtml(row) {
  const pct = Math.min(100, row.pct);
  const barColor = row.pct >= 100 ? 'var(--leaf)' : 'var(--chili)';
  return `
    <div class="nutri-item">
      <span>${row.label_en}${row.verified ? '' : ' (info only)'}</span>
      <span style="display:flex;align-items:center;">${row.value}${row.unit} / ${row.target}${row.unit}
        (${row.pct}%)
        <span class="bar-track"><span class="bar-fill" style="width:${pct}%; background:${barColor};"></span></span>
      </span>
    </div>`;
}

function renderCompliancePanel(view) {
  const rows = view.compliance || [];
  document.getElementById('complianceMethod').textContent = view.complianceMethodology || '';
  document.getElementById('complianceEnforced').innerHTML =
    '<h4>Enforced — must reach 100% or the day is reported as relaxed</h4>' +
    rows.filter((r) => r.binding).map(complianceRowHtml).join('');
  document.getElementById('complianceInfoOnly').innerHTML =
    '<h4>Informational only — computed, shown, never enforced</h4>' +
    rows.filter((r) => !r.binding).map(complianceRowHtml).join('');
}

function buildWhyList(view, resolved) {
  const items = [];
  if (resolved && resolved.province) {
    items.push(`Regional preference: ${resolved.province}.`);
  }
  const protein = (view.compliance || []).find((c) => c.key === 'protein_g');
  if (protein) {
    items.push(`Meets ${protein.pct}% of the day's protein target for this age group.`);
  }
  if (resolved) {
    const delta = (resolved.budget_per_portion_idr || 0) - view.cost_per_portion_idr;
    items.push(`${delta >= 0 ? 'Within' : 'Over'} budget: ${formatIDRDelta(delta)} vs. the per-portion pagu.`);
  }
  const relaxedHere = view.relaxations || [];
  if (relaxedHere.length) {
    const r = relaxedHere[0];
    items.push(`${r.label_en} floor relaxed, short by ${r.shortfall}${r.unit} — see the Validator note in Settings.`);
  }
  return items.length ? items : ['No adjustments were needed for this day.'];
}

/** Populate and show Screen 4 for a given generated-day view object. */
export async function showDetail(view) {
  const week = state.weeks.find((w) => w.runId === view.runId);
  const resolved = week ? week.resolved : null;
  const main = slotDish(view, 'hewani');
  const side = slotDish(view, 'sayur');
  const pct = Math.round((view.adequacy || 0) * 100);

  document.getElementById('detailDayName').textContent = view.name;
  document.getElementById('detailCost').textContent = formatIDR(view.cost_total_idr);
  document.getElementById('whyAdequacy').textContent = `${pct}%`;
  document.getElementById('whyBudgetDelta').textContent = resolved
    ? formatIDRDelta((resolved.budget_per_portion_idr || 0) - view.cost_per_portion_idr)
    : '—';
  document.getElementById('whyList').innerHTML =
    buildWhyList(view, resolved).map((w) => `<li>${w}</li>`).join('');

  renderCompliancePanel(view);

  document.getElementById('mainDishName').textContent = main ? main.name : 'Not planned';
  document.getElementById('sideDishName').textContent = side ? side.name : 'Not planned';
  document.getElementById('mainDishHero').innerHTML =
    `<div class="hero-plate">${slotIcons.hewani}</div>`;
  document.getElementById('sideDishHero').innerHTML =
    `<div class="hero-plate">${slotIcons.sayur}</div>`;

  showScreen('screen-4');   // show immediately; ingredient/step panels fill in as they load

  if (main) {
    const detail = await renderIngredientList('mainIngredientList', main, state.people);
    renderStepsList('mainStepsList', detail);
    renderNutritionPanel('mainNutritionPanel', main);
  }
  if (side) {
    const detail = await renderIngredientList('sideIngredientList', side, state.people);
    renderStepsList('sideStepsList', detail);
    renderNutritionPanel('sideNutritionPanel', side);
  }
}

/** Wire up static controls that exist once in the markup (reject reasons, back buttons, rating). */
export function initPlanTab() {
  document.getElementById('reasonChips').addEventListener('click', async (e) => {
    const btn = e.target.closest('button');
    if (!btn) return;
    document.querySelectorAll('#reasonChips button').forEach((b) => b.classList.remove('picked'));
    btn.classList.add('picked');

    const view = findView(state.activeRejectDay);
    state.rejectionLog.push({ day: view ? view.name : state.activeRejectDay, reason: btn.dataset.reason });
    if (!view) return;

    try {
      const res = await api.review({
        run_id: view.runId, day_index: view.dayIndex, decision: 'reject',
        reason: btn.dataset.reason, replace: true,
      });
      if (res.replacement_day) {
        // replace_day() solves in isolation and doesn't carry the whole
        // plan's relaxation list — clear it rather than show a stale entry.
        Object.assign(view, res.replacement_day, { index: view.dayIndex, relaxations: [] });
        renderTray();
      }
      toast(`Thanks for the feedback — Racik generated an alternative for ${view.name}.`);
    } catch (err) {
      toast(`Couldn't generate an alternative: ${err.message}`);
    } finally {
      document.getElementById('rejectPanel').classList.remove('show');
    }
  });

  setupStarRating('weekStars');

  document.getElementById('backToTray').addEventListener('click', () => showScreen('screen-3'));
  document.getElementById('detailBackBtn').addEventListener('click', () => showScreen('screen-3'));
}
