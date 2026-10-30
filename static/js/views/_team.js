import { h, clear, fmt, select, modal, field, toast, badge, empty, num } from '../ui.js';
import { api } from '../api.js';
import { loadEcf } from './ecf.js';
import { projectMap, pickMap, geocode } from '../map.js';

// Portfolio > Team workload: how loaded each project manager is, in % of what they can carry. Demand comes from each
// running project (complexity, the client's difficulty and risk, the phase, travel from the PM's base) and the spread
// of their sites; capacity from their PM level (EPEC-PM-FW-0002) and time available. See app/workload.py.
const BAND = { available: ['good', '#3c8d40'], good: ['', '#4195f2'], full: ['warn', '#ffb500'], over: ['bad', '#c62828'] };
const LEVELS = [[1, 'Level 1, junior PM: runs one project'], [2, 'Level 2, PM: runs a portfolio of projects'], [3, 'Level 3, senior PM: runs a portfolio of significant projects'], [4, 'Level 4, senior PM / program manager: runs large or multi-discipline projects and programs'], [5, 'Level 5, project director: directs a program and its team of PMs']];
const SPAN = { project: 'one project', portfolio: 'portfolio', program: 'program' };
const norm = (s) => (s || '').toLowerCase().replace(/\s+/g, ' ').trim();

