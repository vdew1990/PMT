import { h, clear, fmt, modal, toast, field, select, table, num, badge, tabs, empty, confirmBox, tone, chart, PALETTE } from '../ui.js';
import { api, state, p, statusMonth } from '../api.js';
import { go, render } from '../app.js';
import { ymParse } from '../monthplan.js';
import { outlineState, outlineStrip, visible as olVisible, MONTH_LEVELS } from '../outline.js';

// MONTH-END > Snapshots and history: the snapshots each month-end close keeps, and the change log. The reports themselves
// (EOM to finance, PMR to the board, PSR to the client) live under REPORTING (eom.js, pmr.js, psr.js).
export default async function reports(root, params) {
  if (params.tab === 'eom') { go('eom'); return; }
  if (params.tab === 'pmr') { go('pmr'); return; }
  const tab = params.tab || 'snapshots';
  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, 'Snapshots and history'), h('div', { class: 'sub' }, 'The month-end snapshots that build the project history, and the change log. The reports are under REPORTING.'))));
  root.append(tabs([['snapshots', 'Month-end snapshots'], ['audit', 'Change log']], tab, (k) => go('reports', { tab: k })));
  const body = h('div'); root.append(body);
  if (tab === 'snapshots') await snapTab(body); else await auditTab(body);
}

