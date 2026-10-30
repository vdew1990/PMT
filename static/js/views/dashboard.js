import { openMarginBridge, marginWord } from '../marginbridge.js';
import { h, clear, fmt, chart, PALETTE, badge, table, empty, select, tone, jumpTo, chartJump } from '../ui.js';
import { api, state, p, loadRows, isCompany } from '../api.js';
import { pickNode, pathTo, setScope } from '../scope.js';
import { go, render, openIn, isDirector } from '../app.js';
import { flowsCard } from '../flows.js';
import { monthForecastDialog } from '../monthforecast.js';
import { projectChart } from '../rollup.js';

const rgba = (hex, a) => { const n = parseInt(hex.slice(1), 16); return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a})`; };

export default async function dashboard(root) {
  const data = await loadRows();
  if (!data.rows.length || !state.project.initialised && !data.total.ctd) {
    root.append(onboarding());
    if (!data.total.allowance && !data.total.ctd) return;
  }
  const sc = state.scope;
  const q = new URLSearchParams();
  if (sc.node) q.set('node', sc.node);
  if (sc.from) q.set('frm', sc.from);
  if (sc.to) q.set('to', sc.to);
  const d = await api.get(p('/dashboard?' + q));
  const rows = data.rows;
  const isRoot = !sc.node;
  const k = d.kpi;

  // ---- header: scope bar --------------------------------------------------------------------
  const path = sc.node ? pathTo(rows, sc.node) : [];
  const crumbs = h('div', { class: 'crumbs' }, h('a', { onclick: () => { setScope(null); render(); } }, 'Whole project'));
  path.forEach((r, i) => {
    crumbs.append(h('span', { class: 'sep' }, '›'));
    crumbs.append(i === path.length - 1 ? h('b', {}, `${r.code} ${r.name}`) : h('a', { onclick: () => { setScope(r); render(); } }, `${r.code} ${r.name}`));
  });
  const gps = rows.filter((r) => r.level === 1);
  const grid = state.rows.grid;
  const mopts = [['', 'All']].concat(grid.map((m) => [m, fmt.month(m)]));
  const from = select(mopts, sc.from || '', { onchange: (e) => { sc.from = e.target.value || null; render(); } });
  const to = select(mopts, sc.to || '', { onchange: (e) => { sc.to = e.target.value || null; render(); } });
  root.append(h('div', { class: 'pagehead' },
    h('div', {}, h('h1', {}, 'Dashboard'), h('div', { class: 'sub' }, isRoot ? 'The whole contract. Choose a CBS scope to dive in; every figure and chart follows.' : `Deep dive: ${d.scope.code} ${d.scope.name}`)),
    h('div', { class: 'sp' }),
    h('div', { class: 'row' }, h('span', { class: 'small muted' }, 'Months'), from, h('span', { class: 'small muted' }, 'to'), to)));
  if (isDirector() && !state.project.is_parent) { const cx = await complexityCard(); if (cx) root.append(cx); }
  if (state.project.initialised && !state.project.is_parent) { const wn = await whatNext(); if (wn) root.append(wn); }
  root.append(h('div', { class: 'card', style: { marginBottom: '14px', padding: '10px 14px' } },
    h('div', { class: 'row' }, crumbs, h('span', { style: { flex: 1 } }),
      ...gps.map((g) => h('span', { class: 'chip' + (sc.node == g.id ? ' on' : ''), onclick: () => { setScope(g); render(); } }, g.code + ' ' + g.name.replace('Project ', '').replace('Materials & Equipment', 'Materials').replace('Expenses & Indirects', 'Expenses'))),
      h('button', { class: 'btn sm', onclick: () => pickNode({ title: 'Choose a CBS scope', allowRoot: true, selected: sc.node, showEac: true, onPick: (r) => { setScope(r); render(); } }) }, 'Pick any CBS level...'))));

  // ---- KPIs ---------------------------------------------------------------------------------
  const kpi = (l, v, s, cls = '', t = '', to = null) => jumpTo(h('div', { class: 'kpi ' + t }, h('div', { class: 'l' }, l), h('div', { class: 'v ' + cls }, v), s ? h('div', { class: 's' }, s) : null), to?.[0], to?.[1]);
  // where each tile and chart leads: the page holding the data behind it (in the dashboard's CBS scope)
  const cc = sc.node ? `#/costcontrol?node=${sc.node}` : '#/costcontrol';
  const TO = {
    budget: ['#/cbs', 'Open the CBS and allowances'], ctd: ['#/actuals', 'Open the actuals (invoices by supplier)'], acc: ['#/accruals', 'Open the accruals'],
    ctc: [sc.node ? `#/forecast?node=${sc.node}` : '#/forecast', 'Open the forecast lines'], eac: [cc, 'Open cost control'], cont: [cc, 'Open cost control (contingency by line)'],
    pos: ['#/commitments', 'Open the commitments (purchase orders)'], rev: ['#/revenue?tab=contract', 'Open the contract value'], claims: ['#/revenue?tab=claims', 'Open the progress claims'],
    margin: ['#/pmr', 'Open the PMR (board report)'], schedule: ['#/revenue?tab=schedule', 'Open the claim schedule'],
  };
  if (state.project.is_parent) {   // a parent: the figures open in the combined cost control, or on the child projects
    Object.keys(TO).forEach((x) => { TO[x] = [cc, 'Open the combined cost control: every line splits by project and opens in it']; });
    ['rev', 'claims', 'margin', 'schedule'].forEach((x) => { TO[x] = ['#/linked', 'Open the child projects']; });
  }
  const catNode = (g) => rows.find((r) => r.code === g);
  root.append(h('div', { class: 'grid g6' },
    isCompany() ? kpi('Allowance', fmt.m(k.allowance), `Budget ${fmt.m(k.budget)} + risk ${fmt.m(k.risk)}`, '', '', TO.budget) : kpi('Budget', fmt.m(k.allowance), 'Your allowance. The risk bucket is held by the company', '', '', TO.budget),
    kpi('Cost to date', fmt.m(k.ctd), k.spent_pct !== null ? `${fmt.pct(k.spent_pct, 0)} of allowance spent` : '', '', 't2', TO.ctd),
    kpi('Accruals', fmt.m(k.acc), 'Open accruals + unposted timesheets', '', 't3', TO.acc),
    kpi('Cost to complete', fmt.m(k.ctc), h('span', {}, 'Open POs ', h('a', { href: TO.pos[0], title: TO.pos[1] }, fmt.m(k.outstanding))), '', 't4', TO.ctc),
    kpi('EAC', fmt.m(k.eac), k.eac_pct_allowance !== null ? `${fmt.pct(k.eac_pct_allowance, 0)} of allowance` : '', '', 't5', TO.eac),
    kpi('Contingency', fmt.m(k.contingency), k.contingency < 0 ? 'Forecast overrun' : 'Headroom to allowance', tone(k.contingency), 't6', TO.cont)));

  if (isRoot && d.margin) {
    const m = d.margin;
    root.append(h('div', { class: 'grid g6', style: { marginTop: '14px' } },
      kpi('Revenue (recognised)', fmt.m(m.revenue_recognised), `Original ${fmt.m(m.revenue_original)}`, '', '', TO.rev),
      kpi('Original margin', fmt.pct(m.gp_original_pct), fmt.m(m.gp_original), '', 't2', TO.margin),
      kpi('Forecast margin', fmt.pct(m.gp_forecast_pct), fmt.m(m.gp_forecast), tone(m.erosion), 't3', TO.margin),
      kpi(marginWord(m.erosion), fmt.m(m.erosion), m.erosion >= 0 ? 'Above the original: click for why' : 'Below the original: click for why', tone(m.erosion), 't4', [() => openMarginBridge(), 'Open the margin bridge: revenue, allowance, and the overruns and underruns behind it']),
      kpi('Claimed to date', fmt.m(d.revenue.claimed_to_date), `Source: ${d.revenue.source}`, '', 't5', TO.claims),
      kpi('Accrual effect on EAC', fmt.m(m.accrual_effect), 'CMT-style EAC would omit this', '', 't6', TO.acc)));
  }

  if (isRoot && d.linked) {
    const chartBox = h('div');
    root.append(h('div', { class: 'card', style: { marginTop: '14px' } }, h('div', { class: 'ch' }, h('h2', {}, 'Project chart'), h('span', { class: 'sp' }),
      h('span', { class: 'small muted' }, 'Click the parent or a child for its cost control')), chartBox));
    projectChart(chartBox, { id: state.pid, kind: 'parent', name: state.project.name, sub: state.project.project_director ? `Director ${state.project.project_director}` : '',
      eac: k.eac, contingency: k.contingency, children: d.linked.map((c) => ({ id: c.id, kind: 'child', name: c.name, eac: c.eac, contingency: c.contingency,
        sub: (state.projects.find((x) => x.id === c.id) || {}).client_name || '' })) }, { current: state.pid });
    root.append(h('div', { class: 'card', style: { marginTop: '14px' } }, h('div', { class: 'ch' }, h('h2', {}, 'Child projects'), h('span', { class: 'sp' }),
      h('a', { class: 'small', href: '#/linked' }, 'Linked projects and the combined CBS')),
      h('div', { class: 'tw' }, h('table', { class: 't' }, h('thead', {}, h('tr', {}, ['Project', 'Status month', 'Allowance', 'CTD + accruals', 'CTC', 'EAC', 'Contingency'].map((x, i) => h('th', { class: i > 1 ? 'r' : '' }, x)))),
        h('tbody', {}, d.linked.map((c) => h('tr', { class: 'click', title: 'Open this project', onclick: () => openIn(c.id, 'dashboard') },
          h('td', {}, h('b', {}, c.name), c.error ? h('div', { class: 'small bad' }, c.error) : null), h('td', {}, fmt.month(c.status_month)),
          h('td', { class: 'r num' }, fmt.money(c.allowance)), h('td', { class: 'r num' }, fmt.money((c.ctd || 0) + (c.acc || 0))), h('td', { class: 'r num' }, fmt.money(c.ctc)),
          h('td', { class: 'r num' }, fmt.money(c.eac)), h('td', { class: 'r num ' + tone(c.contingency) }, fmt.money(c.contingency)))))))));
  }
  if (isRoot && state.project.parent_project_id) {   // a child: where it sits, click up to the parent or across
    const ln = await api.get(p('/linked')).catch(() => null);
    if (ln?.parent) {
      const chartBox = h('div');
      root.append(h('div', { class: 'card', style: { marginTop: '14px' } }, h('div', { class: 'ch' }, h('h2', {}, 'Project chart'), h('span', { class: 'sp' }),
        h('span', { class: 'small muted' }, 'This project is outlined. Click the parent or another child for its cost control')), chartBox));
      projectChart(chartBox, { id: ln.parent.id, kind: 'parent', name: ln.parent.name, sub: ln.parent.director ? `Director ${ln.parent.director}` : '',
        children: ln.children.map((c) => ({ id: c.id, kind: 'child', name: c.name, sub: c.pm ? `PM ${c.pm}` : '' })) }, { current: state.pid });
    }
  }
  if (!state.project.is_parent) root.append(await flowsCard(sc.node));

  // ---- charts row 1 -------------------------------------------------------------------------
  const curve = h('div', { class: 'chartbox tall' }); const bars = h('div', { class: 'chartbox tall' });
  root.append(h('div', { class: 'grid g2', style: { marginTop: '14px' } },
    h('div', { class: 'card' }, h('div', { class: 'ch' }, h('h2', {}, isRoot ? 'Cumulative cost and revenue' : 'Cumulative cost'), h('span', { class: 'sp' }), h('span', { class: 'small muted' }, 'Status month ' + fmt.month(d.status_month) + ' \u00B7 click a line to open its data')), curve),
    h('div', { class: 'card' }, h('div', { class: 'ch' }, h('h2', {}, d.scope.kind === 'project' ? 'Allowance against EAC by category' : 'Allowance against EAC, next level down'), h('span', { class: 'sp' }), h('span', { class: 'small muted' }, 'Click a bar to drill in')), bars)));

  const months = d.cost.months;
  const ds = [
    { label: 'Cost (actual + accrued)', data: d.cost.cum_actual, borderColor: PALETTE[0], backgroundColor: PALETTE[0], borderWidth: 2.5, pointRadius: 0, tension: .15, spanGaps: false },
    { label: 'Cost (forecast)', data: d.cost.cum_forecast, borderColor: PALETTE[0], borderDash: [6, 4], borderWidth: 2, pointRadius: 0, tension: .15 },
  ];
  if (isRoot && d.revenue) {
    ds.push({ label: 'Revenue (claimed)', data: d.revenue.cum_actual, borderColor: PALETTE[1], backgroundColor: PALETTE[1], borderWidth: 2.5, pointRadius: 0, tension: .15, spanGaps: false });
    ds.push({ label: 'Revenue (planned)', data: d.revenue.cum_total.map((v, i) => (d.revenue.months[i] >= d.status_month ? v : null)), borderColor: PALETTE[1], borderDash: [6, 4], borderWidth: 2, pointRadius: 0, tension: .15 });
  }
  ds.push({ label: 'Allowance', data: months.map(() => k.allowance), borderColor: PALETTE[2], borderDash: [2, 3], borderWidth: 2, pointRadius: 0 });
  chart(curve, { type: 'line', data: { labels: months.map(fmt.month), datasets: ds }, options: { interaction: { mode: 'index', intersect: false },
    ...chartJump(({ index, label }) => { location.hash = label.startsWith('Revenue') ? (label.includes('claimed') ? TO.claims[0] : TO.schedule[0]) : label === 'Allowance' ? TO.budget[0] : months[index] <= d.status_month ? TO.ctd[0] : `#/forecast?month=${months[index]}${sc.node ? '&scope=' + sc.node : ''}`; }) } });

  const kids = d.children.filter((c) => c.allowance || c.eac);
  chart(bars, {
    type: 'bar',
    data: { labels: kids.map((c) => c.code), datasets: [{ label: 'Allowance', data: kids.map((c) => c.allowance), backgroundColor: PALETTE[0] }, { label: 'EAC', data: kids.map((c) => c.eac), backgroundColor: PALETTE[1] }] },
    options: {
      ...chartJump(({ index }) => { const c = kids[index]; if (c.kind === 'group') { const r = rows.find((x) => String(x.id) === String(c.id)); setScope(r); render(); } else go('costcontrol', { node: c.id }); }),
      plugins: { tooltip: { callbacks: { title: (items) => { const c = kids[items[0].dataIndex]; return `${c.code} ${c.name}`; } } } },
    },
  });

  // ---- charts row 2 -------------------------------------------------------------------------
  const stack = h('div', { class: 'chartbox' }); const dough = h('div', { class: 'chartbox' }); const marg = h('div', { class: 'chartbox' });
  root.append(h('div', { class: 'grid g3', style: { marginTop: '14px' } },
    h('div', { class: 'card' }, h('div', { class: 'ch' }, h('h2', {}, 'Monthly cost by category'), h('span', { class: 'sp' }), h('span', { class: 'small muted' }, 'Click a past bar for cost control, a future bar for that month in the forecast')), stack),
    h('div', { class: 'card' }, h('div', { class: 'ch' }, h('h2', {}, 'Where the EAC sits'), h('span', { class: 'sp' }), h('span', { class: 'small muted' }, 'Click a slice to open it')), dough),
    h('div', { class: 'card' }, h('h2', {}, isRoot ? 'Profit: original, plan and forecast' : 'Status of lines in scope'), marg)));
  const si = months.findIndex((m) => m >= d.status_month);
  const gpOrder = ['PL', 'PS', 'PM', 'PE']; const gpName = { PL: 'Labour', PS: 'Subcontractors', PM: 'Materials', PE: 'Expenses' };
  chart(stack, {
    type: 'bar',
    data: { labels: months.map(fmt.month), datasets: gpOrder.filter((g) => d.by_gp[g]).map((g, i) => ({ label: gpName[g], data: d.by_gp[g], backgroundColor: (c) => (si >= 0 && c.dataIndex >= si ? rgba(PALETTE[i], .45) : PALETTE[i]) })) },
    options: { scales: { x: { stacked: true }, y: { stacked: true } },
      // a category's bar: that category in cost control (past months) or that month's forecast in a window (future months)
      ...chartJump(({ index, datasetIndex }) => { const g = gpOrder.filter((x) => d.by_gp[x])[datasetIndex]; const n = catNode(g);
        if (months[index] > d.status_month) return monthForecastDialog(months[index], n ? n.id : sc.node);
        location.hash = n ? `#/costcontrol?node=${n.id}` : cc; }) },
  });
  chart(dough, {
    type: 'doughnut',
    data: { labels: ['Cost to date', 'Accruals', 'Cost to complete'], datasets: [{ data: [Math.max(0, k.ctd), Math.max(0, k.acc), Math.max(0, k.ctc)], backgroundColor: [PALETTE[0], PALETTE[2], PALETTE[3]] }] },
    options: { cutout: '62%', plugins: { tooltip: { callbacks: { label: (c) => `${c.label}: ${fmt.money(c.parsed)}` } } }, ...chartJump(({ index }) => { location.hash = [TO.ctd, TO.acc, TO.ctc][index][0]; }) },
  });
  if (isRoot && d.margin) {
    const m = d.margin;
    chart(marg, { type: 'bar', data: { labels: ['Original', 'Revised plan', 'Forecast'], datasets: [{ label: 'Gross profit', data: [m.gp_original, m.gp_revised_plan, m.gp_forecast], backgroundColor: [PALETTE[0], PALETTE[2], PALETTE[1]] }] }, options: { plugins: { legend: { display: false } }, ...chartJump(() => { location.hash = TO.margin[0]; }) } });
  } else {
    const sc2 = d.status_counts;
    chart(marg, { type: 'bar', data: { labels: Object.keys(sc2), datasets: [{ label: 'Lines', data: Object.values(sc2), backgroundColor: [PALETTE[1], PALETTE[5], PALETTE[3], PALETTE[2]] }] }, options: { plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => `${c.parsed.y} lines` } } }, scales: { y: { ticks: { callback: (v) => v, precision: 0 } } }, ...chartJump(() => { location.hash = cc; }) } });
  }

  // ---- breakdown table + concentration ---------------------------------------------------------
  const cols = [
    { label: 'CBS', f: (c) => h('span', { class: 'mono' }, c.code) }, { label: 'Name', f: (c) => c.name },
    { label: 'Allowance', r: 1, f: (c) => fmt.money(c.allowance) }, { label: 'CTD', r: 1, f: (c) => fmt.money(c.ctd) }, { label: 'ACC', r: 1, f: (c) => fmt.money(c.acc) },
    { label: 'CTC', r: 1, f: (c) => fmt.money(c.ctc) }, { label: 'EAC', r: 1, f: (c) => fmt.money(c.eac) },
    { label: 'Contingency', r: 1, f: (c) => h('span', { class: tone(c.contingency) }, fmt.money(c.contingency)) },
    { label: 'Position', f: (c) => c.allowance ? h('div', { class: 'bar' + (c.eac > c.allowance ? ' bad' : ''), title: fmt.pct(c.eac / c.allowance, 0) }, h('i', { style: { width: Math.min(100, (c.eac / c.allowance) * 100) + '%' } })) : '' },
  ];
  root.append(h('div', { class: 'card', style: { marginTop: '14px' } },
    h('div', { class: 'ch' }, h('h2', {}, d.scope.kind === 'project' ? 'Categories' : 'Next level down'), h('span', { class: 'sp' }), d.scope.kind !== 'project' && sc.node ? h('button', { class: 'btn ghost sm', onclick: () => go('costcontrol', { node: sc.node }) }, 'Open in cost control') : null),
    d.children.length ? table(cols, d.children.filter((c) => c.allowance || c.eac || c.ctd), { onRow: (c) => { if (c.kind === 'group') { const r = rows.find((x) => String(x.id) === String(c.id)); setScope(r); render(); } else go('costcontrol', { node: c.id }); } }) : empty('Nothing below this level', 'This is a leaf line. Open it in cost control to see its forecast and transactions.')));

  const con = d.concentration;
  const ovr = (list, sign) => list.length ? h('div', {}, list.map((r) => h('div', { class: 'row', style: { margin: '5px 0', cursor: 'pointer', flexWrap: 'nowrap' }, onclick: () => go('costcontrol', { node: r.id }) },
    h('span', { class: 'mono', style: { width: '96px', flexShrink: 0 } }, r.code), h('span', { style: { flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }, title: r.name }, r.name),
    h('div', { class: 'bar' + (sign < 0 ? ' bad' : ''), style: { width: '120px', flexShrink: 0 } }, h('i', { style: { width: Math.min(100, Math.abs(r.contingency) / Math.abs(list[0].contingency) * 100) + '%', background: sign < 0 ? 'var(--bad)' : 'var(--good)' } })),
    h('span', { class: 'num ' + (sign < 0 ? 'bad' : 'good'), style: { width: '88px', textAlign: 'right', flexShrink: 0 } }, fmt.money(r.contingency))))) : h('div', { class: 'muted' }, 'None');
  root.append(h('div', { class: 'grid g2', style: { marginTop: '14px' } },
    h('div', { class: 'card' }, h('div', { class: 'ch' }, h('h2', {}, 'Overrun concentration'), h('span', { class: 'sp' }), badge(`${con.lines_over} lines, ${fmt.m(con.total_over)}`, 'bad')),
      h('div', { class: 'small muted', style: { marginBottom: '6px' } }, con.lines_over ? `Top 10 carry ${fmt.m(con.top10_over)} (${fmt.pct(con.total_over ? con.top10_over / con.total_over : 0, 0)} of the overrun)` : ''), ovr(d.top_over, -1)),
    h('div', { class: 'card' }, h('div', { class: 'ch' }, h('h2', {}, 'Underruns (headroom)'), h('span', { class: 'sp' }), badge(`${con.lines_under} lines, ${fmt.m(con.total_under)}`, 'good')),
      h('div', { class: 'small muted', style: { marginBottom: '6px' } }, 'Lines forecast below their allowance. Not released until the PM moves it.'), ovr(d.top_under, 1))));

  // ---- project-level side panels ------------------------------------------------------------
  if (isRoot) {
    const vs = d.variations, cl = d.claims;
    root.append(h('div', { class: 'grid g3', style: { marginTop: '14px' } },
      h('div', { class: 'card' }, h('div', { class: 'ch' }, h('h2', {}, 'Variations'), h('span', { class: 'sp' }), h('a', { href: '#/variations' }, 'Open register')),
        h('div', { class: 'row' }, badge(`${vs.open} open`, vs.open ? 'warn' : ''), badge(`${vs.total} total`), badge(`${fmt.m(vs.recognised_value)} recognised`, 'good')),
        h('div', { style: { marginTop: '10px' } }, Object.entries(vs.by_status).map(([s, x]) => h('div', { class: 'row', style: { justifyContent: 'space-between' } }, h('span', {}, s), h('span', { class: 'num' }, `${x.n} · ${fmt.money(x.value)}`))))),
      h('div', { class: 'card' }, h('div', { class: 'ch' }, h('h2', {}, 'Claims'), h('span', { class: 'sp' }), h('a', { href: '#/revenue' }, 'Open claims')),
        Object.keys(cl).length ? Object.entries(cl).map(([s, x]) => h('div', { class: 'row', style: { justifyContent: 'space-between', margin: '3px 0' } }, h('span', { style: { textTransform: 'capitalize' } }, s), h('span', { class: 'num' }, `${x.n} · ${fmt.money(x.amount)}`))) : h('div', { class: 'muted' }, 'No claims raised yet.'),
        h('div', { class: 'small muted', style: { marginTop: '8px' } }, `Contract: original ${fmt.m(d.contract.original)}, recognised ${fmt.m(d.contract.recognised)}`)),
      h('div', { class: 'card' }, h('div', { class: 'ch' }, h('h2', {}, 'Next milestones'), h('span', { class: 'sp' }), h('a', { href: '#/programme' }, 'Project schedule')),
        d.milestones.length ? d.milestones.map((m) => h('div', { class: 'row', style: { justifyContent: 'space-between', margin: '3px 0' } }, h('span', {}, m.name), h('span', { class: 'num muted' }, fmt.date(m.forecast_end || m.baseline_end)))) : h('div', { class: 'muted' }, 'No upcoming milestones. Add the project schedule on the setup page.'))));
  }
  // ---- data health ------------------------------------------------------------------------
  const hl = await api.get(p('/health'));
  const issues = hl.filter((x) => x.level !== 'ok');
  root.append(h('div', { class: 'card', style: { marginTop: '14px' } },
    h('div', { class: 'ch' }, h('h2', {}, 'Data health'), h('span', { class: 'sp' }), badge(`${hl.filter((x) => x.level === 'error').length} errors`, 'bad'), badge(`${hl.filter((x) => x.level === 'warn').length} warnings`, 'warn'), badge(`${hl.filter((x) => x.level === 'ok').length} passed`, 'good')),
    issues.length ? issues.map((i) => h('div', { class: 'row', style: { margin: '4px 0', flexWrap: 'nowrap', alignItems: 'flex-start' } },
      badge(i.level === 'error' ? 'Error' : 'Check', i.level === 'error' ? 'bad' : 'warn'),
      h('div', { style: { flex: 1 } }, h('b', {}, i.title, i.count ? ` (${i.count})` : ''), h('div', { class: 'small muted' }, i.detail)),
      i.link ? (() => {
        const page = ({ cbs: 'cbs', pronto: 'pronto', costcontrol: 'costcontrol', accruals: 'accruals', reconcile: 'reconcile', allowance: 'cbs', claims: 'revenue' }[i.link.split('?')[0]] || 'dashboard');
        const qs = i.link.includes('?') ? i.link.split('?')[1] : '';
        // a parent's check belongs to a child project: open it there
        return i.project_id ? h('a', { onclick: () => openIn(i.project_id, page, qs ? Object.fromEntries(new URLSearchParams(qs)) : null) }, 'Open in project')
          : h('a', { href: '#/' + page + (qs ? '?' + qs : '') }, 'Open');
      })() : null)) : h('div', { class: 'good' }, 'All checks pass.')));
}