export async function teamTab(body, ctx) {
  const { ui } = ctx;
  const q = ui.mode === 'direct' && ui.who ? `?director=${encodeURIComponent(ui.who)}` : '';
  const [w, ppl] = await Promise.all([api.get('/api/workload' + q), api.get('/api/people')]);
  let team = w.team;
  if (ui.mode === 'manage') team = team.filter((r) => norm(r.name) === norm(ui.who));
  body.append(h('div', { class: 'row', style: { marginBottom: '10px' } },
    h('span', { class: 'small muted' }, ui.mode === 'direct' ? `${ui.who}'s team: the PMs on projects they direct, or who report to them.` : ui.mode === 'manage' ? `${ui.who}'s own workload.` : 'Every project manager.'),
    h('span', { class: 'sp', style: { flex: 1 } }), h('button', { class: 'btn sm', onclick: () => personCard({ name: '', fte: 1 }, ppl, ctx.redraw) }, '+ Add a person')));
  if (!team.length) { body.append(empty('Nobody to show', 'Name the EPEC project manager and director on each project (Project setup), then set each PM\'s level here.')); return; }

  const avg = team.reduce((a, r) => a + (r.pct || 0), 0) / team.length;
  const spare = team.reduce((a, r) => a + Math.max(0, r.spare), 0);
  const tile = (l, v, s, c = '', vc = '') => h('div', { class: 'kpi ' + c }, h('div', { class: 'l' }, l), h('div', { class: 'v ' + vc }, v), h('div', { class: 's' }, s));
  body.append(h('div', { class: 'grid g4', style: { marginBottom: '14px' } },
    tile('Project managers', String(team.length), `${team.filter((r) => !r.level_set).length} without a PM level set`),
    tile('Average workload', `${fmt.n(avg)}%`, 'of what each can carry', 't2'),
    tile('Overloaded', String(team.filter((r) => r.band === 'over').length), `${team.filter((r) => r.band === 'full').length} full`, 't3', team.some((r) => r.band === 'over') ? 'bad' : ''),
    tile('Room for more', `${Math.floor(spare / 0.4)} project${Math.floor(spare / 0.4) === 1 ? '' : 's'}`, 'of typical complexity (3), across the team', 't4')));

  // the team at a glance: level, time, workload and the projects each PM manages
  body.append(h('div', { class: 'card', style: { marginBottom: '14px' } }, h('div', { class: 'ch' }, h('h2', {}, 'The team and their projects'), h('span', { class: 'sp' }), h('span', { class: 'small muted' }, 'Click a project to open it, a PM for the workload breakdown')),
    h('div', { class: 'tw' }, h('table', { class: 't' }, h('thead', {}, h('tr', {}, ['Project manager', 'PM level', 'Time', 'Workload', 'Projects managed (complexity)', ''].map((x, i) => h('th', { class: i === 2 || i === 3 ? 'r' : '' }, x)))),
      h('tbody', {}, team.map((r) => { const [cls] = BAND[r.band] || BAND.good; return h('tr', {},
        h('td', {}, h('b', {}, r.name), r.base ? h('div', { class: 'small muted' }, 'Base ' + r.base) : null),
        h('td', { class: 'small' }, r.level ? `Level ${r.level}` : h('span', { class: 'muted' }, 'not set'), h('div', { class: 'muted' }, SPAN[r.span] || 'portfolio')),
        h('td', { class: 'r num' }, `${fmt.n(r.fte * 100)}%`),
        h('td', { class: 'r' }, badge(`${fmt.n(r.pct)}%`, cls), h('div', { class: 'small muted' }, r.band_label)),
        h('td', { class: 'small' }, r.projects.length ? r.projects.map((p) => h('div', {}, h('a', { onclick: () => ctx.open({ id: p.id }) }, p.name), h('span', { class: 'muted' }, ` · complexity ${p.complexity}${p.complexity_set ? '' : ' (suggested)'} · ${p.phase}`))) : h('span', { class: 'muted' }, 'no running projects')),
        h('td', { class: 'small' }, r.too_many ? h('span', { class: 'badge warn', title: r.too_many }, 'more than one project') : r.stretch.length ? h('span', { class: 'badge warn', title: `Complexity above their level: ${r.stretch.join(', ')}` }, 'stretch') : '')); }))))));

  // one bar per PM, 100% marked; click to see why
  const detail = h('div');
  const bars = h('div', { class: 'card', style: { marginBottom: '14px' } }, h('div', { class: 'ch' }, h('h2', {}, 'Workload by project manager'), h('span', { class: 'sp' }), h('span', { class: 'small muted' }, 'The line is 100%: everything they can carry. Click a PM for the breakdown.')),
    h('div', { class: 'wl' }, team.map((r) => {
      const [cls, col] = BAND[r.band] || BAND.good;
      const row = h('div', { class: 'wl-row', onclick: () => { clear(detail).append(breakdown(r, ppl, ctx)); detail.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); } },
        h('div', { class: 'wl-name' }, h('b', {}, r.name), h('div', { class: 'small muted' }, `${r.level ? 'Level ' + r.level : 'Level not set'} · ${SPAN[r.span] || 'portfolio'} · ${r.fte !== 1 ? fmt.n(r.fte * 100) + '% time · ' : ''}${r.projects.length} project${r.projects.length === 1 ? '' : 's'}`)),
        h('div', { class: 'wl-track' }, h('i', { style: { width: Math.min(100, (r.pct || 0) / 1.5) + '%', background: col } }), h('span', { class: 'wl-100' })),
        h('div', { class: 'wl-pct' }, badge(`${fmt.n(r.pct)}%`, cls), h('div', { class: 'small muted' }, r.band_label)),
        r.too_many ? h('div', { class: 'wl-warn', title: r.too_many }, '⚠ one project')
          : r.stretch.length ? h('div', { class: 'wl-warn', title: `Complexity above their level: ${r.stretch.join(', ')}` }, '⚠ stretch') : h('div', { class: 'wl-warn' }));
      return row;
    })));
  body.append(bars, detail);

  // where the team's work is, and where they are based
  const mine = new Set(team.map((r) => norm(r.name)));
  const projects = ctx.all.filter((p) => mine.has(norm(p.pm)));
  const mapBox = h('div', { style: { height: '380px' } });
  body.append(h('div', { class: 'card', style: { marginBottom: '14px' } }, h('div', { class: 'ch' }, h('h2', {}, 'Team sites and bases'), h('span', { class: 'sp' }), h('span', { class: 'small muted' }, 'Sites far from a PM\'s base, or far apart, add to their workload')), mapBox));
  projectMap(mapBox, projects, { onOpen: ctx.open, extra: team.filter((r) => r.lat != null).map((r) => ({ lat: r.lat, lon: r.lon, label: `${r.name} (base${r.base ? ': ' + r.base : ''})` })) })
    .catch((e) => mapBox.replaceChildren(h('div', { class: 'note warn' }, 'The map could not load: ' + e.message)));

  body.append(howCard(w.weights));
}

