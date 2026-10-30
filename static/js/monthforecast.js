// A window with every forecast cost landing in one month, for the scope you are looking at. Lines with no forecast in that month are
// listed too (tick "all lines"), so a cost can be added from here: type it and the line becomes MANUAL, keeping what it forecast in the
// other months. Used by the dashboard charts.
import { h, clear, fmt, modal, toast, badge } from './ui.js';
import { api, p } from './api.js';
import { go, render } from './app.js';

export async function monthForecastDialog(month, node) {
  let changed = false; let showAll = false; let q = '';
  const body = h('div'); const list = h('div', { class: 'tw', style: { maxHeight: '58vh' } });
  let res; let md;
  const load = async () => { res = await api.get(p('/cost-control')); };
  await load();
  if (month < res.status_month) { go('costcontrol'); return; }
  const gi = () => res.grid.indexOf(month);
  const inScope = (rows) => {
    if (!node) return rows;
    const byId = new Map(rows.map((r) => [String(r.id), r]));
    const under = (r) => { let x = r; let n = 0; while (x && n++ < 12) { if (String(x.id) === String(node)) return true; x = x.parent_id == null ? null : byId.get(String(x.parent_id)); } return false; };
    return rows.filter(under);
  };
  const rowsNow = () => inScope(res.rows).filter((r) => r.kind === 'line' || r.kind === 'pot');
  const scopeName = () => { const r = node ? res.rows.find((x) => String(x.id) === String(node)) : null; return r ? `${r.code} ${r.name}` : 'the whole project'; };

  const commit = async (r, input) => {
    const raw = input.value.trim().replace(/[$,\s]/g, '');
    const b = { month, convert: true };
    if (raw === '' || raw === '0') b.clear = true;
    else if (/^-?\d+(\.\d+)?%$/.test(raw)) { b.unit = '%'; b.value = parseFloat(raw); }
    else if (/^-?\d+(\.\d+)?$/.test(raw)) { b.unit = '$'; b.value = parseFloat(raw); }
    else { toast('Type an amount such as 12500, or a percentage such as 25%', 'bad'); return; }
    try {
      const o = await api.post(p(`/nodes/${r.node_id}/forecast-set`), b);
      toast(`${r.code} ${fmt.month(month)}: ${b.clear ? 'cleared' : fmt.money(o.amount)}${o.converted ? ' (now MANUAL, other months kept)' : ''}`);
      changed = true; await load(); draw();
    } catch (err) { toast(err.message, 'bad'); }
  };

  function draw() {
    const i = gi(); const all = rowsNow();
    const withF = all.filter((r) => Math.abs(r.f[i] || 0) > 0.005);
    const shown = () => (showAll || !withF.length ? all : withF).filter((r) => !q || `${r.code} ${r.name}`.toLowerCase().includes(q))
      .sort((a, b) => Math.abs(b.f[i] || 0) - Math.abs(a.f[i] || 0) || String(a.code).localeCompare(String(b.code)));
    const total = withF.reduce((a, r) => a + (r.f[i] || 0), 0);
    clear(body).append(
      h('div', { class: 'grid g3', style: { marginBottom: '10px' } },
        h('div', { class: 'kpi' }, h('div', { class: 'l' }, 'Forecast landing'), h('div', { class: 'v', style: { fontSize: '19px' } }, fmt.money(total)), h('div', { class: 's' }, `${withF.length} lines, ${scopeName()}`)),
        h('div', { class: 'kpi' }, h('div', { class: 'l' }, 'Month'), h('div', { class: 'v', style: { fontSize: '19px' } }, fmt.month(month)), h('div', { class: 's' }, month === res.status_month ? 'The status month: only what is still forecast' : 'Future month')),
        h('div', { class: 'kpi' }, h('div', { class: 'l' }, 'Lines with no forecast'), h('div', { class: 'v', style: { fontSize: '19px' } }, String(all.length - withF.length)), h('div', { class: 's' }, 'Tick "all lines" to add one'))),
      h('div', { class: 'row', style: { gap: '12px', marginBottom: '8px' } },
        h('input', { type: 'search', placeholder: 'Search code or name...', value: q, style: { width: '220px' }, oninput: (e) => { q = e.target.value.toLowerCase(); clear(list).append(tbl(shown())); } }),
        h('label', { class: 'row small' }, h('input', { type: 'checkbox', checked: showAll || !withF.length, disabled: !withF.length, onchange: (e) => { showAll = e.target.checked; draw(); } }), 'All lines in scope (to add a forecast to a line with none)'),
        h('span', { class: 'sp' }), h('span', { class: 'small muted' }, 'Type an amount (or a %) and press Enter. A line on another method becomes MANUAL and keeps the other months.')));
    const tbl = (rows) => h('table', { class: 't' }, h('thead', {}, h('tr', {}, ['CBS', 'Line', 'Method', `Forecast in ${fmt.month(month)}`, 'Allowance left to forecast', 'CTC'].map((x, k) => h('th', { class: k >= 3 ? 'r' : '' }, x)))),
      h('tbody', {}, rows.map((r) => {
        const v = r.f[i] || 0; const editable = r.kind === 'line' && !res.is_parent;
        const input = h('input', { type: 'text', value: v ? String(Math.round(v * 100) / 100) : '', placeholder: editable ? '$ or %' : '', disabled: !editable, style: { width: '110px', textAlign: 'right' }, title: editable ? 'Type an amount and press Enter; empty clears it' : 'An unallocated pool is forecast on its group' });
        input.addEventListener('change', () => commit(r, input));
        return h('tr', {}, h('td', { class: 'mono' }, r.code), h('td', {}, r.name), h('td', {}, badge(r.method || 'AT-BUDGET')),
          h('td', { class: 'r' }, input), h('td', { class: 'r num' }, fmt.money(Math.max(0, (r.allowance || 0) - (r.ctd || 0) - (r.acc || 0)))), h('td', { class: 'r num' }, fmt.money(r.ctc)));
      })),
      h('tfoot', {}, h('tr', {}, h('td', { colSpan: 3 }, `Total of the ${withF.length} lines forecasting in ${fmt.month(month)}`), h('td', { class: 'r num' }, fmt.money(total)), h('td'), h('td'))));
    clear(list).append(tbl(shown())); body.append(list);
  }
  draw();
  md = modal({ title: `Forecast landing in ${fmt.month(month)}: ${scopeName()}`, size: 'xl', body,
    actions: [{ label: 'Open in Forecast lines', kind: 'ghost', onClick: () => { go('forecast', { month, ...(node ? { scope: node } : {}) }); } }, { label: 'Close', onClick: () => { if (changed) render(); } }] });
}
