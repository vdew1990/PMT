import { h } from '../ui.js';
import { state } from '../api.js';
import { gateCard } from './_assess.js';
import { api } from '../api.js';
import { relatedDocs } from './_lifecycle.js';

// PMO > Project gate: the gate record and papers for the open project (moved from Project setup).
export default async function gates(root) {
  const pr = state.project;
  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, 'Project gate'), h('div', { class: 'sub' }, `${pr.name}: record the gate approvals and download each gate's paper.`))));
  root.append(await gateCard({ id: state.pid, name: pr.name }));
  const rel = await api.get(`/api/p/${state.pid}/lifecycle/documents`);
  root.append(relatedDocs('Related documents', rel.docs.filter((d) => d.gate !== null && d.gate !== undefined), 'No library documents are tagged for the project\'s current and next gate yet. Tag them in the Project library.'));
}
