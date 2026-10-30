import { h, clear, fmt, chart, PALETTE, select, modal, field, toast, badge, empty, tone } from '../ui.js';
import { api } from '../api.js';
import { projectMap } from '../map.js';
import { positionPicker, positionScore, quadrant, bandBadge, bandOf, assessDialog, DIFFICULTY, KNOWLEDGE } from './_assess.js';

// Portfolio > Clients: the client CRM. A card per client (sector, contacts, risk profile, how difficult they are to
// work with, payment terms, the relationship) plus what our projects say about them: running and finished projects,
// contract value, margin, who manages them. Clients come from the projects (Project setup: Client); a card adds detail.
const RISK = { Low: 'good', Medium: 'warn', High: 'bad' };
const CPLX = { 1: 'Easy', 2: 'Fairly easy', 3: 'Typical', 4: 'Demanding', 5: 'Difficult' };
const norm = (s) => (s || '').toLowerCase().replace(/\s+/g, ' ').trim();

export async function clientsTab(body, ctx) {
  const all = await api.get('/api/clients');
  const inView = new Set(ctx.list.map((p) => norm(p.client)));
  const scoped = ctx.ui.mode === 'all' ? all : all.filter((c) => inView.has(norm(c.name)));
  const head = h('div', { class: 'row', style: { marginBottom: '10px' } }, h('span', { class: 'small muted' }, ctx.ui.mode === 'all' ? 'Every client.' : 'Clients of the projects in view.'),
    h('span', { class: 'sp', style: { flex: 1 } }), h('button', { class: 'btn sm', onclick: () => clientCard({ name: '' }, () => ctx.redraw()) }, '+ Add client'));
  body.append(head);
  if (!scoped.length) { body.append(empty('No clients yet', 'Name the client on each project (Project setup), or add one here.')); return; }

  // risk against difficulty: where each client sits, dot size = value of their running projects
  const box = h('div', { class: 'chartbox' });
  const S = (k) => scoped.reduce((a, c) => a + (c[k] || 0), 0);
  const tile = (l, v, s, c = '') => h('div', { class: 'kpi ' + c }, h('div', { class: 'l' }, l), h('div', { class: 'v' }, v), h('div', { class: 's' }, s));
  body.append(h('div', { class: 'grid g4', style: { marginBottom: '14px' } },
    tile('Clients', String(scoped.length), `${scoped.filter((c) => c.id).length} with a CRM card`),
    tile('Running work', fmt.m(S('running_value')), 'contract value of running projects', 't2'),
    tile('High risk', String(scoped.filter((c) => c.risk === 'High').length), fmt.m(scoped.filter((c) => c.risk === 'High').reduce((a, c) => a + c.running_value, 0)) + ' running with them', 't3'),
    tile('Challenging', String(scoped.filter((c) => (c.challenge?.score ?? 0) >= 45).length), 'clients scoring 45 or more (challenging or very challenging)', 't4')));
  const rated = scoped.filter((c) => c.knowledge || c.complexity);
  body.append(h('div', { class: 'grid g2', style: { marginBottom: '14px' } },
    h('div', { class: 'card' }, h('div', { class: 'ch' }, h('h2', {}, 'Knowledge against difficulty'), h('span', { class: 'sp' }), h('span', { class: 'small muted' }, 'Dot size: running contract value')), rated.length ? box : h('div', { class: 'muted' }, 'Rate the clients (risk and complexity) on their cards to see them here.')),
    h('div', { class: 'card' }, h('h2', {}, 'Margin by client'), marginList(scoped))));
  if (rated.length) {
    const maxV = Math.max(1, ...rated.map((c) => c.running_value || 0));
    const col = (c) => { const b = c.challenge?.band; return b === 'Very challenging' ? 'rgba(198,40,40,.65)' : b === 'Challenging' ? 'rgba(229,98,16,.65)' : b === 'Easy' ? 'rgba(60,141,64,.6)' : 'rgba(65,149,242,.6)'; };
    const jit = (c, i) => ((i * 37) % 7 - 3) * 0.045;   // keep clients on the same square apart
    chart(box, { type: 'bubble', data: { datasets: [{ label: 'Clients', data: rated.map((c, i) => ({ x: (c.knowledge || 3) + jit(c, i), y: (c.complexity || 3) + jit(c, i + 3), r: 6 + 16 * Math.sqrt((c.running_value || 0) / maxV), c })),
      backgroundColor: rated.map(col), borderColor: '#fff', borderWidth: 2 }] },
    options: { plugins: { legend: { display: false }, tooltip: { callbacks: { label: (it) => { const c = it.raw.c; return `${c.name}: ${quadrant(c.knowledge, c.complexity)?.[0] || 'position not set'}, ${c.challenge?.band || 'not rated'} (${c.challenge?.score ?? '-'}), ${fmt.m(c.running_value)} running`; } } } },
      scales: { x: { min: 0.5, max: 5.5, afterBuildTicks: (ax) => { ax.ticks = [1, 2, 3, 4, 5].map((value) => ({ value })); }, ticks: { callback: (v) => KNOWLEDGE[v] || '' }, title: { display: true, text: 'Knowledge: clueless to expert' } },
        y: { min: 0.5, max: 5.5, afterBuildTicks: (ax) => { ax.ticks = [1, 2, 3, 4, 5].map((value) => ({ value })); }, ticks: { callback: (v) => DIFFICULTY[v] || '' }, title: { display: true, text: 'Difficulty: easy to difficult' } } },
      onClick: (e, els) => { if (els.length) clientCard(rated[els[0].index], () => ctx.redraw()); } } });
  }

  body.append(h('div', { class: 'card' }, h('h2', {}, 'Clients'),
    h('div', { class: 'tw' }, h('table', { class: 't' }, h('thead', {}, h('tr', {}, ['Client', 'Sector', 'Risk', 'Challenge', 'Running', 'All projects', 'Margin', 'PMs', 'Key contact'].map((x, i) => h('th', { class: i >= 4 && i <= 6 ? 'r' : '' }, x)))),
      h('tbody', {}, scoped.map((c) => h('tr', { style: { cursor: 'pointer' }, title: 'Open the client card', onclick: () => clientCard(c, () => ctx.redraw()) },
        h('td', {}, h('b', {}, c.name), c.id ? null : h('div', { class: 'small muted' }, 'no CRM card yet')),
        h('td', {}, c.sector || ''), h('td', {}, c.risk ? badge(c.risk, RISK[c.risk]) : h('span', { class: 'muted small' }, 'not rated')),
        h('td', {}, bandBadge(c.challenge?.score, c.challenge?.band)),
        h('td', { class: 'r num' }, `${c.running.length} · ${fmt.m(c.running_value)}`), h('td', { class: 'r num' }, `${c.projects} · ${fmt.m(c.contract_value)}`),
        h('td', { class: 'r num ' + (c.margin_pct != null && c.margin_pct < 0 ? 'bad' : '') }, fmt.pct(c.margin_pct)),
        h('td', { class: 'small' }, c.pms.join(', ')), h('td', { class: 'small' }, (c.contacts || '').split('\n')[0] || ''))))))));
}

