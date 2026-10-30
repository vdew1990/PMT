import { h, fmt, modal, table, empty, tone } from './ui.js';
import { api, p } from './api.js';
import { go } from './app.js';

// The name for the difference between forecast and original profit: erosion when below, uplift when above.
export const marginWord = (v) => ((v || 0) >= 0 ? 'Margin uplift' : 'Margin erosion');

// Why the forecast profit differs from the day-zero profit: revenue, allowance, and the overruns and underruns behind it.
export async function openMarginBridge() {
  const b = await api.get(p('/margin-bridge'));
  const word = marginWord(b.erosion).toLowerCase();
  const sign = (v) => (v > 0 ? '+' : v < 0 ? '-' : '') + fmt.money(Math.abs(v));
  const big = Math.max(...b.steps.map((s) => Math.abs(s.value)), 1);
  const bar = (s) => h('div', { style: { height: '8px', width: `${Math.max(2, Math.abs(s.value) / big * 100)}%`, background: s.total ? 'var(--navy)' : s.value >= 0 ? 'var(--good)' : 'var(--bad)', borderRadius: '4px' } });
  let run = 0;
  const steps = b.steps.map((s) => { run = s.total ? s.value : run + s.value; return { ...s, run }; });
  const jump = (r) => { document.querySelector('.ov')?.remove(); go('costcontrol', { node: r.node_id ?? r.id }); };
  const lineTable = (rows, empt) => (rows.length ? h('div', { class: 'tw', style: { maxHeight: '260px' } }, table([
    { label: 'CBS', f: (r) => h('span', { class: 'mono' }, r.code) }, { label: 'Line', f: (r) => r.name }, { label: 'Allowance', r: 1, f: (r) => fmt.money(r.allowance) },
    { label: 'Forecast (EAC)', r: 1, f: (r) => fmt.money(r.eac) }, { label: 'Effect on profit', r: 1, f: (r) => h('b', { class: r.effect < 0 ? 'bad' : 'good' }, sign(r.effect)) }], rows, { onRow: jump })) : h('div', { class: 'muted small' }, empt));
  modal({ title: `${marginWord(b.erosion)}: ${sign(b.erosion)}`, size: 'wide', body: h('div', { class: 'grid' },
    h('div', { class: 'note' }, `Forecast profit is ${fmt.money(Math.abs(b.erosion))} ${b.erosion >= 0 ? 'above' : 'below'} the original (day zero) profit. The steps below add up to it; click a line to open it on Cost control.`),
    h('div', { class: 'tw' }, h('table', { class: 't notools' }, h('thead', {}, h('tr', {}, ['Step', '', 'Effect', 'Profit after'].map((x, i) => h('th', { class: i > 1 ? 'r' : '' }, x)))),
      h('tbody', {}, steps.map((s) => h('tr', { class: s.total ? 'par' : '' }, h('td', {}, s.label), h('td', { style: { width: '26%' } }, bar(s)), h('td', { class: 'r num' }, s.total ? fmt.money(s.value) : sign(s.value)), h('td', { class: 'r num' }, fmt.money(s.run))))))),
    h('h3', { style: { margin: '6px 0 2px' } }, `Overruns (${b.over.length} lines)`), lineTable(b.over, 'No line is forecast over its allowance.'),
    h('h3', { style: { margin: '10px 0 2px' } }, `Underruns (${b.under.length} lines)`), lineTable(b.under, 'No line is forecast under its allowance.'),
    b.categories.length ? h('div', { class: 'small muted' }, 'By category: ', b.categories.map((c) => `${c.gp}: overruns ${sign(c.over)}${c.under ? `, underruns ${sign(c.under)}` : ''}`).join('  |  ')) : null),
  actions: [{ label: 'Close', kind: 'ghost', onClick: () => {} }, { label: 'Open Cost control', onClick: () => { go('costcontrol'); } }] });
}
