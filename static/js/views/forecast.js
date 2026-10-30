import { h, clear, fmt, modal, toast, field, select, table, num, confirmBox, badge, empty, chart, PALETTE, tone, debounce, statusPill, filterMenu } from '../ui.js';
import { api, state, p } from '../api.js';
import { go, render } from '../app.js';
import { historyDialog } from '../history.js';
import { outlineState, outlineStrip, visible as olVisible, MONTH_LEVELS } from '../outline.js';
import { fyQuarter } from '../monthplan.js';

const revised = new Set();   // 'node|month' cells typed or moved in this session: marked until the page is left
let lastChange = null;       // what Undo puts back

// FORECAST > Forecast lines: every CBS line with its method, and a full-page editor per line.
const METHOD_NOTE = {
  'GROUND-UP': 'Built from forecast items: resource calendars, milestone payments, rosters, quantity x rate, typed months.',
  'CLAIM': 'Net of retention, from the linked subcontract claim schedule.',
  'BURN-RATE': 'Average monthly spend to date x remaining months. The current month is excluded.',
  'AT-BUDGET': 'Remaining allowance, spread over the remaining months.',
  'AT-COMMIT': 'Open PO commitments plus what you expect to commit that is not yet on a PO.',
  'TOP-DOWN': 'You type the EAC; cost to complete is the EAC less CTD and accruals.',
  'MANUAL': 'You type the monthly amounts.',
};
const KINDS = [
  ['Calendar', 'Resource calendar', 'A day grid for one person or supplier on this line. Type hours a day (x rate), units (days, nights, ea) or dollars.'],
  ['Milestones', 'Milestone payments', 'Procurement paid on milestones: 10% on order, 15% on drawings, 20% on FAT... each with the month you expect it.'],
  ['Roster', 'Roster pattern', 'Crew on a roster: 10:4 from a start date for N swings x headcount x hours, priced from the supplier rates for the role.'],
  ['Linear', 'Quantity x rate', 'Lump sum, even spread over dates, or a recurring cost (weekly hire, monthly fee).'],
  ['Manual', 'Typed months', 'Type the dollars per month.'],
];
const DETAIL = ['Calendar', 'Milestones', 'Roster'];
const hrs = (v) => (v ? Math.round(v * 100) / 100 + ' h' : '');

export default async function forecastView(root, params) {
  if (params.node && !state.project?.is_parent) return lineEditor(root, params);   // a parent project only reads its children's lines
  return lineList(root, params);
}