function marginList(list) {
  const rows = list.filter((c) => c.margin_pct != null).sort((a, b) => a.margin_pct - b.margin_pct);
  if (!rows.length) return h('div', { class: 'muted' }, 'No margins yet.');
  const max = Math.max(0.05, ...rows.map((c) => Math.abs(c.margin_pct)));
  return h('div', {}, rows.map((c) => h('div', { class: 'row', style: { margin: '5px 0', flexWrap: 'nowrap' } },
    h('span', { style: { width: '42%', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }, title: c.name }, c.name),
    h('div', { class: 'bar' + (c.margin_pct < 0 ? ' bad' : ''), style: { flex: 1 } }, h('i', { style: { width: Math.min(100, Math.abs(c.margin_pct) / max * 100) + '%', background: c.margin_pct < 0 ? 'var(--bad)' : PALETTE[0] } })),
    h('span', { class: 'num ' + tone(c.margin_pct, 0), style: { width: '64px', textAlign: 'right' } }, fmt.pct(c.margin_pct)))),
  h('div', { class: 'small muted', style: { marginTop: '6px' } }, 'Forecast margin of running projects, final margin of archived ones, weighted by contract value.'));
}

export function clientCard(c, after) {
  const f = (k, ph = '') => h('input', { type: 'text', value: c[k] || '', placeholder: ph });
  const ta = (k, rows, ph) => h('textarea', { rows, placeholder: ph, style: { width: '100%' } }, c[k] || '');
  const inp = { name: f('name'), sector: select([['', '(choose)'], ...['Developer', 'Utility / network', 'IPP / owner', 'Government', 'Mining / industrial', 'EPC / contractor', 'Other'].map((x) => [x, x])], c.sector || ''),
    abn: f('abn'), website: f('website', 'https://'), hq: f('hq', 'e.g. Brisbane QLD'),
    risk: select([['', '(not rated)'], ['Low', 'Low'], ['Medium', 'Medium'], ['High', 'High']], c.risk || ''),
    payment_terms: f('payment_terms', 'e.g. 30 days EOM, pays late'), contacts: ta('contacts', 4, 'One per line: name · role · email · phone'),
    relationship: ta('relationship', 3, 'How the relationship stands, what matters to them, history'), notes: ta('notes', 2, '') };
  const pick = positionPicker({ knowledge: c.knowledge, difficulty: c.complexity }, () => drawSummary());
  inp.knowledge = pick.knowledge; inp.complexity = pick.complexity;   // read as inp.x.value when saving
  const summary = h('div');
  const ch = c.challenge || {};
  const drawSummary = () => {
    const pos = positionScore(pick.knowledge.value || null, pick.complexity.value || null);
    const score = pos == null ? ch.evidence : ch.evidence == null ? pos : Math.round((pos + ch.evidence) / 2);
    clear(summary).append(...[h('div', { class: 'row', style: { gap: '10px' } }, h('b', {}, 'How challenging'), bandBadge(score, bandOf(score))),
      h('div', { class: 'small', style: { margin: '6px 0' } }, `Position ${pos ?? 'not set'} · Evidence ${ch.evidence ?? 'none yet'}${ch.evidence_projects ? ` (${ch.evidence_projects} project${ch.evidence_projects === 1 ? '' : 's'})` : ''}`),
      h('div', { class: 'small muted' }, 'Half is where you place the client on the grid (60% difficulty, 40% lack of knowledge); half is what EPEC PMs recorded for the client PMs and project complexity through each project. With no assessments yet, the position alone counts.'),
      (ch.client_pms || []).length ? h('div', { style: { marginTop: '10px' } }, h('b', { class: 'small' }, 'Client project managers'), h('table', { class: 't', style: { marginTop: '4px' } }, h('thead', {}, h('tr', {}, ['Client PM', 'Difficulty', 'Complexity of their projects', 'Projects'].map((x) => h('th', {}, x)))),
        h('tbody', {}, ch.client_pms.map((m) => h('tr', {}, h('td', {}, m.name), h('td', {}, m.difficulty != null ? `${m.difficulty} · ${DIFFICULTY[Math.round(m.difficulty)]}` : ''), h('td', {}, m.complexity != null ? String(m.complexity) : ''), h('td', { class: 'small' }, m.projects.join(', ')))))) ) : null].filter(Boolean));
  };
  drawSummary();
  const projects = [...(c.running || []).map((p) => ({ ...p, st: 'Running' })), ...(c.archived || []).map((p) => ({ ...p, st: 'Finished' }))];
  modal({ title: c.name ? `Client: ${c.name}` : 'New client', size: 'wide', body: h('div', { class: 'grid' },
    h('div', { class: 'grid g3' }, field('Client name', inp.name, 'As written on the projects'), field('Sector', inp.sector), field('Head office', inp.hq),
      field('Risk profile', inp.risk, 'Commercial, payment and dispute risk'), field('Payment terms and behaviour', inp.payment_terms), h('span'),
      field('ABN', inp.abn), field('Website', inp.website), h('span')),
    h('div', { class: 'grid g2', style: { alignItems: 'start' } }, h('div', {}, h('b', {}, 'Where this client sits'), h('div', { class: 'small muted', style: { marginBottom: '6px' } }, 'Across: how well they know what they are buying. Up: how difficult they are to deal with. It counts in PM workload.'), pick.el), summary),
    projects.length ? projectsBlock(projects) : null,
    field('Key contacts', inp.contacts), field('Relationship', inp.relationship), field('Notes', inp.notes),
    h('span')),
  actions: [
    ...(c.id ? [{ label: 'Delete card', kind: 'ghost', onClick: async () => { await api.del(`/api/clients/${c.id}`); toast('Client card deleted (the projects keep the client name)'); after?.(); } }] : []),
    { label: 'Cancel', kind: 'ghost', onClick: () => {} },
    { label: 'Save', onClick: async () => {
      const b = Object.fromEntries(Object.entries(inp).map(([k, el]) => [k, el.value]));
      if (!b.name.trim()) throw new Error('Enter the client name');
      if (c.id) await api.put(`/api/clients/${c.id}`, b); else await api.post('/api/clients', b);
      toast('Client saved'); after?.(); } }] });
}

