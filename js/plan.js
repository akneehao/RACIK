// plan.js
// Screen 3 (weekly tray) and Screen 4 (day detail) — the "Meal Plan" tab.
// buildTray() turns the onboarding parameters into one /api/generate call
// per calendar week (so each week's solve sees the previous week's served
// dishes via the backend's menu-history/rotation window), flattens the
// results into state.generatedDays, and renders the tray cards.

import { state, estimateTotalBudget } from './state.js';
import { api } from './api.js';
import { slotLabels } from './icons.js';
import { formatIDR, formatIDRDelta, toast, showScreen, cleanDishName, glossFor, glossProvince } from './utils.js';

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

// Which of state.weeks the tray currently shows — a display cursor, not
// part of the plan data itself, so it lives here rather than in state.js.
// A multi-week custom plan used to have every week's days flattened into
// one long list with no way to page between them, despite the "‹ Week X of
// Y ›" control implying otherwise; it was never actually wired up.
let currentWeekIndex = 0;

/** The generated days belonging to whichever week is currently shown. */
function currentWeekDays() {
  const week = state.weeks[currentWeekIndex];
  if (!week) return [];
  return state.generatedDays.filter((d) => d.runId === week.runId);
}

function updateWeekNav() {
  const total = state.weeks.length;
  const label = document.getElementById('weekNavLabel');
  const prev = document.getElementById('weekNavPrev');
  const next = document.getElementById('weekNavNext');
  if (!label || !prev || !next) return;
  label.textContent = `Week ${total ? currentWeekIndex + 1 : 1} of ${total || 1}`;
  prev.disabled = currentWeekIndex <= 0;
  next.disabled = currentWeekIndex >= total - 1;
}

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
  const gloss = glossFor(dish.name);
  const original = cleanDishName(dish.name);
  return `
    <div class="slot ${CARD_SLOT_CSS[slot]}">
      <span class="slot-eyebrow">${label}</span>
      <span class="slot-name">${gloss}</span>
      ${gloss !== original ? `<span class="slot-name-id">${original}</span>` : ''}
      <div class="slot-foot">
        <span class="slot-tag">${glossProvince(dish.province || 'Nasional')}</span>
        <span class="slot-price">${formatIDR(dish.cost_per_portion_idr)}</span>
      </div>
    </div>`;
}

// Shown right under the day's own ✓/✕ buttons the moment ✕ is clicked — not
// as one shared panel at the bottom of the whole tray, which meant scrolling
// past every other card to reach it. "Just regenerate" (styled neutrally,
// not chili-red like the others) covers an operator who just wants a
// different dish without picking a reason.
const REASON_CHIPS = [
  { reason: 'Too expensive', emoji: '💰' },
  { reason: 'Not common in this area', emoji: '🗺️' },
  { reason: "Nutrition doesn't fit", emoji: '🥦' },
  { reason: "Kids won't like it", emoji: '🙁' },
  { reason: 'Other', emoji: '✏️' },
];

function rejectPanelHtml(view) {
  return `
    <div class="reject-panel">
      <p>Why doesn't this menu work?</p>
      <div class="reason-chips">
        ${REASON_CHIPS.map((r) => `<button data-reason="${r.reason}">${r.emoji} ${r.reason}</button>`).join('')}
        <button class="regen-plain" data-reason="No specific reason">🔄 Just regenerate</button>
      </div>
    </div>`;
}

