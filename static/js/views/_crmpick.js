// "Start from a CRM opportunity": a picker over the MM_CRM opportunity database (read-only: PMT never writes to the CRM).
import { h, modal, toast, select } from '../ui.js';
import { api } from '../api.js';

const STATUSES = [['', 'Any status'], ['Won', 'Won'], ['Contract Negotiations', 'Contract negotiations'], ['Submitted', 'Submitted'], ['Tendering', 'Tendering'], ['Hold', 'Hold']];

export async function crmStatus() {
  try { return await api.get('/api/crm/status'); } catch (e) { return { configured: false, ok: false, message: e.message }; }
}

// pickOpportunity(onPick): onPick receives the opportunity as it maps onto a project ({fields, inferred, reference, notes, crm, labels}).
export function pickOpportunity(onPick) {
  const q = h('input', { type: 'text', placeholder: 'Search by opportunity or client name' });
  const st = select(STATUSES, 'Won');
  const list = h('div', { class: 'small', style: { maxHeight: '55vh', overflow: 'auto' } });
  const m = modal({ title: 'Pick a CRM opportunity', size: 'wide', body: h('div', { class: 'grid' }, h('div', { class: 'grid g2' }, q, st), list),
    actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} }] });
  let timer = null;
  async function load() {
    list.replaceChildren(h('div', { class: 'muted' }, 'Loading...'));
    try {
      const rows = await api.get(`/api/crm/opportunities?q=${encodeURIComponent(q.value)}&status=${encodeURIComponent(st.value)}`);
      list.replaceChildren(...(rows.length ? rows.map((r) => h('div', { class: 'lk-opt', style: { display: 'flex', gap: '10px', justifyContent: 'space-between', cursor: 'pointer', padding: '6px 4px', borderBottom: '1px solid #e0e6e8' },
        onclick: async () => {
          try { const d = await api.get(`/api/crm/opportunities/${r.id}`); d.existing = r.project || null; m.close(); onPick(d); } catch (e) { toast(e.message, 'bad'); }
        } },
        h('span', {}, h('b', {}, r.name || '(no name)'), h('span', { class: 'muted' }, `  ${r.client || ''}`)),
        h('span', { class: 'muted' }, [r.status, r.value ? '$' + Math.round(r.value).toLocaleString('en-AU') : '', r.project ? 'has project: ' + r.project : ''].filter(Boolean).join('  |  ')))) : [h('div', { class: 'muted' }, 'No opportunities match.')]));
    } catch (e) { list.replaceChildren(h('div', { class: 'bad' }, e.message)); }
  }
  q.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(load, 250); });
  st.onchange = load;
  load();
}
