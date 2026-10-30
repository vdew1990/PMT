import { h, clear, fmt, modal, toast, field, select, tone, empty, confirmBox, lookup } from '../ui.js';
import { api, state, p, loadProjects } from '../api.js';
import { openIn, boot } from '../app.js';
import { rollupTree, projectChart } from '../rollup.js';

// SETUP > Linked projects. Levels: child project (a PM runs it) -> parent project (its children together) -> portfolio
// (a PM's projects) -> program (a project director's projects for their clients, and their team of PMs). Linking two
// or more projects creates a parent project that lumps their CBS together code by code (app/linking.py). The parent is
// read-only; every figure drills down to the child project's own line.
export default async function linked(root) {
  const d = await api.get(p('/linked'));
  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, 'Linked projects'),
    h('div', { class: 'sub' }, 'Child project → parent project → portfolio (a PM\'s projects) → program (a project director\'s). A parent project lumps the CBS of its child projects together for a high-level view; each PM keeps working in their own project.'))));

  if (d.is_parent) return parentView(root, d);

  // a child: its parent and the other children
  if (d.parent) {
    const box = h('div');
    root.append(h('div', { class: 'card', style: { marginBottom: '14px' } }, h('h2', {}, 'Project chart'), box));
    projectChart(box, { id: d.parent.id, kind: 'parent', name: d.parent.name, sub: d.parent.director ? `Director ${d.parent.director}` : '',
      children: d.children.map((c) => ({ id: c.id, kind: 'child', name: c.name, sub: c.pm ? `PM ${c.pm}` : '' })) }, { current: state.pid });
    root.append(h('div', { class: 'card', style: { marginBottom: '14px' } },
      h('div', { class: 'ch' }, h('h2', {}, `Linked under ${d.parent.name}`), h('span', { class: 'sp' }),
        h('button', { class: 'btn', onclick: () => openIn(d.parent.id, 'linked') }, 'Open the parent project'),
        h('button', { class: 'btn ghost', onclick: async () => {
          if (!(await confirmBox(`Take ${d.project.name} out of ${d.parent.name}? Its own data is untouched; the parent's figures will no longer include it.`, 'Unlink'))) return;
          await api.post(`/api/projects/${state.pid}/unlink`); toast('Unlinked'); await boot();
        } }, 'Unlink this project')),
      h('p', { class: 'small muted', style: { marginTop: 0 } }, 'Projects in this parent:'),
      h('ul', {}, d.children.map((c) => h('li', {}, c.id === state.pid ? h('b', {}, c.name + ' (this project)') : h('a', { onclick: () => openIn(c.id, 'dashboard') }, c.name), c.pm ? h('span', { class: 'muted small' }, ` · PM ${c.pm}`) : null)))));
    return;
  }

  // a stand-alone project: link it with others
  root.append(linkCard(d));
}

function linkCard(d) {
  const picks = new Map();
  const name = h('input', { type: 'text', placeholder: 'e.g. Wandoan program (BESS + substation)' });
  const director = lookup('director', d.project.director || '', { placeholder: 'Pick or type the project director' });
  const intoSel = select([['', 'A new parent project'], ...d.parents.map((x) => [x.id, x.name])], '');
  const list = h('div', { class: 'grid', style: { gap: '4px' } }, [d.project, ...d.candidates].map((c) => {
    const cb = h('input', { type: 'checkbox', checked: c.id === state.pid });
    if (c.id === state.pid) picks.set(c.id, cb);
    else picks.set(c.id, cb);
    return h('label', { class: 'row small', style: { gap: '8px' } }, cb, h('b', {}, c.name), h('span', { class: 'muted' }, [c.client, c.pm && `PM ${c.pm}`, c.director && `director ${c.director}`].filter(Boolean).join(' · ')));
  }));
  const newBits = h('div', { class: 'grid g2' }, field('Parent project name', name), field('Project director', director, 'Directs the program the parent sits in'));
  intoSel.onchange = () => newBits.classList.toggle('hide', !!intoSel.value);
  return h('div', { class: 'card', style: { maxWidth: '900px' } },
    h('h2', {}, 'Link projects under a parent'),
    h('p', { class: 'small muted' }, 'Pick the projects to link. They keep their own data, PM and CBS. The parent adds their CBS together line by line (the same CBS code in two projects is one line in the parent) and shows the whole picture. Nothing in the parent can be edited: changes are made in the child projects.'),
    field('Link into', intoSel),
    newBits,
    h('div', { style: { margin: '10px 0' } }, h('div', { class: 'small', style: { fontWeight: 700, marginBottom: '4px' } }, 'Projects'), d.candidates.length ? list : empty('No other project to link', 'Only running projects not already under a parent can be linked.')),
    h('button', { class: 'btn', onclick: async () => {
      const ids = [...picks].filter(([, cb]) => cb.checked).map(([id]) => id);
      try {
        const r = await api.post('/api/links', intoSel.value ? { parent_id: +intoSel.value, ids } : { name: name.value, director: director.value, ids });
        await loadProjects(); toast('Linked: the parent project shows them together');
        openIn(r.id, 'linked');
      } catch (e) { toast(e.message, 'bad'); }
    } }, 'Link'));
}

