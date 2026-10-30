// Who changed what: a record's history dialog, shared by every page that shows records.
import { h, fmt, modal, table, badge, empty } from './ui.js';
import { api, p } from './api.js';

export const when = (iso) => {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(+d)) return iso;
  return `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}/${d.getFullYear()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
};

export const who = (r) => h('span', {}, h('b', {}, r.user || ''), r.role ? h('span', { class: 'muted small' }, ' · ' + r.role) : null,
  r.via ? h('div', { class: 'small muted' }, r.via) : null);

export const changeList = (r) => {
  if (r.n) return h('span', { class: 'muted' }, r.what);
  if (!r.changes || !r.changes.length) return h('span', { class: 'muted' }, r.op === 'I' ? 'created' : r.op === 'D' ? 'deleted' : '');
  return h('div', { class: 'chg' }, r.changes.map((c) => h('div', {}, h('span', { class: 'muted' }, c.field + ': '), h('s', { class: 'muted' }, c.old), ' → ', h('b', {}, c.new))));
};

export const opBadge = (r) => badge(r.action, { added: 'good', changed: 'warn', deleted: 'bad' }[r.action] || '');

export async function historyDialog(tbl, id, title) {
  const rows = await api.get(p(`/history?tbl=${tbl}&id=${id}`));
  modal({ title: title || 'History', size: 'wide', body: rows.length
    ? table([{ label: 'When', f: (r) => h('span', { class: 'nowrap' }, when(r.at)) }, { label: 'Who', f: who }, { label: '', f: opBadge }, { label: 'Record', cls: 'wrap', f: (r) => r.what }, { label: 'What changed', cls: 'wrap', f: changeList }], rows.slice().reverse(), { maxHeight: '60vh' })
    : empty('No history yet', 'Changes are recorded from this version of PMT onwards.'),
  actions: [{ label: 'Close', kind: 'ghost', onClick: () => {} }] });
}

// small "by Jane, 12/10/2026 09:14" stamp for tables
export const stamp = (name, at) => name ? h('span', { class: 'small nowrap', title: when(at) }, name, h('span', { class: 'muted' }, ' ' + when(at).slice(0, 10))) : '';