// ------------------------------------------------------------------------------------------------
// List of lines
// ------------------------------------------------------------------------------------------------
async function lineList(root, params) {
  const res = await api.get(p('/cost-control?months=1'));
  const all = res.rows;  // groups and lines in CBS order: grandparent > parent > child
  const ro = !!state.project?.is_parent;   // a parent: the lines are its children's, so nothing here can be edited
  const grid = res.grid; const M = res.status_month; const claimOk = new Set((res.claim_nodes || []).map(String));
  const ost = outlineState('fl');
  const ui = { gp: params.gp || '', method: params.method || '', q: '', todo: false, past: !!params.past || (params.month && params.month < M), hl: params.month || '' };
  const open = new Set(); const closed = new Set();
  const scope = params.scope || params.node;  // a group to show on its own (the dashboard links here)
  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, 'Forecast'), h('div', { class: 'sub' }, `Cost to complete per CBS line and month, from the status month ${fmt.month(M)}. ${ro ? 'The sum of the child projects.' : 'Click a line to build its forecast. The method is changed on the Cost control row.'}`)),
    h('div', { class: 'sp' }), h('button', { class: 'btn ghost', onclick: () => go('calendar') }, 'Labour calendar')));
  const lines = all.filter((r) => r.kind === 'line' || r.kind === 'pot');
  const by = {};
  lines.forEach((r) => { const m = r.method || 'AT-BUDGET'; by[m] = by[m] || { n: 0, ctc: 0 }; by[m].n++; by[m].ctc += r.ctc; });
  const tot = res.total;
  root.append(h('div', { class: 'grid g6', style: { marginBottom: '14px' } },
    kpi('Cost to complete', fmt.m(tot.ctc), `${lines.length} lines`), kpi('EAC', fmt.m(tot.eac), 'CTD + accruals + CTC', 't2'), kpi('Contingency', fmt.m(tot.contingency), 'Allowance less EAC', 't3', tone(tot.contingency)),
    kpi('Built ground-up', fmt.m(by['GROUND-UP']?.ctc || 0), `${by['GROUND-UP']?.n || 0} lines`, 't4'), kpi('Held at budget', fmt.m(by['AT-BUDGET']?.ctc || 0), `${by['AT-BUDGET']?.n || 0} lines: a holding position`, 't5'),
    kpi('Forecast hours', fmt.n(lines.reduce((a, r) => a + (r.fc_hours || 0), 0)), 'From calendars and rosters', 't6')));
  const bar = h('div', { class: 'card row', style: { padding: '10px 14px', marginBottom: '12px' } });
  const note = h('div'); const out = h('div');
  root.append(bar, note, out);
  const chip = (k, label, key) => h('span', { class: 'chip' + (ui[key] === k ? ' on' : ''), onclick: () => { ui[key] = ui[key] === k ? '' : k; drawBar(); draw(); } }, label);
  const search = h('input', { type: 'search', placeholder: 'Search code, name, resource...', style: { width: '240px' }, oninput: debounce(() => { ui.q = search.value.trim().toLowerCase(); draw(); }, 150) });
  function drawBar() {
    clear(bar).append(search, ...['PL', 'PS', 'PM', 'PE'].map((g) => chip(g, `${g} ${state.tax.gp_group[g]}`, 'gp')), h('span', { style: { width: '8px' } }),
      filterMenu('Methods', Object.keys(state.tax.methods).map((m) => chip(m, `${m} ${by[m] ? '(' + by[m].n + ')' : ''}`, 'method')), ui.method ? 1 : 0),
      h('label', { class: 'row small', style: { gap: '4px' } }, h('input', { type: 'checkbox', checked: ui.todo, onchange: (e) => { ui.todo = e.target.checked; draw(); } }), 'Needs attention'),
      h('label', { class: 'row small', style: { gap: '4px' } }, h('input', { type: 'checkbox', checked: ui.past, onchange: (e) => { ui.past = e.target.checked; draw(); } }), 'Show past months'),
      h('button', { class: 'btn sm ghost', onclick: () => { open.clear(); closed.clear(); all.forEach((r) => r.kind === 'group' && closed.add(String(r.id))); draw(); } }, 'Collapse all'),
      h('button', { class: 'btn sm ghost', onclick: () => { closed.clear(); draw(); } }, 'Expand all'));
  }
  const inScope = (r) => {
    if (!scope) return true;
    const byId = new Map(all.map((x) => [String(x.id), x]));
    for (let x = r; x; x = x.parent_id == null ? null : byId.get(String(x.parent_id))) if (String(x.id) === String(scope) || String(x.node_id) === String(scope)) return true;
    return false;
  };
  const mv = (r, i) => (r.a?.[i] || 0) + (r.x?.[i] || 0) + (r.f?.[i] || 0);
  const NUM = [
    ['Allowance', (r) => r.allowance], ['CTD + ACC', (r) => r.ctd + r.acc], ['CTC', (r) => r.ctc, 'b'], ['EAC', (r) => r.eac], ['Contingency', (r) => r.contingency, 't'], ['Hours', (r) => r.fc_hours, 'h'],
  ];
  function draw() {
    const vis = lines.filter((r) => inScope(r) && (!ui.gp || r.gp === ui.gp) && (!ui.method || (r.method || 'AT-BUDGET') === ui.method) && (!ui.todo || r.note || r.po_status === 'SHORT' || r.contingency < -1)
      && (!ui.q || `${r.code} ${r.name} ${r.function || ''} ${r.resource_code || ''}`.toLowerCase().includes(ui.q)));
    if (!vis.length) { clear(out).append(empty('No lines match', 'Change the filters.')); return; }
    const visSet = new Set(vis.map((r) => String(r.id)));
    // months that hold anything, from the status month on (or all of them with "Show past months")
    const miAll = grid.map((_, i) => i).filter((i) => (ui.past || grid[i] >= M || grid[i] === ui.hl) && vis.some((r) => Math.abs(mv(r, i)) > 0.005));
    // folded quarters and hidden months take no room (the strip above the table brings them back); the status month and a highlighted month always show
    const ocols = miAll.map((i) => ({ id: grid[i] })); const ocur = miAll.findIndex((i) => grid[i] >= M);
    const ovis = olVisible(ocols, ocur, ost, MONTH_LEVELS);
    const mi = miAll.filter((i, k) => ovis[k] || grid[i] === ui.hl);
    // a group block runs until the next row at its level or above; its figures are those of the visible lines in it
    const blocks = new Map();
    all.forEach((r, ix) => {
      if (r.kind !== 'group') return;
      const members = []; for (let j = ix + 1; j < all.length && all[j].level > r.level; j++) if (visSet.has(String(all[j].id))) members.push(all[j]);
      if (members.length) blocks.set(String(r.id), members);
    });
    const sums = (rs) => ({ n: NUM.map(([, f]) => rs.reduce((a, r) => a + (f(r) || 0), 0)), m: mi.map((i) => rs.reduce((a, r) => a + mv(r, i), 0)) });
    const cells = (s, tag = 'td', cls = '') => [
      ...s.n.map((v, k) => h(tag, { class: 'r num ' + cls + (NUM[k][2] === 'h' ? '' : ''), style: NUM[k][2] === 'b' ? { fontWeight: 700 } : {} }, NUM[k][2] === 'h' ? hrs(v) : h('span', { class: NUM[k][2] === 't' ? tone(v) : '' }, v ? fmt.money(v) : ''))),
      ...s.m.map((v, k) => h(tag, { class: 'r num mcell ' + cls + (grid[mi[k]] === ui.hl ? ' hl' : '') + (grid[mi[k]] < M ? ' past' : '') }, v ? fmt.money(v) : ''))];
    const head = h('tr', {}, h('th', {}, 'CBS'), h('th', {}, 'Line'), h('th', {}, 'Resource'), h('th', {}, 'Method'), ...NUM.map(([l]) => h('th', { class: 'r' }, l)),
      ...mi.map((i) => h('th', { class: 'r mth ' + (grid[i] < M ? 'mpa' : grid[i] === M ? 'mca' : 'mfu') + (grid[i] === ui.hl ? ' hl' : ''), 'data-m': grid[i], 'data-col': grid[i], title: grid[i] < M ? 'Actual and accrued' : grid[i] === M ? 'Status month: actual, accrued and forecast' : 'Forecast' }, fmt.month(grid[i]) + (grid[i] === M ? ' *' : ''))));
    const grand = sums(vis);
    const totRow = (label, sticky) => h('tr', { class: 'ftot' + (sticky ? ' top' : '') }, h('td', { colSpan: 4 }, label), ...cells(grand));
    const tbody = h('tbody'); let skip = null;
    all.forEach((r) => {
      if (skip !== null) { if (r.level > skip) return; skip = null; }
      if (r.kind === 'group') {
        const mem = blocks.get(String(r.id)); if (!mem) return;
        const isClosed = closed.has(String(r.id));
        const tog = h('span', { class: 'tog', onclick: (e) => { e.stopPropagation(); isClosed ? closed.delete(String(r.id)) : closed.add(String(r.id)); draw(); } }, isClosed ? '▸' : '▾');
        tbody.append(h('tr', { class: r.level === 1 ? 'gp' : r.level === 2 ? 'par' : 'par2' }, h('td', { class: 'mono' }, h('span', { style: { paddingLeft: (r.level - 1) * 14 + 'px' } }), tog, r.code), h('td', {}, r.name, h('span', { class: 'muted small', style: { fontWeight: 400, marginLeft: '8px' } }, `${mem.length} ${mem.length === 1 ? 'line' : 'lines'}`)), h('td'), h('td'), ...cells(sums(mem))));
        if (isClosed) skip = r.level;
        return;
      }
      if (!visSet.has(String(r.id))) return;
      const m = r.method || 'AT-BUDGET';
      const tr = h('tr', { class: ro ? '' : 'click', onclick: ro ? null : () => go('forecast', { node: r.kind === 'pot' ? 'p' + r.node_id : r.node_id }) },
        h('td', { class: 'mono' }, h('span', { style: { paddingLeft: (r.level - 1) * 14 + 'px' } }), r.code), h('td', { title: r.name }, r.name, r.note ? h('span', { class: 'badge warn', title: r.note, style: { marginLeft: '6px' } }, '!') : '', r.po_status === 'SHORT' ? statusPill('SHORT') : ''),
        h('td', { class: 'muted' }, r.resource_code || ''),
        h('td', {}, h('span', { class: 'badge m-' + m, title: (METHOD_NOTE[m] || '') + (ro ? '' : ' Change it on the Cost control row (or the claim schedule, or build the line ground-up).') }, m)),
        ...cells({ n: NUM.map(([, f]) => f(r)), m: mi.map((i) => mv(r, i)) }));
      // a forecast amount can be dragged to another month from the status month on (a line built from items or a claim schedule is changed there)
      if (!ro && r.kind === 'line' && !['GROUND-UP', 'CLAIM'].includes(m)) mi.forEach((i, k) => {
        const td = tr.children[4 + NUM.length + k]; if (grid[i] < M) return;
        td.dataset.n = r.node_id; td.dataset.m = grid[i]; td.classList.add('fdrop');
        if (m === 'MANUAL' && Math.abs(r.f?.[i] || 0) > 0.005) td.classList.add('ftyped');
        if (revised.has(`${r.node_id}|${grid[i]}`)) td.classList.add('frev');
        if (Math.abs(r.f?.[i] || 0) > 0.005) { const txt = td.textContent; td.textContent = ''; td.append(h('span', { class: 'grip4', draggable: 'true', title: 'Drag by this grip to move the forecast to another month (earlier or later, not the past)' }), h('span', { class: 'fv' }, txt)); td.classList.add('fdrag'); }
      });
      tbody.append(tr);
    });
    const t = h('table', { class: 't freeze2 fgrid notools' }, h('thead', {}, head, totRow('Total' + (vis.length < lines.length ? ' of the lines shown' : ''), true)), tbody, h('tfoot', {}, totRow('Total' + (vis.length < lines.length ? ' of the lines shown' : ''))));
    let drag = null;
    const tdOf = (e) => (e.target && e.target.nodeType === 1 ? e.target : e.target?.parentElement)?.closest('td.fdrop');
    const ok = (td) => drag && td && td.dataset.n === drag.n && td.dataset.m !== drag.m;
    tbody.addEventListener('dragstart', (e) => { const td = tdOf(e); if (!td || !(e.target.closest && e.target.closest('.grip4'))) return; drag = { n: td.dataset.n, m: td.dataset.m }; td.classList.add('dragging'); e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', td.dataset.m); });
    tbody.addEventListener('dragend', () => { drag = null; tbody.querySelectorAll('.dragging,.dropok').forEach((x) => x.classList.remove('dragging', 'dropok')); });
    tbody.addEventListener('dragover', (e) => { if (ok(tdOf(e))) { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; } });
    tbody.addEventListener('dragenter', (e) => { tbody.querySelectorAll('.dropok').forEach((x) => x.classList.remove('dropok')); const td = tdOf(e); if (ok(td)) td.classList.add('dropok'); });
    tbody.addEventListener('drop', async (e) => {
      const td = tdOf(e); if (!ok(td)) return; e.preventDefault();
      const mvd = { src: drag.m, dst: td.dataset.m }; const nid = drag.n; drag = null;
      const line = lines.find((x) => String(x.node_id) === String(nid) && x.kind === 'line');
      const send = async (convert) => { try { const r = await api.post(p(`/nodes/${nid}/forecast-move`), { ...mvd, convert }); toast(`Moved to ${fmt.month(mvd.dst)}${r.converted ? ' (now typed months)' : ''}`); } catch (err) { toast(err.message, 'bad'); } render(); };
      if ((line?.method || 'AT-BUDGET') === 'MANUAL') return send(false);
      if (await confirmBox(`${line?.code} forecasts by ${line?.method || 'AT-BUDGET'}. Moving an amount turns it into typed months (MANUAL), starting from what it forecasts now. Continue?`, 'Move and switch to MANUAL')) send(true);
    });
    // double-click a month to type $ or % (a % only on AT-BUDGET and AT-COMMIT lines); empty clears it
    // a single click on a month still opens the line, but waits a moment so a double-click can edit the month instead
    let clickTimer = null;
    tbody.addEventListener('click', (e) => {
      const td = tdOf(e); if (!td || td.querySelector('input') || e.detail > 1) { if (td) e.stopPropagation(); return; }
      e.stopPropagation(); const nid = td.dataset.n; clearTimeout(clickTimer);
      clickTimer = setTimeout(() => { const l = lines.find((x) => String(x.node_id) === String(nid) && x.kind === 'line'); if (l) go('forecast', { node: l.kind === 'pot' ? 'p' + l.node_id : l.node_id }); }, 280);
    }, true);
    tbody.addEventListener('dblclick', (e) => {
      clearTimeout(clickTimer);
      const td = tdOf(e); if (!td || td.querySelector('input')) return;
      const nid = td.dataset.n; const month = td.dataset.m;
      const line = lines.find((x) => String(x.node_id) === String(nid) && x.kind === 'line');
      const old = td.innerHTML;
      const input = h('input', { type: 'text', value: '', placeholder: '$ or %', style: { width: '78px', textAlign: 'right' }, title: 'Type an amount or a % (Enter), leave empty to clear it, Esc to cancel' });
      td.textContent = ''; td.append(input); input.focus();
      const cancel = () => { td.innerHTML = old; };
      input.addEventListener('keydown', async (ev) => {
        if (ev.key === 'Escape') return cancel();
        if (ev.key !== 'Enter') return;
        ev.preventDefault();
        const raw = input.value.trim().replace(/[$,\s]/g, '');
        const body = { month };
        if (raw === '' || raw === '0') body.clear = true;
        else if (/^-?\d+(\.\d+)?%$/.test(raw)) { body.unit = '%'; body.value = parseFloat(raw); }
        else if (/^-?\d+(\.\d+)?$/.test(raw)) { body.unit = '$'; body.value = parseFloat(raw); }
        else { toast('Type an amount such as 12500 or 12,500, or a percentage such as 25%', 'bad'); return; }
        const method = line?.method || 'AT-BUDGET';
        if (method !== 'MANUAL') {
          if (body.unit === '%' && !['AT-BUDGET', 'AT-COMMIT'].includes(method)) { toast(`A % only works on AT-BUDGET and AT-COMMIT lines. This line forecasts by ${method}: type a $ amount.`, 'bad'); return; }
          body.convert = true;
        } else if (body.unit === '%') { toast('A % only works on AT-BUDGET and AT-COMMIT lines. Typed (MANUAL) months take $ amounts.', 'bad'); return; }
        try {
          const r = await api.post(p(`/nodes/${nid}/forecast-set`), body);
          lastChange = { nid, before: r.before, label: `${line?.code} ${fmt.month(month)}` };
          revised.add(`${nid}|${month}`);
          toast(`${line?.code} ${fmt.month(month)}: ${body.clear ? 'cleared' : fmt.money(r.amount)}${r.converted ? ' (now typed months)' : ''}. Undo is at the top of the grid.`);
        } catch (err) { toast(err.message, 'bad'); }
        render();
      });
      input.addEventListener('blur', () => { if (td.contains(input)) cancel(); });
    });
    const wrap = h('div', { class: 'tw', style: { maxHeight: '72vh' } }, t);
    const strip = miAll.length > 1 ? outlineStrip({ cols: ocols, cur: ocur, levels: MONTH_LEVELS, st: ost, onChange: draw, names: { 1: 'This quarter only', 2: 'Every month' } }) : null;
    if (out._olOff) { out._olOff(); out._olOff = null; }
    clear(out).append(h('div', { class: 'row', style: { gap: '10px', margin: '0 0 6px' } },
      h('span', { class: 'small muted' }, 'Double-click a month to type $ or % (empty clears it); drag a forecast amount to move it. Orange-edged cells are typed by hand; the bold-edged ones were changed in this session.'), h('span', { class: 'sp', style: { flex: 1 } }),
      lastChange ? h('button', { class: 'btn ghost sm', onclick: async () => { const c = lastChange; lastChange = null; await api.post(p(`/nodes/${c.nid}/forecast-restore`), { before: c.before }); revised.clear(); toast(`Put back: ${c.label}`); render(); } }, `Undo ${lastChange.label}`) : null), ...(strip ? [strip.el] : []), wrap);
    if (strip) out._olOff = strip.mount(wrap, t);
    if (ui.hl) {
      const th = t.querySelector(`th[data-m="${ui.hl}"]`);
      if (th) { const s = sums(vis); const k = mi.findIndex((i) => grid[i] === ui.hl);
        const sub = (key) => vis.reduce((a, r) => a + (r[key]?.[mi[k]] || 0), 0);
        clear(note).append(h('div', { class: 'note', style: { marginBottom: '12px' } }, h('b', {}, fmt.month(ui.hl)), `: actuals ${fmt.money(sub('a'))}, accruals ${fmt.money(sub('x'))}, forecast ${fmt.money(sub('f'))}, total ${fmt.money(s.m[k])}. The highlighted column is this month; open a line to see what builds it. `,
          h('a', { onclick: () => { ui.hl = ''; draw(); } }, 'Clear highlight')));
        setTimeout(() => { wrap.scrollLeft = Math.max(0, th.offsetLeft - 620); }, 30);
      }
    } else clear(note);
  }
  drawBar(); draw();
}

function kpi(l, v, s, t = '', c = '') { return h('div', { class: 'kpi ' + t }, h('div', { class: 'l' }, l), h('div', { class: 'v ' + c }, v), h('div', { class: 's' }, s)); }

// ------------------------------------------------------------------------------------------------
// One line
// ------------------------------------------------------------------------------------------------
async function lineEditor(root, params) {
  const isPot = String(params.node).startsWith('p');
  const nodeId = isPot ? +String(params.node).slice(1) : +params.node;
  const [res, det, resources] = await Promise.all([api.get(p('/cost-control?months=1')), api.get(p(`/nodes/${nodeId}`)), api.get(p('/resources'))]);
  const row = res.rows.find((r) => String(r.id) === String(params.node));
  if (row && row.kind === 'group') { root.innerHTML = ''; return lineList(root, { scope: row.id }); }
  if (!row) { root.append(empty('Line not found', 'It may have been deleted.', h('button', { class: 'btn', onclick: () => go('forecast') }, 'Back to the list'))); return; }
  const grid = res.grid; const M = res.status_month;
  root.append(h('div', { class: 'crumbs', style: { marginBottom: '6px' } }, h('a', { onclick: () => go('forecast') }, 'Forecast'), h('span', { class: 'sep' }, '›'), ...det.ancestors.slice(0, -1).flatMap((a) => [h('span', { class: 'muted' }, a.code), h('span', { class: 'sep' }, '›')]), h('b', {}, `${row.code} ${row.name}`)));
  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, `${row.code}  ${row.name}`), h('div', { class: 'sub' }, isPot ? 'Unassigned pool: forecast not yet given to a named person or supplier' : [row.function, det.resource ? `${det.resource.name} [${det.resource.code}]` : null].filter(Boolean).join(' · ') || 'CBS line')),
    h('div', { class: 'sp' }), h('button', { class: 'btn ghost', onclick: () => historyDialog('cbs_node', nodeId, `${row.code} history`) }, 'History'), h('button', { class: 'btn ghost', onclick: () => go('costcontrol', { open: row.id }) }, 'Open in cost control')));
  root.dataset.node = row.node_id; root.dataset.row = row.id;  // the line the tiles belong to (tile links)
  root.append(h('div', { class: 'grid g6', style: { marginBottom: '14px' } }, kpi('Allowance', fmt.m(row.allowance), ''), kpi('Cost to date', fmt.m(row.ctd), 'Pronto', 't6'), kpi('Accruals', fmt.m(row.acc), 'Not yet in Pronto', 't3'),
    kpi('Cost to complete', fmt.m(row.ctc), row.fc_hours ? fmt.n(row.fc_hours) + ' hours' : row.method || '', 't4'), kpi('EAC', fmt.m(row.eac), '', 't2'), kpi('Contingency', fmt.m(row.contingency), row.budget_status || '', 't5', tone(row.contingency))));
  if (row.note) root.append(h('div', { class: 'note warn', style: { marginBottom: '12px' } }, row.note));
  if (row.po_status === 'SHORT') root.append(h('div', { class: 'note bad', style: { marginBottom: '12px' } }, `Cost to complete (${fmt.money(row.ctc)}) is below open PO commitments (${fmt.money(row.outstanding)}).`));

  // the method is shown, not picked here: it is changed on the Cost control row (rule methods), the claim schedule (CLAIM) or by building the line ground-up
  const cur = isPot ? (det.unalloc_method || 'AT-BUDGET') : (det.method || 'AT-BUDGET'); const method = { value: cur };
  const start = h('input', { type: 'date', value: det.start_date || '' }); const end = h('input', { type: 'date', value: det.end_date || '' });
  const top = h('input', { type: 'number', step: '0.01', value: (isPot ? det.unalloc_eac : det.eac_override) ?? '' }); const unc = h('input', { type: 'number', step: '0.01', value: det.uncommitted || 0 });
  const extra = h('div', { class: 'grid g4', style: { marginTop: '8px' } });
  if (cur === 'TOP-DOWN') extra.append(field('Top-down EAC', top)); if (cur === 'AT-COMMIT') extra.append(field('Still to commit (not on a PO)', unc));
  const ro = !!state.project?.is_parent;
  root.append(h('div', { class: 'card', style: { marginBottom: '14px' } }, h('div', { class: 'ch' }, h('h2', {}, 'Forecast method'), h('span', { class: 'sp' }), h('span', { class: 'badge m-' + cur }, cur)),
    h('div', { class: 'small muted' }, METHOD_NOTE[cur]),
    h('div', { class: 'grid g4', style: { marginTop: '8px' } }, isPot ? h('span') : field('Line start', start, 'Items without dates follow these'), isPot ? h('span') : field('Line end', end), h('span'), h('div', { style: { alignSelf: 'end' } },
      ro ? null : h('button', { class: 'btn', onclick: async () => {
        const body = isPot ? { unalloc_eac: top.value === '' ? null : num(top.value) } : { start_date: start.value || null, end_date: end.value || null, eac_override: top.value === '' ? null : num(top.value), uncommitted: num(unc.value) };
        await api.put(p(`/nodes/${nodeId}`), body); toast('Saved'); render(); } }, 'Save'))), extra,
    ro || cur === 'GROUND-UP' ? null : h('div', { class: 'row', style: { marginTop: '10px', gap: '8px' } },
      h('button', { class: 'btn ghost', onclick: async () => { await api.put(p(`/nodes/${nodeId}`), isPot ? { unalloc_method: 'GROUND-UP' } : { method: 'GROUND-UP' }); toast('Now built ground-up: add its items below'); render(); } }, 'Build this line ground-up'),
      h('button', { class: 'btn ghost', onclick: () => go('costcontrol', { open: row.id }) }, 'Change the method on Cost control'))));

  const work = h('div'); root.append(work);
  const m = isPot ? null : method.value;
  if (m === 'GROUND-UP' || det.items.length) itemsCard(work, { row, det, resources, nodeId, grid, M, params, isPot });
  if (!isPot && m === 'MANUAL') manualCard(work, det, grid, M, nodeId);
  if (!isPot && m === 'CLAIM') work.append(h('div', { class: 'note', style: { marginBottom: '14px' } }, det.subcontracts.length ? `Linked subcontract: ${det.subcontracts.map((s) => s.name).join(', ')}.` : 'No subcontract is linked to this line yet.', ' ', h('a', { href: '#/subcontracts' }, 'Open subcontracts')));
  if (!['GROUND-UP', 'MANUAL', 'CLAIM'].includes(m) || (isPot && m !== 'GROUND-UP')) work.append(h('div', { class: 'note', style: { marginBottom: '14px' } }, METHOD_NOTE[m || 'AT-BUDGET'], ' To build it from calendars, milestones or rosters, use "Build this line ground-up" above.'));
  if (isPot) work.prepend(h('div', { class: 'note', style: { marginBottom: '14px' } }, h('b', {}, 'This is the unassigned pool of ' + row.code.replace(/\.U$/, '') + '. '),
    'Forecast here what is not yet given to a named person or supplier, for example 400 hours of a project engineer at the rate-card rate. Forecasts on the lines below can then be taken out of this pool (they reduce it) or come in addition.',
    row.pool_drawn ? h('div', { style: { marginTop: '6px' } }, `Already allocated to lines below: ${fmt.money(row.pool_drawn)}. Unassigned forecast left: ${fmt.money(row.ctc)}.`) : null,
    (det.allocations || []).length ? h('div', { style: { marginTop: '6px' } }, 'Taken by: ', ...det.allocations.map((a, i) => h('span', {}, i ? ', ' : '', h('a', { onclick: () => go('forecast', { node: a.node_id, item: a.item_id }) }, `${a.code} ${a.name}`), a.scope ? ` (${a.scope})` : ''))) : null,
    row.pool_drawn ? h('div', { class: 'small', style: { marginTop: '6px' } }, 'The allowance stays on the pool until you transfer it (CBS and allowances), so this pool can show an underrun while the lines that took its forecast show an overrun. The group total is right either way.') : null));
  else if ((det.pools || []).length) work.prepend(poolNote(det.pools));

  // monthly profile
  const idx = grid.map((_, i) => i).filter((i) => row.a[i] || row.x[i] || row.f[i]);
  const box = h('div', { class: 'chartbox short' });
  root.append(h('div', { class: 'card', style: { marginTop: '14px' } }, h('h2', {}, 'Monthly profile'), box));
  setTimeout(() => chart(box, { type: 'bar', data: { labels: idx.map((i) => fmt.month(grid[i])), datasets: [{ label: 'Actual', data: idx.map((i) => row.a[i]), backgroundColor: PALETTE[0] }, { label: 'Accrual', data: idx.map((i) => row.x[i]), backgroundColor: PALETTE[2] }, { label: 'Forecast', data: idx.map((i) => row.f[i]), backgroundColor: PALETTE[3] }] }, options: { scales: { x: { stacked: true }, y: { stacked: true } } } }), 30);
}