// the client's projects as Current, Past or All, with the sites on a map
function projectsBlock(projects) {
  let view = 'all';
  const tabs = h('div', { class: 'row', style: { gap: '6px' } });
  const mapSlot = h('div');
  const list = h('div');
  const n = (st) => projects.filter((p) => p.st === st).length;
  const draw = () => {
    const sel = projects.filter((p) => view === 'all' || (view === 'current' ? p.st === 'Running' : p.st === 'Finished'));
    tabs.replaceChildren(h('b', { style: { marginRight: '8px' } }, 'Projects with this client'),
      ...[['current', `Current (${n('Running')})`], ['past', `Past (${n('Finished')})`], ['all', `All (${projects.length})`]].map(([k, l]) =>
        h('span', { class: 'chip' + (view === k ? ' on' : ''), onclick: () => { view = k; draw(); } }, l)));
    list.replaceChildren(sel.length ? h('div', { class: 'tw' }, h('table', { class: 't' }, h('thead', {}, h('tr', {}, ['Project', '', 'Location', 'Type', 'PM', 'Client PM / complexity', 'Contract value', 'Margin', ''].map((x, i) => h('th', { class: i === 6 || i === 7 ? 'r' : '' }, x)))),
      h('tbody', {}, sel.map((p) => h('tr', {}, h('td', {}, p.name), h('td', {}, badge(p.st, p.st === 'Running' ? 'good' : '')), h('td', { class: 'small' }, p.location || h('span', { class: 'muted' }, 'not set')),
        h('td', { class: 'small' }, p.project_type || ''), h('td', {}, p.pm || ''),
        h('td', { class: 'small' }, p.assessment ? `PM ${p.assessment.pm_difficulty ?? '-'} · cx ${p.assessment.complexity ?? '-'} (${p.assessment.n} month${p.assessment.n === 1 ? '' : 's'})` : h('span', { class: 'muted' }, 'not assessed')),
        h('td', { class: 'r num' }, fmt.money(p.contract_value)), h('td', { class: 'r num' }, fmt.pct(p.margin_pct)), h('td', {}, h('button', { class: 'btn ghost sm', onclick: () => assessDialog(p, () => {}) }, 'Assess'))))))) : h('div', { class: 'muted', style: { padding: '8px 0' } }, 'None.'));
    const mapBox = h('div', { class: 'chartbox', style: { height: '280px', marginTop: '8px' } });   // a new element each time: a Leaflet map cannot be started twice on one
    mapSlot.replaceChildren(mapBox);
    projectMap(mapBox, sel.map((p) => ({ ...p, client: '' })), {}).catch((e) => mapBox.replaceChildren(h('div', { class: 'note warn' }, 'The map could not load: ' + e.message)));
  };
  const box = h('div', {}, tabs, list, mapSlot);
  draw();
  return box;
}
