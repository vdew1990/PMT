import { h } from '../ui.js';
import { state } from '../api.js';
import { phaseCard } from './_assess.js';
import { api } from '../api.js';
import { deliveryStrip, recordDialog, stageFor, lifecycleStrip, relatedDocs } from './_lifecycle.js';

// PMO > Project phase: the delivery phase and its readiness reviews for the open project (moved from Project setup).
export default async function phases(root) {
  const pr = state.project;
  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, 'Project phase'), h('div', { class: 'sub' }, `${pr.name}: the delivery phase, its reminders and readiness reviews.`))));
  const [g, ph, sl] = await Promise.all([api.get(`/api/p/${state.pid}/gates`), api.get(`/api/p/${state.pid}/phases`), api.get(`/api/p/${state.pid}/lifecycle-log`)]);
  const stage = stageFor(g.current?.gate ?? 0, ph.current?.phase, sl.current);
  const latest = (rows, k, f) => Object.fromEntries(rows.slice().sort((a, b) => (a.date + a.id).localeCompare(b.date + b.id)).map((r) => [r[f], r]));
  const stageRecs = latest(sl.rows, null, 'stage'); const phaseRecs = latest(ph.rows, null, 'phase');
  root.append(lifecycleStrip(stage, (k) => recordDialog({ kind: 'stage', key: k, rows: sl.rows, current: sl.current }), stageRecs));
  root.append(h('h3', { style: { margin: '4px 0' } }, 'Delivery phase', h('span', { class: 'small muted', style: { marginLeft: '8px', fontWeight: 400 } }, 'the sub-phases of the Delivery stage')),
    deliveryStrip(ph.current && !ph.current.end_date ? ph.current.phase : null, Object.fromEntries(ph.phases.map((x) => [x.phase, x.reviews.map((r) => r.name).join('; ')])), (k) => recordDialog({ kind: 'phase', key: k, rows: ph.rows, current: ph.current, alsoStage: stage !== 'Delivery' }), phaseRecs, stage === 'Delivery'));
  const rel = await api.get(`/api/p/${state.pid}/lifecycle/documents`);
  root.append(await phaseCard({ id: state.pid, name: pr.name }));
  root.append(relatedDocs('Related documents', rel.docs.filter((d) => d.phase), 'No library documents are tagged for the current phase yet. Tag them in the Project library.'));
}
