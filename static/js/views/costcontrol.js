import { h, clear, fmt, modal, toast, field, select, table, num, confirmBox, badge, tabs, empty, drawer, chart, PALETTE, statusPill, tone, debounce, filterMenu } from '../ui.js';
import { api, state, p, loadRows, pref } from '../api.js';
import { pickNode, indexRows, pathTo, setScope } from '../scope.js';
import { go, render } from '../app.js';
import { accrualDialog } from './accruals.js';
import { splitDialog } from '../rollup.js';
import { monthInput } from '../monthplan.js';
import { outlineState, outlineStrip, visible as olVisible, MONTH_LEVELS } from '../outline.js';
import { cmtUpload } from './_cmt.js';
import { when, who, changeList, opBadge, historyDialog } from '../history.js';

const METHOD_NOTE = {
  'GROUND-UP': 'Built from forecast items below (quantity x rate over time).',
  'CLAIM': 'Net of retention, from the linked subcontract claim schedule.',
  'BURN-RATE': 'Average monthly spend to date x remaining months. The current month is excluded.',
  'AT-BUDGET': 'Remaining allowance, spread over the remaining months.',
  'AT-COMMIT': 'Open PO commitments plus what you expect to commit that is not yet on a PO.',
  'TOP-DOWN': 'You type the EAC; cost to complete is the EAC less CTD and accruals.',
  'MANUAL': 'You type the monthly amounts.',
};

// move allowance from each unallocated pool to the lines whose cost it is covering (transfers, shown before they are made)
async function poolDialog(held = 0, pools = 0) {
  const r = await api.get(p('/pools/allocation'));
  if (!r.moves.length) {
    // the banner counted cost that the pools cover, but there is no line with an allowance of its own to move it to: say why, and where to go
    modal({ title: 'Nothing to move yet', body: h('div', {}, h('p', {}, `${pools} unallocated pool${pools === 1 ? '' : 's'} cover${pools === 1 ? 's' : ''} ${fmt.money(held)} of cost, but no transfer can be made from here: that cost sits on lines with no allowance of their own to top up (for example WIP (Unallocated CTD) or CTC (Unallocated) lines, or cost that has no resource line yet).`),
      h('p', {}, 'To give those lines an allowance, open Allowances and drag a pot onto the line, or link the resource on Setup > Allowance. Until then the pool keeps covering the cost and the group total is right.')),
      actions: [{ label: 'Close', kind: 'ghost', onClick: () => {} }, { label: 'Open Allowances', onClick: () => go('risk', { tab: 'allowance' }) }] });
    return;
  }
  modal({ title: 'Allocate unallocated allowance to cover costs', size: 'wide', body: h('div', {}, h('p', { class: 'muted' }, 'Each line below has cost beyond its own allowance, which the unallocated allowance of its group is covering. Applying posts a transfer from the pool to the line, so the line carries the allowance it needs. Totals do not change.'),
    table([{ label: 'Pool (group)', f: (m) => m.group }, { label: 'Line', f: (m) => m.line }, { label: 'Over its allowance', r: 1, f: (m) => fmt.money(m.over) }, { label: 'Transfer', r: 1, f: (m) => fmt.money(m.amount) }], r.moves, { foot: (c) => (c.label === 'Transfer' ? fmt.money(r.total) : c.label === 'Line' ? 'Total' : '') })),
    actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} }, { label: `Allocate ${fmt.money(r.total)}`, onClick: async () => { const o = await api.post(p('/pools/allocation'), {}); toast(`${o.moves.length} transfer(s) posted`); await loadRows(true); await render(); } }] });
}