function dayCardHtml(view) {
  const main = slotDish(view, 'hewani');
  const pct = Math.round((view.adequacy || 0) * 100);
  return `
    <div class="hover-preview">
      <strong>${main ? glossFor(main.name) : view.name}</strong>
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
    ${rejectPanelHtml(view)}
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
  const loc = document.getElementById('sumLocation').textContent || state.location || '-';
  document.getElementById('traySubline').textContent =
    `${loc} · ${state.people} people · ${dayCount} day${dayCount === 1 ? '' : 's'}`;
}

// Days already put through a nutrition-priority re-solve. Asking again with
// the same inputs returns the same tray, so the button stops offering it
// rather than looping the operator through an identical answer.
const attemptedRepair = new Set();

function updateWeekMetrics(days) {
  const { people } = state;
  if (!days.length) return;
  const totalCost = days.reduce((sum, d) => sum + d.cost_total_idr, 0);
  const avgPortion = Math.round(totalCost / days.length / people);
  const daysMet = days.filter((d) => d.adequacy >= MEETS_AKG_THRESHOLD).length;

  // Compare spend against the resolved ingredient budget, not necessarily
  // the raw pagu input — normally the same number (Agen Biaya's
  // ingredient_budget_share defaults to 1.0: the operator's budget input is
  // already scoped to food/ingredients, not an all-inclusive program pagu,
  // so nothing is held back by default), but notes can still ask it to
  // reserve a share for a specific non-ingredient cost. CP-SAT actively
  // closes the gap to whichever ceiling actually applies (never past it —
  // meeting AKG floors still wins if the two conflict). Pulled from the
  // currently-shown week specifically — each week gets its own /api/generate
  // call and can resolve a different budget share.
  const resolved = state.weeks[currentWeekIndex] ? state.weeks[currentWeekIndex].resolved : null;
  const ceilingPerPortion = resolved
    ? Math.round(resolved.budget_per_portion_idr * (resolved.ingredient_budget_share ?? 1))
    : null;
  const totalBudget = estimateTotalBudget(days.length);

  document.getElementById('metricTotalCost').textContent = `Rp ${(totalCost / 1_000_000).toFixed(2)}M`;
  document.getElementById('metricAvgPortion').textContent = formatIDR(avgPortion);
  document.getElementById('metricPortionSub').textContent = ceilingPerPortion
    ? `${people.toLocaleString('en-US')} people/day · vs ${formatIDR(ceilingPerPortion)} ingredient budget`
    : `${people.toLocaleString('en-US')} people / day`;
  document.getElementById('metricBudgetSub').textContent =
    `of ${formatIDR(totalBudget)} budget · across ${days.length} day${days.length === 1 ? '' : 's'}`;

  const badge = document.getElementById('metricNutritionBadge');
  const sub = document.getElementById('metricNutritionSub');
  // "Meets MBG Standard" means every day meets it — see MEETS_AKG_THRESHOLD
  // and the Daily nutrition compliance panel on each day's detail screen for
  // exactly how each day is judged.
  if (daysMet === days.length) {
    badge.textContent = '✓ Meets MBG Standard';
    badge.className = 'badge ok';
  } else {
    badge.textContent = '⚠ Below MBG Standard';
    badge.className = 'badge warn';
  }
  sub.textContent = `${daysMet} of ${days.length} days met`;

  // The offer only exists when there is something to fix: hidden once every
  // day meets the standard, and disabled once every short day has already
  // been through a repair, so it never reads as a permanent "try again".
  const fixBtn = document.getElementById('fixNutritionBtn');
  if (fixBtn) {
    const shortDays = days.filter((d) => d.adequacy < MEETS_AKG_THRESHOLD);
    const untried = shortDays.filter((d) => !attemptedRepair.has(d.key));
    fixBtn.hidden = shortDays.length === 0;
    fixBtn.disabled = untried.length === 0;
    fixBtn.textContent = untried.length === 0
      ? 'Already rebuilt — raise the budget to go further'
      : untried.length === 1
        ? 'Rebuild that day to meet the standard'
        : `Rebuild ${untried.length} short days to meet the standard`;
    if (shortDays.length === 0) document.getElementById('fixNutritionNote').hidden = true;
  }
}

/** Turn nutrient keys into the labels the compliance panel already uses, so
 * the note reads "Carbohydrate" rather than "carb_g". */
function nutrientLabels(view, keys) {
  const rows = view.compliance || [];
  return (keys || [])
    .map((k) => (rows.find((r) => r.key === k) || {}).label_en || k)
    .join(', ');
}

/** Re-solve every day in the visible week that fell short of AKG.
 *
 * A plain regenerate would return the same trays: nothing about the problem
 * changed. The backend instead reverses the objective's priority for these
 * days — normally overspending is penalised above missing a floor, which is
 * why a tight pagu produces a short day in the first place — so what comes
 * back is a genuinely different tray with a genuinely different price.
 *
 * That makes this a cost decision, not a retry, so the note underneath
 * reports the per-portion overspend rather than quietly absorbing it. Days
 * are repaired one at a time because each solve excludes the rest of the
 * week, and a repaired day changes what the next one must avoid.
 */
async function fixShortDays() {
  const btn = document.getElementById('fixNutritionBtn');
  const note = document.getElementById('fixNutritionNote');
  const short = currentWeekDays().filter((d) => d.adequacy < MEETS_AKG_THRESHOLD
                                                && !attemptedRepair.has(d.key));
  if (!short.length) return;

  btn.disabled = true;
  note.hidden = false;
  note.textContent = `Rebuilding ${short.length} day${short.length === 1 ? '' : 's'}…`;

  const fixed = [];
  const stillShort = [];
  let extraPerPortion = 0;

  for (const view of short) {
    const before = view.cost_per_portion_idr;
    attemptedRepair.add(view.key);
    try {
      const day = await api.improveDay({ run_id: view.runId, day_index: view.dayIndex });
      // Same shape as review()'s replacement_day: solved in isolation, so it
      // carries no plan-wide relaxation list of its own.
      Object.assign(view, day, { index: view.dayIndex, relaxations: [] });
      const info = day.improvement || {};
      if (info.meets_standard) fixed.push(view.name);
      else {
        const labels = nutrientLabels(view, info.remaining_shortfalls);
        stillShort.push(labels ? `${view.name} (${labels})`
                               : `${view.name} (just under, nothing materially short)`);
      }
      extraPerPortion += Math.max(0, (day.cost_per_portion_idr || 0) - before);
    } catch (err) {
      stillShort.push(`${view.name} (${err.message})`);
    }
  }

  reaggregateWeekProcurement(state.weeks[currentWeekIndex]);
  renderTray();
  translateVisibleDishNames().then(() => { if (!anyRejectPanelOpen()) renderTray(); });

  const parts = [];
  if (fixed.length) parts.push(`${fixed.join(', ')} now meet${fixed.length === 1 ? 's' : ''} the standard.`);
  if (extraPerPortion > 0) {
    parts.push(`<span class="over">+${formatIDR(Math.round(extraPerPortion / short.length))} per portion</span> on those days.`);
  }
  if (stillShort.length) {
    parts.push(`Still short: ${stillShort.join('; ')}. Open the day to see the size of the gap.`);
  }
  note.innerHTML = parts.join(' ');
  note.hidden = false;
  toast(fixed.length
    ? `Rebuilt ${fixed.length} day${fixed.length === 1 ? '' : 's'} to meet the MBG standard.`
    : "Couldn't reach the standard for those days.");
}

function findView(key) {
  return state.generatedDays.find((d) => d.key === key);
}

function bindDayCellEvents(row) {
  row.querySelectorAll('.day-cell').forEach((cell) => {
    cell.addEventListener('click', (e) => {
      if (e.target.closest('.status-btns') || e.target.closest('.reject-panel')) return;
      const view = findView(cell.dataset.key);
      if (view) showDetail(view);
    });
    cell.addEventListener('keypress', (e) => {
      if (e.key === 'Enter' && !e.target.closest('.status-btns') && !e.target.closest('.reject-panel')) {
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
      btn.closest('.day-cell').querySelector('.reject-panel')?.classList.remove('show');
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
      refreshStatus();
      const panel = btn.closest('.day-cell').querySelector('.reject-panel');
      panel.classList.add('show');
      panel.querySelectorAll('.reason-chips button').forEach((c) => c.classList.remove('picked'));
    });
  });

  row.querySelectorAll('.reason-chips').forEach((chipBox) => {
    chipBox.addEventListener('click', async (e) => {
      e.stopPropagation();
      const btn = e.target.closest('button');
      if (!btn) return;
      const key = chipBox.closest('.day-cell').dataset.key;
      const view = findView(key);
      if (!view) return;

      chipBox.querySelectorAll('button').forEach((b) => b.classList.remove('picked'));
      btn.classList.add('picked');
      state.rejectionLog.push({ day: view.name, reason: btn.dataset.reason });

      try {
        const res = await api.review({
          run_id: view.runId, day_index: view.dayIndex, decision: 'reject',
          reason: btn.dataset.reason, replace: true,
        });
        if (res.replacement_day) {
          // replace_day() solves in isolation and doesn't carry the whole
          // plan's relaxation list — clear it rather than show a stale entry.
          Object.assign(view, res.replacement_day, { index: view.dayIndex, relaxations: [] });
          reaggregateWeekProcurement(state.weeks.find((w) => w.runId === view.runId));
        }
        // A fresh dish is in place now — clear the rejected/red state so the
        // card goes back to normal and the operator can flag the
        // replacement too, if it's still not right, instead of it staying
        // red forever after already being "fixed".
        delete state.statusMap[key];
        renderTray();
        toast(`Thanks for the feedback. Racik generated an alternative for ${view.name}.`);
        if (res.replacement_day) {
          // The replacement's gloss is fetched after the card is already
          // showing its (correct, real) Indonesian name — see buildTray()'s
          // matching comment on why this used to be on the blocking path.
          translateVisibleDishNames().then(() => { if (!anyRejectPanelOpen()) renderTray(); });
        }
      } catch (err) {
        toast(`Couldn't generate an alternative: ${err.message}`);
        chipBox.closest('.reject-panel').classList.remove('show');
      }
    });
  });
}

