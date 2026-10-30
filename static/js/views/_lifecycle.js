import { h, modal, field, toast, confirmBox } from '../ui.js';
import { api, state } from '../api.js';
import { render } from '../app.js';

// EPEC's Project Lifecycle Management phases, as the PMO graphic shows them (wording from that graphic).
export const LIFECYCLE = [
  { key: 'Handover', color: '#e56210', text: 'The Handover phase outlines the process for the formal handover of the project from the Proposal Team to the Project Delivery Team when the contract has been won.', out: 'Gate 5: Handover to Delivery.' },
  { key: 'Setup', color: '#ffb500', text: 'The Setup phase outlines the process for setting up a project in accordance with EPEC\'s Project Lifecycle Management, after it has been through the Handover phase and Gate 5 is complete.', out: 'Gate 6: Approval to Deliver Project.' },
  { key: 'Delivery', color: '#102361', text: 'The Delivery phase outlines the process for delivering a project in accordance with EPEC\'s Project Lifecycle Management, after it has been through the Setup phase and Gate 6 is complete.', out: 'Ready to Close Out Project Review.' },
  { key: 'Close Out', color: '#4195f2', text: 'The Close Out phase outlines the process for closing out a project in accordance with EPEC\'s Project Lifecycle Management, after it has been practically completed and the Ready to Close Out Project Review has been conducted.', out: 'Gate 7: Approval of Project Practical Completion.' },
  { key: 'Warranty', color: '#335062', text: 'The Warranty phase outlines the process for seeing the project through its Defect Liability Period (DLP) in accordance with EPEC\'s Project Lifecycle Management, after it has been through the Close Out phase and Gate 7 is complete.', out: null },
];

// Where a project stands in that lifecycle, from its latest gate and its delivery phase: Gate 7 done = Warranty; delivery phase
// Close Out = Close Out; Gate 6 = Delivery; Gate 5 = Setup; otherwise Handover.
export function lifecycleStage(gate, phase) {
  if (gate >= 7) return 'Warranty';
  if (phase === 'Close Out') return 'Close Out';
  if (gate >= 6) return 'Delivery';
  if (gate >= 5) return 'Setup';
  return 'Handover';
}

// What the PM has recorded on the tiles wins over the stage worked out from the gates and phase. The delivery stages (Design, Procure,
// Construct, Commission) are sub-phases of the Delivery stage: recording one puts the project in Delivery as well.
export function stageFor(gate, phase, rec) { return rec?.stage || lifecycleStage(gate, phase); }
const dd = (d) => (d ? `${d.slice(8, 10)}/${d.slice(5, 7)}/${d.slice(0, 4)}` : '');
export const span = (r) => (r ? `${dd(r.date)} to ${r.end_date ? dd(r.end_date) : 'now'}` : '');
const today = () => new Date().toISOString().slice(0, 10);

// One window for both rows of tiles: start, end (when it is over) and a note. The stage that is current is edited; any other stage is
// started from the date you give, which also ends the stage before it.
export function recordDialog({ kind, key, rows, current, alsoStage }) {
  const isStage = kind === 'stage'; const field_ = isStage ? 'stage' : 'phase'; const base = `/api/p/${state.pid}/${isStage ? 'lifecycle-log' : 'phases'}`;
  const cur = current && current[field_] === key ? rows.filter((r) => r[field_] === key).sort((a, b) => (a.date + a.id).localeCompare(b.date + b.id)).pop() : null;
  const start = h('input', { type: 'date', value: cur ? cur.date : today() }); const end = h('input', { type: 'date', value: cur?.end_date || '' }); const note = h('input', { type: 'text', value: cur?.note || '', placeholder: 'Optional note', style: { width: '100%' } });
  const body = () => ({ [field_]: key, date: start.value, end_date: end.value || null, note: note.value });
  modal({ title: `${isStage ? 'Lifecycle stage' : 'Delivery stage'}: ${key}`, body: h('div', { class: 'grid' },
    h('div', { class: 'note' }, cur ? `${key} is the current ${isStage ? 'stage' : 'delivery stage'}. Change when it started, add the date it ended, or edit the note.`
      : `Moving the project to ${key} ends ${current ? current[field_] : 'the earlier stage'} on the start date you give.${isStage && key !== 'Delivery' ? ' Any open Delivery sub-phase ends then too.' : ''}${!isStage && alsoStage ? ' Design, Procure, Construct and Commission are part of the Delivery stage, so the project is recorded in Delivery from the same date (it cannot be in Setup and Commissioning at once).' : ''}`),
    h('div', { class: 'grid g2' }, field('Start', start), field('End (when it is over)', end)), field('Note', note)),
    actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} }, { label: 'Save', onClick: async () => {
      if (!start.value) throw new Error('Enter the start date');
      if (cur) await api.put(`${base}/${cur.id}`, body()); else await api.post(base, body());
      toast(`${key} recorded`); await render();
    } }] });
}

