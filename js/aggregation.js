// aggregation.js
// Shared ingredient-aggregation logic used by both the Procurement tab
// (shopping lists) and the Inventory tab (stock/audit records). Mirrors
// the aggregateIngredients() helper from the original TanStack source app.

import { state } from './state.js';

/**
 * Combine main-dish, side-dish, staple, and fruit line items across the
 * given day objects into one ingredient-per-row shopping list, each with
 * every amount seen and a summed illustrative cost.
 */
export function aggregateIngredients(days) {
  const map = {};

  days.forEach((d) => {
    const allIng = [
      ...d.mainIngredients.map(([name, amt]) => ({ name, amt, category: 'Main dish', costShare: d.slotCost.main })),
      ...d.sideIngredients.map(([name, amt]) => ({ name, amt, category: 'Vegetable', costShare: d.slotCost.veg })),
    ];
    allIng.forEach((item) => {
      const key = item.name;
      if (!map[key]) map[key] = { name: item.name, category: item.category, amounts: [], cost: 0 };
      map[key].amounts.push(item.amt);
      map[key].cost += item.costShare / allIng.length; // even split as a simple illustrative allocation
    });

    // staple & fruit as single line items per day
    [
      { name: d.staple, category: 'Staple', amt: `${(state.people / 4).toFixed(0)} portions`, cost: d.slotCost.staple },
      { name: d.fruit, category: 'Fruit', amt: `${state.people} pcs`, cost: d.slotCost.fruit },
    ].forEach((item) => {
      const key = item.name;
      if (!map[key]) map[key] = { name: item.name, category: item.category, amounts: [], cost: 0 };
      map[key].amounts.push(item.amt);
      map[key].cost += item.cost;
    });
  });

  return Object.values(map).sort((a, b) => b.cost - a.cost);
}