/** Mean attainment per nutrient across the visible week, as horizontal bars
 * against a 100% AKG reference line.
 *
 * Horizontal because the categories are words ("Carbohydrate", "Vitamin A"),
 * and a bar per nutrient because the job is comparing magnitudes against one
 * shared reference, not showing change over time.
 *
 * Colour alone does NOT carry the met/short distinction here. The app's green
 * (#43A047) and red (#C0392B) separate by only dE 5.8 under deuteranopia --
 * below the usable floor -- so every bar also states its percentage, sits
 * visibly short of or past the 100% line, and carries a marker when it misses.
 * Advisory nutrients are hatched rather than tinted, because "not enforced" is
 * a different kind of fact from "short" and must not read as a third status.
 */
function renderNutritionProfile(days) {
  const chart = document.getElementById('profileChart');
  if (!chart) return;
  const scope = document.getElementById('profileScope');
  const sub = document.getElementById('profileSub');

  if (!days.length || !days[0].compliance) {
    chart.innerHTML = '';
    if (scope) scope.textContent = '';
    return;
  }

  // Average each nutrient over the week. Every day carries the same nutrient
  // keys, so the first day's rows define the order and the labels.
  const rows = days[0].compliance.map((ref) => {
    const pcts = days
      .map((d) => (d.compliance || []).find((c) => c.key === ref.key))
      .filter(Boolean)
      .map((c) => c.pct);
    const mean = pcts.length ? pcts.reduce((a, b) => a + b, 0) / pcts.length : 0;
    const values = days
      .map((d) => (d.compliance || []).find((c) => c.key === ref.key))
      .filter(Boolean);
    const meanValue = values.length
      ? values.reduce((a, c) => a + Number(c.value), 0) / values.length : 0;
    return {
      key: ref.key,
      label: ref.label_en || ref.key,
      unit: ref.unit || '',
      target: ref.target,
      value: Math.round(meanValue * 10) / 10,
      pct: Math.round(mean),
      binding: ref.binding !== false,
    };
  });

  if (scope) {
    scope.textContent = `${days.length} day${days.length === 1 ? '' : 's'}`;
  }
  if (sub) {
    const shortCount = rows.filter((r) => r.binding && r.pct < 100).length;
    sub.textContent = shortCount
      ? `Mean attainment against the AKG target. ${shortCount} enforced nutrient${shortCount === 1 ? '' : 's'} below target.`
      : 'Mean attainment against the AKG target. Every enforced nutrient is met.';
  }

  // Fixed 200% ceiling rather than the data's own maximum. Scaling to the
  // maximum let one outlier set the axis -- vitamin C routinely lands near
  // 400%, which squeezed the four enforced nutrients into the left quarter of
  // the chart where their distance from the target could not be read. For a
  // kitchen, 300% and 400% of a micronutrient are the same fact ("plenty");
  // what carries information is proximity to 100%. Bars past the cap are
  // drawn full width and marked, and every bar states its true figure.
  const CEILING = 200;
  const linePos = (100 / CEILING) * 100;

  // The engine models every nutrient as a floor (akg.py's NUTRIENT_META
  // carries no direction), but sodium is a ceiling -- AKG states it as a
  // maximum. Presenting "251% of target" for it the way 251% protein is
  // presented would tell a kitchen that a salty week is a good week. Flagged
  // here in the view; giving the solver a real ceiling is a larger change.
  const LIMITS = new Set(['sodium_mg']);

  chart.innerHTML = `
    <div class="profile-rows">
      ${rows.map((r) => {
        const isLimit = LIMITS.has(r.key);
        const overLimit = isLimit && r.pct > 100;
        const status = !r.binding ? 'advisory' : r.pct >= 100 ? 'met' : 'short';
        const over = r.pct > CEILING;
        const width = Math.max(1, (Math.min(r.pct, CEILING) / CEILING) * 100);
        const title = `${r.label}: ${r.value}${r.unit} of ${r.target}${r.unit} `
          + `${isLimit ? 'limit' : 'target'} (${r.pct}%)`
          + (overLimit ? ' \u2014 over the recommended maximum' : '');
        return `
          <div class="profile-row" title="${title}">
            <span class="p-label">${r.label}${isLimit ? ' <i class="p-lim">(limit)</i>' : ''}${
              r.binding ? '' : '<i class="p-adv" aria-hidden="true">*</i>'}</span>
            <span class="p-track" style="--line-pos:${linePos}%">
              <span class="p-bar ${status}${over ? ' over' : ''}" style="width:${width}%"></span>
            </span>
            <span class="p-val ${overLimit ? 'over-limit' : status}">${r.pct}%${
              status === 'short' ? ' <b aria-label="below target">\u25BC</b>'
              : overLimit ? ' <b aria-label="over the limit">\u25B2</b>' : ''}</span>
          </div>`;
      }).join('')}
    </div>`;
}