function breakdown(r, ppl, ctx) {
  const card = ppl.find((x) => norm(x.name) === norm(r.name)) || { name: r.name };
  return h('div', { class: 'card', style: { marginBottom: '14px' } },
    h('div', { class: 'ch' }, h('h2', {}, `${r.name}: ${fmt.n(r.pct)}% loaded`), h('span', { class: 'sp' }), h('button', { class: 'btn ghost sm', onclick: () => personCard(card, ppl, ctx.redraw) }, 'Edit level, time and base')),
    h('div', { class: 'small', style: { marginBottom: '8px' } }, `${r.level_name}. Capacity ${fmt.n(r.capacity, 2)} (level ${r.level || '2 assumed'} x ${fmt.n(r.fte * 100)}% time). `
      + `Demand ${fmt.n(r.demand, 2)} = the projects below${r.spread_factor > 1 ? `, x ${fmt.n(r.spread_factor, 2)} for sites spread on average ${fmt.n(r.spread_km)} km from their middle` : ''}.`
      + (r.base ? ` Based in ${r.base}.` : ' No base set: travel not counted.')),
    r.too_many ? h('div', { class: 'note warn', style: { marginBottom: '8px' } }, `${r.too_many}. Give them one project, or set a higher PM level if they run a portfolio.`) : null,
    r.stretch.length ? h('div', { class: 'note warn', style: { marginBottom: '8px' } }, `Above their PM level for: ${r.stretch.join(', ')}. Consider support from a more senior PM or the director.`) : null,
    h('div', { class: 'tw' }, h('table', { class: 't' }, h('thead', {}, h('tr', {}, ['Project', 'Complexity', 'Needs level', 'Peak load', 'Client', 'Phase', 'From base', 'Travel', 'Demand'].map((x, i) => h('th', { class: i ? 'r' : '' }, x)))),
      h('tbody', {}, r.projects.map((p) => h('tr', { style: { cursor: 'pointer' }, onclick: () => ctx.open({ id: p.id }) },
        h('td', {}, p.name), h('td', { class: 'r' }, `${p.complexity}${p.complexity_set ? '' : ' (suggested)'}`), h('td', { class: 'r' }, String(p.required_level)),
        h('td', { class: 'r num' }, fmt.n(p.base_load, 2)), h('td', { class: 'r num' }, `x ${fmt.n(p.client_factor, 2)}`), h('td', { class: 'r' }, `${p.phase} x ${fmt.n(p.phase_factor, 2)}`),
        h('td', { class: 'r num' }, p.km_from_base != null ? `${fmt.n(p.km_from_base)} km` : '–'), h('td', { class: 'r num' }, `x ${fmt.n(p.travel_factor, 2)}`), h('td', { class: 'r num' }, p.demand.toFixed(3))))))));
}

