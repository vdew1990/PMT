// CBS scope helpers shared by the dashboard, cost control and the pickers.
import { h, modal, field, debounce, fmt } from './ui.js';
import { state, saveLocal, loadRows } from './api.js';

export function indexRows(rows) {
  const byId = new Map(rows.map((r) => [String(r.id), r]));
  const kids = new Map();
  rows.forEach((r) => { const k = r.parent_id === null ? 'root' : String(r.parent_id); if (!kids.has(k)) kids.set(k, []); kids.get(k).push(r); });
  return { byId, kids };
}

export function pathTo(rows, id) {
  const { byId } = indexRows(rows);
  const out = [];
  let r = byId.get(String(id));
  while (r) { out.unshift(r); r = r.parent_id === null ? null : byId.get(String(r.parent_id)); }
  return out;
}

export function setScope(row) {
  state.scope.node = row ? row.id : null;
  state.scope.label = row ? `${row.code} ${row.name}` : null;
  saveLocal();
}

// Searchable tree picker. opts: {title, kinds:['group','line','pot'], onPick(row), selected}
export async function pickNode(opts = {}) {
  const data = state.rows || await loadRows();
  const rows = data.rows;
  const { byId, kids } = indexRows(rows);
  const kinds = opts.kinds || ['group', 'line', 'pot'];
  const expanded = new Set(rows.filter((r) => r.level <= 1).map((r) => String(r.id)));
  const search = h('input', { type: 'search', placeholder: 'Search code, name, function or resource...', style: { width: '100%' } });
  const box = h('div', { class: 'treepick' });
  let m;
  const draw = () => {
    box.replaceChildren();
    const q = search.value.trim().toLowerCase();
    const match = (r) => !q || `${r.code} ${r.name} ${r.function || ''} ${r.resource_code || ''}`.toLowerCase().includes(q);
    const hasMatch = (r) => match(r) || (kids.get(String(r.id)) || []).some(hasMatch) || (r.kind === 'group' && false);
    const walk = (r, depth) => {
      if (q && !hasMatch(r)) return;
      const ch = kids.get(String(r.id)) || [];
      const open = q ? true : expanded.has(String(r.id));
      const pickable = kinds.includes(r.kind) && (!opts.filter || opts.filter(r));
      const tn = h('div', { class: 'tn' + (String(opts.selected) === String(r.id) ? ' sel' : ''), style: { paddingLeft: 10 + depth * 18 + 'px' } },
        h('span', { class: 'tog', onclick: (e) => { e.stopPropagation(); if (expanded.has(String(r.id))) expanded.delete(String(r.id)); else expanded.add(String(r.id)); draw(); } }, ch.length ? (open ? '▾' : '▸') : ''),
        h('span', { class: 'mono' }, r.code), h('span', {}, r.name),
        r.kind === 'pot' ? h('span', { class: 'badge' }, 'unallocated pot') : null,
        h('span', { class: 'sp', style: { flex: 1 } }),
        opts.showEac ? h('span', { class: 'muted small' }, fmt.money(r.eac)) : null);
      if (pickable) tn.onclick = () => { m.close(); opts.onPick(r); };
      else tn.style.opacity = .55;
      box.append(tn);
      if (open) ch.forEach((c) => walk(c, depth + 1));
    };
    (kids.get('root') || []).forEach((r) => walk(r, 0));
  };
  search.oninput = debounce(draw, 120);
  draw();
  m = modal({ title: opts.title || 'Choose a CBS node', body: h('div', {}, opts.allowRoot ? h('div', { style: { marginBottom: '8px' } }, h('button', { class: 'btn ghost sm', onclick: () => { m.close(); opts.onPick(null); } }, 'Whole project')) : null, search, box), size: 'wide' });
}