function renderTray() {
  // Clamp in case the plan shrank (e.g. a regenerate with fewer weeks) out
  // from under whichever week was showing.
  if (currentWeekIndex >= state.weeks.length) currentWeekIndex = Math.max(0, state.weeks.length - 1);

  const days = currentWeekDays();
  const row = document.getElementById('trayRow');
  row.innerHTML = '';
  days.forEach((d) => {
    const cell = document.createElement('div');
    cell.className = 'day-cell';
    cell.tabIndex = 0;
    cell.dataset.key = d.key;
    cell.innerHTML = dayCardHtml(d);
    row.appendChild(cell);
  });
  bindDayCellEvents(row);
  updateWeekMetrics(days);
  renderNutritionProfile(days);
  updateTraySubline(days.length);
  updateWeekNav();
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
      // Explicit, not left to Agen Gizi to infer from free text — every plan
      // was otherwise solved against SD's AKG figures whatever level the
      // kitchen actually serves.
      stage: state.stage,
      target_overrides: state.targetOverrides,
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
  currentWeekIndex = 0;
  // These are fresh days, whatever the old ones were called — a stale entry
  // here would grey the repair button out on a plan it never ran against.
  attemptedRepair.clear();
  // Show the tray the moment the solve is back — its numbers (cost,
  // nutrients, the Indonesian dish names themselves) are already final and
  // correct. The English gloss is a nice-to-have on top, fetched via a real
  // LLM call that used to sit in the critical path and make every
  // generate/regenerate feel slower than the actual solve was; now it
  // patches in moments later without the operator staring at a blank
  // loading state for it.
  renderTray();
  translateVisibleDishNames().then(() => { if (!anyRejectPanelOpen()) renderTray(); });
}

/** True while any day card's own reject-reason panel is open — guards a
 * background re-render (e.g. glosses arriving late) from silently closing
 * a panel the operator is actively using. */
function anyRejectPanelOpen() {
  return !!document.querySelector('.reject-panel.show');
}

/** Gloss every dish name in the current plan into English (see glossFor()
 * above), one batched call for the whole tray rather than one per dish.
 * Never blocks the tray on failure — an unreachable translator just means
 * dish names stay Indonesian-only, same as before this existed. */
async function translateVisibleDishNames() {
  const names = new Set();
  for (const day of state.generatedDays) {
    for (const slot of Object.keys(day.slots || {})) {
      const dish = day.slots[slot];
      if (dish) names.add(cleanDishName(dish.name));
    }
  }
  await glossNames([...names]);
}

/** Shared gloss fetch for both dish names and ingredient names — same
 * endpoint, same cache (state.dishGlosses), just a different vocabulary of
 * short Indonesian food terms. Never throws; an unreachable translator just
 * means those names stay Indonesian-only. */
export async function glossNames(names) {
  const missing = names.filter((n) => n && !(n in state.dishGlosses));
  if (!missing.length) return;
  try {
    const res = await api.translateDishNames(missing);
    for (const g of res.glosses) {
      state.dishGlosses[g.name] = g.english;
    }
  } catch (err) {
    console.warn('Could not translate names:', err);
  }
}

// ---- Day detail (Screen 4) ----

function formatMass(grams) {
  return grams >= 1000 ? `${(grams / 1000).toFixed(2)} kg` : `${Math.round(grams)} g`;
}

/** Clicking an ingredient asks the Reviewer agent what can be done about it.
 *
 * This is the "customize the ingredients" gesture, and the honest answer is
 * usually not "here is a replacement": the agent first says whether the
 * ingredient is CORE to the dish (by mass share), because swapping the fish
 * out of a fish dish is not a substitution, it is a different dish. Only when
 * it is peripheral does it offer to drop or replace it — and only from real
 * lookups in the corpus, never an invented name.
 */