// notes: {stage: latest record}; pick(key) opens the window
export function lifecycleStrip(current, pick = null, recs = {}) {
  const idx = LIFECYCLE.findIndex((x) => x.key === current);
  return h('div', { class: 'lcs' + (pick ? ' pickable' : '') }, LIFECYCLE.map((x, i) => h('div', { class: 'lcs-col' + (x.key === current ? ' on' : '') + (idx >= 0 && i < idx ? ' done' : ''), title: pick ? `Click to record ${x.key}: start, end and note` : '', onclick: pick ? () => pick(x.key) : null },
    h('div', { class: 'lcs-head', style: { background: x.color } }, h('span', {}, x.key)),
    h('div', { class: 'lcs-card', style: x.key === current ? { borderColor: x.color } : {} },
      x.key === current ? h('div', { class: 'lcs-here', style: { background: x.color } }, 'This project is here') : null,
      recs[x.key] ? h('div', { class: 'small', style: { color: x.color === '#ffb500' ? '#8a6200' : x.color, fontWeight: 700, marginBottom: '6px' } }, span(recs[x.key])) : null,
      recs[x.key]?.note ? h('div', { class: 'small muted', style: { marginBottom: '6px' } }, recs[x.key].note) : null,
      h('p', {}, x.text), x.out ? h('p', {}, 'The key output from this phase is ', h('b', {}, x.out)) : h('p', { class: 'muted' }, 'The project is seen through its Defect Liability Period.')))));
}

// The Delivery stage's four sub-phases (PMO graphic): Design, Procure, Construct, Commission.
const DELIVERY = [['Design', '#102361'], ['Procure', '#e56210'], ['Construct', '#ffb500'], ['Commission', '#4195f2']];
export function deliveryStrip(current, notes = {}, pick = null, recs = {}, inDelivery = true) {
  return h('div', { class: 'dls' + (pick ? ' pickable' : '') + (inDelivery ? '' : ' off') }, DELIVERY.map(([k, color], i) => h('div', { class: 'dls-col' + (k === current && inDelivery ? ' on' : (current ? ' dim' : '')), title: pick ? `Click to record ${k}: start, end and note` : '', onclick: pick ? () => pick(k) : null },
    h('div', { class: 'dls-seg' + (i === DELIVERY.length - 1 ? ' last' : ''), style: { background: color, color: color === '#ffb500' ? '#102361' : '#fff' } }, k),
    h('div', { class: 'dls-dot', style: { borderColor: color } }, k === current && inDelivery ? h('span', { style: { background: color } }) : null),
    recs[k] ? h('div', { class: 'small dls-note', style: { fontWeight: 700 } }, span(recs[k])) : null,
    notes[k] ? h('div', { class: 'small muted dls-note' }, notes[k]) : null)));
}

// Library documents tagged for this gate or phase, shown under the gate and phase cards.
export function relatedDocs(title, docs, emptyText) {
  return h('div', { class: 'card', style: { marginTop: '14px' } }, h('h2', {}, title),
    docs.length ? h('ul', {}, docs.map((x) => h('li', {}, h('a', { href: x.url, target: '_blank' }, x.title), x.description ? h('span', { class: 'muted small', style: { marginLeft: '8px' } }, x.description) : null)))
      : h('div', { class: 'small muted' }, emptyText));
}
