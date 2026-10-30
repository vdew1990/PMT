import { h, fmt, toast, confirmBox, empty } from '../ui.js';
import { api, p } from '../api.js';
import { go, render } from '../app.js';

// MONTH-END > Month-end: the monthly routine in order, each step read from the project's own data, with a link to the page that does it.
const MARK = { done: ['✓', 'good'], todo: ['!', 'bad'], warn: ['!', 'warn'], info: ['i', 'muted'] };
export default async function monthend(root) {
  const d = await api.get(p('/month-end'));
  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, `Month-end ${fmt.month(d.month)}`),
    h('div', { class: 'sub' }, 'The monthly routine in order: load Pronto, check accruals, review each line, close the month, send the reports. Each step opens the page that does it and shows where it stands.'))));
  if (!d.initialised) { root.append(empty('Not initialised yet', 'Month-end starts once cost control is initialised (Project setup, Initialise).')); return; }
  const left = d.items.filter((x) => x.state === 'todo' || x.state === 'warn').length;
  root.append(h('div', { class: 'note' + (left ? '' : ' good'), style: { marginBottom: '12px' } }, left ? `${left} of ${d.items.length} steps need a look before ${fmt.month(d.month)} is closed.` : 'Every step is in order.'));
  root.append(h('div', { class: 'card' }, d.items.map((x, i) => h('div', { class: 'row', style: { gap: '12px', padding: '10px 0', borderBottom: i < d.items.length - 1 ? '1px solid var(--hair)' : '0' } },
    h('span', { class: MARK[x.state][1], style: { width: '22px', fontWeight: 700, textAlign: 'center' } }, MARK[x.state][0]),
    h('div', { style: { flex: 1 } }, h('b', {}, `${i + 1}. ${x.title}`), h('div', { class: 'small muted' }, x.detail)),
    x.action === 'close' ? h('button', { class: 'btn', onclick: () => close(d) }, x.state === 'done' ? 'Close again' : 'Close month') : null,
    x.page ? h('button', { class: 'btn ghost', onclick: () => go(x.page, x.params) }, 'Open') : null))));
}

async function close(d) {
  const open = d.items.filter((x) => x.key !== 'close' && x.key !== 'reports' && (x.state === 'todo' || x.state === 'warn'));
  const warn = open.length ? ` Still open: ${open.map((x) => x.title.toLowerCase()).join('; ')}.` : '';
  if (!(await confirmBox(`Close ${fmt.month(d.month)}? This stores the current position as the month-end snapshot (replacing one for the same month).${warn}`, open.length ? 'Close anyway' : 'Close month'))) return;
  await api.post(p('/snapshots'), {}); toast('Snapshot stored'); render();
}