function onboarding() {
  const step = (n, t, s, link) => h('a', { href: link, style: { textDecoration: 'none' } }, h('div', { class: 'kpi', style: { cursor: 'pointer' } }, h('div', { class: 'l' }, 'Step ' + n), h('div', { class: 'v', style: { fontSize: '16px', whiteSpace: 'normal' } }, t), h('div', { class: 's' }, s)));
  return h('div', { class: 'card', style: { marginBottom: '16px' } }, h('h2', {}, 'Get started'),
    h('p', { class: 'muted' }, 'This dashboard fills in as the project is set up. Work through the steps in order.'),
    h('div', { class: 'grid g3' },
      step(1, 'Project', 'Identity and dates', '#/setup?step=project'),
      step(2, 'Contract value', 'Payment Milestones', '#/setup?step=contract'),
      step(3, 'CBS and allowances', 'Structure and proposal allowances', '#/setup?step=cbs'),
      step(4, 'Project schedule', 'Baseline milestones and phases', '#/setup?step=programme'),
      step(5, 'Pronto data', 'Only if Pronto already has cost', '#/setup?step=pronto'),
      step(6, 'Allowance', 'Link resources to allowance buckets', '#/setup?step=allowance'),
      step(7, 'Initialise', 'Check, then lock the baseline', '#/setup?step=initialise')));
}

