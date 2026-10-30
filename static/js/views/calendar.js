import { h, clear, fmt, toast, select, num, badge, empty, field, modal, table } from '../ui.js';
import { api, state, p, loadRows, pref } from '../api.js';
import { go, render } from '../app.js';
import { pickNode, pathTo } from '../scope.js';
import { historyDialog } from '../history.js';
import { outlineState, outlineStrip, DAY_LEVELS } from '../outline.js';

// FORECAST > Labour calendar: per person (or supplier crew) per day, the hours in Pronto timesheets, the hours
// accrued, and the hours forecast. Type hours to forecast future days or to accrue past ones.
const DOW = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const addDays = (s, n) => { const d = new Date(s + 'T00:00:00'); d.setDate(d.getDate() + n); return iso(d); };
const monday = (s) => { const d = new Date(s + 'T00:00:00'); d.setDate(d.getDate() - ((d.getDay() + 6) % 7)); return iso(d); };
const n1 = (v) => (v ? String(Math.round(v * 100) / 100) : ''); // hours keep their decimals (7.6 h, 11.4 h)

export default async function calendarView(root, params) {
  const sd = state.project.status_date || iso(new Date());
  const ui = JSON.parse(sessionStorage.getItem('calui') || '{}');
  ui.start = params.start || ui.start || monday(addDays(sd, -14));
  ui.weeks = +(params.weeks || ui.weeks || pref('cal_weeks')); ui.kind = params.kind ?? ui.kind ?? pref('cal_kind');
  ui.node = params.node ?? ui.node ?? ''; ui.nodeLabel = ui.nodeLabel || '';
  ui.span = ui.span || (pref('cal_project') ? 'project' : 'window');
  const save = () => sessionStorage.setItem('calui', JSON.stringify(ui));
  save();
  // whole project: from the first to the last month of the project, each month collapsed to a column except the open ones
  const SM = sd.slice(0, 7);
  const pStart = ((state.project.project_start || '') || addDays(sd, -180)).slice(0, 7) + '-01';
  const pEndM = ((state.project.project_end || '') || addDays(sd, 365)).slice(0, 7);
  const pEnd = addDays(new Date(+pEndM.slice(0, 4), +pEndM.slice(5, 7), 1).toISOString().slice(0, 10), -1);
  const projectDays = Math.min(1500, Math.round((new Date(pEnd) - new Date(pStart)) / 864e5) + 1);
  if (!Array.isArray(ui.open)) ui.open = [SM];
  const q = ui.span === 'project' ? new URLSearchParams({ start: pStart, days: String(projectDays) }) : new URLSearchParams({ start: ui.start, days: String(ui.weeks * 7) }); if (ui.kind) q.set('kind', ui.kind); if (ui.node) q.set('node', ui.node);
  const [cal, resources] = await Promise.all([api.get(p('/calendar?' + q)), api.get(p('/resources'))]);
  const days = []; for (let d = cal.start; d <= cal.end; d = addDays(d, 1)) days.push(d);

  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, 'Labour calendar'),
    h('div', { class: 'sub' }, `Hours per day, coloured like the Cost Control sheet. Status date ${fmt.date(sd)}: days up to it hold timesheets and accruals, days after it are forecast.`)),
  h('div', { class: 'sp' }), h('button', { class: 'btn ghost', onclick: () => go('forecast') }, 'Forecast lines')));

  const chip = (k, v, label) => h('span', { class: 'chip' + (ui[k] === v ? ' on' : ''), onclick: () => { ui[k] = v; save(); render(); } }, label);
  const nav = (n) => { ui.start = addDays(ui.start, n); save(); render(); };
  root.append(h('div', { class: 'card', style: { padding: '10px 14px', marginBottom: '12px' } },
    h('div', { class: 'row' }, h('button', { class: 'btn ghost sm', onclick: () => { ui.span = 'window'; nav(-7 * Math.max(1, Math.floor(ui.weeks / 2))); } }, '◀'),
      h('input', { type: 'date', value: ui.start, onchange: (e) => { ui.start = monday(e.target.value); save(); render(); } }),
      h('button', { class: 'btn ghost sm', onclick: () => nav(7 * Math.max(1, Math.floor(ui.weeks / 2))) }, '▶'),
      h('button', { class: 'btn ghost sm', onclick: () => { ui.start = monday(addDays(sd, -14)); save(); render(); } }, 'Around the status date'),
      select([[2, '2 weeks'], [4, '4 weeks'], [6, '6 weeks'], [9, '9 weeks'], [13, '13 weeks']], ui.weeks, { onchange: (e) => { ui.weeks = +e.target.value; ui.span = 'window'; save(); render(); } }),
      h('span', { class: 'chip' + (ui.span === 'project' ? ' on' : ''), title: 'Scroll through the whole project: one column per month, open a month to see its days (the current month is open to start with)', onclick: () => { ui.span = ui.span === 'project' ? 'window' : 'project'; save(); render(); } }, 'Whole project by month'),
      h('span', { style: { width: '10px' } }), chip('kind', '', 'Everyone'), chip('kind', 'employee', 'Employees'), chip('kind', 'supplier', 'Suppliers'),
      h('button', { class: 'btn ghost sm', onclick: () => pickNode({ allowRoot: true, kinds: ['group', 'line'], onPick: (r) => { ui.node = r ? String(r.node_id) : ''; ui.nodeLabel = r ? `${r.code} ${r.name}` : ''; save(); render(); } }) }, ui.node ? 'CBS: ' + ui.nodeLabel : 'Whole project')),
    h('div', { class: 'row', style: { marginTop: '8px' } }, h('button', { class: 'btn ghost sm', title: 'For every day in view up to the status date with a timesheet not yet accrued (Pronto unposted, or a subcontractor timesheet): accrue those hours', onclick: () => accrueUnposted() }, 'Accrue all timesheets in view not yet accrued'),
      h('span', { class: 'small muted', style: { marginLeft: '10px' } }, 'Subcontractor timesheets:'), h('button', { class: 'btn ghost sm', onclick: () => window.open(p('/sub-timesheets/template.xlsx')) }, 'Download template'), h('button', { class: 'btn ghost sm', onclick: () => uploadSubTs() }, 'Upload...'),
      h('span', { class: 'small muted', style: { marginLeft: '10px' } }, '3-week lookahead:'), h('button', { class: 'btn ghost sm', title: 'Pre-filled with the current supplier forecast, from the Monday after the status date', onclick: () => window.open(p('/lookahead/template.xlsx')) }, 'Download template'), h('button', { class: 'btn ghost sm', onclick: () => uploadLookahead() }, 'Upload...'),
      h('span', { class: 'sp', style: { flex: 1 } }), h('button', { class: 'btn sm', onclick: () => addPerson(resources) }, '+ Add someone to forecast'))));

  // unassigned pools: forecast held at role or supplier level, not yet given to a named person
  // part: 'pools' = only the unassigned pools, 'grid' = only the calendar (each can be opened in a window of its own)
  const part = params.part || '';
  const ownWindow = (pt) => { const w = window.open(location.pathname + '?popout=1#/calendar?part=' + pt, '_blank', 'popup=yes,width=1500,height=900'); if (!w) toast('The browser blocked the new window. Allow pop-ups for PMT and try again.', 'bad'); };
  if (part === 'pools') document.querySelector('.pagehead h1').textContent = 'Unassigned pools';
  if (!part) root.querySelector('.pagehead .sp')?.after(h('button', { class: 'btn ghost', title: 'Only the calendar, in a window of its own (live)', onclick: () => ownWindow('grid') }, '\u29C9 Calendar in its own window'));
  if ((cal.pools || []).length && part !== 'grid') {
    root.append(h('div', { class: 'card', style: { marginBottom: '12px', background: '#fffaf0' } },
      h('div', { class: 'ch' }, h('h2', {}, 'Unassigned pools'), h('span', { class: 'small muted' }, 'Forecast held for a role or supplier but not yet given to anyone. Click an amount to change it where it was set, or assign hours to a person to tie it out.')),
      h('div', { class: 'tw' }, h('table', { class: 't' }, h('thead', {}, h('tr', {}, ['Pool', 'How it is forecast', 'Unassigned left', 'Allocated to people', ''].map((x, i) => h('th', { class: i === 2 || i === 3 ? 'r' : '' }, x)))),
        h('tbody', {}, cal.pools.map((x) => h('tr', {},
          h('td', {}, h('span', { class: 'mono' }, x.code), ' ', x.name),
          h('td', {}, h('span', { class: 'badge' }, x.method || 'AT-BUDGET'), x.hours ? h('span', { class: 'small muted' }, ` ${n1(x.hours)} h`) : null),
          h('td', { class: 'r num drillable', title: 'Open the pool where its forecast is set', onclick: () => go('forecast', { node: x.id }) }, h('b', {}, fmt.money(x.ctc))),
          h('td', { class: 'r num' }, x.drawn ? fmt.money(x.drawn) : ''),
          h('td', {}, h('span', { class: 'row', style: { gap: '4px' } }, h('button', { class: 'btn sm', onclick: () => assignFromPool(x) }, 'Assign hours to someone'),
            h('button', { class: 'btn ghost sm', onclick: () => go('forecast', { node: x.id }) }, 'Edit pool'), h('button', { class: 'btn ghost sm', onclick: () => go('costcontrol', { open: x.id }) }, 'Cost control'))))))))));
  }

  const poolCard = [...root.children].reverse().find((e) => e.querySelector && [...e.querySelectorAll('h2')].some((x) => x.textContent === 'Unassigned pools'));
  if (poolCard) {
    const was = localStorage.getItem('calPoolsShut');
    let shut = part !== 'pools' && (was === null ? !!pref('cal_pools_shut') : was === '1');
    const ch = poolCard.querySelector('.ch');
    const rest = () => [...poolCard.children].filter((e) => e !== ch);
    const tog = h('span', { class: 'tog', style: { cursor: 'pointer', marginRight: '6px' }, title: 'Show or hide the pools' });
    const set = () => { tog.textContent = shut ? '\u25B8' : '\u25BE'; rest().forEach((e) => { e.style.display = shut ? 'none' : ''; }); const sm = ch.querySelector('.small.muted'); if (sm) sm.style.display = shut ? 'none' : ''; };
    tog.onclick = () => { shut = !shut; localStorage.setItem('calPoolsShut', shut ? '1' : '0'); set(); };
    ch.prepend(tog);
    if (part !== 'pools') ch.append(h('button', { class: 'btn ghost sm', style: { marginLeft: 'auto' }, title: 'Only the pools, in a window of its own (live)', onclick: () => ownWindow('pools') }, '\u29C9 Own window'));
    set();
  }
  if (part === 'pools') return;
  if (!cal.rows.length) {
    root.append(empty('Nobody in this period', 'Timesheets from the Pronto labour export, hour accruals and forecast calendars or rosters with a person or supplier show here.', h('button', { class: 'btn', onclick: () => addPerson(resources) }, '+ Add someone to forecast')));
    return;
  }
  const M = cal.status_month || sd.slice(0, 7);
  // ---- saving: every change is saved on its own, a moment after you leave the cell ------------------
  const queue = new Map(); // `${kind}|${rowKey}|${target}` -> {kind, row, target, days}
  let timer = null;
  const status = h('span', { class: 'small muted' });
  const enqueue = (kind, r, target, d, v) => {
    const k = `${kind}|${r.key}|${target}`;
    const e = queue.get(k) || { kind, r, target, days: {} };
    e.days[d] = v; queue.set(k, e);
    status.textContent = 'Saving...';
    clearTimeout(timer); timer = setTimeout(flush, 600);
  };
  async function flush() {
    const jobs = [...queue.values()]; queue.clear();
    try {
      for (const j of jobs) {
        if (j.kind === 'f') await api.put(p(`/items/${j.target}/days`), { days: j.days });
        else await api.post(p('/accruals/hours'), { resource_id: j.r.resource_id, node_id: j.target, days: j.days, role: j.r.role, workers: Object.fromEntries(Object.keys(j.days).map((d) => [d, (j.r.d[d] || {}).w || 1])) });
      }
      status.textContent = `Saved ${new Date().toLocaleTimeString()}`;
      if (!document.activeElement || !document.activeElement.closest('.lc')) render();
    } catch (err) { status.textContent = ''; toast(err.message, 'bad'); render(); }
  }
  window.addEventListener('hashchange', () => { if (queue.size) flush(); }, { once: true });

  // ---- header -------------------------------------------------------------------------------
  // ---- the outline: months and weeks fold to one summary column each; the strip above the grid has the brackets, rings and the 1 2 3 levels ----
  const allMonths = [...new Set(days.map((d) => d.slice(0, 7)))];
  const ost = outlineState('cal-' + (ui.span === 'project' ? 'p' : 'w'), { folded: ui.span === 'project' ? allMonths.filter((m) => m !== SM).map((m) => `0:${m}`) : [] });   // the whole project opens with only the current month unfolded
  const foldedK = new Set(ost.folded || []);
  const wkKey = (d) => DAY_LEVELS[1].key({ id: d }); const wkLabel = (d) => DAY_LEVELS[1].label({ id: d });
  const groupOf = (d) => { const mk = `0:${d.slice(0, 7)}`; if (foldedK.has(mk)) return { k: 0, key: d.slice(0, 7), gk: mk }; const wk = `1:${wkKey(d)}`; if (foldedK.has(wk)) return { k: 1, key: wkKey(d), gk: wk }; return null; };
  const cols = [];
  days.forEach((d) => { const g = groupOf(d); if (!g) { cols.push({ d }); return; } const last = cols[cols.length - 1]; if (last && last.sum && last.sum.gk === g.gk) last.ds.push(d); else cols.push({ sum: g, ds: [d], m: d.slice(0, 7) }); });
  const setFolded = (fn) => { const s2 = new Set(ost.folded || []); fn(s2); ost.folded = [...s2]; ost.save(); render(); };
  const openGroup = (gk) => setFolded((s2) => s2.delete(gk));
  const toggleMonth = (m) => setFolded((s2) => { const gk = `0:${m}`; if (s2.has(gk)) s2.delete(gk); else s2.add(gk); });
  const months = allMonths.map((m) => ({ m, folded: foldedK.has(`0:${m}`), n: cols.filter((c) => (c.d ? c.d.slice(0, 7) : c.sum.k === 1 ? c.ds[0].slice(0, 7) : '') === m).length }));
  const th1 = h('tr', {}, h('th', { class: 'sticky1', style: { left: 0, zIndex: 4 }, rowSpan: 2 }, 'Person / crew'), h('th', { rowSpan: 2 }, 'Forecast on / accrue to'),
    ...months.map((x) => (!x.folded
      ? (x.n ? h('th', { colSpan: x.n, class: 'mth ' + (x.m < M ? 'mp' : x.m === M ? 'mc' : 'mf'), 'data-m': x.m },
        fmt.month(x.m) + (x.m === M ? '  (current: forecast above, landed below)' : x.m < M ? '  (past)' : '  (forecast)')) : null)
      : h('th', { rowSpan: 2, class: 'mth mcol ' + (x.m < M ? 'mp' : x.m === M ? 'mc' : 'mf'), 'data-m': x.m, 'data-col': days.find((d) => d.startsWith(x.m)), 'data-sum': `0:${x.m}`, 'data-tip': `${fmt.month(x.m)} (${days.filter((d) => d.startsWith(x.m)).length} days) \u00b7 click to open`, title: 'Open this month to see its days', style: { cursor: 'pointer' }, onclick: () => toggleMonth(x.m) }, h('div', {}, '\u25B8'), fmt.month(x.m)))),
    ...['Timesheets', 'Accrued', 'Forecast', 'Forecast $'].map((x) => h('th', { class: 'r', rowSpan: 2 }, x)));
  const dayTh = (d) => { const wd = new Date(d + 'T00:00:00').getDay(); return h('th', { class: 'dh' + (wd === 0 || wd === 6 ? ' we' : '') + (cal.holidays[d] ? ' hol' : '') + (d === sd ? ' sd' : ''), 'data-col': d, title: (cal.holidays[d] || '') + (d === sd ? ' Status date' : '') }, h('div', {}, DOW[wd]), h('div', {}, +d.slice(8))); };
  const th2 = h('tr', {}, cols.filter((c) => !(c.sum && c.sum.k === 0)).map((c) => (c.d ? dayTh(c.d)
    : h('th', { class: 'dh wk', 'data-col': c.ds[0], 'data-sum': c.sum.gk, 'data-tip': `${wkLabel(c.ds[0])} (${c.ds.length} days) \u00b7 click to open`, title: 'Open this week to see its days', style: { cursor: 'pointer' }, onclick: () => openGroup(c.sum.gk) }, h('div', {}, '\u25B8'), h('div', {}, +c.ds[0].slice(8))))));
  const tb = h('tbody');
  const dayTot = Object.fromEntries(days.map((d) => [d, { landed: 0, f: 0 }]));
  const landedOf = (c) => (c.a || 0) + Math.max(c.t || 0, c.x || 0); // a timesheet and its accrual are the same hours

  cal.rows.forEach((r) => {
    const calItems = r.items.filter((i) => i.spread === 'Calendar' && i.basis === 'hours');
    const roster = r.items.find((i) => i.spread === 'Roster');
    const itemSel = calItems.length > 1 ? select(calItems.map((i) => [i.item_id, `${i.code} ${i.scope || ''}`]), calItems[0].item_id, { title: 'Forecast hours typed in this row go to this calendar' }) : null;
    const lineSel = r.lines.length > 1 ? select(r.lines.map((l) => [l.node_id, l.code]), r.lines[0].node_id, { title: 'Hours accrued in this row go to this CBS line' }) : null;
    const itemId = () => (itemSel ? +itemSel.value : calItems[0]?.item_id);
    const lineId = () => (lineSel ? +lineSel.value : r.lines[0]?.node_id);
    const who = h('td', { class: 'sticky1 who', style: { left: 0 }, rowSpan: 2 }, h('b', {}, r.name || r.code),
      h('div', { class: 'small muted' }, r.kind === 'pool' ? 'Unassigned pool, by role' : [r.kind === 'supplier' ? 'Supplier' : r.code, r.role || r.function].filter(Boolean).join(' · ')),
      r.from_pool && r.kind !== 'pool' ? h('div', { class: 'small', style: { color: 'var(--warn)' } }, 'taken from a pool') : null);
    const fcWhere = calItems.length ? (itemSel || h('a', { onclick: () => go('forecast', { node: calItems[0].node_id, item: calItems[0].item_id }), title: 'Open this calendar on its line' }, `${calItems[0].code}`))
      : roster ? h('a', { onclick: () => go('forecast', { node: roster.node_id, item: roster.item_id }) }, `${roster.code} roster`) : h('button', { class: 'btn ghost sm', onclick: () => newCalendarItem(r) }, '+ calendar');
    const accWhere = r.kind === 'pool' ? '' : r.lines.length ? (lineSel || h('span', { class: 'mono' }, r.lines[0].code)) : h('button', { class: 'btn ghost sm', onclick: () => pickNode({ kinds: ['line'], onPick: (n) => { r.lines = [{ node_id: n.node_id, code: n.code }]; render(); } }) }, 'line for accruals');
    const what = h('td', { class: 'small what', rowSpan: 2 }, h('div', {}, h('span', { class: 'muted' }, 'F '), fcWhere), h('div', { style: { marginTop: '4px' } }, h('span', { class: 'muted' }, 'A '), accWhere),
      r.kind === 'supplier' ? h('div', { style: { marginTop: '4px' } }, h('a', { title: 'Give this month\'s accruals the subcontractor\'s invoice number: they reverse when that invoice lands in Pronto', onclick: () => invoiceRef(r) }, 'Invoice ref...')) : null);
    const top = h('tr', { class: 'rt' }, who, what); const bot = h('tr', { class: 'rb' });

    // a forecast cell: green, typed straight in after the status date
    const fcCell = (d, c, dark, span) => {
      const td = h('td', { class: 'cd ' + (dark ? 'fcd' : 'fcl') + dayCls(d), rowSpan: span, title: tipOf(d, c) });
      if (d > sd && calItems.length) {
        splitCell(td, c.f || 0, c.f_ot || 0, '', (nt, ot) => {
          const it = calItems.find((i) => i.item_id === itemId()) || calItems[0];
          const total = nt + ot;
          const v = !total ? null : it.basis === 'people' ? { qty: total / (it.hours_day || 10), ot } : { nt, ot };
          enqueue('f', r, itemId(), d, v);
        });
      } else {
        td.append(h('span', { class: 'v' }, n1(c.f)));
        if (d > sd) td.onclick = () => (roster ? go('forecast', { node: roster.node_id, item: roster.item_id }) : r.kind !== 'pool' && newCalendarItem(r));
      }
      return td;
    };
    // a landed cell. Posted timesheet hours are never editable; only your own accrual is:
    // light blue with no timesheet: type straight in; purple (timesheet + accrual that differs): click to adjust the accrual
    const landedCell = (d, c, dark, span) => {
      const posted = c.a || 0, unposted = c.t || 0, acc = c.acc || 0;
      const past = d <= sd;
      const todo = past && c.f > 0 && !posted && !unposted && !acc;
      const canAccrue = past && r.kind !== 'pool';
      const inline = canAccrue && !posted;   // light blue (incl. unposted timesheets): create, change or clear the accrual
      const td = h('td', { class: 'cd ' + (c.st ? 'st-' + c.st : dark ? 'acd' : 'acl') + (todo ? ' todo' : '') + dayCls(d), rowSpan: span, title: tipOf(d, c) });
      if (inline) {
        const hint = unposted ? n1(unposted) : todo ? n1(c.f) : '';
        const title = (unposted && r.kind === 'supplier' ? `The subcontractor's timesheet shows ${n1(unposted)} h (${c.w || 1} worker(s)). ${acc ? 'Your accrual stands until their invoice lands in Pronto.' : 'Type the hours to accrue them (priced from their rates, overtime per worker).'}`
            : unposted ? `Pronto has ${n1(unposted)} h entered, not posted yet (no cost rate until approved). ${acc ? 'Your accrual stands until the timesheet is posted.' : 'Until you accrue it, it is accrued automatically at the person\'s cost rate. Type the hours to accrue them yourself.'}`
            : todo ? `Forecast was ${n1(c.f)} h and nothing has landed: type the hours to accrue them` : acc ? 'Your accrual: change or clear it' : 'Type hours to accrue');
        td.title = title + '\n' + td.title;
        splitCell(td, acc, c.acc_ot || 0, hint, (nt, ot) => {
          if (!lineId()) { toast('Choose the CBS line to accrue to first (column on the left)', 'bad'); return false; }
          enqueue('a', r, accLine(d) || lineId(), d, nt + ot ? { nt, ot } : null);
        }, unposted ? () => h('span', { class: 'unmini', title: r.kind === 'supplier' ? `Subcontractor timesheet: ${c.w || 1} worker(s)` : 'Entered in Pronto, not yet posted' }, (r.kind === 'supplier' ? 'T ' : 'P ') + n1(unposted)) : null,
        unposted || todo ? splitOf(unposted || c.f, unposted ? (r.kind === 'supplier' ? 'From their timesheet' : 'From Pronto (not posted). Auto-accrued until you change it') : 'From the forecast', unposted ? 0 : c.f_ot) : null);
      } else if (posted || unposted) {
        td.append(h('span', { class: 'v' + (unposted && !posted ? ' un' : '') }, n1(posted + unposted)));
        if (c.st === 'hybrid') td.append(h('span', { class: 'accmini', title: 'Your accrual' }, n1(acc)));
        td.style.cursor = 'pointer';
        td.onclick = () => dayDetail(r, d, c, canAccrue && c.st === 'hybrid', accLine(d) || lineId());
      }
      return td;
    };
    const accLine = (d) => (r.accruals[d] || [])[0]?.node_id;
    // hours split into normal time and overtime: above the normal hours a day (Settings) is overtime
    const splitOf = (hrs, note, ot = null) => { const nd = +(state.project.settings?.normal_hours_day) || 8; const o = ot != null && ot > 0 ? ot : Math.max(0, hrs - nd); return { nt: hrs - o, ot: o, note }; };
    // a collapsed month: its landed hours (past), its forecast (future), both for the current month; click to open it
    const monthCell = (label, ds, what, dark, span, open) => {
      let v = 0;
      ds.forEach((d) => { const c = r.d[d]; if (c) v += what === 'f' ? (c.f || 0) : landedOf(c); });
      return h('td', { class: 'cd mcell ' + (what === 'f' ? (dark ? 'fcd' : 'fcl') : (dark ? 'acd' : 'acl')), rowSpan: span, title: `${label}: ${what === 'f' ? 'forecast' : 'landed'} ${n1(v) || 0} h. Click to open it.`, style: { cursor: 'pointer' }, onclick: open },
        h('span', { class: 'v' }, n1(v)));
    };
    days.forEach((d) => { const c = r.d[d]; if (c) { dayTot[d].landed += landedOf(c); dayTot[d].f += c.f || 0; } });
    cols.forEach((col) => {
      if (col.sum) {   // a folded month or week: its landed hours (all in the past), its forecast (all after the status date), or both
        const first = col.ds[0]; const last = col.ds[col.ds.length - 1];
        const label = col.sum.k === 0 ? fmt.month(col.sum.key) : wkLabel(first); const open = col.sum.k === 0 ? () => toggleMonth(col.sum.key) : () => openGroup(col.sum.gk);
        if (last <= sd) top.append(monthCell(label, col.ds, 'a', false, 2, open));
        else if (first > sd) top.append(monthCell(label, col.ds, 'f', false, 2, open));
        else { top.append(monthCell(label, col.ds, 'f', true, 1, open)); bot.append(monthCell(label, col.ds, 'a', true, 1, open)); }
        return;
      }
      const d = col.d;
      const c = r.d[d] || { a: 0, t: 0, x: 0, xr: 0, f: 0, fc: 0 };
      const m = d.slice(0, 7);
      if (m < M) top.append(landedCell(d, c, false, 2));
      else if (m > M) top.append(fcCell(d, c, false, 2));
      else { top.append(fcCell(d, c, true, 1)); bot.append(landedCell(d, c, true, 1)); }
    });
    top.append(h('td', { class: 'r num', rowSpan: 2 }, n1((r.tot.a || 0) + (r.tot.t || 0))), h('td', { class: 'r num', rowSpan: 2 }, n1(r.tot.x)), h('td', { class: 'r num fcn', rowSpan: 2 }, n1(r.tot.f)), h('td', { class: 'r num', rowSpan: 2 }, r.tot.fc ? fmt.money(r.tot.fc) : ''));
    if (!bot.children.length) bot.append(h('td', { class: 'hidecell' }));
    tb.append(top, bot);
  });
  // A cell that splits into normal time (NT) and overtime (OT) when clicked; leaving the cell saves both.
  // `suggest` ({ nt, ot, note }) fills the boxes when there is no accrual yet (e.g. a Pronto timesheet not posted):
  // revise it, or press Enter to accrue it as it is; leaving it unchanged leaves things as they were.
  function splitCell(td, total, ot, hint, onCommit, extra = null, suggest = null) {
    const show = (t, o, dirty) => {
      clear(td);
      td.append(h('span', { class: 'v' + (t ? '' : ' hint') }, t ? n1(t) : hint || ''));
      if (o > 0.005) td.append(h('span', { class: 'otmini' }, 'OT ' + n1(o)));
      if (extra) td.append(extra());
      td.classList.toggle('dirtycell', !!dirty);
    };
    show(total, ot);
    td.classList.add('splittable');
    td.onclick = () => {
      if (td.classList.contains('editing')) return;
      td.classList.add('editing'); clear(td);
      const sg = !total && suggest ? suggest : null;
      const nt = h('input', { type: 'text', inputmode: 'decimal', value: total ? n1(total - ot) : sg ? n1(sg.nt) : '', placeholder: 'NT', title: 'Normal time hours' });
      const o = h('input', { type: 'text', inputmode: 'decimal', value: ot ? n1(ot) : sg && sg.ot ? n1(sg.ot) : '', placeholder: 'OT', title: 'Overtime hours' });
      let force = false;
      td.append(h('div', { class: 'split' }, h('label', {}, 'NT', nt), h('label', {}, 'OT', o)), sg?.note ? h('div', { class: 'sgnote' }, sg.note) : null);
      nt.focus(); nt.select();
      const done = () => setTimeout(() => {
        if (td.contains(document.activeElement)) return;
        td.classList.remove('editing');
        const n = num(nt.value), x = num(o.value);
        const same = sg && !force && Math.abs(n - sg.nt) < 0.001 && Math.abs(x - (sg.ot || 0)) < 0.001;  // the suggestion untouched: nothing to save
        if (!same && (Math.abs(n + x - total) > 0.001 || Math.abs(x - ot) > 0.001)) {
          if (onCommit(n, x) === false) { show(total, ot); return; }
          total = n + x; ot = x; show(total, ot, true);
        } else show(total, ot);
      }, 0);
      [nt, o].forEach((i) => { i.addEventListener('blur', done); i.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); if (i === nt) o.focus(); else { force = true; o.blur(); } } if (e.key === 'Escape') { nt.value = total ? n1(total - ot) : ''; o.value = ot ? n1(ot) : ''; o.blur(); nt.blur(); } }); });
    };
  }
  function dayCls(d) { const wd = new Date(d + 'T00:00:00').getDay(); return (wd === 0 || wd === 6 ? ' we' : '') + (cal.holidays[d] ? ' hol' : '') + (d === sd ? ' sd' : ''); }
  function tipOf(d, c) {
    return [`${fmt.date(d)}${cal.holidays[d] ? ' · ' + cal.holidays[d] : ''}`, c.a ? `Timesheet posted in Pronto ${n1(c.a)} h` : '', c.t ? `Timesheet entered, not yet posted ${n1(c.t)} h (accrued automatically)` : '',
      c.acc ? `Accrued ${n1(c.acc)} h${c.a || c.t ? (c.x > 0.005 ? `, ${n1(c.x)} h of it not covered by a timesheet` : ', all covered by the timesheet') : ''}` : '', c.f ? `Forecast ${n1(c.f)} h (${fmt.money(c.fc)})` : '',
      { actual: 'Pink: actual (timesheet posted; matches any accrual). Read only.', hybrid: 'Purple: timesheet and accrual differ. Click to adjust your accrual.', accrual: c.a || c.t ? 'Light blue: timesheet entered in Pronto, not yet posted. Read only.' : 'Light blue: accrued. Type to change or clear.' }[c.st] || ''].filter(Boolean).join('\n');
  }
  function dayDetail(r, d, c, editable = false, nodeId = null) {
    const acc = r.accruals[d] || [];
    const box = h('input', { type: 'number', step: '0.5', value: c.acc || '', style: { width: '90px' } });
    const statusText = (st) => ({ open: 'open', partial: 'partly covered by the timesheet; the rest still counts', matched: 'reversed: the timesheet matched it', investigate: 'reversed: the timesheet was for more hours' }[st] || st);
    modal({ title: `${r.name || r.code} · ${fmt.date(d)}`, body: h('div', { class: 'grid' },
      h('div', { class: 'grid g4' }, kpiS('Timesheet posted', n1(c.a) || '0', 'st-actual'), kpiS('Entered, not posted', n1(c.t) || '0', 'st-accrual'), kpiS('Your accrual', n1(c.acc) || '0', 'st-accrual'), kpiS('Forecast', n1(c.f) || '0', 'fcl')),
      c.st === 'hybrid' ? h('div', { class: 'note warn' }, `The timesheet (${n1((c.a || 0) + (c.t || 0))} h) and your accrual (${n1(c.acc)} h) differ. ${c.x > 0.005 ? `${n1(c.x)} h of the accrual is not covered by the timesheet and still counts.` : 'The timesheet covers all of the accrual, so the accrual no longer counts.'}`) : null,
      h('div', { class: 'small muted' }, 'Timesheet hours come from the Pronto labour export and cannot be changed here: correct them in Pronto and upload the export again. Only your accrual can be changed.'),
      editable ? h('div', { class: 'row' }, h('b', {}, 'Accrued hours'), box, h('span', { class: 'small muted' }, 'Set it to what was really worked, or clear it (0) if the timesheet is right.')) : null,
      acc.length ? h('div', {}, h('b', {}, 'Accruals on this day'), ...acc.map((a) => h('div', { class: 'row' }, `${n1(a.hours)} h, ${fmt.money(a.amount)}: ${statusText(a.status)}`,
        h('button', { class: 'btn ghost sm', onclick: () => historyDialog('accrual', a.id, `${r.name}: accrual on ${fmt.date(d)}`) }, 'History')))) : null),
    actions: [{ label: editable ? 'Cancel' : 'Close', kind: 'ghost', onClick: () => {} }, ...(editable ? [{ label: 'Save accrual', onClick: async () => {
      await api.post(p('/accruals/hours'), { resource_id: r.resource_id, node_id: nodeId, days: { [d]: box.value === '' ? null : num(box.value) }, role: r.role });
      toast('Accrual saved'); render(); } }] : [])] });
  }
  const kpiS = (l, v, cls) => h('div', { class: 'kpi ' + cls, style: { borderTopWidth: '1px' } }, h('div', { class: 'l' }, l), h('div', { class: 'v' }, v + ' h'));

  const tf = h('tr', {}, h('td', { class: 'sticky1', style: { left: 0 } }, 'Total hours'), h('td'), ...cols.map((col) => (col.d
    ? h('td', { class: 'r num small' + (col.d > sd ? ' fcn' : '') }, n1(col.d <= sd ? dayTot[col.d].landed : dayTot[col.d].f))
    : h('td', { class: 'r num small' + (col.ds[0] > sd ? ' fcn' : '') }, n1(col.ds.reduce((a, d) => a + (d <= sd ? dayTot[d].landed : dayTot[d].f), 0))))),
    h('td', { class: 'r num' }, n1(cal.rows.reduce((a, r) => a + (r.tot.a || 0) + (r.tot.t || 0), 0))), h('td', { class: 'r num' }, n1(cal.rows.reduce((a, r) => a + r.tot.x, 0))), h('td', { class: 'r num' }, n1(cal.rows.reduce((a, r) => a + r.tot.f, 0))), h('td', { class: 'r num' }, fmt.money(cal.rows.reduce((a, r) => a + r.tot.fc, 0))));
  root.append(h('div', { class: 'row small', style: { margin: '0 0 6px' } }, h('span', { class: 'muted' }, 'Green: type forecast hours. Light blue (past): type the hours you accrue, including days with a timesheet not yet accrued (P = unposted in Pronto, T = subcontractor timesheet). Posted or invoiced hours (pink) are read only.'), h('span', { class: 'sp', style: { flex: 1 } }), status));
  const gridBox = h('div', { class: 'tw lc', style: { maxHeight: part === 'grid' ? 'calc(100vh - 260px)' : '66vh' } }, h('table', { class: 't', 'data-popout': '#/calendar?part=grid' }, h('thead', {}, th1, th2), tb, h('tfoot', {}, tf)));
  const focusIx = days.indexOf(sd);
  const strip = outlineStrip({ cols: days.map((d) => ({ id: d })), cur: focusIx, focus: focusIx, summary: true, levels: DAY_LEVELS, st: ost, onChange: () => render(), names: { 1: 'This week only', 2: 'This month', 3: 'Every day' } });
  root.append(strip.el, gridBox); strip.mount(gridBox, gridBox.querySelector('table'));
  // whole project: start scrolled to the current month, its first day just right of the frozen columns (two months before it in view)
  if (ui.span === 'project') requestAnimationFrame(() => {
    const th = gridBox.querySelector(`th[data-m="${M}"]`); if (!th) return;
    const box = gridBox.getBoundingClientRect().left;
    const edge = Math.max(0, ...[...gridBox.querySelectorAll('thead th.sticky1')].map((e) => e.getBoundingClientRect().right - box));
    gridBox.scrollLeft = Math.max(0, gridBox.scrollLeft + th.getBoundingClientRect().left - box - edge - 120);
  });
  root.append(h('div', { class: 'legend', style: { marginTop: '10px' } },
    h('span', {}, h('i', { class: 'fcl' }), 'Forecast'), h('span', {}, h('i', { class: 'fcd' }), 'Current month: forecast'), h('span', {}, h('i', { class: 'acd' }), 'Current month: landed'),
    h('span', {}, h('i', { class: 'st-accrual' }), 'Accrued, or a timesheet not yet accrued (P = unposted in Pronto, T = subcontractor timesheet)'), h('span', {}, h('i', { class: 'st-actual' }), 'Actual: timesheet posted (matches the accrual)'),
    h('span', {}, h('i', { class: 'st-hybrid' }), 'Timesheet differs from the accrual'), h('span', {}, h('i', { style: { background: '#fff', outline: '2px solid var(--orange)', outlineOffset: '-2px' } }), 'Forecast, nothing landed or accrued'),
    h('span', {}, h('i', { style: { background: '#fff', borderTop: '3px solid #c0392b' } }), 'Public holiday')));

  function invoiceRef(r) {
    const mo = h('input', { type: 'month', value: M }); const ref = h('input', { type: 'text', placeholder: 'e.g. SPK-0926' });
    modal({ title: `${r.name}${r.role ? ' · ' + r.role : ''}: invoice reference`, body: h('div', { class: 'grid' },
      h('div', { class: 'note' }, 'The accrued hours of this month get this invoice number. When the invoice lands in Pronto, all of them are compared with its total and reverse together (pink). If the invoice differs, they show purple.'),
      h('div', { class: 'grid g2' }, field('Month', mo), field('Invoice number', ref))),
    actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} }, { label: 'Apply', onClick: async () => {
      const x = await api.post(p('/accruals/invoice-ref'), { resource_id: r.resource_id, role: r.role, month: mo.value, inv_ref: ref.value.trim() }); toast(`${x.accruals} accruals now wait for invoice ${ref.value}`); render(); } }] });
  }

  function uploadLookahead() {
    const file = h('input', { type: 'file', accept: '.xlsx,.xlsm' });
    modal({ title: 'Upload a 3-week lookahead', body: h('div', { class: 'grid' },
      h('div', { class: 'note' }, 'Each row sets the forecast for one supplier and role on one CBS line for the three weeks in the file: people on site per day (or hours). Days left blank become nobody. A roster on the same line is turned into a day-by-day calendar first, so the lookahead replaces those days rather than adding to them; the roster\'s days after the three weeks stay.'),
      field('Lookahead file', file)),
    actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} }, { label: 'Upload', onClick: async () => {
      if (!file.files[0]) throw new Error('Choose the file');
      const x = await api.upload(p('/lookahead'), file.files[0]);
      modal({ title: 'Lookahead loaded', body: h('div', { class: 'grid' }, h('div', {}, `${fmt.date(x.window[0])} to ${fmt.date(x.window[1])}: ${x.rows.length} rows updated.`),
        x.rows.length ? table([{ label: 'Supplier', f: (y) => y.supplier }, { label: 'Role', f: (y) => y.role }, { label: 'CBS', f: (y) => y.cbs }, { label: 'Days with people', r: 1, f: (y) => y.days }], x.rows) : null,
        x.errors.length ? h('div', { class: 'note bad' }, ...x.errors.map((e) => h('div', {}, e))) : null),
      actions: [{ label: 'Close', onClick: () => render() }] });
    } }] });
  }

  function uploadSubTs() {
    const file = h('input', { type: 'file', accept: '.xlsx,.xlsm' }); const rep = h('input', { type: 'checkbox' });
    modal({ title: 'Upload subcontractor timesheets', body: h('div', { class: 'grid' },
      h('div', { class: 'note' }, 'Use the template (one row per worker per day). Rows already uploaded are skipped, so a running weekly sheet can be uploaded again.'),
      field('Timesheet file', file), h('label', { class: 'row small' }, rep, 'Replace what was uploaded before for the same suppliers and dates')),
    actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} }, { label: 'Upload', onClick: async () => {
      if (!file.files[0]) throw new Error('Choose the file');
      const x = await api.upload(p('/sub-timesheets'), file.files[0], { replace: rep.checked ? '1' : '0' });
      modal({ title: 'Timesheets uploaded', body: h('div', { class: 'grid' }, h('div', {}, `${x.added} rows added, ${x.skipped} already there, ${x.errors.length} not loaded.`),
        x.no_line ? h('div', { class: 'note warn' }, `${x.no_line} rows have no CBS line (the supplier has several lines): give them a CBS code, or choose the line in the calendar when you accrue.`) : null,
        x.errors.length ? h('div', { class: 'note bad' }, ...x.errors.map((e) => h('div', {}, e))) : null),
      actions: [{ label: 'Close', onClick: () => render() }] });
    } }] });
  }

  async function accrueUnposted() {
    const jobs = [];
    cal.rows.forEach((r) => {
      if (r.kind === 'pool' || !r.lines.length) return;
      const days = {}; const workers = {};
      Object.entries(r.d).forEach(([d, c]) => { if (d <= sd && c.t > 0 && !c.a && !c.acc) { days[d] = c.t; if (c.w) workers[d] = c.w; } });
      if (Object.keys(days).length) jobs.push([r, days, workers]);
    });
    if (!jobs.length) return toast('Every unposted timesheet in view is already accrued');
    let n = 0, failed = [];
    for (const [r, days, workers] of jobs) {
      try { await api.post(p('/accruals/hours'), { resource_id: r.resource_id, node_id: r.lines[0].node_id, days, workers, role: r.role, reason: r.kind === 'supplier' ? 'Work done, invoice not yet received' : 'Timesheets not yet posted' }); n += Object.keys(days).length; } catch (e) { failed.push(r.name || r.code); }
    }
    toast(`${n} days accrued from unposted timesheets.` + (failed.length ? ` Not accrued, no cost rate on file: ${failed.join(', ')} (add it on Resources and rates).` : ''), failed.length ? 'bad' : '');
    render();
  }

  async function assignFromPool(pool) {
    const data = await loadRows();
    pickNode({ title: `Who takes hours from ${pool.code}? Choose their line under ${pool.name}`, kinds: ['line'],
      filter: (r) => pathTo(data.rows, r.id).some((a) => String(a.id) === String(pool.node_id)),
      onPick: async (n) => {
        const res = resources.find((x) => x.code === n.resource_code);
        await api.post(p(`/nodes/${n.node_id}/items`), { spread: 'Calendar', basis: 'hours', rate_mode: 'auto', resource_id: res ? res.id : null, role: res ? null : n.function,
          scope: `Allocated from ${pool.code}`, qty: 1, pct: 1, from_pool: 1 });
        toast(`Calendar created for ${n.name}, taken out of ${pool.code}. Type their hours in the green cells.`); render(); } });
  }

  async function newCalendarItem(r) {
    pickNode({ title: `Forecast ${r.name || r.code} against which line?`, kinds: ['line'], onPick: async (n) => {
      await api.post(p(`/nodes/${n.node_id}/items`), { spread: 'Calendar', basis: 'hours', rate_mode: 'auto', resource_id: r.resource_id, role: r.role, scope: `Calendar: ${r.name || r.code}`, qty: 1, pct: 1 });
      toast('Calendar created. Type the hours in the green cells.'); render(); } });
  }

  function addPerson(list) {
    const res = select([['', '(choose)'], ...list.map((x) => [x.id, `${x.kind === 'employee' ? '👤' : '🏢'} ${x.name || x.code} [${x.code}]`])], '');
    const role = h('input', { type: 'text', placeholder: 'For a supplier: the role, e.g. Electrician' });
    modal({ title: 'Add someone to forecast', body: h('div', { class: 'grid' }, h('div', { class: 'note' }, 'Creates a calendar item for this person on a CBS line, then you type their hours a day in the grid. For a crew on a roster (10:4 and so on) use a Roster item on the line instead.'),
      field('Person or supplier', res), field('Role (suppliers)', role)),
    actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} }, { label: 'Choose the CBS line...', onClick: () => {
      if (!res.value) throw new Error('Choose a person or supplier');
      const x = list.find((y) => y.id === +res.value);
      newCalendarItem({ resource_id: x.id, name: x.name, code: x.code, role: role.value || null });
    } }] });
  }
}