async function parentView(root, d) {
  const t = d.total || {};
  const rev = d.children.reduce((a, c) => a + (c.revenue || 0), 0);
  const tile = (l, v, s, c = '', vc = '') => h('div', { class: 'kpi ' + c }, h('div', { class: 'l' }, l), h('div', { class: 'v ' + vc }, v), h('div', { class: 's' }, s));
  root.append(h('div', { class: 'grid g5', style: { marginBottom: '14px' } },
    tile('Child projects', String(d.children.length), d.children.map((c) => c.pm).filter(Boolean).join(', ') || 'no PMs named'),
    tile('Contract value', fmt.m(rev), 'recognised, all children', 't2'),
    tile('Allowance', fmt.m(t.allowance), `${fmt.m((t.ctd || 0) + (t.acc || 0))} spent`, 't3'),
    tile('Final cost (EAC)', fmt.m(t.eac), `CTC ${fmt.m(t.ctc)}`, 't4'),
    tile('Contingency', fmt.m(t.contingency), 'allowance less EAC', 't5', tone(t.contingency))));

  const chartBox = h('div');
  root.append(h('div', { class: 'card', style: { marginBottom: '14px' } }, h('div', { class: 'ch' }, h('h2', {}, 'Project chart'), h('span', { class: 'sp' }),
    h('span', { class: 'small muted' }, 'Click the parent or a child for its cost control')), chartBox));
  projectChart(chartBox, { id: d.project.id, kind: 'parent', name: d.project.name, sub: d.project.director ? `Director ${d.project.director}` : '', eac: t.eac, contingency: t.contingency,
    children: d.children.map((c) => ({ id: c.id, kind: 'child', name: c.name, sub: c.pm ? `PM ${c.pm}` : '', eac: c.eac, contingency: c.contingency })) }, { current: state.pid });
  const add = h('button', { class: 'btn ghost sm', onclick: () => addDialog(d) }, '+ Link another project');
  root.append(h('div', { class: 'card', style: { marginBottom: '14px' } },
    h('div', { class: 'ch' }, h('h2', {}, 'Child projects'), h('span', { class: 'sp' }), add),
    h('div', { class: 'tw' }, h('table', { class: 't' },
      h('thead', {}, h('tr', {}, ['Project', 'PM', 'Status month', 'Contract value', 'Allowance', 'CTD', 'Accruals', 'CTC', 'EAC', 'Contingency', ''].map((x, i) => h('th', { class: i >= 3 && i < 10 ? 'r' : '' }, x)))),
      h('tbody', {}, d.children.map((c) => h('tr', { class: 'click', title: 'Open this project', onclick: () => openIn(c.id, 'dashboard') },
        h('td', {}, h('b', {}, c.name), c.error ? h('div', { class: 'small bad' }, 'Could not be computed: ' + c.error) : null), h('td', {}, c.pm || ''), h('td', {}, fmt.month(c.status_month)),
        h('td', { class: 'r num' }, fmt.money(c.revenue)),
        ...['allowance', 'ctd', 'acc', 'ctc', 'eac'].map((k) => h('td', { class: 'r num' }, fmt.money(c[k]))),
        h('td', { class: 'r num ' + tone(c.contingency) }, fmt.money(c.contingency)),
        h('td', { class: 'nowrap' }, h('button', { class: 'btn ghost sm', onclick: async (e) => {
          e.stopPropagation();
          if (!(await confirmBox(`Take ${c.name} out of ${d.project.name}? Its own data is untouched.`, 'Unlink'))) return;
          await api.post(`/api/projects/${c.id}/unlink`); toast('Unlinked'); await boot();
        } }, 'Unlink'))))),
      h('tfoot', {}, h('tr', {}, h('td', {}, h('b', {}, 'Together')), h('td'), h('td'), h('td', { class: 'r num' }, h('b', {}, fmt.money(rev))),
        ...['allowance', 'ctd', 'acc', 'ctc', 'eac'].map((k) => h('td', { class: 'r num' }, h('b', {}, fmt.money(t[k])))),
        h('td', { class: 'r num ' + tone(t.contingency) }, h('b', {}, fmt.money(t.contingency))), h('td')))))));

  const box = h('div');
  root.append(h('div', { class: 'card' }, h('div', { class: 'ch' }, h('h2', {}, 'CBS of the child projects together'), h('span', { class: 'sp' }),
    h('a', { class: 'small', href: '#/costcontrol' }, 'Open in cost control (month grid, filters)')), box));
  const res = await api.get(p('/cost-control?months=0'));
  rollupTree(box, res);
}

function addDialog(d) {
  const picks = d.candidates.map((c) => [c, h('input', { type: 'checkbox' })]);
  modal({ title: `Link more projects into ${d.project.name}`, body: picks.length ? h('div', { class: 'grid', style: { gap: '4px' } }, picks.map(([c, cb]) => h('label', { class: 'row small', style: { gap: '8px' } }, cb, h('b', {}, c.name), h('span', { class: 'muted' }, [c.client, c.pm && `PM ${c.pm}`].filter(Boolean).join(' · ')))))
    : empty('No project to add', 'Only running projects not already under a parent can be linked.'),
  actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} }, { label: 'Link', onClick: async () => {
    const ids = picks.filter(([, cb]) => cb.checked).map(([c]) => c.id);
    if (!ids.length) return false;
    await api.post('/api/links', { parent_id: state.pid, ids }); toast('Linked'); await boot();
  } }] });
}