function howCard(wt) {
  const pct = (v) => `${Math.round((v - 1) * 100) >= 0 ? '+' : ''}${Math.round((v - 1) * 100)}%`;
  return h('details', { class: 'card' }, h('summary', {}, h('b', {}, 'How workload is worked out')),
    h('div', { class: 'small', style: { marginTop: '8px', lineHeight: 1.6 } },
      h('p', {}, 'Each running project asks for a share of a full-time PM Level 2 at the peak of delivery, by complexity: ', Object.entries(wt.complexity).map(([k, v]) => `${k} = ${Math.round(v * 100)}%`).join(', '), '.'),
      h('p', {}, 'The client changes it: by difficulty ', Object.entries(wt.client).map(([k, v]) => `${k} ${pct(v)}`).join(', '), '; by risk ', Object.entries(wt.risk).map(([k, v]) => `${k} ${pct(v)}`).join(', '), '.'),
      h('p', {}, 'The phase changes it: delivery 100%, mobilising (start within 3 months) 35%, awarded but starting later 15%, last 10% of the project schedule (commissioning) 75%, after the end date (close-out, defects) 40%.'),
      h('p', {}, `Travel: up to +${Math.round(wt.travel[0] * 100)}% for a site ${fmt.n(wt.travel[0] * wt.travel[1])} km or more from the PM's base. Spread: up to +${Math.round(wt.spread[0] * 100)}% on all their projects when their sites average ${fmt.n(wt.spread[0] * wt.spread[1])} km or more from their middle.`),
      h('p', {}, 'Capacity by PM level (EPEC-PM-FW-0002 PM Technical Capability Framework), times their time available: ', Object.entries(wt.capacity).map(([k, v]) => `Level ${k} = ${v}`).join(', '), '. Workload % = demand / capacity: under 70% room for more, 70 to 90% well loaded, 90 to 105% full, above that overloaded.'),
      h('p', {}, 'A project needs at least PM level: ', Object.entries(wt.required_level).map(([k, v]) => `complexity ${k} → Level ${v}`).join(', '), '. Below that it is flagged as a stretch.'),
      h('p', { class: 'muted' }, 'These weights are a starting point to calibrate with the team; they are set in one place (app/workload.py).')));
}

// competency levels by role (app/team.py): 1 to 4, worded like the Project Resourcing Requirement table
const TEAM_ROLES = [['pe', 'Project Engineer', ['Shared / Junior PE', 'Dedicated / Competent PE', 'Senior / Lead PE', 'Principal / Portfolio Engineer']],
  ['dm', 'Design Manager', ['Shared / Design Coordinator', 'Design Manager', 'Senior / Lead Design Manager', 'Design / Engineering Director']],
  ['cm', 'Construction Manager', ['Shared Supervisor', 'Project Construction Manager', 'Senior Construction Manager', 'Construction Director']],
  ['tc', 'Test & Commissioning', ['(not normally required)', 'Commissioning Engineer', 'Lead Test & Commissioning Manager', 'Commissioning Director']],
  ['ct', 'Project Controls (Cost & Schedule)', ['Shared', 'Dedicated Cost / Scheduler', 'Controls Lead', 'Portfolio Controls']],
  ['co', 'Project Coordinator', ['Shared / Part-time', 'Dedicated Project Coordinator', 'Senior Project Coordinator', 'Portfolio PMO Analyst']]];
const DIMS = [['scope', 'Scope clarity & volatility'], ['schedule', 'Schedule complexity & duration'], ['cost', 'Cost / Budget magnitude & control'], ['contracting', 'Contracting complexity'], ['risk', 'Risk & uncertainty'],
  ['quality', 'Quality assurance demand'], ['hse', 'HSE criticality'], ['stakeholders', 'Stakeholder complexity & sensitivity'], ['procurement', 'Procurement criticality'], ['governance', 'Integration & Governance maturity']];
