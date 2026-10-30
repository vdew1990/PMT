import { h, clear, fmt, modal, toast, field, select, empty, badge, confirmBox } from '../ui.js';
import { api, state } from '../api.js';
import { projectResources, rates, supplierRates } from './resources.js';
import { clientCard } from './_clients.js';
import { bandBadge } from './_assess.js';
import { personCard, roleLevelText } from './_team.js';

// OVERVIEW > Stakeholders: the company database, shared by every project. Clients on their own; resources in
// two parts: employees (people, including the project managers and directors) and companies (suppliers,
// subcontractors, consultants). Fields that ask for a name look them up here and add what is typed (app/directory.py).
const KINDS = [['supplier', 'Suppliers'], ['subcontractor', 'Subcontractors'], ['consultant', 'Consultants']];

export default async function directory(root, params) {
  let tab = params.tab || sessionStorage.getItem('dirTab') || 'clients';
  let kind = '';
  let q = '';
  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, 'Stakeholders'),
    h('div', { class: 'sub' }, 'The company database, shared by every project: clients, and resources (employees; companies: suppliers, subcontractors, consultants). Fields that ask for a name pick from here, and a new name typed there is added here.'))));
  const bar = h('div', { class: 'card', style: { padding: '10px 14px', marginBottom: '12px' } });
  const body = h('div');
  root.append(bar, body);
  const search = h('input', { type: 'search', placeholder: 'Filter by name, trade, code...', style: { width: '260px' }, oninput: (e) => { q = e.target.value.trim().toLowerCase(); draw(); } });

  function drawBar() {
    const t = (k, l) => h('button', { class: 'btn sm ' + (tab === k ? '' : 'ghost'), onclick: () => { tab = k; kind = ''; try { sessionStorage.setItem('dirTab', k); } catch (e) { /* ignore */ } drawBar(); draw(); } }, l);
    clear(bar).append(h('div', { class: 'row' },
      h('span', { class: 'small muted', style: { fontWeight: 700 } }, 'CLIENTS'), t('clients', 'Clients'),
      h('span', { style: { width: '18px' } }),
      h('span', { class: 'small muted', style: { fontWeight: 700 } }, 'RESOURCES'), t('employees', 'Employees'), t('companies', 'Companies'),
      h('span', { style: { width: '18px' } }),
      h('span', { class: 'small muted', style: { fontWeight: 700 } }, 'RATES'), t('rates', 'Rate card'), t('srates', 'Supplier rates'),
      tab === 'companies' ? h('span', { class: 'row', style: { gap: '6px', marginLeft: '8px' } }, ...[['', 'All'], ...KINDS].map(([k, l]) =>
        h('span', { class: 'chip' + (kind === k ? ' on' : ''), onclick: () => { kind = k; drawBar(); draw(); } }, l))) : null,
      h('span', { class: 'sp', style: { flex: 1 } }), search));
  }

  const has = (...xs) => !q || xs.some((x) => String(x || '').toLowerCase().includes(q));

  async function draw() {
    clear(body);
    if (tab === 'clients') {
      const list = (await api.get('/api/clients')).filter((c) => has(c.name, c.sector, c.hq, c.contacts));
      body.append(h('div', { class: 'card' }, h('div', { class: 'ch' }, h('h2', {}, `Clients (${list.length})`), h('span', { class: 'sp' }),
        h('button', { class: 'btn sm', onclick: () => clientCard({ name: '' }, draw) }, '+ Add a client')),
      list.length ? h('div', { class: 'tw' }, h('table', { class: 't' },
        h('thead', {}, h('tr', {}, ['Client', 'Sector', 'Head office', 'Risk', 'Challenge', 'Projects', 'Running value', 'PMs'].map((x, i) => h('th', { class: i === 6 ? 'r' : '' }, x)))),
        h('tbody', {}, list.map((c) => h('tr', { class: 'click', title: 'Open the client card', onclick: () => clientCard(c, draw) },
          h('td', {}, h('b', {}, c.name), c.id ? null : h('div', { class: 'small muted' }, 'named on a project, no card yet')), h('td', {}, c.sector || ''), h('td', {}, c.hq || ''),
          h('td', {}, c.risk || ''), h('td', {}, bandBadge(c.challenge?.score, c.challenge?.band)), h('td', {}, String(c.projects || 0)),
          h('td', { class: 'r num' }, fmt.money(c.running_value)), h('td', { class: 'small' }, (c.pms || []).join(', '))))))) : empty('No clients', 'Add one, or type a new client on a project.')));
      return;
    }
    if (tab === 'rates' || tab === 'srates') {
      if (!state.pid) { body.append(empty('Open a project', 'Rates belong to a project: choose one at the top of the page.')); return; }
      await (tab === 'rates' ? rates : supplierRates)(body);
      return;
    }
    if (tab === 'employees') {
      const ppl = await api.get('/api/people');
      const dupBox = h('div'); body.append(dupBox); duplicatesCard(dupBox, draw);
      const list = ppl.filter((x) => has(x.name, x.role, x.function, x.employee_code, x.base));
      body.append(h('div', { class: 'card' }, h('div', { class: 'ch' }, h('h2', {}, `Employees (${list.length})`), h('span', { class: 'sp' }),
        h('span', { class: 'small muted', style: { marginRight: '10px' } }, 'Project managers and directors are employees too: their level and base drive Team workload'),
        h('button', { class: 'btn ghost sm', onclick: () => orgChartDialog(draw) }, 'Load the org chart...'),
        h('a', { class: 'small', style: { marginRight: '10px' }, href: '/api/people/template.xlsx', download: '' }, 'Blank people template'),
        h('button', { class: 'btn ghost sm', title: 'Fill the template with your people and levels; loading it here is not built yet', onclick: () => toast('Importing people is not built yet. Fill in the blank template and it can be loaded here once the layout is confirmed.') }, 'Import people'),
        h('button', { class: 'btn sm', onclick: () => personCard({ name: '', role: 'Employee', fte: 1 }, ppl, draw) }, '+ Add an employee')),
      list.length ? h('div', { class: 'tw' }, h('table', { class: 't' },
        h('thead', {}, h('tr', {}, ['Name', 'Role', 'Function / trade', 'Employee code', 'Classification', 'Status', 'PM level', 'Levels by role', 'Reports to', 'Base', 'Email'].map((x) => h('th', {}, x)))),
        h('tbody', {}, list.map((x) => h('tr', { class: 'click', onclick: () => personCard(x, ppl, draw) },
          h('td', {}, h('b', {}, x.name), x.id ? null : h('div', { class: 'small muted' }, 'named on a project, no card yet')), h('td', {}, x.role || ''), h('td', {}, x.function || ''),
          h('td', { class: 'mono' }, x.employee_code || ''), h('td', { class: 'small', title: x.ecf?.text || '' }, x.ecf ? [`${x.ecf.role} (L${x.ecf.level})`, x.ecf.title ? h('div', { class: x.ecf.title_ok ? 'muted' : 'warn' }, x.ecf.title + (x.ecf.title_ok ? '' : ' (not on the allowed list)')) : null] : ''), h('td', { class: 'small' }, [x.employment_status === 'serving notice' ? badge('Serving notice', 'warn') : x.employment_status === 'left' ? badge('Left', 'bad') : '', x.leaving_date ? h('div', { class: 'muted' }, 'until ' + fmt.date(x.leaving_date)) : null, x.engagement && x.engagement !== 'employee' ? h('div', { class: 'muted' }, x.engagement) : null]), h('td', {}, x.pm_level ? `Level ${x.pm_level}` : ''), h('td', { class: 'small' }, roleLevelText(x.role_levels)), h('td', {}, x.reports_to || ''), h('td', {}, x.base || ''), h('td', {}, x.email || '')))))) : empty('No employees', 'Add one, or they arrive with the Pronto labour data.')));
      if (state.pid) { const pr = h('div', { style: { marginTop: '14px' } }, h('h2', {}, 'On this project: Pronto codes, work rates and CBS lines')); body.append(pr); await projectResources(pr, 'employee'); }
      return;
    }
    const all = await api.get('/api/directory/companies' + (kind ? `?kind=${kind}` : ''));
    const list = all.filter((c) => has(c.name, c.trade, c.code, c.contacts, c.abn));
    const label = kind ? KINDS.find(([k]) => k === kind)[1] : 'Companies';
    body.append(h('div', { class: 'card' }, h('div', { class: 'ch' }, h('h2', {}, `${label} (${list.length})`), h('span', { class: 'sp' }),
      h('button', { class: 'btn sm', onclick: () => companyCard({ kind: kind || 'supplier' }) }, '+ Add a company')),
    list.length ? h('div', { class: 'tw' }, h('table', { class: 't' },
      h('thead', {}, h('tr', {}, ['Name', 'Kind', 'Trade', 'Pronto code', 'ABN', 'Contacts', 'Projects'].map((x) => h('th', {}, x)))),
      h('tbody', {}, list.map((c) => h('tr', { class: 'click', onclick: () => companyCard(c) },
        h('td', {}, h('b', {}, c.name)), h('td', {}, badge(c.kind, c.kind === 'subcontractor' ? 'warn' : c.kind === 'consultant' ? 'good' : '')), h('td', {}, c.trade || ''),
        h('td', { class: 'mono' }, c.code || ''), h('td', {}, c.abn || ''), h('td', { class: 'small' }, (c.contacts || '').split('\n')[0]),
        h('td', { class: 'small' }, (c.projects || []).join(', '))))))) : empty('Nothing here yet', 'Add a company, or they arrive from the Pronto suppliers and subcontracts.')));
    if (state.pid) { const pr = h('div', { style: { marginTop: '14px' } }, h('h2', {}, 'On this project: suppliers and subcontractors, Pronto codes and CBS lines')); body.append(pr); await projectResources(pr, 'supplier'); }
  }

  function companyCard(c) {
    const f = (k, ph = '') => h('input', { type: 'text', value: c[k] ?? '', placeholder: ph });
    const inp = { name: f('name'), kind: select(KINDS.map(([k, l]) => [k, l.replace(/s$/, '')]), c.kind || 'supplier'), trade: f('trade', 'e.g. HV testing, civil, design'),
      code: f('code', 'Pronto supplier code'), abn: f('abn'), email: f('email'), phone: f('phone'), address: f('address'),
      contacts: h('textarea', { rows: 3, placeholder: 'One per line: name · role · email · phone' }, c.contacts || ''), notes: h('textarea', { rows: 2 }, c.notes || '') };
    modal({ title: c.id ? c.name : 'Add a company', size: 'wide', body: h('div', { class: 'grid' },
      h('div', { class: 'grid g3' }, field('Name', inp.name), field('Kind', inp.kind), field('Trade', inp.trade), field('Pronto code', inp.code), field('ABN', inp.abn), field('Email', inp.email), field('Phone', inp.phone), field('Address', inp.address)),
      field('Contacts', inp.contacts), field('Notes', inp.notes),
      c.projects?.length ? h('div', { class: 'small muted' }, 'Used on: ' + c.projects.join(', ')) : null),
    actions: [...(c.id ? [{ label: 'Delete', kind: 'ghost', onClick: async () => { if (!(await confirmBox(`Delete ${c.name} from the database? Projects keep the name they use.`, 'Delete'))) return false; await api.del(`/api/directory/companies/${c.id}`); draw(); } }] : []),
      { label: 'Cancel', kind: 'ghost', onClick: () => {} },
      { label: 'Save', onClick: async () => {
        const b = Object.fromEntries(Object.entries(inp).map(([k, el]) => [k, el.value]));
        if (c.id) await api.put(`/api/directory/companies/${c.id}`, b); else await api.post('/api/directory/companies', b);
        toast('Saved'); draw(); } }] });
  }

  drawBar(); draw();
}

