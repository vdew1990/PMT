import { h, toast, badge } from '../ui.js';
import { api, p } from '../api.js';
import { go } from '../app.js';
import { closeoutTab } from './risk.js';

// CLOSE-OUT > Close-out checklist: what has to be true before the project is archived, then what it learnt for the next estimate.
// Items that PMT can read (claims, retention, subcontracts, variations, accruals, gate) show where they stand; the rest are ticked by hand.
const MARK = { done: ['✓', 'good'], todo: ['!', 'bad'], warn: ['!', 'warn'], info: ['i', 'muted'] };
export default async function closeout(root) {
  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, 'Close-out checklist'),
    h('div', { class: 'sub' }, 'What has to be settled before the project is archived. PMT reads the claims, retention, subcontracts, variations and accruals; the rest you tick when it is done. Below: what the project learnt for the next estimate.'))));
  const list = h('div', { class: 'card', style: { marginBottom: '16px' } }); root.append(list);
  const draw = (d) => {
    list.replaceChildren(...d.items.map((x, i) => h('div', { class: 'row', style: { gap: '12px', padding: '9px 0', borderBottom: i < d.items.length - 1 ? '1px solid var(--hair)' : '0' } },
      x.manual ? h('input', { type: 'checkbox', checked: x.state === 'done', style: { width: 'auto' }, title: 'Tick when done', onchange: async (e) => { draw(await api.post(p('/close-out/tick'), { key: x.key, done: e.target.checked })); } })
        : h('span', { class: MARK[x.state][1], style: { width: '16px', fontWeight: 700, textAlign: 'center' } }, MARK[x.state][0]),
      h('div', { style: { flex: 1 } }, h('b', {}, x.title), h('div', { class: 'small muted' }, x.detail)),
      x.page ? h('button', { class: 'btn ghost sm', onclick: () => go(x.page, x.params) }, 'Open') : null)));
  };
  draw(await api.get(p('/close-out')));
  root.append(h('h2', { style: { margin: '6px 0 8px' } }, 'Lessons for the estimator'));
  const body = h('div'); root.append(body);
  await closeoutTab(body);
}