function bindIngredientReview(list) {
  list.querySelectorAll('.ing-row').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const li = btn.closest('li');
      li.querySelectorAll('.ing-verdict').forEach((n) => n.remove());
      // A second click closes it, so the list does not fill up with panels.
      if (btn.classList.contains('open')) { btn.classList.remove('open'); return; }
      list.querySelectorAll('.ing-row.open').forEach((b) => b.classList.remove('open'));
      list.querySelectorAll('.ing-verdict').forEach((n) => n.remove());
      btn.classList.add('open');

      const note = document.createElement('div');
      note.className = 'ing-verdict';
      note.textContent = 'Checking…';
      li.appendChild(note);

      try {
        const v = await api.substitute({
          dish_id: Number(btn.dataset.dish),
          ingredient: btn.dataset.ingredient,
          province: state.province,
          lang: 'en',
        });
        const share = v.mass_share != null ? `${Math.round(v.mass_share * 100)}% of the dish by mass` : '';
        const verdict = v.is_core
          ? `<b class="core">Core ingredient</b> — ${share}. Changing it changes what the dish is.`
          : `<b class="flex">Flexible</b> — ${share}.`;
        // Both come back as food records, not names — {code, name, group,
        // energy_kcal, protein_g, fat_g}. Show the protein figure alongside:
        // for a core ingredient that is the number deciding whether the swap
        // holds the tray's animal-protein floor.
        const foodName = (f) => (f && f.name) || '';
        const offer = v.substitute
          ? `<div class="ing-offer">Suggested: <b>${foodName(v.substitute)}</b>` +
            ` <span class="ing-macro">${v.substitute.protein_g}g protein / 100g</span></div>`
          : v.action === 'drop'
            ? '<div class="ing-offer">Can be left out.</div>'
            : '';
        const alts = (v.candidates || []).length > 1
          ? `<div class="ing-alts">Other options: ${
              v.candidates.slice(1, 5).map(foodName).filter(Boolean).join(', ')}</div>`
          : '';
        note.innerHTML = `${verdict}${offer}${alts}` +
          `<div class="ing-reason">${v.reason || ''}</div>` +
          (v.source === 'fallback'
            ? '<div class="ing-reason muted">Rule-based review — no model configured.</div>' : '');
      } catch (err) {
        note.textContent = `Couldn't review that ingredient: ${err.message}`;
      }
    });
  });
}

/** Swap one slot's dish for the next-best candidate, keeping the rest of the
 * day as it is. Deliberately scoped: a full re-solve would rebalance every
 * other slot too, which is not what "I'd rather not serve this" means. */
async function swapSlotDish(slot, view, btn) {
  const week = state.weeks.find((w) => w.runId === view.runId);
  const resolved = week ? week.resolved : null;
  if (!resolved) return;
  const label = btn.textContent;
  btn.disabled = true;
  btn.textContent = 'Finding an alternative…';

  const day_slots = {};
  Object.keys(view.slots || {}).forEach((k) => {
    day_slots[k] = view.slots[k] ? view.slots[k].dish_id : null;
  });

  try {
    const day = await api.swap({
      day_index: view.dayIndex,
      slot,
      day_slots,
      stage: resolved.stage,
      province: resolved.province,
      island: resolved.island || '',
      portions: state.people,
      budget_per_portion_idr: resolved.budget_per_portion_idr,
      ingredient_budget_share: resolved.ingredient_budget_share ?? 1,
      exclude_terms: resolved.exclude_terms || [],
      target_overrides: state.targetOverrides,
      lang: 'en',
    });
    Object.assign(view, day, { index: view.dayIndex, relaxations: [] });
    reaggregateWeekProcurement(week);
    renderTray();
    await showDetail(view);
    toast('Swapped. The rest of the day is unchanged.');
  } catch (err) {
    toast(`Couldn't swap that dish: ${err.message}`);
    btn.disabled = false;
    btn.textContent = label;
  }
}

async function renderIngredientList(elId, dish, portions) {
  const el = document.getElementById(elId);
  el.innerHTML = '<li><span>Loading…</span></li>';
  try {
    const detail = await api.dish(dish.dish_id);
    const scale = portions / Math.max(detail.servings_per_recipe || detail.servings || 1, 1);
    const ingredientNames = (detail.ingredients || [])
      .map((ing) => ing.tkpi_name || ing.name || ing.raw);
    await glossNames(ingredientNames);
    el.innerHTML = (detail.ingredients || [])
      .map((ing) => {
        const original = ing.tkpi_name || ing.name || ing.raw;
        // Display and lookup want DIFFERENT names. The panel shows the
        // canonical TKPI name ("Ikan cakalang, segar"), but /api/substitute
        // matches against the recipe's own wording — handed the TKPI name it
        // answers "does not appear in this dish" and reports 0% mass, which
        // reads as a confident wrong answer rather than a failed lookup.
        const lookup = ing.name || ing.raw || original;
        const gloss = state.dishGlosses[original] || original;
        const sub = gloss !== original ? `<span class="ing-name-id">${original}</span>` : '';
        // The button carries the ORIGINAL corpus name, not the English
        // gloss: /api/substitute matches against the ingredient index, which
        // is Indonesian, so sending the gloss would look up nothing.
        return `<li><button type="button" class="ing-row" data-ingredient="${
          lookup.replace(/"/g, '&quot;')}" data-dish="${dish.dish_id}">` +
          `<span>${gloss}${sub}</span>` +
          `<span class="amt">${formatMass(ing.gross_g * scale)}</span></button></li>`;
      })
      .join('') || '<li><span>No ingredient data</span></li>';
    bindIngredientReview(el);
    return detail;
  } catch (err) {
    el.innerHTML = `<li><span>Couldn't load ingredients (${err.message})</span></li>`;
    return null;
  }
}

function renderStepsList(elId, detail) {
  const el = document.getElementById(elId);
  // The backend already returns clean, numbered instructions — rewritten
  // into professional English by an LLM pass over the (informally-worded,
  // scraped) source recipe, cached per dish. `steps_source` says which path
  // produced them: "llm" (rewritten), "cache" (a prior rewrite), or "rule"
  // (no model configured/reachable — a same-language cleanup only, still
  // shown in the original Indonesian rather than silently mistranslated).
  const steps = (detail && detail.steps) || [];
  el.innerHTML = steps.length
    ? steps.map((s) => `<li>${s}</li>`).join('')
    : '<li>No preparation notes available for this dish.</li>';

  el.parentElement.querySelectorAll(':scope > .steps-note').forEach((n) => n.remove());
  if (detail && detail.steps_source === 'rule') {
    el.insertAdjacentHTML('afterend',
      '<p class="steps-note" style="font-size:12px; color:var(--ink-soft); margin-top:8px;">' +
      'Showing the original recipe notes, lightly cleaned. AI rewrite is unavailable right now.</p>');
  }
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
    ['Iron', `${(n.iron_mg || 0).toFixed(1)} mg`],
  ];
  const rowsHtml = rows.map(([label, val]) =>
    `<div class="nutri-item"><span>${label}</span><span>${val}</span></div>`).join('');
  document.getElementById(elId).innerHTML =
    `<h4>This dish's contribution (per portion)</h4>${rowsHtml}` +
    `<p class="data-card-sub" style="margin-top:10px; margin-bottom:0;">` +
    `See "Daily nutrition compliance" above for whether the full day meets AKG.</p>`;
}