// ---- EOM cost and revenue report (the workbook's EOM Report sheet, plus cashflow) -----------------
export async function eomTab(body, params) {
  const hide = params.zero !== 'show';
  const rev = h('input', { value: params.rev || '', placeholder: 'auto', style: { width: '64px' } });
  const q = () => `hide_zero=${hide ? 1 : 0}${rev.value.trim() ? '&revision=' + encodeURIComponent(rev.value.trim()) : ''}`;
  const d = await api.get(p(`/eom-report?${q()}`));
  if (!rev.value) rev.placeholder = d.header.revision;
  const zero = h('input', { type: 'checkbox', checked: hide, onchange: () => go('eom', { zero: zero.checked ? '' : 'show', rev: rev.value.trim() }) });
  body.append(h('div', { class: 'card', style: { marginBottom: '12px' } }, h('div', { class: 'row' },
    h('div', {}, h('b', {}, d.header.title), h('div', { class: 'small muted' }, `Status month ${d.header.status_label} \u00b7 prepared ${d.header.prepared} \u00b7 revision ${d.header.revision}`)),
    h('span', { class: 'sp' }),
    h('label', { class: 'small' }, 'Revision ', rev), h('label', { class: 'small' }, zero, ' Hide zero lines'),
    h('button', { class: 'btn', onclick: () => window.open(p(`/eom-report.pdf?${q()}`)) }, 'Download PDF'),
    h('button', { class: 'btn ghost', onclick: () => window.open(p(`/eom-report.xlsx?${q()}`)) }, 'Download Excel'))));
  const m = (v) => fmt.n(v);
  const mini = (cols, rows, opts = {}) => table(cols.map(([label, f, r]) => ({ label, r, f })), rows, opts);
  const revRows = d.revenue.stages.flatMap((s) => s.rows.map((r, i) => ({ ...r, stage: i ? '' : s.stage })));
  body.append(h('div', { class: 'grid g2' },
    h('div', { class: 'card' }, h('h2', {}, 'Revenue'),
      mini([['Stage', (r) => h('b', {}, r.stage)], ['Scope', (r) => r.total ? h('b', {}, r.scope) : r.scope], ['Previous', (r) => m(r.previous), 1], ['This month', (r) => m(r.this_month), 1],
        ['To date', (r) => r.total ? h('b', {}, m(r.to_date)) : m(r.to_date), 1], ['Remaining', (r) => m(r.remaining), 1], ['Contract value', (r) => m(r.contract_value), 1]], revRows),
      h('div', { class: 'small muted', style: { marginTop: '6px' } }, d.revenue.note)),
    h('div', {},
      h('div', { class: 'card', style: { marginBottom: '12px' } }, h('h2', {}, 'Gross margin'),
        mini([['Metric', (r) => r.metric], ...['original', 'revised', 'to_date', 'at_completion'].map((k, i) => [['Original', 'Revised', 'To date', 'At completion'][i], (r) => r.pct ? fmt.pct(r[k]) : m(r[k]), 1])], d.margin)),
      h('div', { class: 'card', style: { marginBottom: '12px' } }, h('h2', {}, 'Approved variations'),
        d.variations.rows.length ? mini([['Variation', (r) => h('span', { title: r.title }, r.ref)], ['Approved', (r) => m(r.approved), 1], ['This month', (r) => m(r.this_month), 1], ['To be claimed', (r) => m(r.to_be_claimed), 1],
          ['In Pronto?', (r) => badge(r.pronto, r.state === 'ok' ? 'good' : 'bad')]], d.variations.rows) : empty('No approved variations', '')),
      h('div', { class: 'card' }, h('h2', {}, 'Claims \u2014 PMT vs Pronto'),
        mini([['Check', (r) => r.check], ['PMT', (r) => m(r.pmt), 1], ['Pronto', (r) => m(r.pronto), 1], ['Difference', (r) => m(r.diff), 1], ['Status', (r) => badge(r.status, ['OK', 'Fully paid'].includes(r.status) ? 'good' : 'warn')]], d.claims.rows)))));
  // cashflow
  const cf = d.cashflow, cbox = h('div', { style: { height: '340px' } });
  const fcCol = (i) => cf.flag[i] === 'Forecast' ? '#DCEDD5' : cf.flag[i] === 'Current' ? '#A6C9EC' : '#DDEBF7';
  // the months of the table fold into quarters like the other grids (the chart keeps every month); a label that is not a month turns the outline off
  const cfIds = cf.labels.map((l) => ({ id: ymParse(l) })); const outlineOk = cfIds.every((c) => c.id);
  const ost = outlineState('eomcf', { folded: [] }); const cfCur = cf.flag.indexOf('Current');
  const cfVis = outlineOk ? olVisible(cfIds, cfCur, ost, MONTH_LEVELS) : cf.labels.map(() => true);
  const ix = cf.labels.map((_, i) => i).filter((i) => cfVis[i]);
  const cft = h('table', { class: 't' }, h('thead', {}, h('tr', {}, h('th', {}, ''), ix.map((i) => h('th', { class: 'r', 'data-col': cfIds[i].id || '' }, cf.labels[i])))),
    h('tbody', {}, h('tr', {}, h('td', { class: 'small muted' }, ''), ix.map((i) => h('td', { class: 'r small', style: { background: fcCol(i) } }, cf.flag[i]))),
      [['Revenue', 'revenue'], ['Cost', 'cost'], ['Net', 'net', 1], ['Cumulative revenue', 'cum_revenue'], ['Cumulative cost', 'cum_cost'], ['Cumulative net', 'cum_net', 1]].map(([l, k, b]) =>
        h('tr', {}, h('td', {}, b ? h('b', {}, l) : l), ix.map((i) => { const v = cf[k][i]; return h('td', { class: 'r num ' + (v < -0.5 ? 'bad' : '') }, b ? h('b', {}, m(v)) : m(v)); })))));
  const cftw = h('div', { class: 'tw', style: { marginTop: '10px' } }, cft);
  const cfStrip = outlineOk && cf.labels.length > 1 ? outlineStrip({ cols: cfIds, cur: cfCur, levels: MONTH_LEVELS, st: ost, onChange: () => render(), names: { 1: 'This quarter only', 2: 'Every month' } }) : null;
  body.append(h('div', { class: 'card', style: { marginTop: '12px' } }, h('div', { class: 'ch' }, h('h2', {}, 'Cashflow: cost and revenue by month'), h('span', { class: 'sp' }), h('span', { class: 'small muted' }, cf.note)), cbox, ...(cfStrip ? [cfStrip.el] : []), cftw));
  if (cfStrip) cfStrip.mount(cftw, cft);
  chart(cbox, { type: 'bar', data: { labels: cf.labels, datasets: [
    { type: 'bar', label: 'Revenue (month)', data: cf.revenue, backgroundColor: '#e56210', yAxisID: 'y', order: 3 },
    { type: 'bar', label: 'Cost (month)', data: cf.cost, backgroundColor: '#102361', yAxisID: 'y', order: 3 },
    { type: 'line', label: 'Cumulative revenue', data: cf.cum_revenue, borderColor: '#e56210', backgroundColor: '#e56210', yAxisID: 'y2', pointRadius: 0, tension: 0.2, order: 1 },
    { type: 'line', label: 'Cumulative cost', data: cf.cum_cost, borderColor: '#102361', backgroundColor: '#102361', yAxisID: 'y2', pointRadius: 0, tension: 0.2, order: 1 },
    { type: 'line', label: 'Cumulative net', data: cf.cum_net, borderColor: '#ffb500', backgroundColor: '#ffb500', borderDash: [6, 3], yAxisID: 'y2', pointRadius: 0, order: 1 }] },
    options: { scales: { y: { title: { display: true, text: 'Monthly' } }, y2: { position: 'right', grid: { display: false }, ticks: { callback: (v) => fmt.m(v) }, title: { display: true, text: 'Cumulative' } } } } });
  // cost
  const ks = ['allowance', 'ordered', 'outstanding', 'prev_actual', 'actual_month', 'ctd', 'prev_accrued', 'accrued_month', 'acc', 'ctc', 'eac'];
  const kl = ['Revised value', 'Ordered', 'Outstanding commitment', 'Previous actuals', 'Actuals this month', 'CTD', 'Previously accrued', 'Accrued this month', 'Accruals to date', 'CTC', 'EAC'];
  const isLine = (r) => r.kind === 'line' || r.kind === 'pot';
  body.append(h('div', { class: 'card', style: { marginTop: '12px' } }, h('div', { class: 'ch' }, h('h2', {}, 'Cost'), h('span', { class: 'sp' }), h('span', { class: 'small muted' }, `Total EAC ${fmt.money(d.cost.total.eac)}${Math.abs(d.check.eac) > 1 ? ' \u2014 does not tie to cost control!' : ' (ties to cost control)'}`)),
    table([{ label: 'CBS', f: (r) => h('span', { class: 'mono', style: { paddingLeft: (r.level - 1) * 10 + 'px', fontWeight: isLine(r) ? 400 : 700 } }, r.code) }, { label: 'Function', f: (r) => isLine(r) ? r.function : h('b', {}, r.function) },
      { label: 'Resource code', f: (r) => r.resource_code }, { label: 'Resource', f: (r) => r.resource },
      ...ks.map((k, i) => ({ label: kl[i], r: 1, f: (r) => isLine(r) ? m(r[k]) : h('b', {}, m(r[k])) }))], d.cost.rows,
      { maxHeight: '70vh', rowClass: (r) => isLine(r) ? '' : r.level === 1 ? 'gp' : r.level === 2 ? 'par' : 'par2', foot: (c) => c.label === 'CBS' ? 'TOTAL' : (kl.includes(c.label) ? m(d.cost.total[ks[kl.indexOf(c.label)]]) : '') })));
}

