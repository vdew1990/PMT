import { h, badge, fmt, empty } from '../ui.js';
import { api, state } from '../api.js';
import { go } from '../app.js';
import { deliveryStrip, recordDialog, stageFor, lifecycleStrip } from './_lifecycle.js';

// PMO > Project lifecycle: where the open project stands (gate, phase) and the library documents that matter now.
export default async function lifecycle(root) {
  const pid = state.pid;
  const [g, ph] = await Promise.all([api.get('/api/gates'), api.get('/api/phases')]);
  const mine = pid ? await Promise.all([api.get(`/api/p/${pid}/gates`), api.get(`/api/p/${pid}/phases`), api.get(`/api/p/${pid}/lifecycle/documents`), api.get(`/api/p/${pid}/lifecycle-log`)]) : null;
  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, 'Project lifecycle'), h('div', { class: 'sub' }, pid ? `${state.project.name}: where it stands, and the documents from the Project library that matter now.` : 'The gates a project passes through and the reviews in each delivery phase.'))));
  const stage = mine ? stageFor(mine[0].current?.gate ?? 0, mine[1].current?.phase, mine[3].current) : null;
  const by = (rows, f) => Object.fromEntries(rows.slice().sort((a, b) => (a.date + a.id).localeCompare(b.date + b.id)).map((r) => [r[f], r]));
  root.append(lifecycleStrip(stage, mine ? (k) => recordDialog({ kind: 'stage', key: k, rows: mine[3].rows, current: mine[3].current }) : null, mine ? by(mine[3].rows, 'stage') : {}));
  root.append(h('h3', { style: { margin: '4px 0' } }, 'Delivery phase', h('span', { class: 'small muted', style: { marginLeft: '8px', fontWeight: 400 } }, 'the sub-phases of the Delivery stage')),
    deliveryStrip(mine?.[1].current && !mine[1].current.end_date ? mine[1].current.phase : null, {}, mine ? (k) => recordDialog({ kind: 'phase', key: k, rows: mine[1].rows, current: mine[1].current, alsoStage: stage !== 'Delivery' }) : null, mine ? by(mine[1].rows, 'phase') : {}, stage === 'Delivery' || !stage));
  const tile = (label, value, sub, to) => h('div', { class: 'kpi click', style: { cursor: 'pointer' }, onclick: () => go(to) }, h('div', { class: 'l' }, label), h('div', { class: 'v', style: { fontSize: '18px' } }, value), h('div', { class: 's' }, sub));
  const gc = mine?.[0].current; const pc = mine?.[1].current;
  root.append(h('div', { class: 'grid g4', style: { marginBottom: '14px' } },
    tile('Project gate', gc ? gc.label : 'No gate recorded', gc ? `${fmt.date(gc.date)}. Open to record a gate or download its paper.` : 'Open to record a gate', 'gates'),
    tile('Project phase', pc ? pc.phase : 'No phase recorded', pc ? `Since ${fmt.date(pc.date)}. Open for its reminders and reviews.` : 'Open to record the delivery phase', 'phases'),
    tile('Project library', 'All documents', 'Checklists, procedures, forms and guides', 'pmolibrary')));
  if (mine) {
    const d = mine[2];
    root.append(h('div', { class: 'card', style: { marginBottom: '14px' } }, h('h2', {}, 'Documents for where this project is'),
      h('div', { class: 'small muted', style: { marginBottom: '8px' } }, `Tagged in the Project library for ${d.phase ? `the ${d.phase} phase` : 'no recorded phase'}${d.gates_wanted.length ? ` and ${d.gates_wanted.map((x) => 'Gate ' + x).join(', ')}` : ''}.`),
      d.docs.length ? h('ul', {}, d.docs.map((x) => h('li', {}, h('a', { href: x.url, target: '_blank' }, x.title), ' ', badge(x.doc_type || 'Other', 'navy'), x.description ? h('span', { class: 'muted small', style: { marginLeft: '6px' } }, x.description) : null)))
        : empty('Nothing tagged yet', 'Tag documents with a phase or gate in the Project library and they appear here.')));
  }
  root.append(h('div', { class: 'card', style: { marginBottom: '14px' } }, h('h2', {}, 'Gates'),
    ...g.stages.map((s) => h('div', { style: { margin: '8px 0' } }, h('b', {}, s), h('ul', {}, g.gates.filter((x) => x.phase === s).map((x) => h('li', {}, x.label, x.form ? h('span', { class: 'muted small', style: { marginLeft: '8px' } }, x.form) : null)))))));
  root.append(h('div', { class: 'card' }, h('h2', {}, 'Delivery phases'),
    ...ph.phases.map((x) => h('div', { style: { margin: '10px 0' } }, h('b', {}, x.phase), h('div', { class: 'small muted', style: { margin: '2px 0 4px' } }, x.remind),
      h('ul', {}, x.reviews.map((r) => h('li', {}, r.name, ' ', badge(r.status, r.status === 'Mandatory' ? 'warn' : ''), h('span', { class: 'muted small', style: { marginLeft: '6px' } }, r.when || ''))))))));
}
