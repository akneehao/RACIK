// utils.js
// Small, dependency-free helpers used across every module: currency
// formatting, the toast notification, screen/tab visibility toggling,
// and the reusable star-rating widget.

/** Format a number of Rupiah as "Rp 1,234,567". */
export function formatIDR(amount) {
  return `Rp ${Math.round(amount).toLocaleString('en-US')}`;
}

/** Format Rupiah as a signed delta, e.g. "+Rp 1,000" / "−Rp 1,000". */
export function formatIDRDelta(amount) {
  const sign = amount >= 0 ? '+' : '−';
  return `${sign}${formatIDR(Math.abs(amount))}`;
}

let toastTimer = null;

/** Show a brief toast notification at the bottom of the screen. */
export function toast(message) {
  const el = document.getElementById('toast');
  if (!el) return;
  el.textContent = message;
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), 2400);
}

/**
 * Show one `.screen` element within the onboarding flow (screen-1, screen-2)
 * or within the Plan tab (screen-3, screen-4), hiding all siblings.
 */
export function showScreen(id) {
  document.querySelectorAll('.screen').forEach((s) => s.classList.remove('active'));
  const el = document.getElementById(id);
  if (el) el.classList.add('active');
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

/** Update the onboarding stepper (Location / Parameters) to mark step `n` active. */
export function setOnboardingStep(n) {
  document.querySelectorAll('#onboardingStepper .step').forEach((s) => {
    const num = parseInt(s.dataset.step, 10);
    s.classList.toggle('active', num === n);
    s.classList.toggle('done', num < n);
  });
}

/**
 * Turn a "★★★★★" placeholder element into a clickable star-rating widget.
 * Call once per element at startup.
 */
export function setupStarRating(elementId) {
  const el = document.getElementById(elementId);
  if (!el) return;
  const chars = el.textContent.split('');
  el.innerHTML = chars.map((c, i) => `<span data-i="${i}">${c}</span>`).join('');
  el.addEventListener('click', (e) => {
    const span = e.target.closest('span');
    if (!span) return;
    const idx = parseInt(span.dataset.i, 10);
    el.querySelectorAll('span').forEach((s, i) => s.classList.toggle('on', i <= idx));
  });
}

/** Trigger a client-side CSV download from an array of already-formatted row strings. */
export function downloadCsv(header, rows, filename) {
  const blob = new Blob([header + rows.join('\n')], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
  toast(`Downloaded ${filename}`);
}
