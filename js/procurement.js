// procurement.js
// Procurement tab: weekly and daily shopping-list recaps, sourced from the
// procurement breakdown /api/generate already computed against the exact
// solved plan (racik.racik.orchestrator.RacikOrchestrator._procurement_payload)
// — never re-aggregated client-side, so it can't drift from the tray shown
// on the Plan tab.

import { state } from './state.js';
import { formatIDR, downloadCsv } from './utils.js';

function currentWeek() {
  const idx = parseInt(document.getElementById('procWeekSelect').value, 10) || 0;
  return state.weeks[idx];
}

function daysInWeek(weekIndex) {
  const week = state.weeks[weekIndex];
  if (!week) return [];
  return state.generatedDays.filter((d) => d.runId === week.runId);
}

export function populateProcurementSelectors() {
  const weekSel = document.getElementById('procWeekSelect');
  weekSel.innerHTML = state.weeks
    .map((w, i) => `<option value="${i}">Week ${w.week}</option>`)
    .join('');

  const daySel = document.getElementById('procDaySelect');
  const fillDaySelect = () => {
    const weekIdx = parseInt(weekSel.value, 10) || 0;
    daySel.innerHTML = daysInWeek(weekIdx)
      .map((d) => `<option value="${d.key}">${d.name}</option>`)
      .join('');
  };
  fillDaySelect();

  weekSel.onchange = () => { fillDaySelect(); renderProcurement(); };
  daySel.onchange = renderProcurement;
}

function renderTable(tableEl, lines, totalCostIdr) {
  const rows = lines.map((l) => `
    <tr>
      <td>${l.name}${l.matched ? '' : ' <span class="cat-pill" style="background:#F6DCD8;color:var(--chili)">unmatched</span>'}</td>
      <td class="num">${l.gross_kg.toFixed(2)} kg</td>
      <td class="num">${formatIDR(l.cost_idr)}</td>
      <td>${(l.used_in || []).join(', ')}</td>
    </tr>`).join('');
  tableEl.innerHTML = `
    <thead><tr><th>Ingredient</th><th class="num">Weight</th><th class="num">Cost</th><th>Used in</th></tr></thead>
    <tbody>${rows}
      <tr class="total-row"><td>Total</td><td></td><td class="num">${formatIDR(totalCostIdr)}</td><td></td></tr>
    </tbody>`;
}

function csvFor(lines) {
  const header = 'Ingredient,Weight (kg),Cost (IDR),Used in\n';
  const rows = lines.map((l) =>
    `"${l.name}",${l.gross_kg.toFixed(3)},${Math.round(l.cost_idr)},"${(l.used_in || []).join('; ')}"`);
  return { header, rows };
}

export function renderProcurement() {
  if (!state.weeks.length) return;
  const week = currentWeek();
  if (!week || !week.procurement) return;

  const weekDays = daysInWeek(parseInt(document.getElementById('procWeekSelect').value, 10) || 0);
  document.getElementById('procWeekTitle').textContent =
    `Ingredient needs — Week ${week.week} · ${weekDays.length} days × ${state.people} portions`;
  document.getElementById('procWeekSub').textContent =
    `${week.procurement.totals.items} ingredients · ${formatIDR(week.procurement.totals.total_cost_idr)} estimated total`;
  renderTable(document.getElementById('procWeekTable'), week.procurement.lines,
    week.procurement.totals.total_cost_idr);

  document.getElementById('procWeekCsv').onclick = () => {
    const { header, rows } = csvFor(week.procurement.lines);
    downloadCsv(header, rows, `racik-procurement-week${week.week}.csv`);
  };

  const dayKey = document.getElementById('procDaySelect').value;
  const day = state.generatedDays.find((d) => d.key === dayKey) || weekDays[0];
  if (day && day.procurement) {
    document.getElementById('procDayTitle').textContent = `Ingredient needs — ${day.name}`;
    document.getElementById('procDaySub').textContent =
      `${day.procurement.totals.items} ingredients · ${formatIDR(day.procurement.totals.total_cost_idr)} estimated total`;
    renderTable(document.getElementById('procDayTable'), day.procurement.lines,
      day.procurement.totals.total_cost_idr);
    document.getElementById('procDayCsv').onclick = () => {
      const { header, rows } = csvFor(day.procurement.lines);
      downloadCsv(header, rows, `racik-procurement-${day.key}.csv`);
    };
  }
}

export function initProcurementTab() {
  document.querySelectorAll('.subtab').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.subtab').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      document.querySelectorAll('.subtab-panel').forEach((p) => p.classList.remove('active'));
      document.getElementById(`proc-${btn.dataset.subtab}`).classList.add('active');
    });
  });
}