/** The one place a day is actually judged against AKG — every nutrient's
 * real target from the resolved AKG stage, shown as one plain composition
 * list rather than split into separately-labelled "enforced" vs
 * "informational" sections; the methodology note above already explains
 * that distinction once, in prose, for anyone who wants it. */
function complianceRowHtml(row) {
  const pct = Math.min(100, row.pct);
  // A brighter green than the app's usual --leaf here specifically: --leaf
  // is dark/muted enough that on a thin 6px bar against the warm cream
  // background it read as brownish rather than clearly "on target".
  const barColor = row.pct >= 100 ? 'var(--leaf-bright)' : 'var(--chili)';
  return `
    <div class="nutri-item">
      <span>${row.label_en}</span>
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
    '<h4>Nutrition composition</h4>' + rows.map(complianceRowHtml).join('');
  document.getElementById('complianceInfoOnly').innerHTML = '';
}

function buildWhyList(view, resolved) {
  const items = [];
  if (resolved && resolved.province) {
    items.push(`Regional preference: ${glossProvince(resolved.province)}.`);
  }
  const protein = (view.compliance || []).find((c) => c.key === 'protein_g');
  if (protein) {
    items.push(`Meets ${protein.pct}% of the day's protein target for this age group.`);
  }
  if (resolved) {
    // pagu x ingredient_budget_share — usually equal to the raw pagu (see
    // updateWeekMetrics() in this file), but respects a lower share if Agen
    // Biaya reserved one for a specific non-ingredient cost the notes named.
    const ingredientBudget = (resolved.budget_per_portion_idr || 0)
      * (resolved.ingredient_budget_share ?? 1);
    const delta = ingredientBudget - view.cost_per_portion_idr;
    items.push(`${delta >= 0 ? 'Within' : 'Over'} the ${formatIDR(ingredientBudget)} ingredient budget: ${formatIDRDelta(delta)}.`);
  }
  const relaxedHere = view.relaxations || [];
  if (relaxedHere.length) {
    const r = relaxedHere[0];
    items.push(`${r.label_en} floor relaxed, short by ${r.shortfall}${r.unit}: see nutrition composition below.`);
  }
  return items.length ? items : ['No adjustments were needed for this day.'];
}

// Ratings this browser has submitted, keyed dish_id -> stars. The backend
// deliberately exposes no GET for a dish's mean score, so a fresh page load
// can only show what was rated in this session — enough to confirm a click
// registered, which is all this widget is for.
const submittedRatings = {};

/** Render the 1-5 star widget for one dish into `containerId`, and post any
 * click to /api/rate.
 *
 * This is the operator half of the repetition loop. A rating is scoped to
 * the province and age stage the plan was solved for, because history.py
 * keys its recency weights the same way — an unscoped rating would quietly
 * push a dish out of another region's rotation. Without a resolved scope
 * there is nothing coherent to attach the score to, so the widget stays
 * hidden rather than posting a rating that lands in the wrong bucket.
 */
function renderDishRating(containerId, dish, resolved) {
  const el = document.getElementById(containerId);
  if (!el) return;
  if (!dish || !resolved) { el.innerHTML = ''; return; }

  const current = submittedRatings[dish.dish_id] || 0;
  el.innerHTML =
    [1, 2, 3, 4, 5].map((n) =>
      `<button type="button" class="star-btn${n <= current ? ' filled' : ''}" data-n="${n}"
         aria-label="Rate ${n} of 5">★</button>`).join('') +
    `<span class="rate-status">${current ? `Rated ${current}/5 — affects future rotation` : 'Rate this dish'}</span>`;

  const status = el.querySelector('.rate-status');
  el.querySelectorAll('.star-btn').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const n = Number(btn.dataset.n);
      // Paint first: the score is advisory, so a slow network shouldn't make
      // the widget feel broken. Only a real failure repaints it back.
      submittedRatings[dish.dish_id] = n;
      el.querySelectorAll('.star-btn').forEach((b) => b.classList.toggle('filled', Number(b.dataset.n) <= n));
      status.classList.remove('failed');
      status.textContent = 'Saving…';
      try {
        await api.rate({
          dish_id: dish.dish_id,
          rating: n,
          province: resolved.province || '',
          stage: resolved.stage || 'sd',
        });
        status.textContent = `Rated ${n}/5 — affects future rotation`;
      } catch (err) {
        delete submittedRatings[dish.dish_id];
        el.querySelectorAll('.star-btn').forEach((b) => b.classList.remove('filled'));
        status.classList.add('failed');
        status.textContent = "Couldn't save that rating.";
      }
    });
  });
}

