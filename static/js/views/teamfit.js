import { h, empty, badge, fmt } from '../ui.js';
import { api } from '../api.js';
import { openIn } from '../app.js';

// Team > Team fit (project directors): every project's team against its complexity band, role by role. A cell shows who holds the role and is
// coloured by whether they meet what the band asks for. Click a project to open its Project team page.
const FIT = { meets: ['Meets', 'good'], above: ['Above', 'good'], below: ['Below', 'bad'], vacant: ['Not filled', 'warn'], unrated: ['No level', 'warn'], not_required: ['Not required', ''], no_band: ['', ''] };
const RATING = { green: ['Green', 'good'], amber: ['Amber', 'warn'], red: ['Red', 'bad'], unknown: ['Not rated', ''] };
const BG = { meets: '#e4f4ec', above: '#e4f4ec', below: '#fdeceb', vacant: '#fff3d6', unrated: '#fff3d6', not_required: '#f1f4f6', no_band: '#f1f4f6' };

export async function fitTab(body, ctx) {
  const who = ctx.ui.mode === 'direct' && ctx.ui.who ? `?director=${encodeURIComponent(ctx.ui.who)}` : '';
  const d = await api.get('/api/team/fit' + who);
  const leavers = h('div'); leaversCard(leavers);
  if (!d.projects.length) { body.append(empty('No projects', 'Name yourself as the project director on a project (Project setup), then set its complexity baseline and its team.')); return; }
  const count = (r) => d.projects.filter((p) => p.rating === r).length;
  const tile = (l, v, s, c = '') => h('div', { class: 'kpi ' + c }, h('div', { class: 'l' }, l), h('div', { class: 'v' }, v), h('div', { class: 's' }, s));
  body.append(h('div', { class: 'grid g4', style: { marginBottom: '14px' } }, tile('Projects', String(d.projects.length), `${d.projects.filter((p) => !p.band).length} without a complexity baseline`),
    tile('Red', String(count('red')), 'PM or mandatory role short, or the PM sees it harder', 't2'), tile('Amber', String(count('amber')), 'another role short or not recorded', 't3'), tile('Green', String(count('green')), 'every role asked for is covered', 't4')));
  body.append(h('div', { class: 'card' }, h('div', { class: 'ch' }, h('h2', {}, 'Teams against complexity'), h('span', { class: 'sp' }), h('span', { class: 'small muted' }, 'Worst first. Click a project to open its team.')),
    h('div', { class: 'tw' }, h('table', { class: 't nogroup notools' }, h('thead', {}, h('tr', {}, ['Project', 'Band', 'Rating', ...d.roles.map((r) => r.name.replace(' (Cost & Schedule)', ''))].map((x) => h('th', {}, x)))),
      h('tbody', {}, d.projects.map((p) => h('tr', { class: 'click', onclick: () => openIn(p.id, 'projectteam') },
        h('td', {}, h('b', {}, p.name), p.first_gap ? h('div', { class: 'small warn' }, `From ${p.first_gap.month}: ${p.first_gap.reasons[0]}`) : null),
        h('td', { class: 'small nowrap' }, p.band || h('span', { class: 'muted' }, 'no baseline')), h('td', {}, badge(RATING[p.rating][0], RATING[p.rating][1])),
        ...d.roles.map((r) => { const c = p.roles[r.key]; return h('td', { class: 'small', style: { background: BG[c.fit], minWidth: '110px' }, title: c.asked ? `Asked for: ${c.asked}` : '' }, c.who ? h('b', {}, c.who) : (c.status || ''), h('div', { class: c.fit === 'below' ? 'bad' : '' }, FIT[c.fit][0]), r.key === 'pm' && p.pm_dimension_gaps ? h('div', { class: 'bad', title: 'Dimensions where the PM level is below what the baseline asks (open the project team)' }, 'Below in ' + p.pm_dimension_gaps + (p.pm_dimension_gaps === 1 ? ' dimension' : ' dimensions')) : null); })))))),
    h('div', { class: 'small muted', style: { marginTop: '8px' } }, 'Hover a cell to see what the band asks for in that role. "No level" means the person has no level recorded for the role (set it on their card under Employees).')), leavers);
}

// Leavers and people serving notice, with the projects whose teams they hold a role in
export async function leaversCard(body) {
  const d = await api.get('/api/team/leavers');
  if (!d.leavers.length) return;
  const RT = { green: ['Green', 'good'], amber: ['Amber', 'warn'], red: ['Red', 'bad'], unknown: ['Not rated', ''] };
  body.append(h('div', { class: 'card', style: { marginTop: '14px' } }, h('div', { class: 'ch' }, h('h2', {}, 'Leavers and people serving notice'), h('span', { class: 'sp' }), h('span', { class: 'small muted' }, 'A last day on the person ends every project role they hold')),
    d.leavers.map((l) => h('div', { style: { padding: '8px 0', borderBottom: '1px solid var(--hair)' } }, h('div', {}, h('b', {}, l.person), '  ', l.employment_status === 'serving notice' ? badge('Serving notice', 'warn') : null, '  ',
      l.leaving_date ? h('span', { class: 'small' }, 'last day ' + fmt.date(l.leaving_date)) : h('span', { class: 'small warn' }, 'last day not recorded')),
      l.projects.length ? l.projects.map((p) => h('div', { class: 'small', style: { marginLeft: '12px' } }, `${p.project}: ${[...(p.as_director ? ['Project Director'] : []), ...p.roles].join(', ')}. Team now `, badge(RT[p.rating][0], RT[p.rating][1]), p.first_gap ? ` from ${p.first_gap.month}: ${p.first_gap.reasons[0]}` : ''))
        : h('div', { class: 'small muted', style: { marginLeft: '12px' } }, 'Not on any project team.')))));
}