function poolNote(pools) {
  return h('div', { class: 'note', style: { marginBottom: '14px' } }, h('b', {}, 'Pools above this line: '),
    ...pools.map((x, i) => h('span', {}, i ? ' · ' : '', h('a', { onclick: () => go('forecast', { node: 'p' + x.node_id }) }, x.code), ` ${fmt.money(x.ctc)} unassigned forecast left`, x.drawn ? ` (${fmt.money(x.drawn)} already allocated)` : '')),
    h('div', { class: 'small', style: { marginTop: '4px' } }, 'Each item below says whether it is taken out of the pool (the pool shrinks, the total stays) or comes in addition (the total grows).'));
}

// "taken out of the pool above" or "in addition": shown in every item editor of a line that has a pool above it
function poolChoice(it, ctx) {
  const pools = ctx.det.pools || [];
  if (ctx.isPot || !pools.length) return { el: null, value: () => (it.id ? it.from_pool || 0 : 0) };
  const left = pools.reduce((a, x) => a + x.ctc, 0);
  const def = it.id ? !!it.from_pool : left > 0.5;
  const yes = h('input', { type: 'radio', name: 'pool' + (it.id || 'n'), checked: def }); const no = h('input', { type: 'radio', name: 'pool' + (it.id || 'n'), checked: !def });
  const el = h('div', { class: 'card', style: { background: '#fffaf0', padding: '8px 12px', marginTop: '8px' } },
    h('div', { class: 'small' }, h('b', {}, `${pools[0].code}`), ` has ${fmt.money(pools[0].ctc)} of forecast not yet assigned to anyone${pools.length > 1 ? `; ${pools.slice(1).map((x) => `${x.code} ${fmt.money(x.ctc)}`).join(', ')} further up` : ''}.`),
    h('div', { class: 'row', style: { marginTop: '4px' } }, h('label', { class: 'row small', style: { gap: '4px' } }, yes, h('b', {}, 'Take it out of the pool'), ' (allocating: the pool goes down by this amount, the total stays)'),
      h('label', { class: 'row small', style: { gap: '4px' } }, no, h('b', {}, 'In addition'), ' (new scope: the total goes up)')));
  return { el, value: () => (yes.checked ? 1 : 0), onchange: (fn) => { yes.onchange = fn; no.onchange = fn; } };
}