/** Populate and show Screen 4 for a given generated-day view object. */
export async function showDetail(view) {
  const week = state.weeks.find((w) => w.runId === view.runId);
  const resolved = week ? week.resolved : null;
  const main = slotDish(view, 'hewani');
  const side = slotDish(view, 'sayur');
  const pct = Math.round((view.adequacy || 0) * 100);

  document.getElementById('detailDayName').textContent = view.name;
  document.getElementById('detailPortions').textContent = state.people;
  document.getElementById('detailCost').textContent = formatIDR(view.cost_total_idr);
  document.getElementById('whyAdequacy').textContent = `${pct}%`;
  document.getElementById('whyBudgetDelta').textContent = resolved
    ? formatIDRDelta((resolved.budget_per_portion_idr || 0)
        * (resolved.ingredient_budget_share ?? 1) - view.cost_per_portion_idr)
    : '-';
  document.getElementById('whyList').innerHTML =
    buildWhyList(view, resolved).map((w) => `<li>${w}</li>`).join('');

  renderCompliancePanel(view);

  document.getElementById('mainDishName').textContent = main ? glossFor(main.name) : 'Not planned';
  document.getElementById('mainDishNameId').textContent =
    main && glossFor(main.name) !== cleanDishName(main.name) ? cleanDishName(main.name) : '';
  document.getElementById('sideDishName').textContent = side ? glossFor(side.name) : 'Not planned';
  document.getElementById('sideDishNameId').textContent =
    side && glossFor(side.name) !== cleanDishName(side.name) ? cleanDishName(side.name) : '';

  renderDishRating('mainDishRating', main, resolved);
  renderDishRating('sideDishRating', side, resolved);

  [['mainDishSwap', 'hewani', main], ['sideDishSwap', 'sayur', side]].forEach(
    ([id, slot, dish]) => {
      const btn = document.getElementById(id);
      if (!btn) return;
      btn.hidden = !dish;
      btn.disabled = false;
      btn.textContent = 'Swap this dish';
      btn.onclick = () => swapSlotDish(slot, view, btn);
    });

  showScreen('screen-4');   // show immediately; ingredient/step panels fill in as they load

  // Each side does its own /api/dish fetch plus an ingredient-gloss and a
  // recipe-steps rewrite (SEA-LION, slow when the dish isn't cached yet) —
  // run both sides at once rather than making the side dish wait out the
  // main dish's translation first. Independent panels, so a slow/failed
  // side never blocks the other.
  await Promise.all([
    main
      ? renderIngredientList('mainIngredientList', main, state.people).then((detail) => {
          renderStepsList('mainStepsList', detail);
          renderNutritionPanel('mainNutritionPanel', main);
        })
      : null,
    side
      ? renderIngredientList('sideIngredientList', side, state.people).then((detail) => {
          renderStepsList('sideStepsList', detail);
          renderNutritionPanel('sideNutritionPanel', side);
        })
      : null,
  ]);
}

/** After replace_day() swaps one day in isolation, state.weeks[i].procurement
 * (the Procurement tab's weekly recap) still reflects the original solve for
 * every day, so it silently drifts from the tray actually shown. The backend
 * can't recompute a fresh week-level aggregate itself — replace_day() only
 * ever re-solves the one rejected day, not the whole week — so this mirrors
 * racik.racik.procurement.aggregate()'s grouping (by ingredient key, summing
 * mass/cost, merging which dishes use it) from the now-current per-day
 * procurement objects already sitting in state.generatedDays. */
function reaggregateWeekProcurement(week) {
  if (!week) return;
  const days = state.generatedDays.filter((d) => d.runId === week.runId);
  const byKey = new Map();
  for (const day of days) {
    if (!day.procurement) continue;
    for (const line of day.procurement.lines) {
      const existing = byKey.get(line.key);
      if (existing) {
        existing.gross_kg += line.gross_kg;
        existing.gross_g += line.gross_g;
        existing.cost_idr += line.cost_idr;
        existing.used_in = [...new Set([...existing.used_in, ...line.used_in])];
      } else {
        byKey.set(line.key, { ...line, used_in: [...line.used_in] });
      }
    }
  }
  const lines = [...byKey.values()].sort((a, b) => b.cost_idr - a.cost_idr);
  week.procurement = {
    totals: {
      items: lines.length,
      total_cost_idr: lines.reduce((sum, l) => sum + l.cost_idr, 0),
      total_mass_kg: Math.round(lines.reduce((sum, l) => sum + l.gross_kg, 0) * 100) / 100,
      unmatched_items: lines.filter((l) => !l.matched).length,
    },
    lines,
    by_day: days.map((d) => d.procurement),
  };
}

// Fixed 3-column width for the export capture — wide enough for 3 of the
// day cards' natural 340px-minimum width plus their gaps, so the grid
// below can force exactly 3 columns without squeezing each card's own
// internal slot-grid layout narrower than it wants to be.
const EXPORT_TRAY_WIDTH = 1080;

/** Rasterise just the day-by-day meal trays (#trayRow), not the surrounding
 * header, cost/nutrition metrics, star rating, or export card, for the
 * PDF/image export buttons at the bottom of this same screen. Forces a
 * fixed 3-column grid regardless of however many columns the live,
 * width-responsive page happens to be using, so N days lay out the same
 * way every time (5 days as Mon-Tue-Wed / Thu-Fri, for instance) rather
 * than whatever wrap the on-screen viewport width produces. If a
 * day-detail view happens to be open instead, or somehow this fires from
 * another tab, html2canvas can't rasterise a display:none subtree, so this
 * briefly forces screen-3 visible, captures, then restores whatever was
 * showing. Shared by both the PNG and PDF exports. */
