// procurement.js
// Weekly and daily aggregated shopping lists, with CSV export.
// Mirrors src/routes/procurement.tsx from the original reference app:
// a week selector, a day selector, and two recap tables.

import { state } from './state.js';
import { aggregateIngredients } from './aggregation.js';
import { formatIDR, downloadCsv } from './utils.js';

function renderAggTable(tableEl, lines) {
  const total = lines.reduce((s, l) => s + l.cost, 0);
  tableEl.innerHTML = `
    <thead><tr>
      <th>Ingredient</th><th>Category</th><th>Amount</th><th class="num">Est. cost</th>
    </tr></thead>
    <tbody>
      ${lines
        .map(
          (l) => `
        <tr>
          <td>${l.name}</td>
          <td><span class="cat-pill">${l.category}</span></td>
          <td>${l.amounts.slice(0, 2).join(', ')}${l.amounts.length > 2 ? ` +${l.amounts.length - 2} more` : ''}</td>
          <td class="num">${formatIDR(l.cost)}</td>
        </tr>
      `
        )
        .join('')}
      <tr class="total-row">
        <td colspan="3">Total procurement estimate</td>
        <td class="num">${formatIDR(total)}</td>
      </tr>
    </tbody>
  `;
  return total;
}

function csvLinesFor(lines) {
  const header = 'Ingredient,Category,Amount,Estimated Cost (IDR)\n';
  const body = lines.map((l) =>
    [l.name, l.category, l.amounts.join(' | '), Math.round(l.cost)]
      .map((v) => `"${String(v).replace(/"/g, "'")}"`)
      .join(',')
  );
  return { header, body };
}

/** Refresh the Week / Day <select> option lists from the current generated plan. */
export function populateProcurementSelectors() {
  if (!state.generatedDays.length) return;
  const weekSelect = document.getElementById('procWeekSelect');
  const daySelect = document.getElementById('procDaySelect');

  const weeks = [...new Set(state.generatedDays.map((d) => (d.key.includes('-w') ? d.key.split('-w')[1] : '1')))];
  weekSelect.innerHTML = weeks.map((w) => `<option value="${w}">Week ${w}</option>`).join('');
  daySelect.innerHTML = state.generatedDays.map((d, i) => `<option value="${i}">${d.name}</option>`).join('');

  weekSelect.onchange = renderProcurement;
  daySelect.onchange = renderProcurement;
}

/** Recompute and render both the weekly and daily recap tables. */
export function renderProcurement() {
  if (!state.generatedDays.length) return;
  const weekSelect = document.getElementById('procWeekSelect');
  const daySelect = document.getElementById('procDaySelect');

  const selectedWeek = weekSelect.value || '1';
  const weekDays = state.generatedDays.filter(
    (d) => (d.key.includes('-w') ? d.key.split('-w')[1] : '1') === selectedWeek
  );
  const weekLines = aggregateIngredients(weekDays.length ? weekDays : state.generatedDays);

  document.getElementById('procWeekTitle').textContent =
    `Ingredient needs — Week ${selectedWeek} · ${weekDays.length || state.generatedDays.length} days × ${state.people.toLocaleString('en-US')} portions`;
  const weekTotal = renderAggTable(document.getElementById('procWeekTable'), weekLines);
  document.getElementById('procWeekSub').textContent =
    `${weekLines.length} ingredient types · estimated total ${formatIDR(weekTotal)}`;

  const dayIdx = parseInt(daySelect.value || '0', 10);
  const day = state.generatedDays[dayIdx] || state.generatedDays[0];
  const dayLines = aggregateIngredients([day]);
  document.getElementById('procDayTitle').textContent = `Ingredient needs — ${day.name}`;
  const dayTotal = renderAggTable(document.getElementById('procDayTable'), dayLines);
  document.getElementById('procDaySub').textContent =
    `${dayLines.length} ingredient types · estimated total ${formatIDR(dayTotal)}`;

  document.getElementById('procWeekCsv').onclick = () => {
    const { header, body } = csvLinesFor(weekLines);
    downloadCsv(header, body, `procurement-week-${selectedWeek}.csv`);
  };
  document.getElementById('procDayCsv').onclick = () => {
    const { header, body } = csvLinesFor(dayLines);
    downloadCsv(header, body, `procurement-${day.name.toLowerCase()}.csv`);
  };
}

/** Wire up the weekly/daily recap sub-tab toggle. */
export function initProcurementTab() {
  document.querySelectorAll('.subtab').forEach((btn) => {
    btn.addEventListener('click', () => {
      const sub = btn.dataset.subtab;
      document.querySelectorAll('.subtab').forEach((b) => b.classList.toggle('active', b === btn));
      document.querySelectorAll('.subtab-panel').forEach((p) => p.classList.toggle('active', p.id === `proc-${sub}`));
    });
  });
}
