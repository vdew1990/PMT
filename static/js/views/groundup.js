import { h, clear, fmt, modal, toast, field, empty, debounce, badge } from '../ui.js';
import { api, state, p } from '../api.js';
import { go, render } from '../app.js';
import { pickNode } from '../scope.js';
import { outlineState, outlineStrip, visible as olVisible, MONTH_LEVELS } from '../outline.js';

// FORECAST > Ground-Up register: every forecast item of the project, grouped the way the PM wants (H1 > H2 > H3), not in CBS order.
// The groups are labels only: each item still sits on its CBS line and rolls up to Cost control by CBS line and month.
const KIND = { Calendar: 'Resource calendar', Milestones: 'Milestone payments', Roster: 'Roster pattern', Linear: 'Even over dates', Lump: 'Lump sum', Recurring: 'Recurring', Manual: 'Typed months' };
const sel = new Set(); const fold = new Set();
const ui = { q: '', by: 'mine', live: false };

export default async function groundup(root) {
  const ro = !!state.project?.is_parent;
  const d = await api.get(p('/groundup'));
  const ost = outlineState('gu');
  const M = d.month; const items = d.items;
  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, 'Ground-Up register'),
    h('div', { class: 'sub' }, `The most detailed forecast: every item, grouped your way in up to three levels, from the status month ${fmt.month(M)}. Each item stays on its CBS line and rolls up to Cost control by CBS line and month.`)),
    h('span', { class: 'sp' }), ro ? null : h('button', { class: 'btn', onclick: addItem }, 'Add an item...'), h('button', { class: 'btn ghost', onclick: () => go('calendar') }, 'Labour calendar')));
  const live = items.filter((i) => i.live);
  const kpi = (l, v, s, t = '') => h('div', { class: 'kpi ' + t }, h('div', { class: 'l' }, l), h('div', { class: 'v' }, v), h('div', { class: 's' }, s));
  root.append(h('div', { class: 'grid g4', style: { marginBottom: '14px' } }, kpi('Ground-up forecast', fmt.m(d.total), `${live.length} items counted in Cost control`), kpi('Items', String(items.length), `${new Set(items.map((i) => i.node_id)).size} CBS lines`, 't2'),
    kpi('Not grouped yet', String(d.ungrouped), d.ungrouped ? 'Select them and give them a group' : 'Every item is in a group', 't3'),
    kpi('Not counted', String(d.not_live), d.not_live ? 'Their line forecasts by another method' : 'Every item is counted', 't4')));
  if (d.not_live) root.append(h('div', { class: 'note warn', style: { marginBottom: '12px' } }, `${d.not_live} items sit on lines that forecast by another method, so they are not counted. Change a line to GROUND-UP on its row in Cost control, or open the item and save it (that switches the line).`));
  const bar = h('div', { class: 'card row', style: { padding: '10px 14px', marginBottom: '12px' } });
  const pick = h('div', { class: 'note', style: { marginBottom: '8px', display: 'none', alignItems: 'center', gap: '8px', flexWrap: 'wrap' } });
  const out = h('div'); root.append(bar, pick, out);
  const search = h('input', { type: 'search', placeholder: 'Search item, CBS line, person...', style: { width: '240px' }, oninput: debounce(() => { ui.q = search.value.trim().toLowerCase(); draw(); }, 150) });
  const chip = (label, on, fn) => h('span', { class: 'chip' + (on ? ' on' : ''), onclick: fn }, label);
  const drawBar = () => clear(bar).append(search, chip('Your groups', ui.by === 'mine', () => { ui.by = 'mine'; drawBar(); draw(); }), chip('By CBS line', ui.by === 'cbs', () => { ui.by = 'cbs'; drawBar(); draw(); }),
    chip('Counted only', ui.live, () => { ui.live = !ui.live; drawBar(); draw(); }), h('span', { class: 'sp', style: { flex: 1 } }),
    h('button', { class: 'btn sm ghost', onclick: () => { fold.clear(); allKeys().forEach((k) => fold.add(k)); draw(); } }, 'Collapse all'), h('button', { class: 'btn sm ghost', onclick: () => { fold.clear(); draw(); } }, 'Expand all'));

  const keysOf = (i) => (ui.by === 'cbs' ? [i.code, null, null] : [i.h1, i.h2, i.h3]);
  const allKeys = () => { const s = new Set(); items.forEach((i) => { const [a, b, c] = keysOf(i); const A = a || NONE; s.add(A); if (b) s.add(A + '\u0001' + b); if (b && c) s.add(A + '\u0001' + b + '\u0001' + c); }); return s; };
  const NONE = 'Not grouped';
  const itemName = (i) => i.scope || i.note || KIND[i.spread] || i.spread;
  const sumRow = (rs, mi) => ({ t: rs.reduce((a, r) => a + r.total, 0), m: mi.map((m) => rs.reduce((a, r) => a + (r.months[m] || 0), 0)) });

  function draw() {
    const vis = items.filter((i) => (!ui.live || i.live) && (!ui.q || `${i.scope || ''} ${i.line} ${i.code} ${i.who || ''} ${i.h1 || ''} ${i.h2 || ''} ${i.h3 || ''}`.toLowerCase().includes(ui.q)));
    for (const k of [...sel]) if (!items.some((i) => String(i.id) === k)) sel.delete(k);
    if (!vis.length) { clear(out).append(empty(items.length ? 'No items match' : 'No ground-up items yet', items.length ? 'Change the search or filters.' : 'Add an item to a CBS line: a resource calendar, milestone payments, a roster, quantity x rate or typed months.')); return; }
    const miAll = d.grid.filter((m) => vis.some((r) => Math.abs(r.months[m] || 0) > 0.005));
    const ocols = miAll.map((m) => ({ id: m })); const ovis = olVisible(ocols, 0, ost, MONTH_LEVELS);
    const mi = miAll.filter((m, k) => ovis[k]);
    // the tree: H1 > H2 > H3 (items with no H1 last, under Not grouped); a level with no label puts the item straight under the level above
    const tree = new Map();
    vis.forEach((i) => { const [a, b, c] = keysOf(i); const A = a || NONE; const n1 = tree.get(A) || tree.set(A, { items: [], kids: new Map() }).get(A); n1.items.push(i);
      if (b) { const n2 = n1.kids.get(b) || n1.kids.set(b, { items: [], kids: new Map() }).get(b); n2.items.push(i); if (c) { const n3 = n2.kids.get(c) || n2.kids.set(c, { items: [], kids: new Map() }).get(c); n3.items.push(i); } } });
    const order = (m) => [...m.keys()].sort((x, y) => (x === NONE) - (y === NONE) || x.localeCompare(y));
    const head = h('tr', {}, h('th', { style: { width: '26px' } }, h('input', { type: 'checkbox', title: 'Select every item shown', onchange: (e) => { vis.forEach((i) => (e.target.checked ? sel.add(String(i.id)) : sel.delete(String(i.id)))); draw(); drawPick(); } })),
      h('th', {}, 'Group / item'), h('th', {}, 'CBS line'), h('th', {}, 'Who'), h('th', {}, 'Kind'), h('th', {}, 'Window'), h('th', { class: 'r' }, 'Total'),
      ...mi.map((m) => h('th', { class: 'r mth ' + (m === M ? 'mca' : 'mfu'), 'data-m': m, 'data-col': m }, fmt.month(m))));
    const tbody = h('tbody');
    const cellsOf = (s, tag = 'td') => [h(tag, { class: 'r num', style: { fontWeight: 700 } }, s.t ? fmt.money(s.t) : ''), ...s.m.map((v) => h(tag, { class: 'r num mcell' }, v ? fmt.money(v) : ''))];
    const groupRow = (label, key, depth, rs) => {
      const closed = fold.has(key); const cls = depth === 0 ? 'gp' : depth === 1 ? 'par' : 'par2';
      const tog = h('span', { class: 'tog', onclick: () => { closed ? fold.delete(key) : fold.add(key); draw(); } }, closed ? '▸' : '▾');
      const ids = rs.map((r) => String(r.id)); const all = ids.every((x) => sel.has(x));
      const rn = ui.by === 'mine' && label !== NONE && !ro ? h('a', { class: 'small', style: { marginLeft: '8px', fontWeight: 400 }, onclick: (e) => { e.stopPropagation(); renameDialog(depth, label); } }, 'rename') : null;
      tbody.append(h('tr', { class: cls }, h('td', {}, h('input', { type: 'checkbox', checked: all, onchange: (e) => { ids.forEach((x) => (e.target.checked ? sel.add(x) : sel.delete(x))); draw(); drawPick(); } })),
        h('td', { colSpan: 5 }, h('span', { style: { paddingLeft: depth * 16 + 'px' } }), tog, h('b', {}, label), h('span', { class: 'muted small', style: { fontWeight: 400, marginLeft: '8px' } }, `${rs.length} ${rs.length === 1 ? 'item' : 'items'}`), rn), ...cellsOf(sumRow(rs, mi))));
    };
    const itemRow = (i, depth) => tbody.append(h('tr', { class: ro ? '' : 'click', onclick: ro ? null : (e) => { if (e.target.closest('input,a')) return; go('forecast', { node: i.pool ? 'p' + i.node_id : i.node_id, item: i.id }); } },
      h('td', {}, h('input', { type: 'checkbox', checked: sel.has(String(i.id)), onchange: (e) => { e.target.checked ? sel.add(String(i.id)) : sel.delete(String(i.id)); drawPick(); } })),
      h('td', {}, h('span', { style: { paddingLeft: depth * 16 + 'px' } }), itemName(i), i.live ? null : h('span', { style: { marginLeft: '6px' } }, badge('not counted', 'warn'))),
      h('td', { class: 'mono', title: i.line }, i.code), h('td', { class: 'muted' }, [i.who, i.role].filter(Boolean).join(' · ')), h('td', { class: 'muted' }, KIND[i.spread] || i.spread),
      h('td', { class: 'muted nowrap' }, i.start || i.end ? `${fmt.date(i.start)} – ${fmt.date(i.end)}` : ''), ...cellsOf({ t: i.total, m: mi.map((m) => i.months[m] || 0) }).map((c, k) => { if (k === 0) c.style.fontWeight = 400; return c; })));
    const walk = (node, depth, path) => {
      const itemsHere = node.items.filter((i) => { const [a, b, c] = keysOf(i); const lvl = [a, b, c].filter(Boolean).length; return lvl <= depth + 1; });
      itemsHere.forEach((i) => itemRow(i, depth + 1));
      order(node.kids).forEach((k) => { const key = path + '\u0001' + k; const kid = node.kids.get(k); groupRow(k, key, depth + 1, kid.items); if (!fold.has(key)) walk(kid, depth + 1, key); });
    };
    order(tree).forEach((k) => { const n = tree.get(k); groupRow(k, k, 0, n.items); if (!fold.has(k)) walk(n, 0, k); });
    const total = sumRow(vis, mi);
    const t = h('table', { class: 't fgrid notools nogroup' }, h('thead', {}, head, h('tr', { class: 'ftot top' }, h('td', {}), h('td', { colSpan: 5 }, 'Total' + (vis.length < items.length ? ' of the items shown' : '')), ...cellsOf(total))), tbody);
    const wrap = h('div', { class: 'tw', style: { maxHeight: '70vh' } }, t);
    const strip = miAll.length > 1 ? outlineStrip({ cols: ocols, cur: 0, levels: MONTH_LEVELS, st: ost, onChange: draw, names: { 1: 'This quarter only', 2: 'Every month' } }) : null;
    clear(out).append(...(strip ? [strip.el] : []), wrap);
    if (strip) out._olOff = strip.mount(wrap, t);
    drawPick();
  }

  function drawPick() {
    const chosen = items.filter((i) => sel.has(String(i.id)));
    pick.style.display = chosen.length ? 'flex' : 'none'; pick.replaceChildren();
    if (!chosen.length || ro) return;
    const first = chosen[0];
    const dl = (id, vals) => h('datalist', { id }, ...vals.map((v) => h('option', { value: v })));
    const inp = (ph, v, list) => h('input', { type: 'text', placeholder: ph, value: v || '', list, style: { width: '170px' } });
    const same = (k) => (chosen.every((c) => (c[k] || '') === (first[k] || '')) ? first[k] : '');
    const a = inp('H1 (top group)', same('h1'), 'gu-h1'); const b = inp('H2', same('h2'), 'gu-h2'); const c = inp('H3', same('h3'), 'gu-h3');
    pick.append(h('b', {}, `${chosen.length} selected`), a, b, c, dl('gu-h1', d.names.h1), dl('gu-h2', d.names.h2), dl('gu-h3', d.names.h3),
      h('button', { class: 'btn sm', onclick: async () => { await api.post(p('/groundup/group'), { ids: chosen.map((i) => i.id), h1: a.value, h2: b.value, h3: c.value }); sel.clear(); toast('Grouped'); render(); } }, 'Put in this group'),
      h('a', { onclick: () => { sel.clear(); draw(); } }, 'Clear'),
      h('span', { class: 'small muted' }, 'A blank H1 takes them out of every group. H2 needs an H1, H3 needs an H2.'));
  }

  function renameDialog(depth, label) {
    const nn = h('input', { type: 'text', value: label });
    modal({ title: `Rename H${depth + 1} group`, body: h('div', {}, field('New name', nn, 'Every item with this name at this level is renamed.')),
      actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} }, { label: 'Rename', onClick: async () => { await api.post(p('/groundup/rename'), { level: 'h' + (depth + 1), old: label, new: nn.value }); toast('Renamed'); render(); } }] });
  }

  async function addItem() {
    pickNode({ title: 'Add an item to which CBS line?', kinds: ['line', 'pot'], onPick: (r) => go('forecast', { node: r.kind === 'pot' ? 'p' + r.node_id : r.node_id }) });
  }
  drawBar(); draw();
}
