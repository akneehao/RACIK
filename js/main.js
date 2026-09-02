// main.js
// App entry point. Loaded as a single `<script type="module">` from
// index.html — every other file here is imported, nothing else runs.
//
// Responsibility split:
//   state.js         shared mutable app state
//   utils.js         formatting, toast, screen/tab visibility helpers
//   data.js          static recipe pool + dish SVG illustrations
//   aggregation.js   ingredient aggregation shared by Procurement & Inventory
//   onboarding.js    Screen 1 (location) + Screen 2 (parameters)
//   plan.js          Screen 3 (weekly tray) + Screen 4 (day detail)
//   procurement.js   Procurement tab
//   inventory.js     Stock & Audit tab
//   settings.js      Settings tab
//   shell.js         sidebar shell + tab switching (this file wires it up)

import { initOnboarding } from './onboarding.js';
import { buildTray, initPlanTab } from './plan.js';
import { populateProcurementSelectors, renderProcurement, initProcurementTab } from './procurement.js';
import { populateInventorySelector, renderInventory, initInventoryTab } from './inventory.js';
import { renderSettingsTab, initSettingsTab } from './settings.js';
import { enterAppShell, initShell, updateSidebarFooter, goToTab } from './shell.js';
import { state } from './state.js';

function updatePeopleDisplay() {
  document.getElementById('peopleCount').textContent = state.people;
  document.getElementById('sumPeople').textContent = state.people;
}

const renderers = {
  populateProcurementSelectors,
  renderProcurement,
  populateInventorySelector,
  renderInventory,
  renderSettingsTab,
};

function main() {
  initPlanTab();
  initProcurementTab();
  initInventoryTab();
  initShell(renderers);

  initSettingsTab({
    updatePeopleDisplay,
    buildTray,
    refreshProcurement: () => {
      populateProcurementSelectors();
      renderProcurement();
    },
    refreshInventory: () => {
      populateInventorySelector();
      renderInventory();
    },
    updateSidebarFooter,
    goToPlanTab: () => goToTab('plan'),
  });

  // The onboarding "Generate Meal Plan" button builds the tray, then hands
  // off from the two onboarding screens to the persistent sidebar shell.
  initOnboarding(() => {
    buildTray();
    enterAppShell(renderers);
  });
}

document.addEventListener('DOMContentLoaded', main);
