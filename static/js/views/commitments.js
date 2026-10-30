import { h, fmt, table, badge, empty, debounce } from '../ui.js';
import { api, p, pref } from '../api.js';
import { go } from '../app.js';

export default async function commitments(root, params = {}) {
  const all = await api.get(p('/commitments'));
  let open = (() => { try { const v = sessionStorage.getItem('poOpen'); return v === null ? !!pref('po_open_only') : v === '1'; } catch (e) { return !!pref('po_open_only'); } })(); let q = String(params.q || '').toLowerCase();
  const tot = (l, k) => l.reduce((a, r) => a + (r[k] || 0), 0);
  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, 'Commitments'), h('div', { class: 'sub' }, 'Purchase orders from the Pronto PO export. A closed PO commits only what was received; open POs commit their full value.'))));
  if (!all.length) { root.append(empty('No purchase orders loaded', 'Upload the Pronto purchase order report to see commitments.', h('button', { class: 'btn', onclick: () => go('pronto') }, 'Open Pronto data'))); return; }
  const out = h('div'); const kp = h('div', { class: 'grid g4', style: { marginBottom: '14px' } });
  const search = h('input', { type: 'search', value: params.q || '', placeholder: 'Search PO, supplier, CBS...', style: { width: '260px' }, oninput: debounce(() => { q = search.value.toLowerCase(); draw(); }, 150) });
  const chk = h('input', { type: 'checkbox', checked: open, onchange: () => { open = chk.checked; try { sessionStorage.setItem('poOpen', open ? '1' : '0'); } catch (e) { /* ignore */ } draw(); } });
  root.append(kp, h('div', { class: 'row', style: { marginBottom: '10px' } }, search, h('label', { class: 'row small' }, chk, 'Open POs only')), out);
  function draw() {
    const l = all.filter((r) => (!open || r.is_open) && (!q || `${r.order_no} ${r.supplier} ${r.node_code} ${r.category}`.toLowerCase().includes(q)));
    kp.replaceChildren(...[['POs shown', fmt.n(l.length), ''], ['Committed', fmt.money(tot(l, 'committed')), ''], ['Received', fmt.money(tot(l, 'received')), ''], ['Outstanding (open POs)', fmt.money(tot(l, 'outstanding')), 'Floor for cost to complete']].map(([a, b, c]) => h('div', { class: 'kpi' }, h('div', { class: 'l' }, a), h('div', { class: 'v' }, b), h('div', { class: 's' }, c))));
    out.replaceChildren(table([{ label: 'PO', f: (r) => r.order_no }, { label: 'Supplier', f: (r) => r.supplier }, { label: 'Type', f: (r) => r.order_type }, { label: 'Status', f: (r) => badge(r.status, r.is_open ? 'warn' : '') }, { label: 'Ordered', f: (r) => fmt.date(r.ordered) },
      { label: 'CBS', f: (r) => r.node_code ? h('span', { class: r.node_kind === 'group' ? 'mono warn' : 'mono', title: r.node_kind === 'group' ? 'On the unallocated pot: no CBS line for this supplier yet' : r.node_name }, r.node_code + (r.node_kind === 'group' ? ' (pot)' : '')) : h('span', { class: 'bad' }, 'unmapped') },
      { label: 'Committed', r: 1, f: (r) => fmt.money(r.committed) }, { label: 'Received', r: 1, f: (r) => fmt.money(r.received) }, { label: 'Outstanding', r: 1, f: (r) => r.outstanding ? fmt.money(r.outstanding) : '' }], l, { maxHeight: '68vh', onRow: (r) => r.node_id && go('costcontrol', { node: r.node_id }) }));
  }
  draw();
}
