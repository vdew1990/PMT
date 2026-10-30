import { h, clear, fmt, select, table, badge, empty, chart, tone } from '../ui.js';
import { outlineState, outlineStrip, visible as olVisible, MONTH_LEVELS } from '../outline.js';
import { api, state, p } from '../api.js';
import { go, render } from '../app.js';
import { pickNode } from '../scope.js';

// One page per metric (forecast, accruals, actuals) through the month-end closes: pick a close from the dropdown (or
// play them), see that metric by month as it stood then, how it moved from close to close, and per line how the
// method and value changed. Cost control and the labour calendar bring the three metrics together; these split them.
const META = {
  f: { name: 'Forecast', cls: 'mg-fc', color: '#4EA72E', total: 'Cost to complete', overTime: 'EAC at each close', what: 'forecast' },
  x: { name: 'Accruals', cls: 'mg-acc', color: '#4195f2', total: 'Accrued', overTime: 'Accrued balance at each close', what: 'accrued' },
  a: { name: 'Actuals', cls: 'mg-act', color: '#c0392b', total: 'Cost to date', overTime: 'Cost to date at each close', what: 'actual' },
};

export async function historyPage(root, params, metric, opts = {}) {
  const meta = META[metric];
  const key = 'hist_' + metric;
  const ui = JSON.parse(sessionStorage.getItem(key) || '{}');
  ui.node = params.node ?? ui.node ?? ''; ui.as_at = params.as_at || ui.as_at || 'live'; ui.month = ui.month || '';
  const save = () => sessionStorage.setItem(key, JSON.stringify(ui));
  save();
  const qs = (o) => new URLSearchParams(Object.fromEntries(Object.entries(o).filter(([, v]) => v !== '' && v !== null && v !== undefined)));
  const pageHead = () => { if (!opts.embedded) root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, opts.title || meta.name)), h('div', { class: 'sp' }), ...(opts.actions || []))); };
  let g, t;
  try {
    [g, t] = await Promise.all([api.get(p(`/history/${metric}?` + qs({ as_at: ui.as_at, node: ui.node }))), api.get(p(`/history/${metric}/track?` + qs({ node: ui.node })))]);
  } catch (e) {
    pageHead();
    root.append(empty('History is not available', e.message === 'Not Found'
      ? 'The PMT program running on this PC is older than this page. Close PMT (and end Python in Task Manager), then open PMT.exe again.'
      : 'It could not be loaded: ' + e.message));
    return;
  }
  // nothing to compare until the first month-end close (day zero counts once cost control is initialised)
  if (!(t.closes || []).some((c) => c.id !== 'live')) {
    pageHead();
    root.append(empty('Nothing to show yet', `${meta.name} history builds up from the month-end closes. Once the first month is closed (Month-end > Close month), this page shows what was ${metric === 'f' ? 'forecast' : metric === 'x' ? 'accrued' : 'booked'} at each close and how it moved.`,
      h('button', { class: 'btn', onclick: () => go('reports', { tab: 'snapshots' }) }, 'Month-end snapshots')));
    return;
  }
  const months = t.months; const closes = t.closes;
  const sel = closes.find((c) => String(c.id) === String(g.as_at.id)) || closes[closes.length - 1];
  if (!ui.month || !months.includes(ui.month)) ui.month = sel.period;

  if (!opts.embedded) root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, opts.title || meta.name), h('div', { class: 'sub' }, opts.sub || `${meta.name} by month as it stood at each month-end close. Pick a close, or play them, to see how it moved.`)),
    h('div', { class: 'sp' }), ...(opts.actions || [])));
  // ---- controls
  const asAt = select(closes.map((c) => [c.id, c.label]), sel.id, { onchange: (e) => { ui.as_at = e.target.value; save(); render(); } });
  const step = (n) => { const i = closes.findIndex((c) => c.id === sel.id); const j = Math.max(0, Math.min(closes.length - 1, i + n)); ui.as_at = String(closes[j].id); save(); render(); };
  root.append(h('div', { class: 'card row', style: { padding: '10px 14px', marginBottom: '12px' } },
    h('span', { class: 'small muted' }, 'Scope'), h('button', { class: 'btn ghost sm', onclick: () => pickNode({ allowRoot: true, onPick: (r) => { ui.node = r ? (r.kind === 'pot' ? 'p' + r.node_id : String(r.node_id)) : ''; save(); render(); } }) }, g.scope),
    h('span', { style: { width: '12px' } }), h('span', { class: 'small muted' }, 'As at'), h('button', { class: 'btn ghost sm', onclick: () => step(-1) }, '◀'), asAt, h('button', { class: 'btn ghost sm', onclick: () => step(1) }, '▶'),
    h('button', { class: 'btn sm', onclick: () => play() }, '▶ Play the closes'),
    h('span', { class: 'sp', style: { flex: 1 } }), closes.length < 2 ? h('span', { class: 'small muted' }, 'Close a month on the Month-end page to start building history.') : null));

  // ---- KPIs: first close against now
  const first = closes[0], now = closes[closes.length - 1];
  const kv = (l, v, s, c = '') => h('div', { class: 'kpi ' + c }, h('div', { class: 'l' }, l), h('div', { class: 'v' }, v), h('div', { class: 's' }, s));
  const changes = closes.reduce((n, c, i) => n + (i && c.method !== closes[i - 1].method ? 1 : 0), 0);
  root.append(h('div', { class: 'grid g6', style: { marginBottom: '14px' } },
    kv(`${meta.total} at ${sel.label}`, fmt.m(metric === 'f' ? sel.ctc : metric === 'x' ? sel.acc : sel.ctd), `${g.scope}`),
    kv(`EAC at ${sel.label}`, fmt.m(sel.eac), `allowance ${fmt.m(sel.allowance)}`, 't2'),
    kv('EAC moved', fmt.m(now.eac - first.eac), `${first.label} to ${now.label}`, 't3', tone(first.eac - now.eac)),
    kv('Closes', String(closes.length - 1), 'plus now'), kv('Method changes', String(changes), sel.method, 't4'),
    kv(`${meta.name} in ${fmt.month(ui.month)}`, fmt.m(sel.values[months.indexOf(ui.month)] || 0), `as at ${sel.label}`, 't5')));

  // ---- charts: the cost curve at each close (selected bold, the others faded) and the total over time
  const c1 = h('div', { class: 'chartbox' }); const c2 = h('div', { class: 'chartbox' });
  root.append(h('div', { class: 'grid g2', style: { marginBottom: '14px' } },
    h('div', { class: 'card' }, h('h2', {}, `Cost curve as at ${sel.label}`), h('div', { class: 'small muted', style: { marginBottom: '6px' } }, 'Cumulative actual + accrued + forecast. Earlier closes are faded: a perfect forecast would keep every curve on top of each other.'), c1),
    h('div', { class: 'card' }, h('h2', {}, meta.overTime), h('div', { class: 'small muted', style: { marginBottom: '6px' } }, metric === 'f' ? 'A flat line is a perfect forecast; every step is the forecast moving.' : `How the ${meta.what} total moved from close to close.`), c2)));
  const cum = (c) => { let s = 0; return months.map((_, i) => (s += c.a[i] + c.x[i] + c.f[i])); };
  let ch1;
  const draw1 = (cur) => {
    const ds = closes.map((c) => ({ label: c.label, data: cum(c), borderColor: c.id === cur.id ? '#102361' : 'rgba(16,35,97,.15)', borderWidth: c.id === cur.id ? 3 : 1.2, pointRadius: 0, fill: false, tension: .15, order: c.id === cur.id ? 0 : 1 }));
    ds.push({ label: 'Allowance', data: months.map(() => cur.allowance), borderColor: '#e56210', borderDash: [6, 4], borderWidth: 1.5, pointRadius: 0, fill: false });
    if (ch1) { ch1.data.datasets = ds; ch1.update(); return; }
    ch1 = chart(c1, { type: 'line', data: { labels: months.map(fmt.month), datasets: ds }, options: { animation: { duration: 500 }, plugins: { legend: { display: false } } } });
  };
  setTimeout(() => {
    draw1(sel);
    chart(c2, { type: 'line', data: { labels: closes.map((c) => c.label.replace('EOM ', '')), datasets: [
      { label: metric === 'f' ? 'EAC' : meta.total, data: closes.map((c) => (metric === 'f' ? c.eac : metric === 'x' ? c.acc : c.ctd)), borderColor: meta.color, backgroundColor: meta.color, tension: 0, pointRadius: closes.map((c) => (c.id === sel.id ? 6 : 3)) },
      ...(metric === 'f' ? [{ label: 'Allowance', data: closes.map((c) => c.allowance), borderColor: '#e56210', borderDash: [6, 4], pointRadius: 0 }] : [])] } });
  }, 30);
  async function play() {
    for (const c of closes) { draw1(c); asAt.value = c.id; await new Promise((r) => setTimeout(r, 900)); }
  }

  // ---- the question "what did I forecast for <month> back in <close>": every close against every month
  const mi = months.indexOf(sel.period);
  const shownAll = months.filter((m, i) => closes.some((c) => Math.abs(c.values[i]) > 0.5));
  const ost1 = outlineState('fh1', { folded: [] }); const oc1 = shownAll.map((m) => ({ id: m }));
  const ov1 = olVisible(oc1, shownAll.indexOf(ui.month), ost1, MONTH_LEVELS);
  const shown = shownAll.filter((m, k) => ov1[k]);   // folded and hidden months take no room: the strip above the table brings them back
  const head = h('tr', {}, h('th', { class: 'sticky1', style: { left: 0, zIndex: 4 } }, 'As at close'), h('th', {}, 'Method'), h('th', { class: 'r' }, 'EAC'),
    ...shown.map((m) => h('th', { class: 'mth ' + (m === ui.month ? 'mcf' : ''), 'data-col': m, style: { cursor: 'pointer' }, title: `What was ${meta.what} for ${fmt.month(m)} at each close`, onclick: () => { ui.month = m; save(); render(); } }, fmt.month(m))),
    h('th', { class: 'r' }, 'Total'));
  const body = h('tbody', {}, closes.map((c, ci) => h('tr', { class: 'click' + (c.id === sel.id ? ' sel' : ''), onclick: () => { ui.as_at = String(c.id); save(); render(); } },
    h('td', { class: 'sticky1', style: { left: 0, background: '#fff' } }, h('b', {}, c.label)),
    h('td', {}, h('span', { class: 'badge m-' + c.method }, c.method), ci && c.method !== closes[ci - 1].method ? h('span', { class: 'small', style: { color: 'var(--warn)' } }, ' changed') : null),
    h('td', { class: 'r num' }, fmt.money(c.eac)),
    ...shown.map((m) => { const i = months.indexOf(m); const v = c.values[i]; const past = m < c.period; return h('td', { class: 'r num mg ' + (v ? meta.cls : '') + (m === ui.month ? ' colsel' : ''), style: past && metric === 'f' ? { opacity: .45 } : {}, title: `${c.label}: ${meta.what} for ${fmt.month(m)} ${fmt.money(v)}` }, v ? fmt.n(v) : ''); }),
    h('td', { class: 'r num' }, fmt.money(c.total)))));
  const tbl1 = h('table', { class: 't' }, h('thead', {}, head), body); const tw1 = h('div', { class: 'tw', style: { maxHeight: '40vh' } }, tbl1);
  const ol1 = outlineStrip({ cols: oc1, cur: shownAll.indexOf(ui.month), levels: MONTH_LEVELS, st: ost1, onChange: () => render(), names: { 1: 'This quarter only', 2: 'Every month' } });
  const q = closes.map((c) => `${c.label}: ${fmt.money(c.values[months.indexOf(ui.month)] || 0)}`).join(' · ');
  root.append(h('div', { class: 'card', style: { marginBottom: '14px' } }, h('h2', {}, `${meta.name} at each close`),
    h('div', { class: 'small', style: { margin: '4px 0 8px' } }, h('b', {}, `${meta.name} for ${fmt.month(ui.month)}`), ` (click a month heading to change): ${q}`),
    shown.length ? h('div', {}, ol1.el, tw1) : empty('Nothing yet', `No ${meta.what} amounts in this scope.`)));
  if (shown.length) ol1.mount(tw1, tbl1);

  // ---- per line as at the selected close: method (and switch), total and change since the close before
  const rows = g.rows.filter((r) => Math.abs(r.total) > 0.5 || (r.prev_total && Math.abs(r.prev_total) > 0.5));
  const gi = g.months.indexOf(sel.period);
  const mshownAll = g.months.filter((m, i) => rows.some((r) => Math.abs(r.values[i]) > 0.5));
  const ost2 = outlineState('fh2', { folded: [] }); const oc2 = mshownAll.map((m) => ({ id: m }));
  const ov2 = olVisible(oc2, mshownAll.indexOf(sel.period), ost2, MONTH_LEVELS);
  const mshown = mshownAll.filter((m, k) => ov2[k]);
  root.append(h('div', { class: 'card' }, h('div', { class: 'ch' }, h('h2', {}, `Per line as at ${g.as_at.label}`), h('span', { class: 'sp' }), g.prev ? h('span', { class: 'small muted' }, `Change against ${g.prev.label}`) : null),
    rows.length ? h('div', { class: 'tw', style: { maxHeight: '55vh' } }, h('table', { class: 't' },
      h('thead', {}, h('tr', {}, h('th', { class: 'sticky1', style: { left: 0, zIndex: 4 } }, 'CBS'), h('th', {}, 'Line'), h('th', {}, 'Method'), h('th', { class: 'r' }, 'Total'), h('th', { class: 'r' }, 'Change'), h('th', { class: 'r' }, 'EAC'),
        ...mshown.map((m) => h('th', { class: 'mth ' + (m < sel.period ? 'mpa' : m === sel.period ? 'mcf' : 'mfu'), 'data-col': m }, fmt.month(m))))),
      h('tbody', {}, rows.map((r) => h('tr', { class: 'click', title: 'Show this line\'s history', onclick: () => { ui.node = r.kind === 'pot' ? 'p' + r.ref.replace(/^p/, '') : r.ref; save(); render(); } },
        h('td', { class: 'mono sticky1', style: { left: 0, background: '#fff' } }, r.code), h('td', { class: 'wrap' }, r.name),
        h('td', {}, h('span', { class: 'badge m-' + (r.method || 'AT-BUDGET') }, r.method || 'AT-BUDGET'), r.prev_method && r.prev_method !== r.method ? h('div', { class: 'small muted' }, `was ${r.prev_method}`) : null),
        h('td', { class: 'r num' }, h('b', {}, fmt.money(r.total))), h('td', { class: 'r num ' + (r.prev_total === null ? '' : tone(r.prev_total - r.total)) }, r.prev_total === null ? 'new' : (Math.abs(r.total - r.prev_total) < 0.5 ? '–' : fmt.money(r.total - r.prev_total))),
        h('td', { class: 'r num' }, fmt.money(r.eac)),
        ...mshown.map((m) => { const v = r.values[g.months.indexOf(m)]; return h('td', { class: 'r num mg ' + (v ? meta.cls : '') }, v ? fmt.n(v) : ''); })))))) : empty('Nothing in this scope', `No ${meta.what} amounts as at this close.`)));
  { const tw2 = root.querySelector('.card:last-child .tw'); if (tw2 && mshownAll.length > 1) {
    const ol2 = outlineStrip({ cols: oc2, cur: mshownAll.indexOf(sel.period), levels: MONTH_LEVELS, st: ost2, onChange: () => render(), names: { 1: 'This quarter only', 2: 'Every month' } });
    tw2.before(ol2.el); ol2.mount(tw2, tw2.querySelector('table')); } }
}