const PM_LEVELS = [[1, 'Level 1'], [2, 'Level 2'], [3, 'Level 3'], [4, 'Level 4'], [5, 'Level 5']];
export const roleLevelText = (lv) => TEAM_ROLES.filter(([k]) => lv?.[k]).map(([k, , labels]) => `${k.toUpperCase()} ${lv[k]}`).join(' \u00b7 ');
export async function personCard(p, ppl, after) {
  const ecf = await loadEcf();
  const f = (k, ph = '') => h('input', { type: 'text', value: p[k] ?? '', placeholder: ph });
  const directors = [...new Set([...ppl.filter((x) => (x.role || '').toLowerCase().includes('director')).map((x) => x.name), p.reports_to].filter(Boolean))];
  const inp = { name: f('name'), role: select([...new Set(['Junior Project Manager', 'Project Manager', 'Senior Project Manager', 'Project Director', 'Project Engineer', 'Project Coordinator', 'Employee', 'Other', p.role].filter(Boolean))].map((x) => [x, x]), p.role || 'Project Manager'),
    employee_code: f('employee_code', 'Pronto employee code'), function: f('function', 'e.g. Electrician, Engineer'), phone: f('phone'),
    pm_level: select([['', '(not set)'], ...LEVELS], p.pm_level ?? ''), fte: h('input', { type: 'number', step: '0.1', value: p.fte ?? 1 }),
    reports_to: select([['', '(none)'], ...directors.map((x) => [x, x])], p.reports_to || ''), base: f('base', 'e.g. Brisbane QLD'), email: f('email'), lat: h('input', { type: 'number', value: p.lat ?? '' }), lon: h('input', { type: 'number', value: p.lon ?? '' }), notes: f('notes') };
  const rl = Object.fromEntries(TEAM_ROLES.map(([k, , labels]) => [k, select([['', '(not recorded)'], ...labels.map((l, i) => [i + 1, `${i + 1} \u00b7 ${l}`])], p.role_levels?.[k] ?? '')]));
  // EPEC Classification Framework: role, level (only where the role spans two) and an allowed business title
  const eRole = select([['', '(not classified)'], ...ecf.roles.map((r) => [r.key, `${r.family_name}: ${r.name}${r.level_from ? ' (level ' + r.level_from + (r.level_to && r.level_to !== r.level_from ? ' to ' + r.level_to : '') + ')' : ''}`])], p.ecf_role || '');
  const eLevel = select([], p.ecf_level ?? ''); const eTitle = h('input', { type: 'text', value: p.business_title || '', list: 'ecf-titles', placeholder: 'Business title (HR approved)' }); const eList = h('datalist', { id: 'ecf-titles' });
  const eNote = h('div', { class: 'small muted' });
  const syncEcf = () => {
    const r = ecf.roles.find((x) => x.key === eRole.value);
    clear(eLevel); clear(eList);
    if (r && r.level_from) { for (let l = r.level_from; l <= (r.level_to || r.level_from); l++) eLevel.append(h('option', { value: l, selected: String(p.ecf_level ?? r.level_from) === String(l) }, `Level ${l}`)); eLevel.disabled = !(r.level_to && r.level_to !== r.level_from); }
    else { eLevel.append(h('option', { value: '' }, r ? 'No level in the framework' : '')); eLevel.disabled = true; }
    (r?.titles || []).forEach((x) => eList.append(h('option', { value: x })));
    eNote.textContent = r ? (r.titles.length ? 'Allowed titles: ' + r.titles.join(', ') + '. ' : '') + 'Every business title needs HR approval.' : 'Pick the role this person holds in the EPEC Classification Framework (Classification framework, PMO). It gives their level on Project team.';
  };
  eRole.onchange = syncEcf; syncEcf();
  const eStatus = select([['', 'Active'], ['serving notice', 'Serving notice'], ['left', 'Left']], p.employment_status || ''); const eLeave = h('input', { type: 'date', value: p.leaving_date || '' });
  const eEng = select([['', 'Employee'], ['contractor', 'Contractor'], ['secondment', 'Secondment']], p.engagement && p.engagement !== 'employee' ? p.engagement : '');
  const impactBox = h('div', { class: 'small' });
  if (p.id && (p.leaving_date || p.employment_status === 'serving notice')) api.get(`/api/people/${p.id}/impact`).then((i) => {
    impactBox.append(i.projects.length ? h('div', { class: 'note warn' }, h('b', {}, 'Affects: '), i.projects.map((x, k) => h('span', {}, k ? '; ' : '', `${x.project} (${[...(x.as_director ? ['Project Director'] : []), ...x.roles].join(', ')})${x.first_gap ? ', from ' + x.first_gap.month : ''}`))) : h('span', { class: 'muted' }, 'No project team holds them yet.'));
  }).catch(() => {});
  const dl = Object.fromEntries(DIMS.map(([k]) => [k, select([['', '(overall PM level)'], ...PM_LEVELS], p.dimension_levels?.[k] ?? '')]));
  const box = h('div', { style: { height: '220px' } }); const found = h('div', { class: 'small' }); let pk = null;
  const find = async () => { try { const r = await geocode(inp.base.value); clear(found).append(...(r.length ? r.slice(0, 3).map((x) => h('div', {}, h('a', { onclick: () => { inp.lat.value = x.lat; inp.lon.value = x.lon; pk?.set(x.lat, x.lon); clear(found); } }, x.label))) : [h('span', { class: 'muted' }, 'Nothing found')])); } catch (e) { found.textContent = e.message + '. Click the base on the map instead.'; } };
  modal({ title: p.id ? `${p.name}` : p.name ? `${p.name}: set up` : 'Add a person', size: 'wide', body: h('div', { class: 'grid' },
    h('div', { class: 'grid g3' }, field('Name', inp.name, 'As written on the projects'), field('Role', inp.role), field('PM level', inp.pm_level, 'EPEC-PM-FW-0002 PM Technical Capability Framework'),
      field('Time available', inp.fte, '1 = full time on project management, 0.5 = half'), field('Reports to (director)', inp.reports_to), field('Email', inp.email),
      field('Employee code', inp.employee_code), field('Function / trade', inp.function), field('Phone', inp.phone)),
    h('div', { class: 'grid g4' }, field('Home base', inp.base), h('div', { style: { marginTop: '20px' } }, h('button', { class: 'btn ghost sm', onclick: find }, 'Find'), found), field('Latitude', inp.lat, 'Or click the map'), field('Longitude', inp.lon)),
    h('h3', { style: { margin: '10px 0 4px' } }, 'Employment'),
    h('div', { class: 'grid g3' }, field('Status', eStatus, 'Serving notice: the team page flags every role they hold'), field('Last day', eLeave, 'Ends every project role they hold on that date'), field('Engagement', eEng)), impactBox,
    h('h3', { style: { margin: '10px 0 4px' } }, 'Classification (EPEC Classification Framework)'),
    h('div', { class: 'grid g3' }, field('ECF role', eRole), field('Level', eLevel), field('Business title', eTitle)), eList, eNote,
    h('h3', { style: { margin: '10px 0 4px' } }, 'Competency by role'),
    h('div', { class: 'small muted', style: { marginBottom: '6px' } }, 'Only needed to override what the classification above gives. Used on Project team to check the team against the complexity band. The PM level above covers the Project Manager role.'),
    h('div', { class: 'grid g3' }, ...TEAM_ROLES.map(([k, name, labels]) => field(name, rl[k]))),
    h('h3', { style: { margin: '10px 0 4px' } }, 'Competency by dimension (for project managers)'),
    h('div', { class: 'small muted', style: { marginBottom: '6px' } }, 'The PM level (EPEC-PM-FW-0002) in each dimension of the Project Complexity Matrix. Leave a dimension on overall PM level unless it differs: it is compared with what the project asks of its PM, which only the project director sees.'),
    h('div', { class: 'grid g3' }, ...DIMS.map(([k, name]) => field(name, dl[k]))),
    box, field('Notes', inp.notes)),
  actions: [...(p.id ? [{ label: 'Delete', kind: 'ghost', onClick: async () => { await api.del(`/api/people/${p.id}`); after?.(); } }] : []), { label: 'Cancel', kind: 'ghost', onClick: () => {} },
    { label: 'Save', onClick: async () => {
      const b = Object.fromEntries(Object.entries(inp).map(([k, el]) => [k, el.value]));
      if (!b.name.trim()) throw new Error('Enter the name');
      b.fte = num(b.fte) || 1; b.employment_status = eStatus.value; b.leaving_date = eLeave.value; b.engagement = eEng.value; b.ecf_role = eRole.value; b.ecf_level = eLevel.value; b.business_title = eTitle.value; b.dimension_levels = Object.fromEntries(Object.entries(dl).map(([k, el]) => [k, el.value])); b.role_levels = Object.fromEntries(Object.entries(rl).map(([k, el]) => [k, el.value]));
      if (p.id) await api.put(`/api/people/${p.id}`, b); else await api.post('/api/people', b);
      toast('Saved'); after?.(); } }] });
  pickMap(box, { lat: p.lat, lon: p.lon }, (la, lo) => { inp.lat.value = la; inp.lon.value = lo; }).then((x) => { pk = x; }).catch(() => box.remove());
}
