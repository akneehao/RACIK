// inventory.js
// Stock & Audit tab: budget vs. planned vs. actual, a per-day bar chart,
// nutrition compliance tracking, and an editable per-ingredient stock table.
// Records are keyed per ingredient-per-day (`${dayKey}::${ingredientName}`)
// so each ingredient can have its own received/used/actual-cost figures —
// mirrors the InventoryRecord shape from the original reference app.

import { state } from './state.js';
import { aggregateIngredients } from './aggregation.js';
import { formatIDR, formatIDRDelta, downloadCsv } from './utils.js';

function ensureInventoryDefaults(day) {
  const lines = aggregateIngredients([day]);
  lines.forEach((l) => {
    const key = `${day.key}::${l.name}`;
    if (!state.inventoryRecords[key]) {
      const variance = 0.92 + Math.random() * 0.18; // illustrative received/actual variance
      state.inventoryRecords[key] = {
        planned: l.cost,
        received: 100,
        used: Math.round(88 + Math.random() * 10),
        actualCost: Math.round(l.cost * variance),
        note: '',
      };
    }
  });
  return lines;
}

function dayActualCost(day) {
  const lines = aggregateIngredients([day]);
  return lines.reduce((s, l) => {
    const rec = state.inventoryRecords[`${day.key}::${l.name}`];
    return s + (rec ? rec.actualCost : l.cost);
  }, 0);
}

function renderStatCards(dayPlanned, plannedTotal, actualTotal) {
  const variance = actualTotal - plannedTotal;

  document.getElementById('invBudget').textContent = formatIDR(state.weeklyBudget);
  document.getElementById('invPlanned').textContent = formatIDR(plannedTotal);
  document.getElementById('invActual').textContent = formatIDR(actualTotal);
  document.getElementById('invActualPct').textContent = `${Math.round((actualTotal / Math.max(1, plannedTotal)) * 100)}% of plan`;

  const varEl = document.getElementById('invVariance');
  varEl.textContent = formatIDRDelta(variance);
  varEl.className = `stat-value ${variance <= 0 ? 'tone-good' : 'tone-bad'}`;
  document.getElementById('invVarianceHint').textContent =
    variance <= 0 ? 'Under plan — savings' : 'Over plan — needs explanation';
}

function renderBarChart(dayPlanned, dayActuals) {
  const maxVal = Math.max(...state.generatedDays.map((d, i) => Math.max(dayPlanned[i], dayActuals[i])), 1);

  const legend = document.createElement('div');
  legend.className = 'chart-legend';
  legend.innerHTML = `<span><i class="dot plan"></i>Planned</span><span><i class="dot actual"></i>Actual</span>`;

  const groups = document.createElement('div');
  groups.style.display = 'flex';
  groups.style.alignItems = 'flex-end';
  groups.style.gap = '10px';
  groups.style.height = '190px';

  state.generatedDays.forEach((d, i) => {
    const planH = Math.round((dayPlanned[i] / maxVal) * 140);
    const actH = Math.round((dayActuals[i] / maxVal) * 140);
    const group = document.createElement('div');
    group.className = 'bar-group';
    group.innerHTML = `
      <div class="bars">
        <div class="bar plan" style="height:${planH}px" title="Planned ${formatIDR(dayPlanned[i])}"></div>
        <div class="bar actual" style="height:${actH}px" title="Actual ${formatIDR(dayActuals[i])}"></div>
      </div>
      <span class="bar-label">${d.name.slice(0, 3)}</span>
    `;
    groups.appendChild(group);
  });

  const chartEl = document.getElementById('invChart');
  chartEl.innerHTML = '';
  chartEl.appendChild(legend);
  chartEl.appendChild(groups);
}

function renderComplianceCard(selectedDay) {
  const compliant = state.generatedDays.filter((d) => d.adequacy >= 80).length;
  document.getElementById('invComplianceSub').textContent =
    `${compliant} of ${state.generatedDays.length} days meet all AKG nutrition criteria.`;
  document.getElementById('invComplianceBar').style.width =
    `${Math.round((compliant / state.generatedDays.length) * 100)}%`;

  document.getElementById('invNutritionMini').innerHTML = `
    <div class="nutri-item"><span>Calories</span><span>${selectedDay.kcal} kcal</span></div>
    <div class="nutri-item"><span>Protein</span><span>${selectedDay.protein} g</span></div>
    <div class="nutri-item"><span>Fat</span><span>${selectedDay.fat} g</span></div>
    <div class="nutri-item"><span>Nutrient adequacy</span><span>${selectedDay.adequacy}%</span></div>
  `;
}