// After Initialise: what to do next, from the project's own state. It goes away when the first month is closed or when it is dismissed.
async function whatNext() {
  const key = 'pmt.whatnext.' + state.pid;
  try { if (localStorage.getItem(key) === 'off') return null; } catch (e) { /* storage may be blocked */ }
  const me = await api.get(p('/month-end')).catch(() => null); if (!me) return null;
  if (me.items.find((x) => x.key === 'close')?.state === 'done' && !sessionStorage.getItem('whatnext')) return null;
  const pre = (await api.get(p('/preflight')).catch(() => ({ items: [] }))).items;
  const get = (k) => pre.find((x) => x.key === k);
  const todo = [
    [get('resources')?.count ? `Link ${get('resources').count} resources to allowance buckets` : null, 'setup', { step: 'allowance' }],
    [get('parked')?.state === 'warn' ? `Allocate the ${fmt.m(get('parked').amount)} parked on pools to lines` : null, 'costcontrol', {}],
    [get('methods')?.count ? 'Check the forecast method on each line' : null, 'costcontrol', {}],
    ['Close the first month when Pronto is loaded', 'monthend', {}]].filter((x) => x[0]);
  const dismiss = () => { try { localStorage.setItem(key, 'off'); } catch (e) { /* ignore */ } sessionStorage.removeItem('whatnext'); render(); };
  return h('div', { class: 'card', style: { marginBottom: '14px' } }, h('div', { class: 'ch' }, h('h2', {}, 'What next'), h('span', { class: 'sp' }), h('a', { onclick: dismiss }, 'Dismiss')),
    h('div', { class: 'small muted', style: { marginBottom: '6px' } }, 'The project is initialised. These are the next jobs, in order.'),
    ...todo.map(([t, page, params], i) => h('div', { class: 'row', style: { gap: '10px', padding: '5px 0' } }, h('b', { class: 'muted' }, String(i + 1)), h('a', { onclick: () => go(page, params) }, t))));
}