export default async function costControl(root, params) {
  const res = await api.get(p('/cost-control?months=1&merge=1'));  // base and variation scope of a line together
  const rows = res.rows; const grid = res.grid; const M = res.status_month;
  const { byId, kids } = indexRows(rows);
  const sc = state.scope;
  if (params.node) { const r = byId.get(String(params.node)); if (r) setScope(r); }
  const scopeId = state.scope.node;
  const ui = JSON.parse(sessionStorage.getItem('ccui') || '{}');
  ui.level = ui.level ?? +pref('cc_level'); ui.months = ui.months ?? !!pref('cc_months'); ui.hideZero = ui.hideZero ?? !!pref('cc_hide_zero'); ui.only = ui.only ?? pref('cc_only'); ui.q = '';
  const ost = outlineState('cc');   // folded quarters and hidden months of the month grid (kept on this PC; null = quarters before the status month are folded)
  const save = () => sessionStorage.setItem('ccui', JSON.stringify({ level: ui.level, months: ui.months, hideZero: ui.hideZero, only: ui.only }));
  const open = new Set();
  rows.forEach((r) => { if (r.kind === 'group' && r.level < ui.level) open.add(String(r.id)); });
  // which groups are open survives a re-draw (after an edit, say) as long as the level chip has not changed
  const OKEY = 'ccOpen:' + state.pid;
  const saveOpen = () => { try { sessionStorage.setItem(OKEY, JSON.stringify({ level: ui.level, ids: [...open] })); } catch (e) { /* storage may be blocked */ } };
  try { const st = JSON.parse(sessionStorage.getItem(OKEY) || 'null'); if (st && st.level === ui.level && Array.isArray(st.ids)) { open.clear(); st.ids.forEach((x) => open.add(String(x))); } } catch (e) { /* ignore */ }
  if (scopeId) pathTo(rows, scopeId).forEach((r) => open.add(String(r.id)));

  const t = res.total;
  root.append(h('div', { class: 'pagehead' },
    h('div', {}, h('h1', {}, 'Cost control'), h('div', { class: 'sub' }, res.is_parent
      ? `Parent project: ${(res.children || []).map((c) => c.name).join(' + ')}, CBS added together code by code (latest status month ${fmt.month(M)}). Click any line or amount for each project's share and open it in that project.`
      : `Status month ${fmt.month(M)}. EAC = CTD + accruals + CTC (accruals are included, unlike the CMT).`)),
    h('div', { class: 'sp' }),
    res.is_parent ? null : h('button', { class: 'btn ghost', title: 'Compare a Cost Management Tool with cost control, then reject or align each difference', onclick: cmtUpload }, 'Load a CMT'),
    h('button', { class: 'btn ghost', onclick: () => window.open(p('/cost-control.xlsx')) }, 'Export to Excel')));
  try {
    const ls = JSON.parse(sessionStorage.getItem('lastSpread') || 'null');
    if (ls && !res.is_parent) root.append(h('div', { class: 'note', style: { marginBottom: '10px' } }, `Spread ${fmt.money(ls.total)} from ${ls.from} over ${ls.n} lines. `,
      h('button', { class: 'btn ghost sm', onclick: async () => { await api.post(p('/ledger/spread/undo'), { pairs: ls.pairs }); sessionStorage.removeItem('lastSpread'); toast('Spread undone'); await render(); } }, 'Undo'),
      h('button', { class: 'btn ghost sm', style: { marginLeft: '6px' }, onclick: () => { sessionStorage.removeItem('lastSpread'); render(); } }, 'Dismiss')));
  } catch (e) { /* ignore */ }
  // unallocated pools that still forecast their remaining allowance: on a project that is already running that counts the cost twice
  if (res.initialised && !res.is_parent) {
    const live = (res.rows || []).filter((r) => r.kind === 'pot' && r.method && r.method !== 'NONE' && Math.abs((r.allowance || 0) - (r.ctd || 0) - (r.acc || 0)) > 0.5);
    if (live.length) {
      const sum = live.reduce((a, r) => a + (r.ctc || 0), 0);
      root.append(h('div', { class: 'note warn', style: { marginBottom: '10px' } },
        h('b', {}, `${live.length} unallocated pools still forecast their allowance (${fmt.money(sum)}). `),
        'If their cost is already on the lines below, that counts it twice. Set them to NONE, then forecast what remains on the lines, or on the CTC (Unallocated) line of the parent. ',
        h('button', { class: 'btn sm', style: { marginLeft: '6px' }, onclick: async () => { const o = await api.post(p('/pools/method'), { method: 'NONE' }); toast(`${o.updated} unallocated pools set to NONE`); await render(); } }, 'Set all unallocated pools to NONE')));
    }
  }
  if (!res.is_parent) root.append(h('div', { class: 'small muted', style: { marginBottom: '8px' } }, 'To spread an unallocated pool over its lines: press the grip (four dots) beside its allowance on an (Unallocated) row, drag down over the lines, release. Double-click an allowance to open it.'));
  // unallocated pools now cover the costs that landed on the lines beneath them: say so, and offer the allocation that makes it permanent
  const covered = (res.rows || []).filter((r) => r.kind === 'pot' && r.pool_covered > 0.5);
  if (covered.length && !res.is_parent) root.append(h('div', { class: 'note', style: { marginBottom: '10px', display: 'flex', gap: '12px', alignItems: 'center' } }, h('span', { style: { flex: 1 } },
    `${covered.length} unallocated pool${covered.length > 1 ? 's' : ''} cover${covered.length > 1 ? '' : 's'} ${fmt.money(covered.reduce((a, r) => a + r.pool_covered, 0))} of cost that landed on the lines beneath ${covered.length > 1 ? 'them' : 'it'}, so that cost is not forecast a second time. Allocate the allowance to those lines to make it permanent.`),
    h('button', { class: 'btn sm', onclick: () => poolDialog(covered.reduce((a, r) => a + r.pool_covered, 0), covered.length) }, 'Allocate allowance to cover costs')));
  // ---- Q13: a line whose schedule item went in a re-upload stays flagged for everyone until it is linked again or dismissed ----
  const lostText = (x) => `Schedule item '${x.task || 'unknown'}'${x.wbs ? ` (${x.wbs})` : ''} gone on ${fmt.date(x.date) || 'an unknown date'}; ${x.role === 'stop' ? 'stop date' : x.role === 'start' ? 'start date' : 'dates'} kept as typed value.`;
  const lostAll = (r) => (r.schedule_link_lost || []).map(lostText).join(' ');
  function lostMark(r) {
    if (!r.schedule_link_lost || res.is_parent) return null;
    return h('button', { type: 'button', class: 'badge warn lostmark', title: lostAll(r) + ' Open the line to link it to the schedule or dismiss.',
      'aria-label': `Schedule item gone: ${lostAll(r)} Open the line to link it to the schedule or dismiss.`,
      onclick: (e) => { e.stopPropagation(); openDrawer(r, 'forecast'); } }, h('span', { 'aria-hidden': 'true' }, '\u26a0'), ui.months ? null : ' Schedule gone');
  }
  // the detail note in the drawer and the month window: what went, Link to schedule (opens the window editor's task pick) and Dismiss
  function lostNote(r, onDone, linkTo) {
    if (!r.schedule_link_lost || res.is_parent) return null;
    const L = r.schedule_link_lost;
    return h('div', { class: 'note warn lostnote', style: { marginBottom: '10px' } },
      h('b', {}, L.length > 1 ? 'Schedule items gone' : 'Schedule item gone'),
      h('ul', { style: { margin: '4px 0 6px 18px', padding: 0 } }, L.map((x) => h('li', {}, lostText(x)))),
      h('div', { class: 'row', style: { gap: '6px' } },
        linkTo ? h('button', { type: 'button', class: 'btn sm', onclick: () => linkTo((L[L.length - 1] || {}).role === 'stop' ? 'stop' : 'start') }, 'Link to schedule') : null,
        h('button', { type: 'button', class: 'btn ghost sm', title: 'Take the flag off this line for every user. The dates stay as they are.', onclick: async () => {
          try { const o = await api.del(p(`/nodes/${r.node_id}/schedule-link-lost`)); toast(o.cleared ? `${r.code}: schedule flag dismissed` : `${r.code}: the flag was already cleared`); await onDone(); }
          catch (err) { toast(err.message, 'bad'); }
        } }, 'Dismiss')));
  }
  const lostCount = res.is_parent ? 0 : rows.filter((r) => r.kind === 'line' && r.schedule_link_lost).length;
  if (lostCount) root.append(h('div', { class: 'note warn', style: { marginBottom: '10px', display: 'flex', gap: '12px', alignItems: 'center' } },
    h('span', { style: { flex: 1 } }, `${lostCount} line${lostCount > 1 ? 's have' : ' has'} lost ${lostCount > 1 ? 'their' : 'its'} schedule item in a schedule re-upload: the dates are kept as typed values. Link each to the schedule again or dismiss the flag.`),
    h('button', { type: 'button', class: 'btn sm', onclick: () => { ui.only = 'lost'; save(); drawBar(); draw(); } }, 'Show them')));
  const crumbs = h('div', { class: 'crumbs' });
  const bar = h('div', { class: 'card', style: { padding: '10px 14px', marginBottom: '12px' } });
  const search = h('input', { type: 'search', placeholder: 'Search code, name, resource, function...', style: { width: '280px' }, oninput: debounce(() => { ui.q = search.value.trim().toLowerCase(); draw(); }, 150) });
  const lv = [1, 2, 3, 4, 5].map((n) => h('span', { class: 'chip' + (ui.level === n ? ' on' : ''), onclick: () => { ui.level = n; save(); open.clear(); rows.forEach((r) => r.kind === 'group' && r.level < n && open.add(String(r.id))); saveOpen(); drawBar(); draw(); } }, 'Level ' + n));
  const filt = (k, label) => h('span', { class: 'chip' + (ui.only === k ? ' on' : ''), onclick: () => { ui.only = ui.only === k ? '' : k; save(); drawBar(); draw(); } }, label);
  function drawBar() {
    clear(bar);
    const path = scopeId ? pathTo(rows, scopeId) : [];
    clear(crumbs).append(h('a', { onclick: () => { setScope(null); go('costcontrol'); render(); } }, 'Whole project'));
    path.forEach((r, i) => { crumbs.append(h('span', { class: 'sep' }, '›'), i === path.length - 1 ? h('b', {}, `${r.code} ${r.name}`) : h('a', { onclick: () => { setScope(r); render(); } }, `${r.code} ${r.name}`)); });
    bar.append(h('div', { class: 'row' }, crumbs, h('button', { class: 'btn sm ghost', onclick: () => pickNode({ allowRoot: true, selected: scopeId, showEac: true, onPick: (r) => { setScope(r); render(); } }) }, 'Change scope')),
      h('div', { class: 'row', style: { marginTop: '8px' } }, search, h('span', { class: 'small muted' }, 'Expand to'), ...[1, 2, 3, 4, 5].map((n, i) => { const c = lv[i]; c.className = 'chip' + (ui.level === n ? ' on' : ''); return c; }),
        h('span', { style: { width: '6px' } }), filterMenu('Filters', [filt('over', 'Overruns'), filt('under', 'Underruns'), filt('short', 'CTC below PO'), filt('nomethod', 'Nothing to forecast from'), filt('lost', 'Schedule item gone')], ui.only ? 1 : 0),
        h('label', { class: 'row small', style: { gap: '4px' } }, h('input', { type: 'checkbox', checked: ui.hideZero, onchange: (e) => { ui.hideZero = e.target.checked; save(); draw(); } }), 'Hide empty lines'),
        h('label', { class: 'row small', style: { gap: '4px' } }, h('input', { type: 'checkbox', checked: ui.months, onchange: (e) => { ui.months = e.target.checked; save(); drawBar(); draw(); } }), 'Show monthly grid')));
  }
  root.append(bar);
  const wrap = h('div'); root.append(wrap);
  root.append(h('div', { class: 'legend', style: { marginTop: '10px' } },
    h('span', {}, h('i', { class: 'mg-act' }), 'Actual'), h('span', {}, h('i', { class: 'mg-acc' }), 'Accrual (not yet in Pronto)'), h('span', {}, h('i', { class: 'mg-hyb' }), 'Hybrid: actual + accrual'),
    h('span', {}, h('i', { class: 'mg-acd' }), 'Current month landed (+ still forecast)'), h('span', {}, h('i', { class: 'mg-fcd' }), `Current month as forecast${res.planned_from ? ' at ' + res.planned_from : ''}`), h('span', {}, h('i', { class: 'mg-fc' }), 'Forecast'),
    h('span', {}, 'Click CTC for the line by month and what each method would give.')));

  const inScope = (r) => {
    if (!scopeId) return true;
    const root0 = byId.get(String(scopeId)); if (!root0) return true;
    let x = r;
    while (x) { if (String(x.id) === String(scopeId) || (x.kind === 'pot' && String(x.parent_id) === String(scopeId))) return true; x = x.parent_id === null ? null : byId.get(String(x.parent_id)); }
    return false;
  };
  const passes = (r) => {
    if (r.kind === 'group') return true;
    if (ui.hideZero && !r.schedule_link_lost && r.origin !== 'ctc' && r.origin !== 'wip' && !(r.allowance || r.ctd || r.acc || r.ctc || r.outstanding)) return false;
    if (ui.only === 'over' && !(r.contingency < -1)) return false;
    if (ui.only === 'under' && !(r.contingency > 1)) return false;
    if (ui.only === 'short' && r.po_status !== 'SHORT') return false;
    if (ui.only === 'nomethod' && !r.note) return false;
    if (ui.only === 'lost' && !r.schedule_link_lost) return false;
    return true;
  };

  function draw() {
    const q = ui.q;
    const match = (r) => `${r.code} ${r.name} ${r.function || ''} ${r.resource_code || ''}`.toLowerCase().includes(q);
    const list = [];
    const visibleLeaf = new Map();
    const hasVisible = (r) => {
      if (r.kind !== 'group') { const v = passes(r) && (!q || match(r)); return v; }
      const cached = visibleLeaf.get(r.id); if (cached !== undefined) return cached;
      const v = rows.some((c) => String(c.parent_id) === String(r.id) && hasVisible(c));
      visibleLeaf.set(r.id, v); return v;
    };
    const walk = (r) => {
      if (!inScope(r) && !pathTo(rows, scopeId).some((a) => a.id === r.id)) return;
      if ((ui.only || q || ui.hideZero) && r.kind === 'group' && !hasVisible(r) && r.level > 1 && !(r.allowance || r.ctd)) return;
      if ((ui.only || q) && r.kind === 'group' && !hasVisible(r)) return;
      if (r.kind !== 'group' && !(passes(r) && (!q || match(r)))) return;
      list.push(r);
      if (r.kind === 'group' && (q || ui.only || open.has(String(r.id)))) rows.filter((c) => String(c.parent_id) === String(r.id)).forEach(walk);
    };
    rows.filter((r) => r.level === 1).forEach(walk);

    const gi = grid.indexOf(M);
    // Month view keeps the working columns (Method, Start, Stop, Months, EAC, Contingency) frozen beside the grid; without it the full set of figures shows
    const GM = !!ui.months;
    const LAB = { cbs: 'CBS', name: 'Name', func: 'Function / trade', budget: 'Allowance', po: 'Ordered', outstanding: 'Open POs', ctd: 'CTD', acc: 'ACC', ctc: 'CTC', eac: 'EAC', cont: 'Contingency', risk: 'Risk cost', status: 'Status', method: 'Method', start: 'Start', stop: 'Stop', months: 'Months' };
    const ORDER = GM ? ['cbs', 'name', 'method', 'start', 'stop', 'months', 'eac', 'cont'] : ['cbs', 'name', 'func', 'budget', 'po', 'outstanding', 'ctd', 'acc', 'ctc', 'eac', 'cont', 'risk', 'status', 'method', 'start', 'stop', 'months'];
    const RIGHT = new Set(['budget', 'po', 'outstanding', 'ctd', 'acc', 'ctc', 'eac', 'cont', 'risk']);
    const FW = GM ? { cbs: 84, name: 150, method: 100, start: 74, stop: 74, months: 64, eac: 92, cont: 104 } : { cbs: 120, name: 260 };
    const FL = {}; { let x = 0; ORDER.forEach((k) => { if (FW[k] && (GM || k === 'cbs' || k === 'name')) { FL[k] = x; x += FW[k]; } }); }
    const frozen = (td, k, bg, z = 1) => { if (FL[k] === undefined) return td; td.classList.add('sticky1'); Object.assign(td.style, { left: FL[k] + 'px', background: bg, minWidth: FW[k] + 'px', maxWidth: (k === 'name' && !GM ? 320 : FW[k]) + 'px', zIndex: z }); if (k === 'name') Object.assign(td.style, { overflow: 'hidden', textOverflow: 'ellipsis' }); return td; };
    const thead = h('tr', {}, ORDER.map((k) => frozen(h('th', { class: RIGHT.has(k) ? 'r' : '' }, LAB[k]), k, 'var(--navy)', 3)));
    const gcols = grid.map((m) => ({ id: m }));
    const gvis = ui.months ? olVisible(gcols, gi, ost, MONTH_LEVELS) : [];
    const plan = ui.months ? grid.map((m, i) => ({ kind: i === gi ? 'cur' : 'm', i })).filter((c) => gvis[c.i]) : [];   // only the columns that show: folded and hidden ones take no room
    plan.forEach((c) => {
      if (c.kind === 'cur') thead.append(h('th', { class: 'mth mca', 'data-col': grid[c.i], title: 'Actual + accrued this month' }, fmt.month(grid[c.i])), h('th', { class: 'mth mcf', 'data-col': grid[c.i], title: res.planned_from ? `As forecast at ${res.planned_from}` : 'No month-end close yet: the current forecast is shown' }, fmt.month(grid[c.i]) + ' (F)'));
      else thead.append(h('th', { class: 'mth mhd ' + (c.i < gi ? 'mpa' : 'mfu'), 'data-col': grid[c.i] }, fmt.month(grid[c.i]),
        h('span', { class: 'hx', title: `Hide ${fmt.month(grid[c.i])} (a + on the strip above brings it back)`, onclick: (e) => { e.stopPropagation(); ost.hidden = [...new Set([...ost.hidden, grid[c.i]])]; ost.save(); draw(); } }, '\u00d7')));
    });
    // ---- the Method and Start / Stop / Months block, editable in the row. Fill any two and the third is worked out (in the same cell you can type or read it) ----
    const WIN = res.windows || {};
    const claimOk = new Set((res.claim_nodes || []).map(String));
    const isLine = (r) => r.kind === 'line' && !res.is_parent;
    const mlast = (v) => { const [y, m] = v.split('-').map(Number); return `${v}-${String(new Date(y, m, 0).getDate()).padStart(2, '0')}`; };
    const mdiff = (a, b) => { const [y1, m1] = a.split('-').map(Number); const [y2, m2] = b.split('-').map(Number); return (y2 - y1) * 12 + m2 - m1 + 1; };
    function methodCell(r) {
      if (r.kind === 'group') return h('td');
      if (!isLine(r)) return h('td', {}, r.method ? h('span', { class: 'badge', title: METHOD_NOTE[r.method] }, r.method) : '');
      const opts = Object.keys(state.tax.methods).filter((m) => m !== 'CLAIM' || claimOk.has(String(r.node_id)) || r.method === 'CLAIM');
      const sel = select(opts, r.method || 'AT-BUDGET'); sel.classList.add('inl', 'm-' + (r.method || 'AT-BUDGET'));
      sel.title = METHOD_NOTE[r.method || 'AT-BUDGET'] || '';
      sel.addEventListener('click', (e) => e.stopPropagation());
      sel.addEventListener('change', async () => {
        const m = sel.value; const back = () => { sel.value = r.method || 'AT-BUDGET'; };
        try {
          if (m === 'TOP-DOWN') {
            const eac = h('input', { type: 'text', inputmode: 'decimal', value: r.eac_top ?? Math.round(r.eac) });
            const ok = await new Promise((res2) => modal({ title: `${r.code} ${r.name}: top-down EAC`, body: h('div', { class: 'grid' }, h('div', { class: 'note' }, `The final cost you expect for this line. Cost to complete is worked out as EAC less cost to date (${fmt.money(r.ctd)}) and accruals (${fmt.money(r.acc)}).`), field('EAC for this line', eac, `Allowance ${fmt.money(r.allowance)}`)),
              actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => res2(false) }, { label: 'Use top-down', onClick: () => res2(true) }] }));
            if (!ok) return back();
            await api.put(p(`/nodes/${r.node_id}`), { method: m, eac_override: num(eac.value) });
          } else await api.put(p(`/nodes/${r.node_id}`), { method: m });
          toast(`${r.code} now forecast ${m}`);
          if (m === 'GROUND-UP' || (m === 'CLAIM' && claimOk.has(String(r.node_id)))) { go(m === 'CLAIM' ? 'subcontracts' : 'forecast', m === 'CLAIM' ? {} : { node: r.node_id }); return; }
          await render();
        } catch (err) { toast(err.message, 'bad'); back(); }
      });
      return h('td', { class: 'nowrap' }, sel);
    }
    function windowCells(r) {
      if (!isLine(r)) return [h('td'), h('td'), h('td')];
      const w = WIN[String(r.node_id)] || {}; const drv = (k) => (w[k] && !w[k].suspended ? w[k] : null);
      const eff = (k, own) => (own ? own.slice(0, 7) : String(r[k] || '').slice(0, 7));
      const sIn = monthInput(eff('start', r.start_own)); const eIn = monthInput(eff('end', r.end_own));
      const mIn = h('input', { type: 'number', min: 1, step: 1, value: sIn.ym && eIn.ym ? mdiff(sIn.ym, eIn.ym) : '' });
      const mark = (inp, k, own) => {
        inp.classList.add('inl'); inp.addEventListener('click', (e) => e.stopPropagation());
        if (drv(k)) { inp.classList.add('drv'); inp.title = `Follows the project schedule: ${drv(k).task} (${drv(k).edge === 'start' ? 'start' : 'finish'}). Type to override it; open the line's window to return to the schedule.`; }
        else if (w[k] && w[k].suspended) { inp.classList.add('ovr'); inp.title = `Typed over the schedule (${w[k].task}). Open the forecast window to return to it.`; }
        else if (!own) { inp.classList.add('inh'); inp.title = 'Inherited from the group above. Type to set this line\'s own window.'; }
      };
      mark(sIn, 'start', r.start_own); mark(eIn, 'stop', r.end_own); mIn.classList.add('inl', 'mo');
      const keep = (role, v, typed) => (drv(role) ? { mode: 'schedule', task_id: drv(role).task_id, edge: drv(role).edge } : typed(v));
      const tS = (v) => (v ? { mode: 'typed', date: v + '-01' } : { mode: 'typed' }); const tE = (v) => (v ? { mode: 'typed', date: mlast(v) } : { mode: 'typed' });
      async function commit(which) {
        const s = sIn.ym; const e = eIn.ym; const m = +mIn.value || 0; let a; let b; let months = null;
        if (which === 'start') { a = tS(s); if (e) b = keep('stop', e, tE); else if (m) { b = { mode: 'duration' }; months = m; } else b = tE(''); }
        else if (which === 'stop') { b = tE(e); if (s) a = keep('start', s, tS); else if (m) { a = { mode: 'duration' }; months = m; } else a = tS(''); }
        else {
          if (m < 1) return;
          if (s) { a = keep('start', s, tS); b = { mode: 'duration' }; months = m; } else if (e) { b = keep('stop', e, tE); a = { mode: 'duration' }; months = m; }
          else return toast('Fill in Start or Stop first, then the months', 'bad');
        }
        try { const o = await api.post(p(`/nodes/${r.node_id}/window`), { start: a, stop: b, months }); await render(); if (o.warnings && o.warnings.length) toast('Some typed months now sit outside the window: they are outlined in the month grid', 'bad'); }
        catch (err) { toast(err.message, 'bad'); }
      }
      sIn.addEventListener('change', () => commit('start')); eIn.addEventListener('change', () => commit('stop')); mIn.addEventListener('change', () => commit('months'));
      return [h('td', { class: 'nowrap' }, sIn), h('td', { class: 'nowrap' }, eIn), h('td', {}, mIn)];
    }
    const tbody = h('tbody');
    list.forEach((r) => {
      const cls = r.level === 1 ? 'gp' : r.kind !== 'group' ? '' : r.level === 2 ? 'par' : 'par2';
      const isOpen = open.has(String(r.id));
      const hasKids = r.kind === 'group' && rows.some((x) => String(x.parent_id) === String(r.id));
      const tog = h('span', { class: 'tog', onclick: (e) => { e.stopPropagation(); isOpen ? open.delete(String(r.id)) : open.add(String(r.id)); saveOpen(); draw(); } }, hasKids ? (isOpen ? '▾' : '▸') : '');
      const bg = r.level === 1 ? 'var(--grey)' : r.kind === 'group' ? '#f4f6fb' : '#fff';
      const wc = windowCells(r);
      const CELL = {
        cbs: h('td', { class: 'mono' }, h('span', { style: { paddingLeft: (r.level - 1) * (GM ? 10 : 14) + 'px' } }), tog, r.code),
        name: h('td', {}, lostMark(r), lostMark(r) ? ' ' : null, r.name, r.active === 0 ? badge('inactive') : null, r.parts ? h('span', { class: 'badge navy', style: { marginLeft: '6px' }, title: 'Includes variation scope tracked on its own CBS copy: open the line for the breakdown' }, `+${r.parts.length - 1} var`) : null),
        func: h('td', { class: 'muted' }, r.function || ''),
        budget: amt(r, 'budget', r.allowance), po: amt(r, 'po', r.po_committed), outstanding: amt(r, 'outstanding', r.outstanding), ctd: amt(r, 'ctd', r.ctd, true), acc: amt(r, 'acc', r.acc), ctc: amt(r, 'ctc', r.ctc, true),
        eac: amt(r, 'eac', r.eac, true, { fontWeight: 700 }), cont: amt(r, 'contingency', r.contingency, true, {}, tone(r.contingency)), risk: amt(r, 'risk', r.risk_cost),
        status: h('td', {}, statusPill(r.budget_status), r.po_status === 'SHORT' ? statusPill('SHORT') : '', r.note ? h('span', { class: 'badge warn', title: r.note, style: { marginLeft: '4px' } }, '!') : ''),
        method: methodCell(r), start: wc[0], stop: wc[1], months: wc[2],
      };
      const tr = h('tr', { class: cls + ' click', onclick: () => openDrawer(r) }, ...ORDER.map((k) => frozen(CELL[k], k, bg)));
      plan.forEach((c) => tr.append(...monthCells(r, c.i)));
      tr._r = r;
      tbody.append(tr);
    });
    // the month grid's totals: what landed in past months, forecast in future months, and the current month twice (landed, then as forecast at the last close)
    function monthTotals() {
      const leaves = rows.filter((r) => r.kind !== 'group' && inScope(r));
      const sum = (f) => leaves.reduce((a, r) => a + f(r), 0);
      const cell = (v, cls) => h('td', { class: 'r num ' + cls }, Math.abs(v) > 0.5 ? fmt.n(v) : '');
      return plan.flatMap((c) => {
        const i = c.i;
        if (i < gi) return [cell(sum((r) => r.a[i] + r.x[i]), 'mg mg-pa')];
        if (i > gi) return [cell(sum((r) => r.f[i]), 'mg mg-fc')];
        return [cell(sum((r) => r.a[i] + r.x[i]), 'mg mg-acd'), cell(sum((r) => { const pl = res.planned && res.planned[String(r.id)]; return pl === undefined || pl === null ? r.a[i] + r.x[i] + r.f[i] : pl; }), 'mg mg-fcd')];
      });
    }
    const leavesAll = rows.filter((r) => r.kind !== 'group' && inScope(r));
    const sumK = (k) => leavesAll.reduce((a, r) => a + (r[k] || 0), 0);
    const TOT = { budget: sumK('allowance'), po: sumK('po_committed'), outstanding: sumK('outstanding'), ctd: sumK('ctd'), acc: sumK('acc'), ctc: sumK('ctc'), eac: sumK('eac'), cont: sumK('allowance') - sumK('eac'), risk: sumK('risk_cost') };
    const FOOT = (k) => (k === 'cbs' ? h('td', {}, scopeId ? 'Total in scope' : 'Project total') : RIGHT.has(k) ? h('td', { class: 'r num' }, fmt.money(TOT[k])) : h('td'));
    const tf = h('tfoot', {}, h('tr', {}, ...ORDER.map((k) => frozen(FOOT(k), k, 'var(--grey)', 4)), ...(ui.months ? monthTotals() : [])));
    const ccTable = h('table', { class: 't cc' + (GM ? ' gm' : '') }, h('thead', {}, thead), tbody, tf); const ccTw = h('div', { class: 'tw', style: { maxHeight: '70vh' } }, ccTable);
    const strip = ui.months && list.length ? outlineStrip({ cols: gcols, cur: gi, levels: MONTH_LEVELS, st: ost, onChange: draw, names: { 1: 'This quarter only', 2: 'Every month' } }) : null;
    if (wrap._olOff) { wrap._olOff(); wrap._olOff = null; }
    clear(wrap).append(list.length ? h('div', {}, ...(strip ? [strip.el] : []), ccTw) : empty('No lines to show', 'Nothing matches the current filters, or the CBS has no lines yet.', h('button', { class: 'btn', onclick: () => go('cbs') }, 'Open CBS and allowances')));
    if (strip) wrap._olOff = strip.mount(ccTw, ccTable);
  }

  // ---- month cells in the Cost Control sheet's colours ------------------------------------------
  // past: pink actual, light blue accrual, purple both (hybrid); current month twice: what was forecast at the last
  // month-end (dark green) and what has landed (dark blue); future: light green forecast
  function monthCells(r, i) {
    const m = grid[i]; const gi = grid.indexOf(M);
    const a = r.a[i], x = r.x[i], f = r.f[i];
    const st = Math.abs(a) > 0.5 && Math.abs(x) > 0.5 ? 'hyb' : Math.abs(a) > 0.5 ? 'act' : Math.abs(x) > 0.5 ? 'acc' : '';
    const click = (v) => (v ? (e) => { e.stopPropagation(); drillModal(r, 'month', m); } : null);
    if (i < gi) {
      const v = a + x;
      return [h('td', { class: `r num mg mg-${st || 'pa'}` + (v ? ' drillable' : ''), title: v ? `Actual ${fmt.money(a)} | Accrual ${fmt.money(x)}. Click for the records.` : '', onclick: click(v) }, v ? fmt.n(v) : '')];
    }
    if (i > gi) {
      if (r.kind !== 'line' || res.is_parent) return [h('td', { class: 'r num mg mg-fc' + (f ? ' drillable' : ''), title: f ? `Forecast ${fmt.money(f)}. Click for how it is built.` : '', onclick: f ? (e) => { e.stopPropagation(); monthsPane(r); } : null }, f ? fmt.n(f) : '')];
      // typed months outside the line's activity window (the schedule moved it) are outlined so they can be dealt with
      const out = r.method === 'MANUAL' && Math.abs(f) > 0.005 && r.start && r.end && (m < r.start || m > r.end);
      const td = h('td', { class: 'r num mg mg-fc mg-edit' + (out ? ' mg-out' : ''), title: (out ? `Typed month outside the activity window (${fmt.month(r.start)} to ${fmt.month(r.end)}). ` : '') + `Click to type an amount, double-click for the forecast window.` }, f ? fmt.n(f) : '');
      let timer = null;
      td.addEventListener('click', (e) => { e.stopPropagation(); if (e.detail > 1 || td.querySelector('input')) return; clearTimeout(timer); timer = setTimeout(() => typeMonth(td, r, m), 250); });
      td.addEventListener('dblclick', (e) => { e.stopPropagation(); clearTimeout(timer); if (!td.querySelector('input')) monthsPane(r); });
      return [td];
    }
    const pl = res.planned && res.planned[String(r.id)] !== undefined ? res.planned[String(r.id)] : null;
    const planned = pl === null ? a + x + f : pl;
    const v = a + x;
    return [
      h('td', { class: `r num mg mg-${st || 'acd'}` + (v || f ? ' drillable' : ''), title: `Landed this month: actual ${fmt.money(a)} + accrued ${fmt.money(x)}${f ? `. Still forecast in this month: ${fmt.money(f)}` : ''}`, onclick: click(v || f) }, v ? fmt.n(v) : '', f > 0.5 ? h('sup', { class: 'still' }, '+' + fmt.m(f)) : null),
      h('td', { class: 'r num mg mg-fcd', title: `Forecast for ${fmt.month(m)} ${res.planned_from ? 'at ' + res.planned_from : '(no month-end close yet: current forecast)'}: ${fmt.money(planned)}` }, planned ? fmt.n(planned) : '')
    ];
  }

  // ---- type a future month in place: a line on any other method becomes MANUAL, keeping what it forecast, and only this month changes ----
  function typeMonth(td, r, m) {
    const old = td.innerHTML;
    const input = h('input', { type: 'text', value: '', placeholder: '$ or %', style: { width: '78px', textAlign: 'right' }, title: 'Type an amount (or a % on AT-BUDGET and AT-COMMIT lines), Enter to save, empty clears the month, Esc cancels' });
    td.textContent = ''; td.append(input); input.focus();
    const cancel = () => { td.innerHTML = old; };
    input.addEventListener('keydown', async (ev) => {
      if (ev.key === 'Escape') return cancel();
      if (ev.key !== 'Enter') return;
      ev.preventDefault();
      const raw = input.value.trim().replace(/[$,\s]/g, '');
      const body = { month: m, convert: true };
      if (raw === '' || raw === '0') body.clear = true;
      else if (/^-?\d+(\.\d+)?%$/.test(raw)) { body.unit = '%'; body.value = parseFloat(raw); }
      else if (/^-?\d+(\.\d+)?$/.test(raw)) { body.unit = '$'; body.value = parseFloat(raw); }
      else { toast('Type an amount such as 12500 or 12,500, or a percentage such as 25%', 'bad'); return; }
      try {
        const out = await api.post(p(`/nodes/${r.node_id}/forecast-set`), body);
        toast(`${r.code} ${fmt.month(m)}: ${body.clear ? 'cleared' : fmt.money(out.amount)}${out.converted ? ` (now MANUAL, the other months keep what ${r.method || 'AT-BUDGET'} gave)` : ''}`);
      } catch (err) { toast(err.message, 'bad'); }
      render();
    });
    input.addEventListener('blur', () => { if (td.contains(input)) cancel(); });
  }

  // ---- the activity window: Start, Stop and Duration (months). Start and Stop can each follow an item on the project schedule (its start or
  // finish date), or be typed. Edit one of three filled typed fields and the other typed ones clear; fill any two and the third is worked out ----
  const ym = (d) => { const [y, mo] = d.slice(0, 7).split('-').map(Number); return y * 12 + mo - 1; };
  const lastDay = (n) => { const y = Math.floor(n / 12), mo = (n % 12) + 1; return `${y}-${String(mo).padStart(2, '0')}-${String(new Date(y, mo, 0).getDate()).padStart(2, '0')}`; };
  const firstDay = (n) => `${Math.floor(n / 12)}-${String((n % 12) + 1).padStart(2, '0')}-01`;
  async function pickTask(title, onPick) {
    const tasks = (await api.get(p('/programme/tasks'))).filter((t) => t.layer !== 'upstream');
    if (!tasks.length) return toast('No project schedule is loaded yet (Setup, Project schedule)', 'bad');
    let q = ''; const list = h('div', { class: 'tw', style: { maxHeight: '48vh' } });
    let md;
    const pick = (t, edge) => { md.close(); onPick(t, edge); };
    const draw = () => clear(list).append(h('table', { class: 't' }, h('tbody', {}, tasks.filter((t) => !q || `${t.wbs} ${t.name}`.toLowerCase().includes(q)).slice(0, 300).map((t) => h('tr', {},
      h('td', { class: 'mono muted' }, t.wbs || ''), h('td', { style: { paddingLeft: 6 + ((t.outline || 1) - 1) * 12 + 'px' } }, t.name, t.milestone ? badge('milestone', 'warn') : null),
      h('td', {}, fmt.date(t.start_date)), h('td', {}, t.milestone ? '' : fmt.date(t.finish_date)),
      h('td', { class: 'nowrap' }, t.milestone ? h('button', { class: 'btn sm', onclick: () => pick(t, 'start') }, 'Use this date') : [h('button', { class: 'btn sm', title: 'Start and Stop both follow this task: the line runs alongside it', onclick: () => pick(t, 'both') }, 'Whole task'), h('button', { class: 'btn ghost sm', style: { marginLeft: '4px' }, onclick: () => pick(t, 'start') }, 'Its start'), h('button', { class: 'btn ghost sm', style: { marginLeft: '4px' }, onclick: () => pick(t, 'finish') }, 'Its finish')]))))));
    draw();
    md = modal({ title, size: 'wide', body: h('div', {}, h('input', { type: 'search', placeholder: 'Search the project schedule...', style: { width: '100%', marginBottom: '8px' }, oninput: (e) => { q = e.target.value.toLowerCase(); draw(); } }), list), actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} }] });
  }
  function windowEditor(det, nodeId, onDone, eff) {
    const W = det.window || {};
    const init = (role) => { const w = W[role]; return w && !w.suspended ? { mode: 'schedule', task_id: w.task_id, task: w.task, edge: w.edge, date: w.date } : { mode: 'typed', date: det[role === 'start' ? 'start_date' : 'end_date'] || '', over: w && w.suspended ? w : null }; };
    const st = { start: init('start'), stop: init('stop') };
    const dates = { start: h('input', { type: 'date', value: st.start.date || '' }), stop: h('input', { type: 'date', value: st.stop.date || '' }) };
    const dur = h('input', { type: 'number', min: 1, step: 1, value: st.start.date && st.stop.date ? ym(st.stop.date) - ym(st.start.date) + 1 : (W.months || '') });
    const free = () => ['start', 'stop'].filter((r) => st[r].mode !== 'schedule').map((r) => dates[r]).concat([dur]);
    const filled = () => [dates.start, dates.stop, dur].filter((x) => x.value !== '');
    let was = false;
    const calc = () => {
      if (filled().length !== 2) return;
      const [a, b] = [dates.start, dates.stop];
      if (!a.value && !a.readOnly) { if (+dur.value >= 1) a.value = firstDay(ym(b.value) - (+dur.value - 1)); }
      else if (!b.value && !b.readOnly) { if (+dur.value >= 1) b.value = lastDay(ym(a.value) + (+dur.value - 1)); }
      else if (a.value && b.value) dur.value = ym(b.value) - ym(a.value) + 1;
    };
    const boxes = { start: h('div', { class: 'small', style: { marginTop: '4px' } }), stop: h('div', { class: 'small', style: { marginTop: '4px' } }) };
    const paint = () => ['start', 'stop'].forEach((r) => {
      const x = st[r]; dates[r].readOnly = x.mode === 'schedule'; dates[r].style.opacity = x.mode === 'schedule' ? '.75' : '';
      if (x.mode === 'schedule') dates[r].value = x.date || '';
      const link = (label, fn, cls = 'btn ghost sm') => h('button', { class: cls, style: { marginLeft: '6px' }, onclick: fn }, label);
      clear(boxes[r]).append(x.mode === 'schedule'
        ? h('span', {}, badge('Schedule', 'green'), ` ${x.task} (${x.edge === 'start' ? 'start' : 'finish'}, ${fmt.date(x.date)}) `, link('Change', () => choose(r)), link('Type instead', () => { st[r] = { mode: 'typed', date: dates[r].value, over: x }; paint(); }))
        : h('span', { class: 'muted' }, x.over ? h('span', {}, badge('Typed over the schedule', 'navy'), ` ${x.over.task} (${x.over.edge === 'start' ? 'start' : 'finish'}) was driving this. `, link('Return to schedule', async () => { await api.post(p(`/nodes/${nodeId}/window-reset`), { role: r }); toast('Back on the schedule'); await onDone(); }))
          : h('span', {}, 'Typed. '), link('Link to a schedule item', () => choose(r))));
    });
    function choose(r) {
      pickTask(`${r === 'start' ? 'Start' : 'Stop'} of ${det.code || 'this line'} follows which schedule item?`, (t, edge) => { const set = (role, e) => { st[role] = { mode: 'schedule', task_id: t.id, task: t.name, edge: e, date: e === 'start' ? t.start_date : t.finish_date }; }; if (edge === 'both') { set('start', 'start'); set('stop', 'finish'); } else set(r, edge); dur.value = ''; paint(); if (st.start.mode === 'schedule' && st.stop.mode === 'schedule') dur.value = ym(st.stop.date) - ym(st.start.date) + 1; if (saveBtn) saveBtn.focus(); });
    }
    [dates.start, dates.stop, dur].forEach((x) => {
      x.addEventListener('focus', () => { was = filled().length === 3; });
      x.addEventListener('input', () => { if (was) { free().filter((y) => y !== x).forEach((y) => { y.value = ''; }); was = false; } st.start.date = dates.start.value; st.stop.date = dates.stop.value; calc(); });
    });
    paint();
    let saveBtn = null;
    const linked = [W.start, W.stop].some(Boolean);
    const el = h('div', { class: 'card', style: { marginBottom: '12px' } }, h('div', { class: 'ch' }, h('h2', {}, 'Activity window'), h('span', { class: 'sp' }),
      h('span', { class: 'small muted' }, linked ? 'Linked to the project schedule: it follows it when the schedule changes.' : 'Not linked to the schedule: set it here, or link Start and Stop to schedule items.')),
      h('div', { class: 'grid g3' }, h('div', {}, field('Start', dates.start), boxes.start), h('div', {}, field('Stop', dates.stop), boxes.stop), field('Duration (months)', dur)),
      h('div', { class: 'small muted', style: { margin: '6px 0' } }, !det.start_date && eff && eff.start && !linked ? `Now inherited from the group above: ${fmt.month(eff.start)} to ${fmt.month(eff.end)}. ` : '',
        'Start and Stop can follow a schedule item (a task\'s start or finish, or a milestone), or be typed. Fill any two of the three and the third is worked out; changing one of three filled typed fields clears the other typed ones. The forecast is spread over this window.'),
      h('div', { class: 'row' }, saveBtn = h('button', { class: 'btn', onclick: async () => {
        calc();
        const spec = (r) => (st[r].mode === 'schedule' ? { mode: 'schedule', task_id: st[r].task_id, edge: st[r].edge } : dates[r].value ? { mode: 'typed', date: dates[r].value } : { mode: 'duration' });
        const a = spec('start'), b = spec('stop');
        if (a.mode === 'duration' && b.mode === 'duration') {
          if (!W.start && !W.stop && !dur.value) { await api.put(p(`/nodes/${nodeId}`), { start_date: null, end_date: null }); toast('Window cleared: the line takes its group\'s dates'); return onDone(); }
          return toast('Fill in two of Start, Stop and Duration', 'bad');
        }
        if ((a.mode === 'duration' || b.mode === 'duration') && !(+dur.value >= 1)) return toast('Fill in two of Start, Stop and Duration', 'bad');
        const r = await api.post(p(`/nodes/${nodeId}/window`), { start: a, stop: b, months: +dur.value || null });
        toast('Activity window saved'); await onDone(); if (r.warnings && r.warnings.length) toast('Some typed months now sit outside the window: they are outlined on Cost control', 'bad');
      } }, 'Save window')));
    el._choose = choose;
    return el;
  }

  // ---- spread an unallocated pool over the lines beneath it: press on the grip in the pool's Allowance cell, drag down over the lines, release ----
  function startSpread(pot, td) {
    const tbody = td.closest('tbody'); const trs = [...tbody.rows]; const from = trs.indexOf(td.closest('tr'));
    const under = (r) => { let x = r; let n = 0; while (x && n++ < 12) { if (String(x.id) === String(pot.node_id)) return true; x = x.parent_id == null ? null : byId.get(String(x.parent_id)); } return false; };
    const eligible = (tr) => tr._r && tr._r.kind === 'line' && under(tr._r);
    trs.forEach((tr) => eligible(tr) && tr.classList.add('sp-ok'));
    document.body.classList.add('spreading');
    let hot = [];
    const mark = (to) => { trs.forEach((t) => t.classList.remove('sp-hit')); const lo = Math.min(from, to); const hi = Math.max(from, to); hot = trs.slice(lo, hi + 1).filter(eligible); hot.forEach((t) => t.classList.add('sp-hit')); };
    const over = (e) => { const tr = e.target.closest && e.target.closest('tr'); const i = tr ? trs.indexOf(tr) : -1; if (i >= 0) mark(i); };
    const up = () => {
      document.removeEventListener('mouseover', over); document.removeEventListener('mouseup', up);
      document.body.classList.remove('spreading'); trs.forEach((t) => t.classList.remove('sp-ok', 'sp-hit'));
      if (hot.length) spreadDialog(pot, hot.map((t) => t._r)); else toast('Drag the grip down over the lines that should get allowance', 'bad');
    };
    document.addEventListener('mouseover', over); document.addEventListener('mouseup', up);
  }
  function spreadDialog(pot, lines) {
    const avail = Math.max(0, (pot.allowance || 0) - (pot.ctd || 0) - (pot.acc || 0));
    const need = (l) => Math.max(0, (l.eac || 0) - (l.allowance || 0));
    const sumNeed = lines.reduce((a, l) => a + need(l), 0);
    let mode = sumNeed > 0.5 ? 'need' : 'equal';
    const amount = h('input', { type: 'text', inputmode: 'decimal', value: String(Math.round(Math.min(avail, mode === 'need' ? sumNeed : avail) * 100) / 100), style: { width: '120px', textAlign: 'right' } });
    const ins = lines.map((l) => h('input', { type: 'text', inputmode: 'decimal', style: { width: '110px', textAlign: 'right' } }));
    const msg = h('div', { class: 'small', style: { margin: '8px 0' } });
    const fill = () => {
      const amt = Math.max(0, num(amount.value)); const n = lines.length; let parts;
      if (mode === 'equal') parts = lines.map((_, i) => Math.round((amt / n) * 100) / 100);
      else { const tot = sumNeed || 1; const scale = amt >= sumNeed ? 1 : amt / tot; parts = lines.map((l) => Math.round(need(l) * scale * 100) / 100); }
      ins.forEach((x, i) => { x.value = parts[i] ? String(parts[i]) : ''; }); check();
    };
    const total = () => ins.reduce((a, x) => a + num(x.value), 0);
    const check = () => { const t = total(); msg.className = 'small ' + (t > avail + 0.005 ? 'bad' : 'muted'); msg.textContent = `Spreading ${fmt.money(t)} of the ${fmt.money(avail)} the pool can give; ${fmt.money(avail - t)} stays in the pool.`; };
    const radios = [['need', 'By need (EAC less allowance)'], ['equal', 'Equal'], ['typed', 'Typed per line']].map(([k, label]) => h('label', { class: 'row small', style: { gap: '4px' } },
      h('input', { type: 'radio', name: 'spmode', value: k, checked: mode === k, onchange: () => { mode = k; if (k !== 'typed') fill(); } }), label));
    amount.addEventListener('input', () => { if (mode !== 'typed') fill(); });
    ins.forEach((x) => x.addEventListener('input', () => { mode = 'typed'; radios[2].querySelector('input').checked = true; check(); }));
    const tb = h('table', { class: 't' }, h('thead', {}, h('tr', {}, ['CBS', 'Line', 'Allowance now', 'EAC', 'Short by', 'Gets'].map((x, i) => h('th', { class: i >= 2 ? 'r' : '' }, x)))),
      h('tbody', {}, lines.map((l, i) => h('tr', {}, h('td', { class: 'mono' }, l.code), h('td', {}, l.name), h('td', { class: 'r num' }, fmt.money(l.allowance)), h('td', { class: 'r num' }, fmt.money(l.eac)), h('td', { class: 'r num ' + (need(l) > 0.5 ? 'bad' : '') }, need(l) > 0.5 ? fmt.money(need(l)) : ''), h('td', { class: 'r' }, ins[i])))));
    modal({ title: `Spread ${pot.code.replace(/\.U$/, '')} unallocated allowance over ${lines.length} line${lines.length > 1 ? 's' : ''}`, size: 'wide', body: h('div', {},
      h('div', { class: 'note', style: { marginBottom: '10px' } }, `The pool holds ${fmt.money(pot.allowance)}; ${fmt.money(avail)} is free (the rest covers cost parked on the pool). Each line gets a ledger transfer from the pool.`),
      h('div', { class: 'row', style: { gap: '14px', flexWrap: 'wrap', marginBottom: '8px' } }, h('span', { class: 'small' }, 'Amount to spread'), amount, ...radios), h('div', { class: 'tw', style: { maxHeight: '40vh' } }, tb), msg),
      actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} }, { label: 'Spread', onClick: async () => {
        const moves = lines.map((l, i) => ({ to_id: l.node_id, budget: num(ins[i].value) })).filter((m) => m.budget > 0.004);
        if (total() > avail + 0.005) throw new Error(`The pool can give ${fmt.money(avail)}`);
        const o = await api.post(p('/ledger/spread'), { from_id: pot.node_id, moves });
        try { sessionStorage.setItem('lastSpread', JSON.stringify({ pairs: o.pairs, total: o.total, from: pot.code.replace(/\.U$/, ''), n: moves.length })); } catch (e) { /* ignore */ }
        toast(`Spread ${fmt.money(o.total)} over ${moves.length} lines`); await render(); } }] });
    fill();
  }

  // ---- CTC month pane: the line's months, what each method would give, and where its detail lives -----
  async function monthsPane(r0) {
    if (res.is_parent) return splitDialog(r0);
    const isPot = r0.kind === 'pot'; const nid = r0.node_id;
    const row = rows.find((x) => String(x.id) === String(r0.id)) || r0;
    const gi = grid.indexOf(M);
    const det = await api.get(p(`/nodes/${nid}`));
    const wi = await api.get(p(`/nodes/${nid}/what-if?pot=${isPot ? 1 : 0}`));
    const shownAll = grid.map((m, i) => i).filter((i) => i >= gi - 3 && (i <= gi || Object.values(wi.methods).some((w) => w && w.f[i]) || row.f[i]));
    const mpState = outlineState('mp', { folded: [] }); const mpCols = shownAll.map((i) => ({ id: grid[i] })); const mpVis = olVisible(mpCols, shownAll.indexOf(gi), mpState, MONTH_LEVELS);
    const shown = shownAll.filter((i, k) => mpVis[k]);   // folded and hidden months take no room (the strip above the table brings them back)
    const head = h('tr', {}, h('th', {}, ''), ...shown.flatMap((i) => i === gi ? [h('th', { class: 'mth mca', 'data-col': grid[i] }, fmt.month(grid[i])), h('th', { class: 'mth mcf', 'data-col': grid[i] }, fmt.month(grid[i]) + ' (F)')] : [h('th', { class: 'mth ' + (i < gi ? 'mpa' : 'mfu'), 'data-col': grid[i] }, fmt.month(grid[i]))]), h('th', { class: 'r' }, 'CTC'), h('th', { class: 'r' }, 'EAC'), h('th', { class: 'r' }, 'Contingency'), h('th'));
    const lineRow = h('tr', {}, h('td', {}, h('b', {}, 'Now'), ' ', h('span', { class: 'badge' }, row.method || 'AT-BUDGET')), ...shown.flatMap((i) => monthCells(row, i)), h('td', { class: 'r num' }, h('b', {}, fmt.money(row.ctc))), h('td', { class: 'r num' }, fmt.money(row.eac)), h('td', { class: 'r num ' + tone(row.contingency) }, fmt.money(row.contingency)), h('td'));
    const alt = Object.entries(wi.methods).filter(([m]) => m !== (row.method || 'AT-BUDGET')).map(([m, w]) => h('tr', { class: 'wi' }, h('td', {}, h('span', { class: 'badge', title: METHOD_NOTE[m] }, m)),
      ...shown.flatMap((i) => { const v = w ? w.f[i] : 0; const cell = h('td', { class: 'r num ' + (i > gi ? 'mg mg-fc' : i === gi ? 'mg mg-fc' : 'muted') }, i >= gi && v ? fmt.n(v) : ''); return i === gi ? [cell, h('td', { class: 'muted' })] : [cell]; }),
      h('td', { class: 'r num' }, w ? fmt.money(w.ctc) : ''), h('td', { class: 'r num' }, w ? fmt.money(w.eac) : ''), h('td', { class: 'r num ' + (w ? tone(w.contingency) : '') }, w ? fmt.money(w.contingency) : ''),
      h('td', {}, w && w.note ? h('span', { class: 'small muted', title: w.note }, w.note.length > 34 ? w.note.slice(0, 34) + '…' : w.note) : h('span', { class: 'small muted', title: 'Change the method on the Cost control row' }, 'compare only'))));
    const sub = (det.subcontracts || [])[0];
    const mpEd = !isPot && row.kind === 'line' ? windowEditor(det, nid, async () => { md.close(); await render(); }, { start: row.start, end: row.end }) : null;
    const links = h('div', { class: 'row', style: { marginTop: '12px' } },
      h('button', { class: 'btn', onclick: () => go('forecast', { node: isPot ? 'p' + nid : nid }) }, (row.method === 'GROUND-UP' ? 'Open the ground-up detail' : 'Open this line in Forecast')),
      sub ? h('button', { class: 'btn ghost', onclick: () => go('subcontracts', { open: sub.id }) }, `Claim sheet: ${sub.name}`) : null,
      h('button', { class: 'btn ghost', onclick: () => go('review', { node: r0.id }) }, 'Month-end review of this line'),
      h('button', { class: 'btn ghost', onclick: () => { md.close(); drillModal(r0, 'ctc'); } }, 'Records behind the CTC'));
    const md = modal({ title: `${row.code} ${row.name}: cost by month`, size: 'xl', body: h('div', {},
      h('div', { class: 'small muted', style: { marginBottom: '8px' } }, `${METHOD_NOTE[row.method || 'AT-BUDGET']} ${res.planned_from ? `The darker green ${fmt.month(M)} (F) column is the month as forecast at ${res.planned_from}.` : ''}`),
      row.note ? h('div', { class: 'note warn', style: { marginBottom: '8px' } }, row.note) : null,
      lostNote(row, async () => { md.close(); await render(); }, (role) => { mpEd.scrollIntoView({ block: 'nearest' }); mpEd._choose(role); }),
      mpEd,
      h('div', { class: 'tw' }, h('table', { class: 't' }, h('thead', {}, head), h('tbody', {}, lineRow, h('tr', {}, h('td', { colSpan: 99, class: 'small muted' }, 'What the other methods would give for this line (nothing changes until you pick one):')), ...alt))),
      links), actions: [{ label: 'Close', kind: 'ghost', onClick: () => {} }] });
    if (shownAll.length > 1) {   // the outline strip above the month table in the window
      const tw = [...document.querySelectorAll('.ov')].pop()?.querySelector('.tw');
      if (tw) { const mpStrip = outlineStrip({ cols: mpCols, cur: shownAll.indexOf(gi), levels: MONTH_LEVELS, st: mpState, onChange: () => { md.close(); monthsPane(r0); }, names: { 1: 'This quarter only', 2: 'Every month' } }); tw.before(mpStrip.el); mpStrip.mount(tw, tw.querySelector('table')); }
    }
  }

  // ---- drill-through: every amount opens the records behind it --------------------------------
  const TAB_OF = { budget: 'allowance', contingency: 'allowance', po: 'commit', outstanding: 'commit', ctd: 'actuals', acc: 'accruals', eac: 'forecast', risk: 'forecast' };
  function amt(r, metric, v, always = false, style = {}, toneCls = '') {
    const has = v || (always && v === 0);
    const td = h('td', { class: 'r num ' + toneCls + (has ? ' drillable' : ''), style, title: has ? 'Click for the records behind this amount' : '' }, v || always ? fmt.money(v) : '');
    // a number on a line opens that line on the tab that holds it (allowance: Allowance, CTD: Actuals, POs: POs, ACC: Accruals), so it can be adjusted there;
    // a group's total, which has no tab of its own, still lists the records behind it
    const SRC = { ctd: () => go('actuals', { node: r.node_id }), acc: () => go('accruals', { code: r.code }), po: () => go('commitments', { q: r.code }), outstanding: () => go('commitments', { q: r.code }) };
    if (metric === 'budget' && r.kind !== 'group' && !res.is_parent) {
      // the allowance cell is selected with a click and opened on its Allowance tab with a double-click; on an unallocated pool it also has a grip:
      // drag it down over the lines beneath to spread the pool over them
      td.classList.add('alw');
      td.title = r.kind === 'pot' ? 'Drag the grip over the lines below to spread this pool over them. Double-click to open its allowance.' : 'Click to select, double-click to open the allowance of this line';
      td.onclick = (e) => { e.stopPropagation(); document.querySelectorAll('td.alw.sel').forEach((x) => x.classList.remove('sel')); td.classList.add('sel'); };
      td.ondblclick = (e) => { e.stopPropagation(); openDrawer(r, 'allowance'); };
      if (r.kind === 'pot' && v > 0.5) {
        const grip = h('span', { class: 'grip4 spgrip', title: 'Drag down over the lines to spread this pool over them' });
        grip.addEventListener('mousedown', (e) => { e.preventDefault(); e.stopPropagation(); startSpread(r, td); });
        td.prepend(grip);
      }
    } else if (SRC[metric] && has && r.kind !== 'group' && !res.is_parent) {
      // a click looks at that line on the tab that holds the number; a double-click goes to the page it comes from
      let timer = null;
      td.title = 'Click for this line, double-click to open the page it comes from';
      td.onclick = (e) => { e.stopPropagation(); clearTimeout(timer); timer = setTimeout(() => openDrawer(r, TAB_OF[metric]), 260); };
      td.ondblclick = (e) => { e.stopPropagation(); clearTimeout(timer); SRC[metric](); };
    } else if (has) td.onclick = (e) => { e.stopPropagation(); if (metric === 'ctc' && r.kind !== 'group') monthsPane(r); else if (TAB_OF[metric] && r.kind !== 'group') openDrawer(r, TAB_OF[metric]); else drillModal(r, metric); };
    return td;
  }
  async function drillModal(r, metric, month = null) {
    if (res.is_parent) return splitDialog(r, `${metric ? metric.toUpperCase() + (month ? ' in ' + fmt.month(month) : '') + ': ' : ''}what each project puts into this line. Open a project for the records behind it.`);
    const node = r.kind === 'pot' ? 'p' + r.node_id : String(r.node_id ?? r.id);
    const q = new URLSearchParams({ node, metric }); if (month) q.set('month', month);
    let d;
    try { d = await api.get(p('/drill?' + q)); } catch (e) { toast(e.message, 'bad'); return; }
    const cell = (c, v) => {
      if (v === null || v === undefined || v === '') return '';
      if (c.type === 'money') return fmt.money(v, 2);
      if (c.type === 'date') return fmt.date(v);
      if (c.type === 'month') return fmt.month(v);
      if (c.type === 'num') return fmt.n(v, 2);
      return String(v);
    };
    const body = h('div', {}, d.note ? h('div', { class: 'note', style: { marginBottom: '10px' } }, d.note) : null);
    (d.sections || []).forEach((sec) => {
      const card = h('div', { style: { marginBottom: '14px' } }, h('h3', { style: { margin: '0 0 6px' } }, sec.title));
      if (sec.note) card.append(h('div', { class: 'small muted', style: { marginBottom: '6px' } }, sec.note));
      if (!sec.rows.length) card.append(h('div', { class: 'muted' }, 'No records.'));
      else {
        const cols = sec.columns.map((c) => ({ label: c.label, r: ['money', 'num'].includes(c.type) ? 1 : 0, cls: c.type === 'wrap' ? 'wrap' : '', f: (x) => cell(c, x[c.key]) }));
        card.append(h('div', { style: { overflowX: 'auto' } }, table(cols, sec.rows, { maxHeight: '34vh', onRow: sec.tbl ? (x) => historyDialog(sec.tbl, x.id, `${sec.tbl === 'accrual' ? 'Accrual' : 'Record'} ${fmt.money(x.amount)} on ${x.code}`) : null })));
        if (sec.total !== null && sec.total !== undefined) card.append(h('div', { class: 'row', style: { justifyContent: 'flex-end', marginTop: '6px', fontWeight: 700 } }, `${sec.total_label || 'Total'}: ${fmt.money(sec.total, 2)}`));
      }
      body.append(card);
    });
    if (!(d.sections || []).length) body.append(empty('Nothing behind this amount', 'No records were found for this selection.'));
    modal({ title: String(d.title).includes(r.code) ? d.title : `${r.code} ${r.name}: ${d.title}`, size: 'wide', body, actions: [{ label: 'Close', kind: 'ghost', onClick: () => {} }, { label: 'Open line', onClick: () => openDrawer(r, TAB_OF[metric] || 'forecast') }] });
  }

  // ---- detail drawer -------------------------------------------------------------------------
  async function openDrawer(r0, tab = 'forecast') {
    if (res.is_parent) return splitDialog(r0);   // a parent: each child project's share, opening on the child's own line
    const isGroup = r0.kind === 'group'; const isPot = r0.kind === 'pot';
    const nodeId = r0.node_id;
    const det = await api.get(p(`/nodes/${nodeId}`));
    const riskList = (await api.get(p('/risk')).catch(() => ({ risks: [] }))).risks.filter((r) => r.status !== 'ceased');
    const row = rows.find((x) => String(x.id) === String(r0.id)) || r0;
    const body = h('div', { dataset: { node: nodeId, row: r0.id } }); const d = drawer({ title: `${row.code}  ${row.name}`, sub: `${row.function || ''} ${det.ancestors.map((a) => a.code).join(' › ')}`, body });
    const kp = (l, v, c = '') => h('div', { class: 'kpi' }, h('div', { class: 'l' }, l), h('div', { class: 'v ' + c, style: { fontSize: '17px' } }, v));
    body.append(h('div', { class: 'grid g6', style: { marginBottom: '14px' } }, kp('Allowance', fmt.m(row.allowance)), kp('CTD', fmt.m(row.ctd)), kp('Accruals', fmt.m(row.acc)), kp('CTC', fmt.m(row.ctc)), kp('EAC', fmt.m(row.eac)), kp('Contingency', fmt.m(row.contingency), tone(row.contingency))));
    if (row.note) body.append(h('div', { class: 'note warn', style: { marginBottom: '10px' } }, row.note));
    let winEd = null;   // the forecast tab's window editor, for Link to schedule
    if (row.kind === 'line') { const ln = lostNote(row, async () => { await keep(r0, d); }, (role) => { if (cur !== 'forecast') { cur = 'forecast'; sw(); } if (winEd) { winEd.scrollIntoView({ block: 'nearest' }); winEd._choose(role); } }); if (ln) body.append(ln); }
    if (row.po_status === 'SHORT') body.append(h('div', { class: 'note bad', style: { marginBottom: '10px' } }, `Cost to complete (${fmt.money(row.ctc)}) is below open PO commitments (${fmt.money(row.outstanding)}). Raise the forecast or close the PO in Pronto.`));
    // how the budget is made up: original, movements, then each variation (topped up here or tracked on a copy) = total
    const bu = await api.get(p(`/nodes/${nodeId}/budget-buildup${isPot ? '?own=1' : ''}`)).catch(() => null);
    if (bu && bu.rows.length) {
      const company = !!(state.project.settings || {}).allowance_view && state.project.settings.allowance_view === 'company';
      const cell = (x, b) => h('td', { class: 'r num', style: b ? { fontWeight: 700 } : {} }, fmt.money(x));
      body.append(h('div', { class: 'card', style: { marginBottom: '12px' } }, h('div', { class: 'ch' }, h('h2', {}, 'Budget build-up'), h('span', { class: 'sp' }),
        h('span', { class: 'small muted' }, 'The original budget plus each change since: transfers, risk released and every approved variation.')),
        h('table', { class: 't' }, h('thead', {}, h('tr', {}, h('th', {}, ''), h('th', { class: 'r' }, 'Budget'), h('th', { class: 'r' }, 'Risk'), company ? h('th', { class: 'r' }, 'Total allowance') : null, h('th', {}, ''))),
          h('tbody', {}, bu.rows.map((x) => h('tr', {}, h('td', {}, x.kind === 'variation' ? h('span', {}, badge('Variation', 'navy'), ' ', x.label) : (x.kind === 'estimate' ? h('b', {}, x.label) : x.label)),
            cell(x.budget), cell(x.risk), company ? cell(x.budget + x.risk) : null,
            h('td', { class: 'small muted' }, x.kind === 'variation' ? h('span', {}, x.tracked, ' ', h('a', { style: { cursor: 'pointer' }, onclick: () => go('variations', { open: x.variation_id }) }, 'open')) : '')))),
          h('tfoot', {}, h('tr', {}, h('td', {}, 'Total budget'), cell(bu.total.budget, true), cell(bu.total.risk, true), company ? cell(bu.total.budget + bu.total.risk, true) : null, h('td', {}))))));
    }
    // base scope and variation scope tracked on their own CBS copies, shown together on this line
    if (row.parts) {
      const P = row.parts; const S = (k) => P.reduce((a, x) => a + (x[k] || 0), 0);
      const money = (v) => fmt.money(v);
      body.append(h('div', { class: 'card', style: { marginBottom: '12px' } }, h('div', { class: 'ch' }, h('h2', {}, 'Base scope and variation scope'), h('span', { class: 'sp' }),
        h('span', { class: 'small muted' }, 'This line adds up the original CBS (base) and the copies made to track approved variations separately. The tabs below are the base scope; Open shows a variation on its own.')),
        h('div', { class: 'tw' }, h('table', { class: 't' },
          h('thead', {}, h('tr', {}, ['Tracked as', 'CBS', 'Allowance', 'CTD', 'Accruals', 'CTC', 'EAC', 'Contingency', ''].map((x, i) => h('th', { class: i >= 2 && i <= 7 ? 'r' : '' }, x)))),
          h('tbody', {}, P.map((x) => h('tr', {}, h('td', {}, x.part === 'base' ? h('b', {}, 'Base scope') : h('span', {}, badge('Variation', 'navy'), ' ', x.label)), h('td', { class: 'mono' }, x.code),
            ...['allowance', 'ctd', 'acc', 'ctc', 'eac'].map((k) => h('td', { class: 'r num' }, money(x[k]))), h('td', { class: 'r num ' + tone(x.contingency) }, money(x.contingency)),
            h('td', { class: 'nowrap' }, x.part === 'base' ? '' : h('span', {}, h('button', { class: 'btn ghost sm', title: 'The variation copy on its own: forecast, actuals, accruals', onclick: () => { d.close(); openDrawer({ ...x, parts: undefined }); } }, 'Open'),
              h('button', { class: 'btn ghost sm', onclick: () => go('variations', { open: x.variation_id }) }, 'Variation')))))),
          h('tfoot', {}, h('tr', {}, h('td', {}, 'Total'), h('td'), ...['allowance', 'ctd', 'acc', 'ctc', 'eac', 'contingency'].map((k) => h('td', { class: 'r num' }, money(S(k)))), h('td')))))));
    }
    const pane = h('div');
    let cur = tab; let sparkDraw = null;
    drawerCtx = { tab: () => cur, scroll: () => (document.querySelector('.drawer .db') || { scrollTop: 0 }).scrollTop };
    const tabItems = [['forecast', 'Forecast'], ['actuals', 'Actuals'], ['commit', 'POs'], ['accruals', 'Accruals'], ['allowance', 'Allowance'], ['history', 'History']];
    const sw = () => { clear(tb).append(tabs(tabItems, cur, (k) => { cur = k; sw(); })); clear(pane); ({ forecast: forecastTab, actuals: actualsTab, commit: commitTab, accruals: accrTab, allowance: allowTab, history: historyTab })[cur](); };
    const tb = h('div'); body.append(tb, pane); sw();

    function monthsSeries(withColors = true) {
      const idx = grid.map((m, i) => i).filter((i) => row.a[i] || row.x[i] || row.f[i]);
      return idx;
    }
    function forecastTab() {
      if (isGroup) {
        const m = select(Object.keys(state.tax.methods), 'AT-BUDGET');
        pane.append(h('div', { class: 'note' }, 'This is a group. Forecast methods are set per line. Set one method for every line below it:'), h('div', { class: 'row', style: { margin: '10px 0' } }, m, h('label', { class: 'row small' }, h('input', { type: 'checkbox', id: 'incpots', checked: true }), 'include unallocated pots'),
          h('button', { class: 'btn', onclick: async () => { const r = await api.post(p('/methods'), { node_id: nodeId, method: m.value, include_pots: document.getElementById('incpots').checked }); toast(`${r.updated} lines updated`); d.close(); render(); } }, 'Apply to all lines below')));
        pane.append(spark());
        return;
      }
      const node = det;
      const cur = isPot ? (det.unalloc_method || 'AT-BUDGET') : (det.method || 'AT-BUDGET');
      const top = h('input', { type: 'number', step: '0.01', value: (isPot ? det.unalloc_eac : det.eac_override) ?? '' }); const unc = h('input', { type: 'number', step: '0.01', value: det.uncommitted || 0 });
      // the method is changed on the row in the table, not here; what is typed here are the inputs of the method the line has
      const meth = h('div', { class: 'card', style: { marginBottom: '12px' } }, h('div', { class: 'ch' }, h('b', {}, 'Forecast method'), h('span', { class: 'badge m-' + cur }, cur)),
        h('div', { class: 'small muted', style: { margin: '4px 0 8px' } }, METHOD_NOTE[cur], ' Change the method on this line\'s row in the table; the other months-by-method comparisons are in the month forecast window.'),
        cur === 'TOP-DOWN' || cur === 'AT-COMMIT' ? h('div', { class: 'grid g4' }, cur === 'TOP-DOWN' ? field('Top-down EAC', top, 'Used by TOP-DOWN') : field('Not yet committed', unc, 'Used by AT-COMMIT'), h('span'), h('span'), h('span')) : null,
        cur === 'TOP-DOWN' || cur === 'AT-COMMIT' ? h('div', { class: 'row', style: { marginTop: '10px' } }, h('button', { class: 'btn', onclick: async () => {
          const body = isPot ? { unalloc_eac: top.value === '' ? null : num(top.value) } : { eac_override: top.value === '' ? null : num(top.value), uncommitted: num(unc.value) };
          await api.put(p(`/nodes/${nodeId}`), body); toast('Saved'); await keep(r0, d); } }, 'Save')) : null);
      pane.append(meth);
      pane.append(spark());
      if (!isPot) { winEd = windowEditor(det, nodeId, async () => { await keep(r0, d); }, { start: row.start, end: row.end }); pane.append(winEd); }
      pane.append(h('div', { class: 'row', style: { margin: '-4px 0 12px' } }, h('button', { class: 'btn ghost sm', onclick: () => go('forecast', { node: isPot ? 'p' + nodeId : nodeId }) }, 'Open this line in Forecast'), h('span', { class: 'small muted' }, 'Resource calendars, milestone payments and rosters are built there.')));
      if (!isPot && (method.value === 'GROUND-UP' || det.items.length)) pane.append(itemsCard());
      if (!isPot && method.value === 'MANUAL') pane.append(manualCard());
      if (!isPot && method.value === 'CLAIM') pane.append(h('div', { class: 'note' }, det.subcontracts.length ? `Linked subcontract: ${det.subcontracts.map((s) => s.name).join(', ')}. Edit its milestones on the Subcontracts page.` : 'No subcontract is linked to this line yet. Create one on the Subcontracts page and link it to this CBS line.', ' ', h('a', { href: '#/subcontracts' }, 'Open subcontracts')));
    }
    function spark() {
      const box = h('div', { class: 'chartbox short' }); const title = h('span', { class: 'small muted' });
      const c = h('div', { class: 'card' }, h('div', { class: 'ch' }, h('h2', {}, 'Monthly profile'), h('span', { class: 'sp' }), title), box);
      // f: the forecast months to draw (the line's own, or what another method would give, as a preview before saving)
      sparkDraw = (f, label) => {
        const fc = f || row.f; title.textContent = label || '';
        const idx = grid.map((m, i) => i).filter((i) => row.a[i] || row.x[i] || fc[i]);
        chart(box, { type: 'bar', data: { labels: idx.map((i) => fmt.month(grid[i])), datasets: [{ label: 'Actual', data: idx.map((i) => row.a[i]), backgroundColor: PALETTE[0] }, { label: 'Accrual', data: idx.map((i) => row.x[i]), backgroundColor: PALETTE[2] }, { label: f ? 'Forecast (preview)' : 'Forecast', data: idx.map((i) => fc[i]), backgroundColor: PALETTE[3] }] }, options: { animation: false, scales: { x: { stacked: true }, y: { stacked: true } } } });
      };
      setTimeout(() => sparkDraw(), 30);
      return c;
    }
    function itemsCard() {
      const c = h('div', { class: 'card', style: { marginBottom: '12px' } }, h('div', { class: 'ch' }, h('h2', {}, 'Forecast items'), h('span', { class: 'sp' }), h('button', { class: 'btn sm', onclick: () => itemDialog() }, '+ Add item')));
      if (!det.items.length) c.append(h('div', { class: 'muted' }, 'No items yet. Each item is a quantity at a rate, spread over time by its spread mode.'));
      else c.append(table([{ label: 'Scope', f: (i) => i.scope || '' }, { label: 'Spread', f: (i) => i.spread }, { label: 'Qty', r: 1, f: (i) => fmt.n(i.qty, 2) }, { label: 'Unit', f: (i) => i.unit || '' }, { label: 'Rate', r: 1, f: (i) => fmt.money(i.rate, 2) }, { label: 'Start', f: (i) => fmt.date(i.start_date) }, { label: 'End', f: (i) => fmt.date(i.end_date) }, { label: 'Frequency', f: (i) => i.spread === 'Recurring' ? `${i.freq || 'Monthly'}${i.occurrences ? ' x' + i.occurrences : ''}` : '' },
        { label: 'Total', r: 1, f: (i) => ['Calendar', 'Roster'].includes(i.spread) ? h('a', { onclick: () => go('forecast', { node: nodeId, item: i.id }) }, 'see Forecast') : i.spread === 'Manual' ? fmt.money(det.manual.filter((m) => m.item_id === i.id).reduce((a, m) => a + m.amount, 0)) : fmt.money(i.qty * i.rate * (i.pct ?? 1)) },
        { label: '', f: (i) => h('span', { class: 'row', style: { gap: '4px' } }, h('button', { class: 'btn ghost sm', onclick: () => ['Calendar', 'Milestones', 'Roster'].includes(i.spread) ? go('forecast', { node: nodeId, item: i.id }) : itemDialog(i) }, 'Edit'), h('button', { class: 'btn danger sm', onclick: async () => { await api.del(p(`/items/${i.id}`)); await keep(r0, d); } }, '×')) }], det.items));
      return c;
    }
    function itemDialog(it = null) {
      const riskSel = select([['', '(not risk related)'], ...(riskList || []).map((r) => [r.id, `${r.ref} ${r.title}`])], it?.risk_id || '');
      const scope = h('input', { type: 'text', value: it?.scope || '' }); const spread = select(['Lump', 'Linear', 'Recurring', 'Manual'], it?.spread || 'Linear');
      const unit = h('input', { type: 'text', value: it?.unit || '', placeholder: 'hr, day, ea' }); const qty = h('input', { type: 'number', step: 'any', value: it?.qty ?? 1 }); const rate = h('input', { type: 'number', step: '0.01', value: it?.rate ?? 0 });
      const pct = h('input', { type: 'number', step: '0.01', value: it?.pct ?? 1 }); const start = h('input', { type: 'date', value: it?.start_date || '' }); const end = h('input', { type: 'date', value: it?.end_date || '' });
      const freq = select(state.tax.frequencies, it?.freq || 'Monthly'); const occ = h('input', { type: 'number', value: it?.occurrences || '', placeholder: 'or until End' });
      const manual = h('div', { class: 'grid g4' });
      const futureMonths = grid.filter((m) => m >= M);
      const mi = {}; futureMonths.forEach((m) => { mi[m] = h('input', { type: 'number', step: '0.01', value: det.manual.find((x) => x.item_id === it?.id && x.month === m)?.amount ?? '' }); manual.append(field(fmt.month(m), mi[m])); });
      const toggles = h('div');
      const sync = () => { toggles.replaceChildren(spread.value === 'Manual' ? h('div', {}, h('div', { class: 'note', style: { marginBottom: '8px' } }, 'Type the amount for each remaining month.'), manual) : h('div', { class: 'grid g3' }, field('Start', start), field('End', end), spread.value === 'Recurring' ? h('div', { class: 'grid g2' }, field('Frequency', freq), field('Occurrences', occ)) : h('span'))); };
      spread.onchange = sync; sync();
      modal({ title: it ? 'Edit forecast item' : 'Add forecast item', size: 'wide', body: h('div', { class: 'grid' }, field('Scope', scope, 'What this item pays for'),
        h('div', { class: 'grid g4' }, field('Spread mode', spread, 'Lump: all in the start month. Linear: even from start to end. Recurring: qty x rate each period. Manual: typed months.'), field('Unit', unit), field('Quantity (per period if recurring)', qty), field('Rate', rate)), field('Share of total (1 = 100%)', pct), field('Risk (if this cost is a risk event)', riskSel), toggles),
        actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} }, { label: 'Save item', onClick: async () => {
          const months = {}; Object.entries(mi).forEach(([m, i]) => { if (i.value !== '') months[m] = num(i.value); });
          await api.post(p(`/nodes/${nodeId}/items`), { id: it?.id, scope: scope.value, spread: spread.value, unit: unit.value, qty: num(qty.value), rate: num(rate.value), pct: num(pct.value) || 1, start_date: start.value || null, end_date: end.value || null, freq: freq.value, occurrences: occ.value ? +occ.value : null, risk_id: riskSel.value ? +riskSel.value : null, months: spread.value === 'Manual' ? months : undefined });
          await keep(r0, d); } }] });
    }
    function manualCard() {
      const fm = grid.filter((m) => m >= M); const inp = {};
      const c = h('div', { class: 'card', style: { marginBottom: '12px' } }, h('h2', {}, 'Monthly forecast'), h('div', { class: 'grid g4' }, fm.map((m) => { inp[m] = h('input', { type: 'number', step: '0.01', value: det.manual.find((x) => !x.item_id && x.month === m)?.amount ?? '' }); return field(fmt.month(m), inp[m]); })),
        h('div', { style: { marginTop: '10px' } }, h('button', { class: 'btn', onclick: async () => { const months = {}; Object.entries(inp).forEach(([m, i]) => { if (i.value !== '') months[m] = num(i.value); }); await api.put(p(`/nodes/${nodeId}/manual`), { months }); toast('Saved'); await keep(r0, d); } }, 'Save months')));
      return c;
    }
    async function actualsTab() {
      pane.append(h('div', { class: 'muted' }, 'Loading transactions...'));
      const key = isPot ? 'p' + nodeId : String(nodeId);
      const tx = await api.get(p(`/pronto/tx?node=${key}&limit=300`));
      const tgs = await api.get(p('/risk/transactions?' + new URLSearchParams({ node: String(nodeId), limit: '300' })));
      const tagBy = Object.fromEntries(tgs.map((t) => [t.row_hash, t.tags]));
      clear(pane).append(h('div', { class: 'row', style: { marginBottom: '8px' } }, badge(`${fmt.n(tx.total.n)} transactions`), badge(fmt.money(tx.total.cost, 2), 'navy'), tx.total.n > 300 ? h('span', { class: 'muted small' }, 'Showing the latest 300') : null),
        row.ctd_journal ? h('div', { class: 'note', style: { marginBottom: '8px' } }, `Includes ${fmt.money(row.ctd_journal)} of journalled accruals and reversals already in Pronto.`) : null,
        tx.rows.length ? table([{ label: 'Date', f: (x) => fmt.date(x.tx_date) }, { label: 'Doc', f: (x) => x.doc_type }, { label: 'Ref', f: (x) => x.reference || '' }, { label: 'Account', f: (x) => x.account_desc || x.account_code || '' }, { label: 'Description', cls: 'wrap', f: (x) => x.description || '' }, { label: 'Qty', r: 1, f: (x) => fmt.n(x.qty, 1) }, { label: 'Cost', r: 1, f: (x) => fmt.money(x.cost, 2) }, ...(riskList.length ? [{ label: 'Risk', f: (x) => riskCell(x) }] : [])], tx.rows, { maxHeight: '48vh' }) : empty('No transactions', 'Nothing from Pronto has landed on this line.'));
    }
    function riskCell(x) {
      const cur = (tagBy[x.row_hash] || [])[0];
      const sel = select([['', ''], ...riskList.map((r) => [r.id, r.ref])], cur ? cur.risk_id : '', { style: { width: '84px' }, title: 'Tag this cost to a risk' });
      sel.onclick = (e) => e.stopPropagation();
      sel.onchange = async () => { if (cur) await api.del(p(`/risk/tag/${cur.id}`)); if (sel.value) await api.post(p('/risk/tag'), { risk_id: +sel.value, row_hash: x.row_hash }); toast(sel.value ? 'Tagged to the risk' : 'Tag removed'); };
      return sel;
    }
    function commitTab() {
      if (!det.pos.length) { pane.append(empty('No purchase orders', 'No PO from the Pronto export maps to this line.')); return; }
      pane.append(table([{ label: 'PO', f: (x) => x.order_no }, { label: 'Supplier', f: (x) => x.supplier_name }, { label: 'Status', f: (x) => badge(x.status, x.is_open ? 'warn' : '') }, { label: 'Committed', r: 1, f: (x) => fmt.money(x.committed) }, { label: 'Received', r: 1, f: (x) => fmt.money(x.received) }, { label: 'Outstanding', r: 1, f: (x) => fmt.money(x.is_open ? Math.max(0, x.committed - x.received) : 0) }], det.pos));
    }
    function accrTab() {
      const lines = isGroup ? [] : [r0];
      pane.append(h('div', { class: 'row', style: { marginBottom: '8px' } }, isGroup ? '' : h('button', { class: 'btn sm', onclick: () => accrualDialog(nodeId, rows, () => keep(r0, d)) }, '+ Add accrual'), row.acc_ts ? badge(`${fmt.money(row.acc_ts)} unposted timesheets`, 'warn') : null),
        det.accruals.length ? table([{ label: 'Month', f: (x) => fmt.month(x.month) }, { label: 'Hours', r: 1, f: (x) => x.hours ? fmt.n(x.hours, 1) : '' }, { label: 'Amount', r: 1, f: (x) => fmt.money(x.amount) }, { label: 'Raised by', f: (x) => x.created_by || '' }, { label: 'Status', f: (x) => badge(x.status, { open: 'warn', matched: 'good', investigate: 'bad' }[x.status] || '') }, { label: 'Invoice ref', f: (x) => x.inv_ref || '' }, { label: 'Reason', f: (x) => x.reason || '' }], det.accruals, { onRow: (x) => historyDialog('accrual', x.id, `Accrual ${fmt.money(x.amount)} ${fmt.month(x.month)}`) }) : h('div', { class: 'muted' }, 'No manual accruals on this line.'), det.accruals.length ? h('div', { class: 'small muted', style: { marginTop: '6px' } }, 'Click an accrual to see who raised it, who changed it and when.') : null);
    }
    async function historyTab() {
      const hs = await api.get(p(`/history?tbl=cbs_node&id=${nodeId}`));
      pane.append(h('div', { class: 'small muted', style: { marginBottom: '8px' } }, 'Changes to this line, its forecast items, accruals and allowance, by whoever made them.'),
        hs.length ? table([{ label: 'When', f: (r) => h('span', { class: 'nowrap' }, when(r.at)) }, { label: 'Who', f: who }, { label: '', f: opBadge }, { label: 'Record', cls: 'wrap', f: (r) => r.what }, { label: 'What changed', cls: 'wrap', f: changeList }], hs.slice().reverse(), { maxHeight: '55vh' }) : empty('No history yet', 'Changes are recorded from this version of PMT onwards.'));
    }
    function allowTab() {
      pane.append(table([{ label: 'Date', f: (x) => fmt.date(x.date) || fmt.date((x.created_at || '').slice(0, 10)) }, { label: 'Type', f: (x) => x.kind }, { label: 'Budget', r: 1, f: (x) => fmt.money(x.budget, 2) }, { label: 'Risk', r: 1, f: (x) => fmt.money(x.risk, 2) }, { label: 'Ref', f: (x) => x.ref || '' }, { label: 'Note', f: (x) => x.note || '' }], det.ledger),
        h('div', { style: { marginTop: '10px' } }, h('a', { href: '#/cbs' }, 'Transfer allowance on the CBS page')));
    }
  }
  let drawerCtx = null;   // the open drawer's tab and scroll, so that saving in it comes back to the same place
  const keep = async (r0, d) => {
    sessionStorage.setItem('reopen', String(r0.id));
    try { if (drawerCtx) { sessionStorage.setItem('reopenTab', drawerCtx.tab()); sessionStorage.setItem('reopenScroll', String(drawerCtx.scroll())); } } catch (e) { /* ignore */ }
    d.close(); await render();
  };

  drawBar(); draw();
  const reopen = sessionStorage.getItem('reopen');
  if (reopen) {
    sessionStorage.removeItem('reopen'); const rr = byId.get(reopen);
    const tabBack = sessionStorage.getItem('reopenTab') || 'forecast'; const yBack = +(sessionStorage.getItem('reopenScroll') || 0);
    sessionStorage.removeItem('reopenTab'); sessionStorage.removeItem('reopenScroll');
    if (rr) openDrawer(rr, tabBack).then(() => { const back = () => { const el = document.querySelector('.drawer .db'); if (el) el.scrollTop = yBack; }; setTimeout(back, 60); setTimeout(back, 350); });
  }
  if (params.open) { const r = byId.get(String(params.open)); if (r) openDrawer(r); }
}
