import { h, clear, fmt, select, table, empty, debounce, badge } from '../ui.js';
import { api, state, p } from '../api.js';
import { when, who, changeList, opBadge, historyDialog } from '../history.js';

// Everything anyone changed on this project, newest first.
export default async function activityView(root, params) {
  const f = { user: params.user || '', tbl: params.tbl || '', q: '' };
  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, 'Activity and history'),
    h('div', { class: 'sub' }, 'Who changed what and when, for everyone working on this project. Automatic changes (for example an accrual reversed because its invoice landed) say so.'))));
  const bar = h('div', { class: 'row card', style: { padding: '10px 14px', marginBottom: '12px' } });
  const out = h('div');
  root.append(bar, out);
  let first = true;
  async function load() {
    const q = new URLSearchParams({ limit: '400' });
    if (f.user) q.set('user', f.user); if (f.tbl) q.set('tbl', f.tbl); if (f.q) q.set('q', f.q);
    const d = await api.get(p('/activity?' + q));
    if (first) {
      first = false;
      const us = select([['', 'Everyone'], ...d.people.map((x) => [x.upn, x.name + (x.role ? ` (${x.role})` : '')])], f.user, { onchange: (e) => { f.user = e.target.value; load(); } });
      const ts = select([['', 'All records'], ...['accrual', 'forecast_item', 'forecast_day', 'forecast_ms', 'cbs_node', 'allowance_ledger', 'variation', 'risk', 'subcontract', 'sub_claim', 'claim', 'import_batch', 'supplier_rate', 'resource', 'project'].map((t) => [t, d.tables[t] || t])], f.tbl, { onchange: (e) => { f.tbl = e.target.value; load(); } });
      const s = h('input', { type: 'search', placeholder: 'Search text, amounts, names...', style: { width: '260px' }, oninput: debounce(() => { f.q = s.value.trim(); load(); }, 250) });
      bar.append(h('span', { class: 'small muted' }, 'Who'), us, h('span', { class: 'small muted' }, 'What'), ts, s);
    }
    const hist = (r) => r.row_id && r.exists ? h('button', { class: 'btn ghost sm', onclick: () => historyDialog(r.tbl, r.row_id, r.what) }, 'History') : '';
    clear(out).append(d.rows.length ? table([{ label: 'When', f: (r) => h('span', { class: 'nowrap' }, when(r.at)) }, { label: 'Who', f: who }, { label: '', f: opBadge },
      { label: 'Record', cls: 'wrap', f: (r) => h('span', {}, r.what, r.remote ? h('span', { class: 'muted small', title: 'Received from a colleague through the shared folder' }, ' ⇄') : null) },
      { label: 'What changed', cls: 'wrap', f: changeList }, { label: '', f: hist }], d.rows, { maxHeight: '72vh' })
      : empty('Nothing recorded yet', 'Changes are recorded from this version of PMT onwards.'));
  }
  await load();
}