// Employees: load the org chart (preview first), and the possible duplicate records with a merge
async function orgChartDialog(after) {
  const p = await api.get('/api/people/org-chart');
  const list = (title, items, render) => items.length ? h('details', { style: { margin: '6px 0' } }, h('summary', { class: 'small' }, h('b', {}, `${title} (${items.length})`)), h('div', { class: 'small', style: { maxHeight: '160px', overflow: 'auto', marginTop: '4px' } }, items.map((x) => h('div', {}, render(x))))) : null;
  modal({ title: 'Load the org chart', size: 'wide', body: h('div', {},
    h('div', { class: 'note' }, `${p.source}. ${p.people} people: ${p.to_create} would be added, ${p.already_there} are already here (only blank fields are filled in; nothing is overwritten). The chart gives names, business titles and reporting lines: no ECF level of an individual, no PM level, no contact details. People who have left are not loaded. The reporting lines are the pre-restructure ones where the 21/10/2026 memo did not change them.`),
    list('Possible duplicates of people already here', p.possible_duplicates, (x) => `${x.chart} (chart) and ${x.existing} (here)`),
    list('Business titles to review with HR', p.titles_to_review, (x) => `${x.name}: ${x.title}, ${x.why}`),
    list('No business title on the chart (not classified)', p.no_title, (x) => x),
    list('ECF role from a grade word on the chart, no title', p.from_grade_word, (x) => x),
    list('Role spans two levels: the level is not on the chart', p.level_to_confirm, (x) => `${x.name}: ${x.role}, levels ${x.levels}`),
    list('Serving notice', p.serving_notice, (x) => x), list('Contractors and secondees', p.engagement, (x) => `${x.name}: ${x.engagement}`)),
  actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} }, { label: `Load ${p.to_create} people`, onClick: async () => { const r = await api.post('/api/people/org-chart', {}); toast(`${r.created} added, ${r.filled} updated`); after?.(); } }] });
}