export async function pmrTab(body) {
  const d = await api.get(p('/pmr'));
  const sec = (title, rows) => h('div', { class: 'card' }, h('h2', {}, title), h('table', { class: 't' }, h('tbody', {}, rows.map(([l, v, n]) => h('tr', {}, h('td', {}, l), h('td', { class: 'r num', style: { fontWeight: 700 } }, typeof v === 'number' ? fmt.money(v) : (v || '')), h('td', { class: 'muted small' }, n || ''))))));
  body.append(h('div', { class: 'row', style: { marginBottom: '12px' } }, h('button', { class: 'btn', onclick: () => window.open(p('/pmr.xlsx')) }, 'Download PMR output (Excel)'), h('span', { class: 'muted small' }, 'Paste into the Project Monthly Report. The check line should read zero.')));
  const r = d.revenue, c = d.cost, k = d.contingency, m = d.margin;
  body.append(h('div', { class: 'grid g2' },
    sec('Revenue', [['Original contract value', r.original], ['Approved variations', r.approved_variations], ['Revised contract value (official)', r.revised_official], ['Recognised revenue', r.recognised, 'Approved and agreed'], ['Claimed to date', r.claimed_to_date], ['Residual to claim', r.residual]]),
    sec('Cost', [['Original budget (excl. risk)', c.original_budget], ['Variation allowance', c.variations_allowance], ['Current allowance', c.current_allowance], ['Cost to date', c.ctd], ['Accruals', c.accruals], ['Cost to complete', c.ctc], ['EAC', c.eac, 'CTD + ACC + CTC']]),
    sec('Contingency', [['Original risk', k.original_risk], ['Current risk', k.current_risk], ['Contingency at completion', k.forecast_at_completion, 'Allowance less EAC; negative is an overrun']]),
    sec('Margin', [['Original gross profit', m.gp_original], ['Forecast gross profit', m.gp_forecast], [m.erosion >= 0 ? 'Uplift' : 'Erosion', m.erosion], ['Original margin', fmt.pct(m.gp_original_pct)], ['Forecast margin', fmt.pct(m.gp_forecast_pct)]])));
  body.append(h('div', { class: 'note ' + (Math.abs(d.check.grid_minus_eac) > 1 ? 'bad' : ''), style: { marginTop: '12px' } }, `Check: monthly cost grid less EAC = ${fmt.money(d.check.grid_minus_eac)}`));
}