async function captureMenuPlan() {
  if (!state.weeks.length) throw new Error('Generate a plan first.');

  const target = document.getElementById('trayRow');
  const screen3 = document.getElementById('screen-3');
  const planNav = document.querySelector('.nav-item[data-tab="plan"]');
  const previousNav = document.querySelector('.nav-item.active');
  const wasOnPlanTab = previousNav === planNav;
  const wasShowingDayDetail = document.getElementById('screen-4')?.classList.contains('active');

  if (!wasOnPlanTab) planNav?.click();
  if (wasShowingDayDetail) {
    document.querySelectorAll('.screen').forEach((s) => s.classList.remove('active'));
    screen3.classList.add('active');
  }

  // A visible white margin around the cards in the exported file itself,
  // not just wherever the PDF happens to place the image on its page — a
  // capture cropped exactly to the grid's own edges left every card
  // touching the border with no breathing room.
  const EXPORT_PADDING = 32;
  const prevWidth = target.style.width;
  const prevMaxWidth = target.style.maxWidth;
  const prevGrid = target.style.gridTemplateColumns;
  const prevPadding = target.style.padding;
  const prevBoxSizing = target.style.boxSizing;
  const prevBackground = target.style.background;
  // content-box (the CSS default) so the padding added below sits outside
  // this width, keeping the grid's own 3 columns exactly EXPORT_TRAY_WIDTH
  // wide rather than shrinking to make room for it.
  target.style.boxSizing = 'content-box';
  target.style.width = `${EXPORT_TRAY_WIDTH}px`;
  target.style.maxWidth = 'none';
  target.style.gridTemplateColumns = 'repeat(3, 1fr)';
  target.style.padding = `${EXPORT_PADDING}px`;
  target.style.background = '#ffffff';

  // Let the browser actually paint the now-visible, now-widened layout
  // before capturing: html2canvas reads computed layout, so a capture
  // issued in the same tick as these changes can race the reflow and grab
  // stale (zero-size, or pre-widen) boxes.
  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));

  try {
    // No explicit width/windowWidth: passing them made html2canvas
    // recompute layout against a virtual viewport that didn't quite match
    // the element's own forced width above, clipping off the right/bottom
    // padding. Letting it auto-size from the element's own (now-forced)
    // scrollWidth/scrollHeight captures exactly the padded box.
    return await window.html2canvas(target, {
      backgroundColor: '#ffffff',
      scale: 2,
      // A day's own reject-reason panel, if left open, is an operator
      // control, not part of the plan being exported.
      ignoreElements: (el) => el.classList?.contains('reject-panel'),
    });
  } finally {
    target.style.width = prevWidth;
    target.style.maxWidth = prevMaxWidth;
    target.style.gridTemplateColumns = prevGrid;
    target.style.padding = prevPadding;
    target.style.boxSizing = prevBoxSizing;
    target.style.background = prevBackground;
    if (wasShowingDayDetail) {
      screen3.classList.remove('active');
      document.getElementById('screen-4').classList.add('active');
    }
    if (!wasOnPlanTab) previousNav?.click();
  }
}

/** Render the menu plan to a PNG and download it. */
async function exportAsImage() {
  try {
    const canvas = await captureMenuPlan();
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/png'));
    if (!blob) throw new Error('Could not render image');
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'racik-meal-plan.png';
    a.click();
    URL.revokeObjectURL(url);
    toast('Meal plan image downloaded.');
    return true;
  } catch (err) {
    toast(`Couldn't save image: ${err.message}`);
    return false;
  }
}

/** Render the menu plan and lay it into a downloaded PDF, scaled to fit
 * entirely on one landscape A4 page rather than tiling across several — the
 * 3-then-2 day grid from captureMenuPlan() is meant to be read as one wide
 * sheet, not flipped through, and landscape is the natural fit for a grid
 * that's wider than it is tall. Deliberately not window.open()+print():
 * that path depends on popups being allowed, which even a genuine click
 * can't guarantee (confirmed blocked in at least one real environment); a
 * direct file download has no such dependency. */
async function exportAsPdf() {
  try {
    const canvas = await captureMenuPlan();
    const { jsPDF } = window.jspdf;
    const pdf = new jsPDF({ unit: 'mm', format: 'a4', orientation: 'landscape' });
    const pageWidth = pdf.internal.pageSize.getWidth();
    const pageHeight = pdf.internal.pageSize.getHeight();
    const margin = 8;
    const usableWidth = pageWidth - margin * 2;
    const usableHeight = pageHeight - margin * 2;

    const scale = Math.min(usableWidth / canvas.width, usableHeight / canvas.height);
    const imgWidth = canvas.width * scale;
    const imgHeight = canvas.height * scale;
    const x = (pageWidth - imgWidth) / 2;
    const y = (pageHeight - imgHeight) / 2;

    const imgData = canvas.toDataURL('image/png');
    pdf.addImage(imgData, 'PNG', x, y, imgWidth, imgHeight);

    pdf.save('racik-meal-plan.pdf');
    toast('Meal plan PDF downloaded.');
    return true;
  } catch (err) {
    toast(`Couldn't save PDF: ${err.message}`);
    return false;
  }
}

/** Returns whether the export actually produced something. The caller only
 * marks the card "done" (a checkmark, styled as success) when this is true,
 * so a not-really-implemented option never shows the same visual state as a
 * real export. */
async function handleExport(type) {
  if (typeof window.html2canvas !== 'function') {
    toast("Export isn't available right now, try again in a moment.");
    return false;
  }
  if (type === 'pdf') {
    if (typeof window.jspdf === 'undefined') {
      toast("PDF export isn't available right now, try again in a moment.");
      return false;
    }
    return exportAsPdf();
  }
  if (type === 'image') return exportAsImage();
  return false;
}

/** Wire up static controls that exist once in the markup (back buttons,
 * week pagination, the PDF/image export card). Each day card's own reject
 * panel and reason chips are bound in bindDayCellEvents() instead, since
 * they're rebuilt with the tray. */
export function initPlanTab() {
  document.getElementById('backToTray').addEventListener('click', () => showScreen('screen-3'));
  document.getElementById('detailBackBtn').addEventListener('click', () => showScreen('screen-3'));

  document.getElementById('fixNutritionBtn').addEventListener('click', fixShortDays);

  document.getElementById('weekNavPrev').addEventListener('click', () => {
    if (currentWeekIndex <= 0) return;
    currentWeekIndex -= 1;
    renderTray();
  });
  document.getElementById('weekNavNext').addEventListener('click', () => {
    if (currentWeekIndex >= state.weeks.length - 1) return;
    currentWeekIndex += 1;
    renderTray();
  });

  document.querySelectorAll('.export-option').forEach((opt) => {
    opt.addEventListener('click', async () => {
      const succeeded = await handleExport(opt.dataset.type);
      opt.classList.toggle('done', succeeded);
    });
  });
}
