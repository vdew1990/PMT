import { h, toast, badge, empty } from '../ui.js';
import { api } from '../api.js';
import { render } from '../app.js';

// CONTROL > My profile: your own employee record as you may see it. Some of it is only for HR and your project director (not shown), some you can read
// but not change, and some you can change yourself (your phone, your home base). Which is which is set in app/objects.py and is a first proposal for the
// role-based design session. It is a view, not a lock: PMT has no sign-in.
const ACC = { edit: ['You can change this', 'good'], view: ['View only', ''], unavailable: ['Not held yet', 'warn'] };

export default async function myProfile(root) {
  const r = await api.get('/api/me/record');
  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, 'My profile'), h('div', { class: 'sub' }, 'Your own record in PMT: what you can see, and what you can change.'))));
  if (!r.found) { root.append(empty('No employee record', r.message)); return; }
  const inputs = {};
  const rows = r.fields.map((f) => h('tr', {}, h('td', {}, h('b', {}, f.label), f.note ? h('div', { class: 'small muted' }, f.note) : null),
    h('td', {}, f.access === 'edit' ? (inputs[f.key] = h('input', { type: 'text', value: f.value ?? '', style: { width: '100%' } })) : (f.value ?? h('span', { class: 'muted' }, ''))), h('td', {}, badge(ACC[f.access][0], ACC[f.access][1]))));
  root.append(h('div', { class: 'card' }, h('div', { class: 'ch' }, h('h2', {}, r.name)),
    h('div', { class: 'tw' }, h('table', { class: 't nogroup notools' }, h('thead', {}, h('tr', {}, ['Information', 'Value', 'Who changes it'].map((x) => h('th', {}, x)))), h('tbody', {}, rows))),
    h('div', { class: 'row', style: { marginTop: '10px', gap: '10px' } }, h('button', { class: 'btn', onclick: async () => {
      const body = Object.fromEntries(Object.entries(inputs).filter(([k]) => r.fields.find((f) => f.key === k).access === 'edit').map(([k, el]) => [k, el.value]));
      try { await api.put('/api/me/record', body); toast('Saved'); render(); } catch (e) { toast(e.message, 'bad'); }
    } }, 'Save my changes'), h('span', { class: 'small muted' }, r.note + ` (${r.hidden} items.)`))));
}