async function snapTab(body) {
  const list = await api.get(p('/snapshots'));
  const label = (s) => `${s.label}${s.kind === 'baseline' ? '' : ''} (${s.kind === 'baseline' ? 'estimate' : fmt.month(s.period)})`;
  body.append(h('div', { class: 'card', style: { marginBottom: '14px' } }, h('div', { class: 'ch' }, h('h2', {}, 'Snapshots'), h('span', { class: 'sp' }), h('span', { class: 'small muted' }, 'Day zero is the original estimate. Close each month to keep the history.'), h('button', { class: 'btn', onclick: async () => {
      let open = 0;
      try { const rv = await api.get(p('/month-review')); const tol = Math.max(1, state.project.tolerance || 1); open = rv.rows.filter((r) => !r.decision && (Math.abs(r.variance) > tol || (r.planned > tol && r.landed < tol))).length; } catch (e) { /* the reminder is optional */ }
      const warn = open ? ` ${open} line(s) where plan and landed differ have not been reviewed yet (Month-end > Review lines).` : '';
      if (!(await confirmBox(`Close ${fmt.month(statusMonth())}? This stores the current position as the month-end snapshot (replacing one for the same month).${warn}`, open ? 'Close anyway' : 'Close month'))) { if (open) go('review'); return; } await api.post(p('/snapshots'), {}); toast('Snapshot stored'); render(); } }, 'Close month: store snapshot')),
    list.length ? table([{ label: 'Period', f: (s) => fmt.month(s.period) }, { label: 'Label', f: (s) => s.label }, { label: 'Type', f: (s) => badge(s.kind === 'baseline' ? 'Day zero' : 'Month end', s.kind === 'baseline' ? 'navy' : '') }, { label: 'Stored', f: (s) => s.created_at },
      { label: 'Allowance', r: 1, f: (s) => fmt.money(JSON.parse(s.summary_json).totals.allowance) }, { label: 'EAC', r: 1, f: (s) => fmt.money(JSON.parse(s.summary_json).totals.eac) }, { label: 'Forecast margin', r: 1, f: (s) => fmt.pct(JSON.parse(s.summary_json).margin.gp_forecast_pct) },
      { label: '', f: (s) => s.kind === 'baseline' ? '' : h('button', { class: 'btn danger sm', onclick: async (e) => { e.stopPropagation(); if (await confirmBox('Delete this snapshot?', 'Delete', true)) { await api.del(p(`/snapshots/${s.id}`)); render(); } } }, '\u00d7') }], list, { onRow: (s) => { selA.value = String(s.id); run(); window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' }); } })
      : empty('No snapshots yet', 'Store one at each month end. Day zero is stored when cost control is initialised.')));
  if (!list.length) return;

  // ---- compare ------------------------------------------------------------------------------------
  const ordered = [...list].sort((x, y) => (x.kind === 'baseline' ? -1 : y.kind === 'baseline' ? 1 : x.period.localeCompare(y.period)));
  const opts = [...ordered.map((s) => [String(s.id), label(s)]), ['live', 'Live (now)']];
  const latest = ordered.filter((s) => s.kind !== 'baseline').pop();
  const selA = select(opts, String((ordered.length > 1 && latest && String(latest.period) === statusMonth() ? ordered[ordered.length - 2] : latest || ordered[0]).id), {});
  const selB = select(opts, 'live', {});
  const out = h('div');
  body.append(h('div', { class: 'card' }, h('div', { class: 'ch' }, h('h2', {}, 'Compare two versions'), h('span', { class: 'sp' }), h('span', { class: 'small muted' }, 'Compare the estimate with any month, or any month with another, to see how the forecast has moved.')),
    h('div', { class: 'row' }, field('From (older)', selA), h('span', { style: { marginTop: '18px' } }, '\u2192'), field('To (newer)', selB), h('button', { class: 'btn', style: { marginTop: '18px' }, onclick: run }, 'Compare'))), out);
  async function run() {
    clear(out).append(h('div', { class: 'muted', style: { margin: '12px 0' } }, 'Comparing...'));
    const q = `a=${selA.value}&b=${selB.value}`;
    const [cmp, curves, whole] = await Promise.all([api.get(p(`/snapshots-compare?${q}`)), api.get(p(`/snapshots-curves?${q}`)), api.get(p(`/snapshots-series?${q}`))]);
    const ma = cmp.a.margin, mb = cmp.b.margin;
    const A = cmp.rows.filter((r) => r.level === 1);
    const tot = (k) => [A.reduce((x, r) => x + r[k + '_a'], 0), A.reduce((x, r) => x + r[k + '_b'], 0)];
    const tile = (l, [x, y], money = true, good = 'down') => h('div', { class: 'kpi' }, h('div', { class: 'l' }, l), h('div', { class: 'v', style: { fontSize: '18px' } }, money ? fmt.m(y) : fmt.pct(y)), h('div', { class: 's' }, `was ${money ? fmt.m(x) : fmt.pct(x)} `, h('b', { class: (good === 'down' ? y - x > 0.5 : y - x < -0.0005) ? 'bad' : (Math.abs(y - x) < (money ? 0.5 : 0.0005) ? '' : 'good') }, money ? (y - x >= 0 ? '+' : '') + fmt.m(y - x) : ((y - x) >= 0 ? '+' : '') + ((y - x) * 100).toFixed(1) + ' pts')));
    const lvl = { v: 2 }; const moversOnly = { v: true }; const tbl = h('div'); const detail = h('div');
    const draw = () => {
      const rows = cmp.rows.filter((r) => r.level <= lvl.v && r.kind !== 'pot' && (!moversOnly.v || Math.abs(r.eac_d) > 1 || Math.abs(r.allowance_d) > 1 || Math.abs(r.ctd_d) > 1 || r.new || r.removed));
      clear(tbl).append(rows.length ? table([{ label: 'CBS', f: (r) => h('span', { class: 'mono', style: { paddingLeft: (r.level - 1) * 12 + 'px' } }, r.code) }, { label: 'Name', f: (r) => h('span', {}, r.name, r.new ? badge('new', 'good') : r.removed ? badge('removed', 'warn') : null) },
        { label: 'Allowance then', r: 1, f: (r) => fmt.money(r.allowance_a) }, { label: 'now', r: 1, f: (r) => fmt.money(r.allowance_b) }, { label: 'CTD then', r: 1, f: (r) => fmt.money(r.ctd_a) }, { label: 'now', r: 1, f: (r) => fmt.money(r.ctd_b) }, { label: 'CTC then', r: 1, f: (r) => fmt.money(r.ctc_a) }, { label: 'now', r: 1, f: (r) => fmt.money(r.ctc_b) },
        { label: 'EAC then', r: 1, f: (r) => fmt.money(r.eac_a) }, { label: 'now', r: 1, f: (r) => fmt.money(r.eac_b) }, { label: 'EAC movement', r: 1, f: (r) => h('b', { class: tone(-r.eac_d) }, (r.eac_d > 0 ? '+' : '') + fmt.money(r.eac_d)) }], rows, { maxHeight: '55vh', onRow: (r) => showSeries(r.code, r.name) }) : empty('No movement', 'Nothing has changed at this level between the two versions.'));
    };
    async function showSeries(code, name) {
      const sr = await api.get(p(`/snapshots-series?${q}${code ? '&code=' + encodeURIComponent(code) : ''}`));
      const box = h('div', { class: 'chartbox' });
      clear(detail).append(h('div', { class: 'card', style: { marginTop: '14px' } }, h('h2', {}, `Monthly forecast movement: ${code ? code + ' ' + name : 'whole project'}`), h('div', { class: 'small muted', style: { margin: '4px 0 8px' } }, 'Cost by month (actual, accrual and forecast) in each version. The difference shows where money moved in time and in total.'), box));
      const first = sr.months.findIndex((_, i) => sr.a[i] || sr.b[i]);
      const lo = Math.max(0, first); const sl = (x) => x.slice(lo);
      chart(box, { type: 'bar', data: { labels: sl(sr.months).map(fmt.month), datasets: [{ type: 'bar', label: cmp.a.label, data: sl(sr.a), backgroundColor: PALETTE[0] }, { type: 'bar', label: cmp.b.label, data: sl(sr.b), backgroundColor: PALETTE[1] }, { type: 'line', label: 'Movement', data: sl(sr.delta), borderColor: PALETTE[2], backgroundColor: PALETTE[2], borderWidth: 2, pointRadius: 3 }] } });
      detail.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
    const cbox = h('div', { class: 'chartbox' }); const mbox = h('div', { class: 'chartbox' });
    clear(out).append(h('div', { style: { marginTop: '14px' } },
      h('div', { class: 'grid g6' }, tile('Allowance', tot('allowance')), tile('Cost to date', tot('ctd'), true, 'none'), tile('Cost to complete', tot('ctc')), tile('EAC', tot('eac')), tile('Forecast margin', [ma?.gp_forecast_pct, mb?.gp_forecast_pct], false, 'up'), tile('Forecast profit', [ma?.gp_forecast, mb?.gp_forecast], true, 'up')),
      h('div', { class: 'grid g2', style: { marginTop: '14px' } }, h('div', { class: 'card' }, h('h2', {}, 'Cumulative cost and revenue, both versions'), cbox), h('div', { class: 'card' }, h('h2', {}, 'EAC movement by category'), mbox)),
      h('div', { class: 'card', style: { marginTop: '14px' } }, h('div', { class: 'ch' }, h('h2', {}, `Movement by CBS: ${cmp.a.label} \u2192 ${cmp.b.label}`), h('span', { class: 'sp' }), h('span', { class: 'small muted' }, 'Show to level'), select([[1, '1 Grandparent'], [2, '2 Parent'], [3, '3 Group'], [4, '4 Line'], [5, '5 Deepest']], 2, { onchange: (e) => { lvl.v = +e.target.value; draw(); } }), h('label', { class: 'row small' }, h('input', { type: 'checkbox', checked: true, onchange: (e) => { moversOnly.v = e.target.checked; draw(); } }), 'Only items that moved'), h('button', { class: 'btn ghost sm', onclick: () => showSeries(null) }, 'Whole-project monthly movement')), tbl), detail));
    draw();
    const ca = curves.a, cb = curves.b; const labels = ca.months.length >= cb.months.length ? ca.months : cb.months;
    const al = (c, k) => labels.map((m) => { const i = c.months.indexOf(m); return i < 0 ? null : c[k][i]; });
    chart(cbox, { type: 'line', data: { labels: labels.map(fmt.month), datasets: [{ label: `Cost: ${ca.label}`, data: al(ca, 'cost'), borderColor: PALETTE[0], borderDash: [6, 4], borderWidth: 2, pointRadius: 0 }, { label: `Cost: ${cb.label}`, data: al(cb, 'cost'), borderColor: PALETTE[0], borderWidth: 2.5, pointRadius: 0 }, { label: `Revenue: ${ca.label}`, data: al(ca, 'revenue'), borderColor: PALETTE[1], borderDash: [6, 4], borderWidth: 2, pointRadius: 0 }, { label: `Revenue: ${cb.label}`, data: al(cb, 'revenue'), borderColor: PALETTE[1], borderWidth: 2.5, pointRadius: 0 }] }, options: { interaction: { mode: 'index', intersect: false } } });
    const cats = cmp.rows.filter((r) => r.level === 2 && Math.abs(r.eac_d) > 1).sort((x, y) => Math.abs(y.eac_d) - Math.abs(x.eac_d)).slice(0, 14);
    chart(mbox, { type: 'bar', data: { labels: cats.map((r) => r.code), datasets: [{ label: 'EAC movement', data: cats.map((r) => r.eac_d), backgroundColor: cats.map((r) => (r.eac_d > 0 ? PALETTE[1] : PALETTE[0])) }] }, options: { indexAxis: 'y', plugins: { legend: { display: false }, tooltip: { callbacks: { title: (it) => { const r = cats[it[0].dataIndex]; return `${r.code} ${r.name}`; }, label: (c) => fmt.money(c.parsed.x) } } } } });
  }
  run();
}

async function auditTab(body) {
  const a = await api.get(p('/audit'));
  body.append(a.length ? table([{ label: 'When', f: (x) => x.at }, { label: 'Action', f: (x) => x.action }, { label: 'Detail', cls: 'wrap', f: (x) => x.detail }], a, { maxHeight: '70vh' }) : empty('Nothing logged yet', 'Project creation, initialisation, unlocking and wiping are recorded here.'));
}
