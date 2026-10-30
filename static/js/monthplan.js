// Which month columns a wide grid shows: every month, a quarter in place of its months, or nothing for the past or the future.
// The current (status) month always shows. A quarter is an Australian financial year quarter (Q1 is July to September).
import { fyQuarter } from './outlinecore.js';
export { fyQuarter };
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
// Column groups, as in Excel: each financial year quarter is a group of month columns that can be folded (its months are hidden and a
// narrow stub stays to open it) or opened. The status month always stays visible. Months can also be hidden one at a time.
export const quarterKeys = (months) => [...new Set(months.map((m) => fyQuarter(m).key))];
// the default: quarters before the status month's quarter are folded, the current and later ones are open
export function defaultCollapsed(months, gi) {
  if (gi < 0 || !months.length) return [];
  const keys = quarterKeys(months); const cq = keys.indexOf(fyQuarter(months[gi]).key);
  return keys.filter((k, i) => i < cq);
}
// cycling through the year: step the open window of quarters one on (+1) or back (-1), folding the one it leaves
export function stepQuarters(months, collapsed, dir) {
  const keys = quarterKeys(months); const open = keys.filter((k) => !collapsed.has(k));
  if (!open.length) return [...collapsed];
  const lo = keys.indexOf(open[0]); const hi = keys.indexOf(open[open.length - 1]); const next = new Set(collapsed);
  if (dir > 0 && hi < keys.length - 1) { next.delete(keys[hi + 1]); if (open.length > 1) next.add(keys[lo]); }
  else if (dir < 0 && lo > 0) { next.delete(keys[lo - 1]); if (open.length > 1) next.add(keys[hi]); }
  return [...next];
}
// returns [{ kind: 'm' | 'cur', i, qk, qlabel, first } | { kind: 'stub', idxs, qk, qlabel, first } | { kind: 'hid', idxs, manual: true }]
export function buildPlan(months, gi, cfg) {
  const out = []; let pend = null;
  const flush = () => { if (pend) { out.push(pend); pend = null; } };
  months.forEach((m, i) => {
    const q = fyQuarter(m); const base = { qk: q.key, qlabel: q.label };
    if (i === gi) { flush(); out.push({ kind: 'cur', i, ...base }); return; }
    if (cfg.hide && cfg.hide.has(m)) { if (!pend || pend.kind !== 'hid') { flush(); pend = { kind: 'hid', idxs: [], manual: true }; } pend.idxs.push(i); return; }
    if (cfg.collapsed && cfg.collapsed.has(q.key)) { if (!pend || pend.kind !== 'stub' || pend.qk !== q.key) { flush(); pend = { kind: 'stub', idxs: [], ...base }; } pend.idxs.push(i); return; }
    flush(); out.push({ kind: 'm', i, ...base });
  });
  flush();
  const seen = new Set();
  out.forEach((c) => { if (c.kind !== 'hid') { c.first = !seen.has(c.qk); seen.add(c.qk); } });
  return out;
}

// ---- a short month field (Sep-26): typed as Sep-26, Sep 2026, 2026-09 or 9/26, read back as YYYY-MM through .ym ----
import { h } from './ui.js';
export const ymShow = (ym) => (ym ? `${MON[+ym.slice(5, 7) - 1]}-${ym.slice(2, 4)}` : '');
export function ymParse(t) {
  t = String(t || '').trim(); if (!t) return ''; let m;
  if ((m = t.match(/^(\d{4})-(\d{1,2})$/))) return +m[2] >= 1 && +m[2] <= 12 ? `${m[1]}-${m[2].padStart(2, '0')}` : null;
  if ((m = t.match(/^([A-Za-z]{3})[a-z]*[-\s/]*(\d{2}|\d{4})$/))) { const k = MON.findIndex((x) => x.toLowerCase() === m[1].toLowerCase()); if (k >= 0) return `${m[2].length === 2 ? '20' + m[2] : m[2]}-${String(k + 1).padStart(2, '0')}`; }
  if ((m = t.match(/^(\d{1,2})[/-](\d{2}|\d{4})$/))) return +m[1] >= 1 && +m[1] <= 12 ? `${m[2].length === 2 ? '20' + m[2] : m[2]}-${m[1].padStart(2, '0')}` : null;
  return null;
}
export function monthInput(ym, cls = '') {
  const inp = h('input', { type: 'text', value: ymShow(ym), placeholder: 'Mon-YY', autocomplete: 'off', class: cls });
  let good = ym || '';
  Object.defineProperty(inp, 'ym', { get() { const v = ymParse(inp.value); if (v === null) { inp.value = ymShow(good); return good; } good = v; return v; } });
  inp.addEventListener('blur', () => { const v = ymParse(inp.value); inp.value = ymShow(v === null ? good : v); });
  return inp;
}