// For the project director: the baseline they set, what the PM has assessed since, and the client's difficulty. The PM never sees the baseline.
async function complexityCard() {
  const c = await api.get(p('/complexity')).catch(() => null);
  if (!c || !c.director) return null;
  const rows = c.assessments.filter((r) => r.total != null); const b = c.baseline; const last = rows[rows.length - 1];
  const kpi = (l, v, s, cls = '') => h('div', { class: 'kpi' }, h('div', { class: 'l' }, l), h('div', { class: 'v ' + cls, style: { fontSize: '20px' } }, v), s ? h('div', { class: 's' }, s) : null);
  const diffs = c.assessments.filter((r) => r.pm_difficulty).map((r) => r.pm_difficulty);
  return h('div', { class: 'card', style: { marginBottom: '14px', cursor: 'pointer' }, title: 'Open Project complexity', onclick: () => go('complexity', { tab: last ? 'pm' : 'baseline' }) },
    h('div', { class: 'ch' }, h('h2', {}, 'Project complexity'), h('span', { class: 'sp' }), h('a', {}, 'Open')),
    h('div', { class: 'grid g4' },
      kpi('Your baseline', b ? `${b.total} points` : 'Not set', b ? b.band : 'Set it on Project complexity'),
      kpi('PM\'s latest assessment', last ? `${last.total} points` : 'None yet', last ? `${fmt.month(last.month)}, ${last.band}` : 'The PM scores it each month-end', last && b ? tone(b.total - last.total) : ''),
      kpi('Against your baseline', last && b ? `${last.total - b.total > 0 ? '+' : ''}${last.total - b.total}` : 'n/a', last && b ? (last.total - b.total > 0 ? 'The PM sees it harder than you did' : last.total - b.total < 0 ? 'The PM sees it easier than you did' : 'Same as your baseline') : '', last && b ? tone(b.total - last.total) : ''),
      kpi('Client difficulty', diffs.length ? `${diffs[diffs.length - 1]} of 5` : 'n/a', diffs.length > 1 ? (diffs[diffs.length - 1] > diffs[0] ? `Up from ${diffs[0]} at the first assessment` : diffs[diffs.length - 1] < diffs[0] ? `Down from ${diffs[0]} at the first assessment` : 'Unchanged since the first assessment') : 'From the PM\'s assessments')));
}
