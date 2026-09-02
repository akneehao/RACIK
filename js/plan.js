// plan.js
// Screen 3 (weekly tray) and Screen 4 (day detail) — the "Meal Plan" tab.
// buildTray() is the single entry point that turns the onboarding
// parameters into state.generatedDays and renders the tray cards.

import { state } from './state.js';
import { recipePool, dayLabels, weekdayOrder, dishArt, mainArtKey, sideArtKey } from './data.js';
import { formatIDR, formatIDRDelta, toast, showScreen, setupStarRating } from './utils.js';

/** Build the ordered list of { key, name } days implied by the current duration settings. */
function planDayList() {
  if (state.selectedDuration === 'custom') {
    const chosen = weekdayOrder.filter((k) => state.customSelectedDays.has(k));
    const list = [];
    for (let w = 1; w <= state.customWeeks; w++) {
      chosen.forEach((k) => {
        const label = state.customWeeks > 1 ? `${dayLabels[k]} (Wk ${w})` : dayLabels[k];
        list.push({ key: `${k}-w${w}`, name: label });
      });
    }
    return list;
  }
  const n = parseInt(state.selectedDuration, 10) || 5;
  return weekdayOrder.slice(0, n).map((k) => ({ key: k, name: dayLabels[k] }));
}

function dayCardHtml(d) {
  return `
    <div class="hover-preview">
      <strong>${d.main}</strong>
      <div>${d.why[0]}</div>
      <div class="nutri-row"><span>Calories</span><span>${d.kcal} kcal</span></div>
      <div class="nutri-row"><span>Protein</span><span>${d.protein} g</span></div>
      <div class="nutri-row"><span>Nutrient adequacy</span><span>${d.adequacy}%</span></div>
    </div>
    <div class="day-top">
      <span class="day-name">${d.name}</span>
      <div class="status-btns">
        <button class="yes" data-key="${d.key}" aria-label="Accept menu for ${d.name}">✓</button>
        <button class="no" data-key="${d.key}" aria-label="Reject menu for ${d.name}">✕</button>
      </div>
    </div>
    <div class="meal-tray">
      <div class="slot-grid">
        <div class="slot slot-veg">
          <span class="slot-eyebrow">Vegetable</span>
          <span class="slot-name">${d.side}</span>
          <div class="slot-foot"><span class="slot-tag">${d.sideRegion}</span><span class="slot-price">${formatIDR(d.slotCost.veg)}</span></div>
        </div>
        <div class="slot slot-main">
          <span class="slot-eyebrow">Main dish</span>
          <span class="slot-name">${d.main}</span>
          <div class="slot-foot"><span class="slot-tag">${d.mainRegion}</span><span class="slot-price">${formatIDR(d.slotCost.main)}</span></div>
        </div>
        <div class="slot slot-fruit">
          <span class="slot-eyebrow">Fruit</span>
          <span class="slot-name">${d.fruit}</span>
          <div class="slot-foot"><span class="slot-tag">${d.fruitRegion}</span><span class="slot-price">${formatIDR(d.slotCost.fruit)}</span></div>
        </div>
        <div class="slot slot-staple">
          <span class="slot-eyebrow">Staple</span>
          <span class="slot-name">${d.staple}</span>
          <div class="slot-foot"><span class="slot-tag">${d.stapleRegion}</span><span class="slot-price">${formatIDR(d.slotCost.staple)}</span></div>
        </div>
        <div class="slot slot-extra ${d.extra ? '' : 'slot-empty'}">
          <span class="slot-eyebrow">Extra</span>
          <span class="slot-name">${d.extra ? d.extra : 'No extra today'}</span>
          ${d.extra ? `<div class="slot-foot"><span></span><span class="slot-price">${formatIDR(d.slotCost.extra)}</span></div>` : ''}
        </div>
      </div>
    </div>
    <div class="day-foot">
      <span class="cost">${formatIDR(d.cost)} total</span>
      ${d.tag ? `<span class="tag">${d.tag}</span>` : '<span></span>'}
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
  const loc = document.getElementById('sumLocation').textContent || 'Bandung, West Java';
  document.getElementById('traySubline').textContent =
    `${loc} · ${state.people} people · ${dayCount} day${dayCount === 1 ? '' : 's'}`;
}

function updateWeekMetrics() {
  const { generatedDays, weeklyBudget, people } = state;
  const totalCost = generatedDays.reduce((sum, d) => sum + d.cost, 0);
  const avgPortion = Math.round(totalCost / generatedDays.length / people);
  const avgAdequacy = Math.round(generatedDays.reduce((s, d) => s + d.adequacy, 0) / generatedDays.length);
  const daysMet = generatedDays.filter((d) => d.adequacy >= 80).length;

  document.getElementById('metricTotalCost').textContent = `Rp ${(totalCost / 1_000_000).toFixed(2)}M`;
  document.getElementById('metricBudgetSub').textContent = `of Rp ${(weeklyBudget / 1_000_000).toFixed(1)}M budget`;
  document.getElementById('metricAvgPortion').textContent = formatIDR(avgPortion);

  const badge = document.getElementById('metricNutritionBadge');
  const sub = document.getElementById('metricNutritionSub');
  if (avgAdequacy >= 80) {
    badge.textContent = '✓ Meets MBG Standard';
    badge.className = 'badge ok';
  } else {
    badge.textContent = '⚠ Below MBG Standard';
    badge.className = 'badge warn';
  }
  sub.textContent = `${daysMet} of ${generatedDays.length} days met`;
}

function bindDayCellEvents(row) {
  row.querySelectorAll('.day-cell').forEach((cell) => {
    const d = state.generatedDays.find((x) => x.key === cell.dataset.key);
    cell.addEventListener('click', (e) => {
      if (e.target.closest('.status-btns')) return;
      showDetail(d);
    });
    cell.addEventListener('keypress', (e) => {
      if (e.key === 'Enter' && !e.target.closest('.status-btns')) showDetail(d);
    });
  });

  row.querySelectorAll('.status-btns .yes').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      state.statusMap[btn.dataset.key] = 'yes';
      refreshStatus();
      document.getElementById('rejectPanel').classList.remove('show');
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

/** Regenerate state.generatedDays from the current onboarding parameters and render the tray. */
export function buildTray() {
  const list = planDayList();
  state.generatedDays = list.map((d, i) => {
    const recipe = recipePool[i % recipePool.length];
    return Object.assign({ key: d.key, name: d.name }, recipe);
  });

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
  updateTraySubline(list.length);
  refreshStatus();
}

// ---- Day detail (Screen 4) ----

function nutritionBarWidth(value, kind) {
  const maxes = { kcal: 400, protein: 30, fat: 25, fiber: 6, iron: 3 };
  const max = maxes[kind] || 100;
  return Math.min(100, Math.round((value / max) * 100));
}

function renderIngredientList(elId, items) {
  document.getElementById(elId).innerHTML = items
    .map(([name, amt]) => `<li><span>${name}</span><span class="amt">${amt}</span></li>`)
    .join('');
}

function renderStepsList(elId, steps) {
  document.getElementById(elId).innerHTML = steps.map((s) => `<li>${s}</li>`).join('');
}

function renderNutritionPanel(elId, n, adequacyOk) {
  const rows = [];
  if (n.kcal !== undefined) rows.push(['Calories', `${n.kcal} kcal`, nutritionBarWidth(n.kcal, 'kcal')]);
  if (n.protein !== undefined) rows.push(['Protein', `${n.protein} g`, nutritionBarWidth(n.protein, 'protein')]);
  if (n.fat !== undefined) rows.push(['Fat', `${n.fat} g`, nutritionBarWidth(n.fat, 'fat')]);
  if (n.fiber !== undefined) rows.push(['Fiber', `${n.fiber} g`, nutritionBarWidth(n.fiber, 'fiber')]);
  if (n.iron !== undefined) rows.push(['Iron', `${n.iron} mg`, nutritionBarWidth(n.iron, 'iron')]);

  const rowsHtml = rows
    .map(
      ([label, val, w]) =>
        `<div class="nutri-item"><span>${label}</span><span style="display:flex;align-items:center;">${val}<span class="bar-track"><span class="bar-fill" style="width:${w}%"></span></span></span></div>`
    )
    .join('');
  const complianceHtml = adequacyOk
    ? `<div class="compliance" style="color:var(--leaf-dark)">✓ Meets MBG nutrition standard</div>`
    : `<div class="compliance" style="color:var(--chili)">⚠ Below MBG nutrition standard</div>`;
  document.getElementById(elId).innerHTML = `<h4>Nutrition per portion</h4>${rowsHtml}${complianceHtml}`;
}

/** Populate and show Screen 4 for a given generated-day object. */
export function showDetail(d) {
  document.getElementById('detailDayName').textContent = d.name;
  document.getElementById('detailCost').textContent = formatIDR(d.cost);
  document.getElementById('whyAdequacy').textContent = `${d.adequacy}%`;

  const perPortionBudget = 9700; // illustrative, matches the Screen 2 estimate
  const perPortionCost = Math.round(d.cost / state.people);
  document.getElementById('whyBudgetDelta').textContent = formatIDRDelta(perPortionBudget - perPortionCost);
  document.getElementById('whyList').innerHTML = d.why.map((w) => `<li>${w}</li>`).join('');

  document.getElementById('mainDishName').textContent = d.main;
  document.getElementById('sideDishName').textContent = d.side;
  document.getElementById('mainDishHero').innerHTML = `<div class="hero-plate">${dishArt[mainArtKey[d.main]] || ''}</div>`;
  document.getElementById('sideDishHero').innerHTML = `<div class="hero-plate">${dishArt[sideArtKey[d.side]] || ''}</div>`;

  renderIngredientList('mainIngredientList', d.mainIngredients);
  renderIngredientList('sideIngredientList', d.sideIngredients);
  renderStepsList('mainStepsList', d.mainSteps);
  renderStepsList('sideStepsList', d.sideSteps);
  renderNutritionPanel('mainNutritionPanel', d.mainNutrition, d.adequacy >= 80);
  renderNutritionPanel('sideNutritionPanel', d.sideNutrition, d.adequacy >= 80);

  showScreen('screen-4');
}

/** Wire up static controls that exist once in the markup (reject reasons, back buttons, rating). */
export function initPlanTab() {
  document.getElementById('reasonChips').addEventListener('click', (e) => {
    const btn = e.target.closest('button');
    if (!btn) return;
    document.querySelectorAll('#reasonChips button').forEach((b) => b.classList.remove('picked'));
    btn.classList.add('picked');

    const dayObj = state.generatedDays.find((d) => d.key === state.activeRejectDay);
    state.rejectionLog.push({ day: dayObj ? dayObj.name : state.activeRejectDay, reason: btn.dataset.reason });

    setTimeout(() => {
      toast(`Thanks for the feedback — Racik will generate an alternative for ${dayObj ? dayObj.name : state.activeRejectDay}.`);
      document.getElementById('rejectPanel').classList.remove('show');
    }, 350);
  });

  setupStarRating('weekStars');

  document.getElementById('backToTray').addEventListener('click', () => showScreen('screen-3'));
  document.getElementById('detailBackBtn').addEventListener('click', () => showScreen('screen-3'));
}
