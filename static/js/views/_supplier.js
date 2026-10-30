import { h, fmt, select, field } from '../ui.js';
import { api, p } from '../api.js';

// Supplier and purchase order picker. Type or pick a supplier: a known Pronto supplier fills its code and lists its
// purchase orders; any other name is kept as a new supplier, matched on Diagnostics once Pronto has it. The PO is one of
// the supplier's Pronto orders or a number typed ahead of Pronto (also matched later).
let cache = null;
export async function knownSuppliers(fresh = false) {
  if (!cache || fresh) cache = await api.get(p('/suppliers'));
  return cache;
}

export async function supplierPicker(init = {}) {
  const list = await knownSuppliers();
  const label = (s) => `${s.name} (${s.code})`;
  const byLabel = new Map(list.map((s) => [label(s).toUpperCase(), s]));
  const byCode = new Map(list.map((s) => [s.code.toUpperCase(), s]));
  const dlId = 'sup-' + Math.random().toString(36).slice(2, 8);
  const dl = h('datalist', { id: dlId }, list.map((s) => h('option', { value: label(s) })));
  // companies in the database not (yet) seen in Pronto: subcontractors and suppliers named before their first PO
  api.get('/api/directory/names?kind=company').then((cs) => {
    const have = new Set(list.map((s) => s.name.toUpperCase()));
    cs.filter((c) => !have.has(c.name.toUpperCase())).forEach((c) => dl.append(h('option', { value: c.name }, c.sub || '')));
  }).catch(() => {});
  const start = init.supplier_code && byCode.get(String(init.supplier_code).toUpperCase());
  const sup = h('input', { type: 'text', list: dlId, value: start ? label(start) : (init.supplier_name || init.supplier_code || ''), placeholder: 'Type to search the Pronto suppliers, or a new name', style: { width: '100%' } });
  const code = h('input', { type: 'text', value: start ? start.code : (init.supplier_code || ''), placeholder: 'Pronto code, if known', style: { width: '140px' } });
  const hint = h('div', { class: 'small' });
  const poSel = h('select', { style: { width: '100%' } });
  const poNew = h('input', { type: 'text', value: '', placeholder: 'PO number (not in Pronto yet)', style: { width: '100%' } });
  const poHint = h('div', { class: 'small muted' });
  const current = () => byLabel.get(sup.value.trim().toUpperCase()) || byCode.get(sup.value.trim().toUpperCase()) || byCode.get(code.value.trim().toUpperCase());

  function drawPos(keep) {
    const s = current();
    const pos = s ? s.pos : [];
    const want = keep ?? init.po_no ?? '';
    poSel.replaceChildren(h('option', { value: '' }, pos.length ? '(choose a purchase order)' : '(no purchase order)'),
      ...pos.map((x) => h('option', { value: x.order_no, selected: x.order_no === want }, `${x.order_no} · ${fmt.money(x.committed)} · ${x.open ? 'open' : 'closed'}${x.cbs.length ? ' · ' + x.cbs.join(', ') : ''}`)),
      h('option', { value: '__new', selected: !!want && !pos.some((x) => x.order_no === want) }, 'A PO not in Pronto yet...'));
    poNew.value = want && !pos.some((x) => x.order_no === want) ? want : poNew.value;
    poNew.style.display = poSel.value === '__new' ? '' : 'none';
    const x = pos.find((y) => y.order_no === poSel.value);
    poHint.textContent = poSel.value === '__new' ? 'Kept as "to be matched": it ties out when the PO appears in the Pronto purchase orders.'
      : x ? `Pronto: committed ${fmt.money(x.committed)}, received ${fmt.money(x.received)}, ${x.lines} line(s)${x.categories.length ? ', ' + x.categories.join(', ') : ''}.` : '';
  }
  function onSupplier() {
    const s = current();
    if (s) {
      code.value = s.code; code.disabled = true;
      hint.className = 'small good'; hint.textContent = `Known in Pronto: ${s.code}${s.subcontracts.length ? ` · already used by ${s.subcontracts.join(', ')}` : ''}`;
    } else {
      code.disabled = false;
      hint.className = 'small warn'; hint.textContent = sup.value.trim() ? 'New supplier, not in the Pronto data yet: it is matched on Diagnostics once it comes through.' : '';
    }
    drawPos(poSel.value && poSel.value !== '__new' ? poSel.value : undefined);
  }
  sup.addEventListener('change', onSupplier); sup.addEventListener('input', () => { if (current()) onSupplier(); });
  code.addEventListener('change', onSupplier);
  poSel.addEventListener('change', () => drawPos(poSel.value === '__new' ? (poNew.value || '') : poSel.value));
  onSupplier();
  if (!current() && init.supplier_code) code.value = init.supplier_code;

  const el = h('div', { class: 'grid g2' },
    h('div', {}, dl, field('Supplier', sup), h('div', { class: 'row', style: { gap: '6px' } }, h('span', { class: 'small muted' }, 'Code'), code), hint),
    h('div', {}, field('Purchase order', poSel), poNew, poHint));
  return {
    el,
    value: () => {
      const s = current();
      const po = poSel.value === '__new' ? poNew.value.trim() : poSel.value;
      return { supplier_code: s ? s.code : (code.value.trim() || null), supplier_name: s ? s.name : (sup.value.trim() || null), po_no: po || null };
    },
  };
}