function renderStockTable(day) {
  const table = document.getElementById('invTable');
  table.innerHTML = `
    <thead><tr>
      <th>Ingredient</th><th>Received %</th><th>Used %</th><th>Remaining</th>
      <th class="num">Planned cost</th><th class="num">Actual cost</th><th>Note</th>
    </tr></thead>
    <tbody id="invTableBody"></tbody>
  `;

  const lines = aggregateIngredients([day]);
  const body = document.getElementById('invTableBody');
  body.innerHTML = lines
    .map((l) => {
      const key = `${day.key}::${l.name}`;
      const rec = state.inventoryRecords[key];
      const remaining = (rec.received - rec.used).toFixed(1);
      const isBad = parseFloat(remaining) < 0;
      const diff = rec.actualCost - rec.planned;
      const diffClass = diff > 0 ? 'bad' : 'good';
      const diffLabel = diff === 0 ? 'on plan' : formatIDRDelta(diff);
      return `
        <tr data-key="${key}">
          <td><b>${l.name}</b><br><span style="font-size:11px;color:var(--ink-soft)">${l.category} · ${l.amounts[0] || '—'}</span></td>
          <td><input type="number" class="inv-received" data-key="${key}" value="${rec.received}" min="0" max="200"> %</td>
          <td><input type="number" class="inv-used" data-key="${key}" value="${rec.used}" min="0" max="200"> %</td>
          <td class="${isBad ? 'remaining-bad' : ''}">${remaining}%</td>
          <td class="num">${formatIDR(rec.planned)}</td>
          <td class="num">
            <input type="number" class="inv-actual-cost wide" data-key="${key}" value="${rec.actualCost}" step="1000">
            <span class="variance-note ${diffClass}">${diffLabel}</span>
          </td>
          <td><input type="text" class="inv-note wide" data-key="${key}" placeholder="Receipt / supplier / variance reason" value="${rec.note}"></td>
        </tr>
      `;
    })
    .join('');

  body.querySelectorAll('.inv-received').forEach((inp) => {
    inp.addEventListener('input', () => {
      state.inventoryRecords[inp.dataset.key].received = parseFloat(inp.value) || 0;
      renderInventory();
    });
  });
  body.querySelectorAll('.inv-used').forEach((inp) => {
    inp.addEventListener('input', () => {
      state.inventoryRecords[inp.dataset.key].used = parseFloat(inp.value) || 0;
      renderInventory();
    });
  });
  body.querySelectorAll('.inv-actual-cost').forEach((inp) => {
    inp.addEventListener('change', () => {
      state.inventoryRecords[inp.dataset.key].actualCost = parseFloat(inp.value) || 0;
      renderInventory();
    });
  });
  body.querySelectorAll('.inv-note').forEach((inp) => {
    inp.addEventListener('input', () => {
      state.inventoryRecords[inp.dataset.key].note = inp.value;
    });
  });
}

/** Refresh the day <select> options from the current generated plan. */
export function populateInventorySelector() {
  if (!state.generatedDays.length) return;
  const sel = document.getElementById('invDaySelect');
  sel.innerHTML = state.generatedDays.map((d, i) => `<option value="${i}">${d.name}</option>`).join('');
  sel.onchange = renderInventory;
}

/** Recompute and render every part of the Inventory & Audit tab. */
export function renderInventory() {
  if (!state.generatedDays.length) return;
  state.generatedDays.forEach((d) => ensureInventoryDefaults(d));

  const dayPlanned = state.generatedDays.map((d) => aggregateIngredients([d]).reduce((s, l) => s + l.cost, 0));
  const plannedTotal = dayPlanned.reduce((s, v) => s + v, 0);
  const dayActuals = state.generatedDays.map((d) => dayActualCost(d));
  const actualTotal = dayActuals.reduce((s, v) => s + v, 0);

  renderStatCards(dayPlanned, plannedTotal, actualTotal);
  renderBarChart(dayPlanned, dayActuals);

  const daySel = document.getElementById('invDaySelect');
  const dayIdx = parseInt(daySel.value || '0', 10);
  const day = state.generatedDays[dayIdx] || state.generatedDays[0];

  renderComplianceCard(day);
  renderStockTable(day);
}

/** Wire up the "Export audit CSV" button (exports every ingredient, every day). */
export function initInventoryTab() {
  document.getElementById('invExportBtn').addEventListener('click', () => {
    const header = 'Date,Ingredient,Planned Cost,Actual Cost,Received %,Used %,Note\n';
    const rows = [];
    state.generatedDays.forEach((d) => {
      const lines = aggregateIngredients([d]);
      lines.forEach((l) => {
        const rec = state.inventoryRecords[`${d.key}::${l.name}`];
        if (!rec) return;
        rows.push(
          [d.name, l.name, Math.round(rec.planned), rec.actualCost, rec.received, rec.used, rec.note]
            .map((v) => `"${String(v).replace(/"/g, "'")}"`)
            .join(',')
        );
      });
    });
    downloadCsv(header, rows, 'racik-audit-stock.csv');
  });
}