async function duplicatesCard(box, after) {
  const d = await api.get('/api/people/duplicates');
  clear(box);
  if (!d.pairs.length) return;
  const side = (x) => `${x.name}${x.title ? ', ' + x.title : x.role ? ', ' + x.role : ''}`;
  box.append(h('div', { class: 'card', style: { marginBottom: '14px' } }, h('div', { class: 'ch' }, h('h2', {}, `Possible duplicates (${d.pairs.length})`), h('span', { class: 'sp' }), h('span', { class: 'small muted' }, 'Merging keeps one record: the other name stays as another spelling, and roles, levels and team entries move across.')),
    d.pairs.map((x) => h('div', { class: 'row', style: { gap: '10px', padding: '6px 0', borderBottom: '1px solid var(--hair)' } }, h('div', { style: { flex: 1 } }, side(x.a), h('span', { class: 'muted' }, '  and  '), side(x.b)),
      h('button', { class: 'btn ghost sm', onclick: async () => { if (!(await confirmBox(`Keep ${x.a.name} and merge ${x.b.name} into it?`, 'Merge'))) return; await api.post('/api/people/merge', { keep: x.a.id, drop: x.b.id }); toast('Merged'); after(); } }, `Keep ${x.a.name}`),
      h('button', { class: 'btn ghost sm', onclick: async () => { if (!(await confirmBox(`Keep ${x.b.name} and merge ${x.a.name} into it?`, 'Merge'))) return; await api.post('/api/people/merge', { keep: x.b.id, drop: x.a.id }); toast('Merged'); after(); } }, `Keep ${x.b.name}`)))));
}
