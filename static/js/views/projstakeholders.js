import { h, modal, toast, field, select, table, confirmBox, badge, empty } from '../ui.js';
import { api, p } from '../api.js';
import { render } from '../app.js';

// COMMUNICATION > Stakeholders: the stakeholders of this one project. (OVERVIEW > Stakeholders is the company-wide directory.)
export default async function projstakeholders(root) {
  const d = await api.get(p('/stakeholders'));
  const lvl = [['', '(not set)'], ...d.levels.map((x) => [x, x])];
  const tone = (v) => (v === 'High' ? badge(v, 'bad') : v === 'Medium' ? badge(v, 'warn') : v ? badge(v) : '');
  function edit(r = {}) {
    const f = { name: h('input', { type: 'text', value: r.name || '' }), organisation: h('input', { type: 'text', value: r.organisation || '' }), role: h('input', { type: 'text', value: r.role || '' }),
      contact: h('input', { type: 'text', value: r.contact || '', placeholder: 'Email or phone' }), interest: select(lvl, r.interest || ''), influence: select(lvl, r.influence || ''), notes: h('input', { type: 'text', value: r.notes || '' }) };
    modal({ title: r.id ? 'Edit stakeholder' : 'Add a stakeholder', body: h('div', { class: 'grid g2' }, field('Name', f.name), field('Organisation', f.organisation), field('Role on this project', f.role), field('Contact', f.contact),
      field('Interest in the project', f.interest), field('Influence over the project', f.influence), h('div', { style: { gridColumn: '1 / -1' } }, field('Notes', f.notes))),
    actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} }, { label: 'Save', onClick: async () => {
      const b = { id: r.id, source: r.source }; Object.entries(f).forEach(([k, i]) => { b[k] = i.value; });
      await api.post(p('/stakeholders'), b); await render();
    } }] });
  }
  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, 'Stakeholders'), h('div', { class: 'sub' }, 'The people and organisations that matter to this project: client, network service provider, subcontractors, landowners, regulators. The company-wide directory of clients, employees and companies is under OVERVIEW > Stakeholders.')), h('div', { class: 'sp' }),
    h('button', { class: 'btn ghost', title: 'Add the parties on the Project org chart and the named project people that are not listed yet', onclick: async () => { const r = await api.post(p('/stakeholders/import'), {}); toast(`${r.added} added`); await render(); } }, 'Add from org chart and project team'),
    h('button', { class: 'btn', onclick: () => edit() }, 'Add a stakeholder')));
  root.append(d.rows.length ? table([
    { label: 'Name', f: (r) => h('b', {}, r.name) }, { label: 'Organisation', f: (r) => r.organisation || '' }, { label: 'Role', f: (r) => r.role || '' }, { label: 'Contact', f: (r) => r.contact || '' },
    { label: 'Interest', f: (r) => tone(r.interest) }, { label: 'Influence', f: (r) => tone(r.influence) }, { label: 'Notes', f: (r) => r.notes || '' },
    { label: '', f: (r) => h('span', { class: 'row', style: { gap: '4px' } }, h('button', { class: 'btn ghost sm', onclick: () => edit(r) }, 'Edit'),
      h('button', { class: 'btn danger sm', onclick: async () => { if (await confirmBox(`Remove ${r.name} from this project's stakeholders?`, 'Remove', true)) { await api.del(p(`/stakeholders/${r.id}`)); await render(); } } }, 'Remove')) },
  ], d.rows) : empty('No stakeholders yet', 'Add one, or use "Add from org chart and project team" to start from the parties already on the Project org chart.'));
}
