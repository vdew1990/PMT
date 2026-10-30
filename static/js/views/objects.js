import { h, badge, tabs } from '../ui.js';
import { api } from '../api.js';

// CONTROL > Data objects: the objects PMT holds (EPEC employee, client or subcontractor person, client, subcontractor / supplier, project) and the properties of each:
// where it is kept, how sensitive it is, and whether it is held yet. Read only: it is the agreed data model (app/objects.py).
const SENS = { open: ['Open', 'good'], internal: ['EPEC staff', ''], personal: ['Personal', 'warn'], restricted: ['Restricted', 'bad'] };
const STAT = { live: ['Held', 'good'], derived: ['Worked out', ''], planned: ['Planned', 'warn'], deferred: ['Waiting for access design', 'bad'], missing: ['Missing', 'bad'] };
let tab = 'employee';

export default async function objects(root) {
  const d = await api.get('/api/objects');
  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, 'Data objects'),
    h('div', { class: 'sub' }, 'People, organisations and projects as objects with properties. ' + d.note))));
  const body = h('div');
  const draw = () => {
    const t = d.types.find((x) => x.key === tab) || d.types[0];
    body.replaceChildren(h('div', { class: 'card' }, h('div', { class: 'ch' }, h('h2', {}, t.name), h('span', { class: 'sp' }), h('span', { class: 'small muted' }, `${t.properties.length} properties`)),
      h('div', { class: 'tw' }, h('table', { class: 't nogroup notools' }, h('thead', {}, h('tr', {}, ['Property', 'Type', 'Held in', 'Who may see it', 'Status', 'Note'].map((x) => h('th', {}, x)))),
        h('tbody', {}, t.properties.map((p) => h('tr', {}, h('td', {}, h('b', {}, p.label)), h('td', { class: 'small' }, p.type), h('td', { class: 'small mono' }, p.where), h('td', {}, badge(SENS[p.sensitivity][0], SENS[p.sensitivity][1])),
          h('td', {}, badge(STAT[p.status][0], STAT[p.status][1])), h('td', { class: 'small wrap' }, p.note || '')))))),
      h('div', { class: 'small muted', style: { marginTop: '8px' } }, Object.entries(d.sensitivity).map(([k, v]) => `${SENS[k][0]}: ${v}`).join('. ') + '.')));
  };
  root.append(tabs(d.types.map((t) => [t.key, t.name]), tab, (k) => { tab = k; draw(); root.querySelector('.tabs')?.querySelectorAll('button').forEach((b, i) => b.classList.toggle('on', d.types[i].key === k)); }), body);
  draw();
}
