import { h, clear, fmt, modal, toast, field, select, table, confirmBox, badge, empty } from '../ui.js';
import { api } from '../api.js';
import { render } from '../app.js';

// PMO > Project library: all knowledge material (checklists, procedures, forms) in one place.
// Project lifecycle brings up the documents tagged for a project's current phase and gate.
export default async function pmolibrary(root) {
  const k = await api.get('/api/kb');
  const ui = { q: '', type: '', phase: '' };
  const opt = (list) => [['', 'Any'], ...list.map((x) => [x, x])];
  const out = h('div');
  const gateName = (g) => (k.gates.find((x) => x.gate === g)?.label || `Gate ${g}`);
  const size = (n) => (n > 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);

  function edit(d = null) {
    const f = h('input', { type: 'file' });
    const title = h('input', { type: 'text', value: d?.title || '' });
    const type = select(k.types, d?.doc_type || 'Checklist'); const phase = select([['', 'Not tied to a phase'], ...k.phases.map((x) => [x, x])], d?.phase || '');
    const gate = select([['', 'Not tied to a gate'], ...k.gates.map((g) => [g.gate, g.label])], d?.gate ?? '');
    const ptype = select([['', 'All project types'], ...k.project_types.map((x) => [x, x])], d?.project_type || '');
    const desc = h('input', { type: 'text', value: d?.description || '', placeholder: 'What it is for, when to use it' });
    modal({ title: d ? 'Edit document details' : 'Add a document to the library', body: h('div', { class: 'grid g2' },
      d ? null : h('div', { style: { gridColumn: '1 / -1' } }, field('File', f, 'Word, Excel, PDF or any file up to 15 MB')),
      h('div', { style: { gridColumn: '1 / -1' } }, field('Title', title)), field('Type', type), field('Delivery phase', phase, 'Shown on Project lifecycle while a project is in this phase'), field('Gate', gate, 'Shown while a project is at or next to this gate'), field('Project type', ptype, 'Leave on All project types unless the document only applies to one kind of project'),
      h('div', { style: { gridColumn: '1 / -1' } }, field('Description', desc))),
    actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} }, { label: 'Save', onClick: async () => {
      const b = { title: title.value, doc_type: type.value, phase: phase.value, gate: gate.value, project_type: ptype.value, description: desc.value };
      if (d) await api.put(`/api/kb/${d.id.split(':')[1]}`, b);
      else { if (!f.files[0]) throw new Error('Choose a file'); await api.upload('/api/kb', f.files[0], b); }
      toast('Saved'); await render();
    } }] });
  }

  function draw() {
    const rows = k.docs.filter((d) => (!ui.type || d.doc_type === ui.type) && (!ui.phase || d.phase === ui.phase) && (!ui.q || `${d.title} ${d.description || ''} ${d.filename}`.toLowerCase().includes(ui.q)));
    clear(out).append(rows.length ? table([
      { label: 'Document', f: (d) => h('div', {}, h('b', {}, d.title), d.description ? h('div', { class: 'small muted' }, d.description) : null) },
      { label: 'Type', f: (d) => d.doc_type || '' }, { label: 'Phase', f: (d) => d.phase || '' }, { label: 'Project type', f: (d) => d.project_type || 'All' }, { label: 'Gate', f: (d) => (d.gate ? gateName(d.gate) : '') },
      { label: 'File', f: (d) => h('span', { class: 'small' }, d.filename, ' · ', size(d.size)) },
      { label: 'Source', f: (d) => (d.builtin ? badge('EPEC form', 'navy') : h('span', { class: 'small muted' }, `${d.uploaded_by || ''} ${d.uploaded_at ? fmt.date(d.uploaded_at.slice(0, 10)) : ''}`)) },
      { label: '', f: (d) => h('span', { class: 'row', style: { gap: '4px' } }, h('a', { class: 'btn ghost sm', href: d.url, target: '_blank' }, 'Download'),
        d.builtin ? null : h('button', { class: 'btn ghost sm', onclick: () => edit(d) }, 'Edit'),
        d.builtin ? null : h('button', { class: 'btn danger sm', onclick: async () => { if (await confirmBox(`Delete "${d.title}" from the library?`, 'Delete', true)) { await api.del(`/api/kb/${d.id.split(':')[1]}`); await render(); } } }, 'Delete')) },
    ], rows) : empty('No documents match', 'Add a document, or clear the filters.'));
  }
  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, 'Project library'), h('div', { class: 'sub' }, 'All knowledge material in one place: checklists, procedures, forms and guides. Project lifecycle shows the ones that matter for where a project is.')), h('div', { class: 'sp' }),
    h('a', { class: 'btn ghost', href: '/api/kb/download-all', title: 'One zip with every document in the library and the blank Project setup templates (full and per step)' }, 'Download all documents and setup templates'),
    h('button', { class: 'btn', onclick: () => edit() }, 'Add a document')));
  const q = h('input', { type: 'search', placeholder: 'Search documents...', style: { width: '260px' }, oninput: (e) => { ui.q = e.target.value.toLowerCase(); draw(); } });
  root.append(h('div', { class: 'card', style: { padding: '10px 14px', marginBottom: '12px' } }, h('div', { class: 'row', style: { gap: '10px' } }, q,
    h('label', { class: 'row small' }, 'Type ', select(opt(k.types), '', { onchange: (e) => { ui.type = e.target.value; draw(); } })), h('label', { class: 'row small' }, 'Phase ', select(opt(k.phases), '', { onchange: (e) => { ui.phase = e.target.value; draw(); } })))), out);
  draw();
}