function manualCard(work, det, grid, M, nodeId) {
  const fm = grid.filter((x) => x >= M); const inp = {};
  work.append(h('div', { class: 'card', style: { marginBottom: '14px' } }, h('h2', {}, 'Typed months'), h('div', { class: 'grid g6' }, fm.map((x) => { inp[x] = h('input', { type: 'number', step: '0.01', value: det.manual.find((y) => !y.item_id && y.month === x)?.amount ?? '' }); return field(fmt.month(x), inp[x]); })),
    h('div', { style: { marginTop: '10px' } }, h('button', { class: 'btn', onclick: async () => { const months = {}; Object.entries(inp).forEach(([k, i]) => { if (i.value !== '') months[k] = num(i.value); }); await api.put(p(`/nodes/${nodeId}/manual`), { months }); toast('Saved'); render(); } }, 'Save months'))));
}

// ------------------------------------------------------------------------------------------------
// Ground-up items
// ------------------------------------------------------------------------------------------------
function itemsCard(work, ctx) {
  const { det, nodeId, params } = ctx;
  const card = h('div', { class: 'card', style: { marginBottom: '14px' } });
  const edit = h('div');
  work.append(card, edit);
  const resName = (id) => { const r = ctx.resources.find((x) => x.id === id); return r ? r.name || r.code : ''; };
  card.append(h('div', { class: 'ch' }, h('h2', {}, 'Forecast items'), h('span', { class: 'sp' }), ...KINDS.map(([k, label]) => h('button', { class: 'btn sm ghost', title: KINDS.find((x) => x[0] === k)[2], onclick: () => openEditor({ spread: k === 'Linear' ? 'Linear' : k }) }, '+ ' + label))));
  if (!det.items.length) card.append(h('div', { class: 'muted' }, 'No items yet. Add one of the kinds above. A line can mix them, for example a roster for the crew plus a lump sum for mobilisation.'));
  else {
    card.append(table([
      { label: 'Kind', f: (i) => badge(KINDS.find((k) => k[0] === i.spread)?.[1] || i.spread, DETAIL.includes(i.spread) ? 'navy' : '') }, { label: 'Scope', cls: 'wrap', f: (i) => i.scope || '' },
      { label: 'Resource', f: (i) => [resName(i.resource_id), i.role].filter(Boolean).join(' · ') },
      ...(ctx.isPot || !(det.pools || []).length ? [] : [{ label: 'Pool', f: (i) => i.from_pool ? badge('taken from pool', 'warn') : badge('in addition') }]),
      { label: 'Detail', cls: 'wrap', f: (i) => i.spread === 'Roster' ? `${i.pattern || ''} from ${fmt.date(i.start_date)}${i.swings ? ', ' + i.swings + ' swings' : ''}, ${i.headcount || 1} x ${i.hours_day || '?'} h`
        : i.spread === 'Calendar' ? `Day grid in ${state.tax.basis[i.basis || 'hours'] || i.basis}` : i.spread === 'Milestones' ? `${fmt.money(i.qty * i.rate * (i.pct ?? 1))} over milestones`
          : i.spread === 'Recurring' ? `${i.freq || 'Monthly'}${i.occurrences ? ' x' + i.occurrences : ''}` : `${fmt.date(i.start_date)} – ${fmt.date(i.end_date)}` },
      { label: '', f: (i) => h('span', { class: 'row', style: { gap: '4px' } }, h('button', { class: 'btn ghost sm', onclick: () => openEditor(i) }, 'Edit'), h('button', { class: 'btn ghost sm', onclick: () => historyDialog('forecast_item', i.id, i.scope || 'Forecast item') }, 'History'),
        h('button', { class: 'btn danger sm', onclick: async () => { if (await confirmBox('Delete this forecast item and its day grid or milestones?', 'Delete', true)) { await api.del(p(`/items/${i.id}`)); render(); } } }, '×')) },
    ], det.items));
  }
  async function openEditor(it) {
    const full = it.id ? await api.get(p(`/items/${it.id}`)) : { ...it, node_id: nodeId, days: {}, milestones: [] };
    clear(edit);
    const close = () => { clear(edit); };
    const ed = { Calendar: calendarEditor, Milestones: milestoneEditor, Roster: rosterEditor }[full.spread] || classicEditor;
    ed(edit, full, { ...ctx, close });
    edit.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
  if (params.item) { const it = det.items.find((x) => String(x.id) === String(params.item)); if (it) openEditor(it); }
}

// a live preview of what an item forecasts, by month
function previewBox() {
  const box = h('div', { class: 'card', style: { background: '#f5f8ff' } }, h('div', { class: 'muted small' }, 'Preview appears here.'));
  const show = (pv) => {
    const months = Object.entries(pv.months).filter(([, v]) => Math.abs(v) > 0.005);
    clear(box).append(h('div', { class: 'row', style: { marginBottom: '8px' } }, h('b', {}, 'Cost to complete ' + fmt.money(pv.total)), pv.hours ? badge(fmt.n(pv.hours) + ' hours') : null, pv.days ? badge(pv.days + ' days after the status date') : null,
      pv.rate ? h('span', { class: 'small muted' }, `Rate ${fmt.money(pv.rate.rate, 2)}/${pv.rate.unit || 'hr'}${pv.rate.ot_rate ? `, OT ${fmt.money(pv.rate.ot_rate, 2)} after ${pv.rate.nt_hours} h` : ''}${pv.rate.allowance ? `, allowance ${fmt.money(pv.rate.allowance, 2)}/day` : ''} (${pv.rate.source})`) : null),
    ...pv.notes.map((n) => h('div', { class: 'note warn', style: { marginBottom: '6px' } }, n)),
    months.length ? h('div', { class: 'row', style: { gap: '6px' } }, months.map(([m, v]) => h('div', { class: 'kpi', style: { padding: '6px 10px', borderTopWidth: '2px' } }, h('div', { class: 'l' }, fmt.month(m)), h('div', { style: { fontWeight: 700 } }, fmt.money(v))))) : h('div', { class: 'muted small' }, `Nothing falls after the status date (${fmt.date(pv.status_date)}).`));
  };
  return { box, show };
}

function headFields(it, ctx) {
  const scope = h('input', { type: 'text', value: it.scope || '', placeholder: 'What this item pays for' });
  const note = h('input', { type: 'text', value: it.note || '' });
  return { scope, note };
}

function resourceSelect(ctx, value, kinds = ['employee', 'supplier']) {
  const opts = [['', '(choose)']];
  kinds.forEach((k) => { const l = ctx.resources.filter((r) => r.kind === k); if (l.length) l.forEach((r) => opts.push([r.id, `${k === 'employee' ? '👤' : '🏢'} ${r.name || r.code} [${r.code}]`])); });
  return select(opts, value ?? (ctx.det.resource_id || ''));
}

async function roleSelect(resId, current, resources = []) {
  const wrap = h('span');
  const fill = async (rid) => {
    const kind = resources.find((x) => x.id === +rid)?.kind;
    const rates = rid && kind !== 'employee' ? (await api.get(p('/supplier-rates'))).filter((r) => r.resource_id === +rid) : [];
    const s = rates.length ? select([['', '(choose role)'], ...rates.map((r) => [r.role, `${r.role} · ${fmt.money(r.rate, 2)}/${r.unit}`])], current || '')
      : h('input', { type: 'text', value: kind === 'employee' ? '' : current || '', disabled: kind === 'employee', placeholder: kind === 'employee' ? 'Not needed for an employee' : rid ? 'No supplier rates yet' : 'Role from the rate card, e.g. Project Engineer' });
    clear(wrap).append(s); wrap.input = s;
  };
  await fill(resId);
  wrap.refill = fill;
  return wrap;
}

function saveBar(onSave, ctx, extra = []) {
  return h('div', { class: 'row', style: { marginTop: '12px' } }, h('button', { class: 'btn', onclick: async (e) => { e.target.disabled = true; try { await onSave(); } catch (err) { toast(err.message, 'bad'); } e.target.disabled = false; } }, 'Save item'), h('button', { class: 'btn ghost', onclick: ctx.close }, 'Cancel'), ...extra);
}

const saveItem = async (ctx, body) => { const r = await api.post(p(`/nodes/${ctx.nodeId}/items`), body); toast('Forecast item saved'); return r; };

// ---- Calendar: a day grid for one resource ------------------------------------------------------
async function calendarEditor(root, it, ctx) {
  const { scope, note } = headFields(it, ctx);
  const res = resourceSelect(ctx, it.resource_id);
  const role = await roleSelect(it.resource_id, it.role, ctx.resources);
  const basis = select(Object.entries(state.tax.basis), it.basis || 'hours');
  const mode = select([['auto', 'Look it up (employee rate, rate card or supplier rates)'], ['fixed', 'Type a rate']], it.rate_mode || (it.rate ? 'fixed' : 'auto'));
  const rate = h('input', { type: 'number', step: '0.01', value: it.rate ?? '' });
  const unit = h('input', { type: 'text', value: it.unit || '', placeholder: 'hr, day, night, ea' });
  const days = { ...(it.days || {}) };
  const pool = poolChoice(it, ctx);
  const changed = new Set();
  const pv = previewBox();
  const sd = state.project.status_date || new Date().toISOString().slice(0, 10);
  // months shown: from the month before the status date (to see the recent past) to the line end, at least six months
  const lineEnd = (ctx.row.end || '').slice(0, 7);
  const firstDay = Object.keys(days).sort()[0]; const lastDay = Object.keys(days).sort().slice(-1)[0];
  let from = [addMonths(sd.slice(0, 7), -1), firstDay ? firstDay.slice(0, 7) : null].filter(Boolean).sort()[0];
  let to = [addMonths(sd.slice(0, 7), 5), lineEnd, lastDay ? lastDay.slice(0, 7) : null].filter(Boolean).sort().slice(-1)[0];
  const hols = Object.fromEntries((await api.get(p('/holidays'))).map((x) => [x.day, x.name]));
  const gridBox = h('div');
  const refresh = debounce(async () => {
    try { pv.show(await api.post(p('/forecast/preview'), body(false))); } catch (e) { /* incomplete */ }
  }, 350);
  const body = (forSave) => ({ id: it.id, spread: 'Calendar', scope: scope.value, note: note.value, resource_id: res.value ? +res.value : null, role: role.input?.value || null,
    basis: basis.value, rate_mode: mode.value, rate: mode.value === 'fixed' ? num(rate.value) : null, unit: unit.value, qty: 1, pct: 1, from_pool: pool.value(),
    days: forSave ? Object.fromEntries([...changed].map((d) => [d, days[d] ?? null])) : days });
  const drawGrid = () => clear(gridBox).append(dayGrid({ from, to, values: days, statusDate: sd, holidays: hols, unit: basis.value === 'dollars' ? '$' : basis.value === 'hours' ? 'h' : unit.value || 'u',
    onChange: (d, v) => { if (v === null) delete days[d]; else days[d] = v; changed.add(d); refresh(); } }));
  res.onchange = async () => { await role.refill(res.value); role.input.onchange = refresh; refresh(); };
  if (role.input) role.input.onchange = refresh;
  [basis, mode, rate, unit].forEach((x) => { x.onchange = () => { rateRow(); drawGrid(); refresh(); }; });
  const rateField = h('span');
  const rateRow = () => { clear(rateField).append(mode.value === 'fixed' ? field('Rate', rate) : h('span')); };
  rateRow();
  // fill tool
  const fFrom = h('input', { type: 'date', value: nextDay(sd) }); const fTo = h('input', { type: 'date' }); const fVal = h('input', { type: 'number', step: 'any', value: 8, style: { width: '80px' } });
  const fPat = select([['WEEKDAYS', 'Weekdays'], ['DAILY', 'Every day'], ...state.tax.patterns.filter((x) => x.includes(':')).map((x) => [x, `Roster ${x}`])], 'WEEKDAYS');
  const fSkip = h('input', { type: 'checkbox', checked: true });
  const fill = (clearIt) => {
    if (!fFrom.value || !fTo.value) return toast('Choose the From and To dates', 'bad');
    const ds = patternDays(fFrom.value, fTo.value, fPat.value).filter((d) => !(fSkip.checked && hols[d]));
    ds.forEach((d) => { if (clearIt) delete days[d]; else days[d] = num(fVal.value); changed.add(d); });
    if (fTo.value.slice(0, 7) > to) to = fTo.value.slice(0, 7);
    if (fFrom.value.slice(0, 7) < from) from = fFrom.value.slice(0, 7);
    drawGrid(); refresh(); toast(`${ds.length} days ${clearIt ? 'cleared' : 'filled'}`);
  };
  root.append(h('div', { class: 'card', style: { marginBottom: '14px', borderTop: '3px solid var(--gold)' } },
    h('div', { class: 'ch' }, h('h2', {}, it.id ? 'Edit resource calendar' : 'New resource calendar'), h('span', { class: 'sp' }),
      it.id && it.resource_id ? h('button', { class: 'btn ghost sm', title: 'Forecast hours on days up to the status date that have no timesheet yet become hour accruals', onclick: async () => { const r = await api.post(p(`/items/${it.id}/accrue-past`)); toast(`${r.accrued_days} days accrued`); render(); } }, 'Accrue past days without timesheets') : null),
    h('div', { class: 'grid g4' }, field('Scope', scope), field('Resource', res), field('Role (suppliers)', role), field('Values in the grid are', basis)),
    h('div', { class: 'grid g4', style: { marginTop: '8px' } }, field('Rate', mode), rateField, field('Unit label', unit), field('Note', note)), pool.el,
    h('div', { class: 'row card', style: { marginTop: '12px', background: '#f6f8f9', padding: '8px 12px' } }, h('b', { class: 'small' }, 'Fill'), fVal, h('span', { class: 'small' }, 'from'), fFrom, h('span', { class: 'small' }, 'to'), fTo, fPat,
      h('label', { class: 'row small', style: { gap: '4px' } }, fSkip, 'skip public holidays'), h('button', { class: 'btn sm', onclick: () => fill(false) }, 'Fill'), h('button', { class: 'btn sm ghost', onclick: () => fill(true) }, 'Clear these days'),
      h('span', { class: 'sp', style: { flex: 1 } }), h('button', { class: 'btn sm ghost', onclick: () => { from = addMonths(from, -1); drawGrid(); } }, '+ earlier month'), h('button', { class: 'btn sm ghost', onclick: () => { to = addMonths(to, 1); drawGrid(); } }, '+ later month')),
    h('div', { style: { marginTop: '10px' } }, gridBox), h('div', { style: { marginTop: '10px' } }, pv.box),
    saveBar(async () => { await saveItem(ctx, body(true)); render(); }, ctx)));
  drawGrid(); refresh();
}

// ---- Milestones -----------------------------------------------------------------------------------
async function milestoneEditor(root, it, ctx) {
  const { scope, note } = headFields(it, ctx);
  const value = h('input', { type: 'number', step: '0.01', value: it.id ? (it.qty || 1) * (it.rate || 0) * (it.pct ?? 1) : '' , placeholder: 'PO or contract value' });
  const po = h('input', { type: 'text', value: it.po_no || '' });
  const res = resourceSelect(ctx, it.resource_id, ['supplier']);
  const rows = (it.milestones || []).map((x) => ({ ...x }));
  if (!rows.length) rows.push({ name: '', pct: '', month: '', status: 'forecast' });
  const pool = poolChoice(it, ctx);
  const list = h('div'); const pv = previewBox(); const totalBox = h('div', { class: 'row', style: { marginTop: '8px' } });
  const preset = select([['', 'Fill from a preset...'], ...Object.keys(state.tax.milestone_presets).map((k) => [k, k])], '');
  preset.onchange = () => { const ps = state.tax.milestone_presets[preset.value]; if (!ps) return; rows.splice(0, rows.length, ...ps.map(([n, pc]) => ({ name: n, pct: pc, month: '', status: 'forecast' }))); draw(); refresh(); preset.value = ''; };
  const refresh = debounce(async () => { try { pv.show(await api.post(p('/forecast/preview'), body())); } catch (e) { /* incomplete */ } }, 300);
  const body = () => ({ id: it.id, spread: 'Milestones', scope: scope.value, note: note.value, qty: 1, rate: num(value.value), pct: 1, po_no: po.value, resource_id: res.value ? +res.value : null, from_pool: pool.value(),
    milestones: rows.filter((r) => r.name || r.pct).map((r, i) => ({ id: r.id, seq: i, name: r.name, pct: num(r.pct), month: r.month || null, status: r.status || 'forecast', note: r.note || null })) });
  function draw() {
    const v = num(value.value);
    clear(list).append(h('table', { class: 't', style: { width: '100%' } }, h('thead', {}, h('tr', {}, ['#', 'Milestone', '%', 'Amount', 'Expected month', 'Status', 'Note', ''].map((x, i) => h('th', { class: [2, 3].includes(i) ? 'r' : '' }, x)))),
      h('tbody', {}, rows.map((r, i) => {
        const nm = h('input', { type: 'text', value: r.name || '', placeholder: 'e.g. On drawing submission', oninput: (e) => { r.name = e.target.value; refresh(); } });
        const pc = h('input', { type: 'number', step: '0.5', value: r.pct === '' || r.pct === undefined ? '' : +(num(r.pct) * 100).toFixed(4), style: { width: '80px' }, oninput: (e) => { r.pct = num(e.target.value) / 100; amt.textContent = fmt.money(v * r.pct); total(); refresh(); } });
        const amt = h('span', {}, fmt.money(v * num(r.pct)));
        const mo = h('input', { type: 'month', value: (r.month || '').slice(0, 7), onchange: (e) => { r.month = e.target.value; refresh(); } });
        const st = select([['forecast', 'Forecast'], ['reached', 'Reached, not invoiced'], ['invoiced', 'Invoiced (in actuals)']], r.status || 'forecast', { onchange: (e) => { r.status = e.target.value; refresh(); } });
        const nt = h('input', { type: 'text', value: r.note || '', oninput: (e) => { r.note = e.target.value; } });
        const mv = (d) => { const j = i + d; if (j < 0 || j >= rows.length) return; [rows[i], rows[j]] = [rows[j], rows[i]]; draw(); };
        return h('tr', {}, h('td', { class: 'muted' }, i + 1), h('td', { class: 'in' }, nm), h('td', { class: 'in r' }, pc), h('td', { class: 'r num' }, amt), h('td', { class: 'in' }, mo), h('td', {}, st), h('td', { class: 'in' }, nt),
          h('td', {}, h('span', { class: 'row', style: { gap: '2px' } }, h('button', { class: 'btn ghost sm', onclick: () => mv(-1) }, '↑'), h('button', { class: 'btn ghost sm', onclick: () => mv(1) }, '↓'), h('button', { class: 'btn danger sm', onclick: () => { rows.splice(i, 1); draw(); refresh(); } }, '×'))));
      }))), h('div', { class: 'row', style: { marginTop: '8px' } }, h('button', { class: 'btn ghost sm', onclick: () => { rows.push({ name: '', pct: '', month: '', status: 'forecast' }); draw(); } }, '+ Add milestone'), preset));
    total();
  }
  function total() {
    const t = rows.reduce((a, r) => a + num(r.pct), 0);
    clear(totalBox).append(badge(`Total ${(t * 100).toFixed(1)}%`, Math.abs(t - 1) < 0.0005 ? 'good' : 'bad'), Math.abs(t - 1) < 0.0005 ? h('span', { class: 'small muted' }, 'Milestones add up to the full value.') : h('span', { class: 'small bad' }, `They should add up to 100%. ${t < 1 ? fmt.money(num(value.value) * (1 - t)) + ' is not forecast.' : ''}`));
  }
  value.oninput = () => { draw(); refresh(); };
  root.append(h('div', { class: 'card', style: { marginBottom: '14px', borderTop: '3px solid var(--gold)' } }, h('h2', {}, it.id ? 'Edit milestone payments' : 'New milestone payments'),
    h('div', { class: 'grid g4' }, field('Scope', scope), field('Value (excl. GST)', value, 'Usually the PO value'), field('PO number', po), field('Supplier', res)), pool.el,
    h('div', { class: 'small muted', style: { margin: '10px 0 6px' } }, 'One row per milestone in the order the supplier reaches them. An open milestone in a past month moves to the status month; an invoiced one is in actuals and leaves the forecast.'),
    list, totalBox, h('div', { style: { marginTop: '10px' } }, pv.box), saveBar(async () => { await saveItem(ctx, body()); render(); }, ctx)));
  draw(); refresh();
}

// ---- Roster -------------------------------------------------------------------------------------
async function rosterEditor(root, it, ctx) {
  const { scope, note } = headFields(it, ctx);
  const res = resourceSelect(ctx, it.resource_id, ['supplier', 'employee']);
  const role = await roleSelect(it.resource_id || ctx.det.resource_id, it.role, ctx.resources);
  const start = h('input', { type: 'date', value: it.start_date || nextDay(state.project.status_date || '') });
  const pat = h('input', { type: 'text', value: it.pattern || '10:4', list: 'pmt-patterns', style: { width: '120px' } });
  const dl = h('datalist', { id: 'pmt-patterns' }, state.tax.patterns.map((x) => h('option', { value: x })));
  const swings = h('input', { type: 'number', step: '1', min: '1', value: it.swings ?? 5 });
  const end = h('input', { type: 'date', value: it.end_date && !it.swings ? it.end_date : '' });
  const heads = h('input', { type: 'number', step: '1', min: '1', value: it.headcount ?? 1 });
  const hours = h('input', { type: 'number', step: '0.5', value: it.hours_day ?? 12 });
  const skip = h('input', { type: 'checkbox', checked: !!it.skip_holidays });
  const mode = select([['auto', 'From the supplier rates for the role'], ['fixed', 'Type a rate per hour']], it.rate_mode || 'auto');
  const rate = h('input', { type: 'number', step: '0.01', value: it.rate ?? '' });
  const rateWrap = h('span');
  const pool = poolChoice(it, ctx);
  const pv = previewBox();
  const body = () => ({ id: it.id, spread: 'Roster', scope: scope.value, note: note.value, resource_id: res.value ? +res.value : null, role: role.input?.value || null,
    start_date: start.value || null, end_date: end.value || null, pattern: pat.value, swings: swings.value === '' ? null : +swings.value, headcount: num(heads.value) || 1,
    hours_day: num(hours.value), skip_holidays: skip.checked ? 1 : 0, rate_mode: mode.value, rate: mode.value === 'fixed' ? num(rate.value) : null, qty: 1, pct: 1, basis: 'hours', from_pool: pool.value() });
  const refresh = debounce(async () => {
    try { const r = await api.post(p('/forecast/preview'), body()); pv.show(r); calStrip(r.all_days); } catch (e) { clear(pv.box).append(h('div', { class: 'note bad' }, e.message)); }
  }, 300);
  const strip = h('div', { style: { marginTop: '8px' } });
  const calStrip = (dd) => { const s = new Set(dd); if (!dd.length) { clear(strip); return; } const a = dd[0].slice(0, 7); const b = dd[dd.length - 1].slice(0, 7);
    clear(strip).append(dayGrid({ from: a, to: b, values: Object.fromEntries(dd.map((d) => [d, num(heads.value) * num(hours.value)])), statusDate: state.project.status_date, holidays: {}, readOnly: true, unit: 'h' })); };
  res.onchange = async () => { await role.refill(res.value); role.input.onchange = refresh; refresh(); };
  role.input && (role.input.onchange = refresh);
  mode.onchange = () => { clear(rateWrap).append(mode.value === 'fixed' ? field('Rate per hour', rate) : h('span')); refresh(); };
  mode.onchange();
  [start, pat, swings, end, heads, hours, skip, rate].forEach((x) => { x.oninput = refresh; x.onchange = refresh; });
  root.append(h('div', { class: 'card', style: { marginBottom: '14px', borderTop: '3px solid var(--gold)' } }, dl, h('h2', {}, it.id ? 'Edit roster' : 'New roster'),
    h('div', { class: 'small muted', style: { marginBottom: '8px' } }, 'Example: from 01/09/2026 a 10:4 roster for 5 swings with 5 electricians of supplier X at 12 hours a shift. The cost follows the supplier\'s rates for the role: normal time, overtime after the normal hours, and the daily allowance.'),
    h('div', { class: 'grid g4' }, field('Scope', scope), field('Supplier or person', res), field('Role', role, h('a', { href: '#/resources?tab=srates' }, 'Supplier rates')), field('Note', note)),
    h('div', { class: 'grid g6', style: { marginTop: '8px' } }, field('First day', start), field('Pattern (on:off)', pat), field('Swings', swings, 'or leave blank and set an end'), field('Or end date', end), field('Headcount', heads), field('Hours a shift', hours)),
    h('div', { class: 'grid g4', style: { marginTop: '8px' } }, field('Rate', mode), rateWrap, h('label', { class: 'row small', style: { marginTop: '22px' } }, skip, 'No work on public holidays'), h('span')), pool.el,
    h('div', { style: { marginTop: '10px' } }, pv.box), strip, saveBar(async () => { await saveItem(ctx, body()); render(); }, ctx)));
  refresh();
}

// ---- Quantity x rate (Lump, Linear, Recurring) and typed months for one item ---------------------
async function classicEditor(root, it, ctx) {
  const { scope, note } = headFields(it, ctx);
  const spread = select(['Lump', 'Linear', 'Recurring', 'Manual'], it.spread || 'Linear');
  const unit = h('input', { type: 'text', value: it.unit || '', placeholder: 'hr, day, ea' }); const qty = h('input', { type: 'number', step: 'any', value: it.qty ?? 1 }); const rate = h('input', { type: 'number', step: '0.01', value: it.rate ?? 0 });
  const pct = h('input', { type: 'number', step: '0.01', value: it.pct ?? 1 }); const start = h('input', { type: 'date', value: it.start_date || '' }); const end = h('input', { type: 'date', value: it.end_date || '' });
  const freq = select(state.tax.frequencies, it.freq || 'Monthly'); const occ = h('input', { type: 'number', value: it.occurrences || '', placeholder: 'or until End' });
  const fm = ctx.grid.filter((m) => m >= ctx.M); const mi = {};
  const manual = h('div', { class: 'grid g6' }, fm.map((m) => { mi[m] = h('input', { type: 'number', step: '0.01', value: ctx.det.manual.find((x) => x.item_id === it.id && x.month === m)?.amount ?? '' }); return field(fmt.month(m), mi[m]); }));
  const tog = h('div', { style: { marginTop: '8px' } });
  const pool = poolChoice(it, ctx);
  const pv = previewBox();
  const body = () => { const months = {}; Object.entries(mi).forEach(([m, i]) => { if (i.value !== '') months[m] = num(i.value); });
    return { id: it.id, scope: scope.value, note: note.value, spread: spread.value, unit: unit.value, qty: num(qty.value), rate: num(rate.value), pct: num(pct.value) || 1, start_date: start.value || null, end_date: end.value || null, freq: freq.value, occurrences: occ.value ? +occ.value : null, months: spread.value === 'Manual' ? months : undefined, from_pool: pool.value() }; };
  const refresh = debounce(async () => { if (spread.value === 'Manual') { clear(pv.box); return; } try { pv.show(await api.post(p('/forecast/preview'), body())); } catch (e) { /* incomplete */ } }, 300);
  const sync = () => { clear(tog).append(spread.value === 'Manual' ? manual : h('div', { class: 'grid g4' }, field('Start', start), field('End', end), ...(spread.value === 'Recurring' ? [field('Every', freq), field('Occurrences', occ)] : []))); refresh(); };
  spread.onchange = sync;
  [unit, qty, rate, pct, start, end, freq, occ].forEach((x) => { x.oninput = refresh; x.onchange = refresh; });
  root.append(h('div', { class: 'card', style: { marginBottom: '14px', borderTop: '3px solid var(--gold)' } }, h('h2', {}, it.id ? 'Edit forecast item' : 'New forecast item'),
    h('div', { class: 'grid g6' }, field('Scope', scope), field('Spread', spread), field('Quantity', qty), field('Unit', unit), field('Rate', rate), field('Share (1 = 100%)', pct)), tog, field('Note', note), pool.el,
    h('div', { style: { marginTop: '10px' } }, pv.box), saveBar(async () => { await saveItem(ctx, body()); render(); }, ctx)));
  sync();
}

// ------------------------------------------------------------------------------------------------
// Day grid: one row per month, one column per day of the month
// ------------------------------------------------------------------------------------------------
export function dayGrid({ from, to, values, statusDate, holidays = {}, onChange, readOnly = false, unit = 'h' }) {
  const months = []; for (let m = from; m <= to && months.length < 36; m = addMonths(m, 1)) months.push(m);
  const head = h('tr', {}, h('th', {}, 'Month'), ...Array.from({ length: 31 }, (_, i) => h('th', { class: 'dn' }, i + 1)), h('th', { class: 'r' }, 'Total'));
  const tb = h('tbody');
  // months are the rows here, so the outline folds rows: a heading row per financial year quarter (click to fold it), and the 1 2 levels above the grid
  const FK = 'pmt.dgfold'; let foldedQ = new Set(); try { foldedQ = new Set(JSON.parse(localStorage.getItem(FK) || '[]')); } catch (e) { /* storage may be blocked */ }
  const saveQ = () => { try { localStorage.setItem(FK, JSON.stringify([...foldedQ])); } catch (e) { /* ignore */ } };
  const qOf = (m) => fyQuarter(m); const qMonths = new Map(); months.forEach((m) => { const k = qOf(m).key; qMonths.set(k, (qMonths.get(k) || 0) + 1); });
  const qRows = new Map(); const qHead = new Map();
  const applyFold = () => { qRows.forEach((rs, k) => rs.forEach((r) => r.classList.toggle('tt-fold', foldedQ.has(k)))); qHead.forEach((c, k) => { c.arr.style.transform = foldedQ.has(k) ? '' : 'rotate(90deg)'; c.cnt.textContent = foldedQ.has(k) ? ` \u00b7 ${qMonths.get(k)} month${qMonths.get(k) === 1 ? '' : 's'} folded` : ''; }); lv.querySelectorAll('b').forEach((b, i) => b.classList.toggle('on', i === 1 ? foldedQ.size === 0 : foldedQ.size === qMonths.size - 1 && !foldedQ.has(qOf(statusDate ? statusDate.slice(0, 7) : months[0]).key))); };
  const lv = h('div', { class: 'ol-lv', style: { position: 'static', margin: '2px 0 4px 2px' } },
    h('b', { 'data-tip': 'This quarter only', onclick: () => { const cq = qOf(statusDate ? statusDate.slice(0, 7) : months[0]).key; foldedQ = new Set([...qMonths.keys()].filter((k) => k !== cq)); saveQ(); applyFold(); } }, '1'),
    h('b', { 'data-tip': 'Every month', onclick: () => { foldedQ = new Set(); saveQ(); applyFold(); } }, '2'));
  months.forEach((m) => {
    const [y, mo] = m.split('-').map(Number); const nd = new Date(y, mo, 0).getDate();
    const qk = qOf(m).key;
    if (!qHead.has(qk)) {
      const arr = h('span', { style: { display: 'inline-block', width: '14px', transition: 'transform .12s' } }, '\u25B8'); const cnt = h('span', { class: 'muted small' });
      qHead.set(qk, { arr, cnt });
      tb.append(h('tr', { class: 'par qh', style: { cursor: 'pointer' }, onclick: () => { if (foldedQ.has(qk)) foldedQ.delete(qk); else foldedQ.add(qk); saveQ(); applyFold(); } }, h('td', { colSpan: 33, style: { padding: '3px 8px' } }, arr, qOf(m).label, cnt)));
    }
    const tot = h('td', { class: 'r num tot' });
    const sum = () => { let s = 0; for (let d = 1; d <= nd; d++) s += num(values[`${m}-${String(d).padStart(2, '0')}`] || 0); tot.textContent = s ? Math.round(s * 100) / 100 + ' ' + unit : ''; };
    const tr = h('tr', {}, h('td', { class: 'mo' }, fmt.month(m)));
    for (let d = 1; d <= 31; d++) {
      if (d > nd) { tr.append(h('td', { class: 'nx' })); continue; }
      const iso = `${m}-${String(d).padStart(2, '0')}`; const wd = new Date(y, mo - 1, d).getDay();
      const cls = ['d', wd === 0 || wd === 6 ? 'we' : '', holidays[iso] ? 'hol' : '', statusDate && iso <= statusDate ? 'past' : ''].join(' ');
      const v = values[iso];
      if (readOnly) { tr.append(h('td', { class: cls + (v ? ' on' : ''), title: `${fmt.date(iso)}${holidays[iso] ? ' ' + holidays[iso] : ''}` }, v ? '' : '')); continue; }
      const inp = h('input', { type: 'text', inputmode: 'decimal', placeholder: ' ', value: v ?? '', title: `${['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][wd]} ${fmt.date(iso)}${holidays[iso] ? ' · ' + holidays[iso] : ''}${statusDate && iso <= statusDate ? ' · on or before the status date: timesheets and accruals, not forecast' : ''}` });
      inp.onchange = () => { const t = inp.value.trim(); onChange && onChange(iso, t === '' ? null : num(t)); sum(); };
      inp.onkeydown = (e) => { // arrow keys move across the grid; up and down keep the day number
        if (!['ArrowRight', 'ArrowLeft', 'ArrowUp', 'ArrowDown'].includes(e.key)) return;
        const all = [...tb.querySelectorAll('input')].filter((x) => x.offsetParent); const i = all.indexOf(inp);
        const j = e.key === 'ArrowRight' ? i + 1 : e.key === 'ArrowLeft' ? i - 1 : sameDay(all, i, e.key === 'ArrowDown' ? 1 : -1);
        const t = all[j]; if (t) { e.preventDefault(); t.focus(); t.select(); }
      };
      tr.append(h('td', { class: cls }, inp));
    }
    tr.append(tot); sum(); tb.append(tr); if (!qRows.has(qk)) qRows.set(qk, []); qRows.get(qk).push(tr);
  });
  setTimeout(applyFold, 0);
  return h('div', { class: 'tw dg' + (readOnly ? ' ro' : '') }, ...(qHead.size > 1 ? [lv] : []), h('table', { class: 't' }, h('thead', {}, head), tb),
    h('div', { class: 'legend', style: { padding: '6px 8px' } }, h('span', {}, h('i', { style: { background: '#e8ecf3' } }), 'Weekend'), h('span', {}, h('i', { style: { background: '#fbd9d5' } }), 'Public holiday'), h('span', {}, h('i', { style: { background: '#d9dde0' } }), 'On or before the status date')));
}
function sameDay(all, i, dir) { // the same day number in the next / previous month row
  const row = all[i].closest('tr'); const rows = [...row.parentNode.children].filter((x) => !x.classList.contains('qh') && !x.classList.contains('tt-fold')); const r = rows.indexOf(row); const col = [...row.children].indexOf(all[i].parentNode);
  const t = rows[r + dir]; if (!t) return i; const cell = t.children[col]?.querySelector('input'); return cell ? all.indexOf(cell) : i;
}

export function addMonths(ym, n) { const [y, m] = ym.split('-').map(Number); const t = y * 12 + (m - 1) + n; return `${Math.floor(t / 12)}-${String((t % 12) + 1).padStart(2, '0')}`; }
const nextDay = (iso) => { if (!iso) return ''; const d = new Date(iso + 'T00:00:00'); d.setDate(d.getDate() + 1); return toIso(d); };
const toIso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
export function patternDays(a, b, pat) {
  const out = []; const d = new Date(a + 'T00:00:00'); const e = new Date(b + 'T00:00:00');
  let on = 0, off = 0; if (pat.includes(':')) [on, off] = pat.split(':').map(Number);
  for (let i = 0; d <= e && i < 2000; i++, d.setDate(d.getDate() + 1)) {
    const wd = d.getDay();
    if (pat === 'DAILY' || (pat === 'WEEKDAYS' && wd > 0 && wd < 6) || (on && i % (on + off) < on)) out.push(toIso(d));
  }
  return out;
}
