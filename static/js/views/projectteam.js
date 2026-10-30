import { h, clear, fmt, modal, toast, field, select, badge, empty, confirmBox, lookup } from '../ui.js';
import { api, state, p } from '../api.js';
import { go, render, isDirector } from '../app.js';
import { radar } from './complexity.js';
import { PALETTE } from '../ui.js';
import { statusMonth } from '../api.js';

// SETUP > Project team: the team chart, and each role against what the project's complexity band asks for (EPEC Project Complexity Matrix,
// Project Resourcing Requirement). The PM and the director are the project's own fields (Project setup); the other six roles are filled here.
const NS = 'http://www.w3.org/2000/svg';
const sv = (tag, attrs = {}, ...kids) => { const e = document.createElementNS(NS, tag); Object.entries(attrs).forEach(([k, v]) => v != null && e.setAttribute(k, v)); kids.flat().forEach((k) => k != null && e.append(k)); return e; };
const FIT = { meets: ['Meets', 'good'], above: ['Above the requirement', 'good'], below: ['Below the requirement', 'bad'], vacant: ['Not filled', 'warn'], unrated: ['Level not recorded', 'warn'], not_required: ['Not required', ''], no_band: ['Waiting for the baseline', ''] };
const COLOUR = { meets: 'var(--good)', above: 'var(--good)', below: 'var(--bad)', vacant: 'var(--warn)', unrated: 'var(--warn)', not_required: '#9aa9b3', no_band: '#9aa9b3' };
const RATING = { green: ['Green', 'good'], amber: ['Amber', 'warn'], red: ['Red', 'bad'], unknown: ['Not rated yet', ''] };

export default async function projectTeam(root) {
  const t = await api.get(p('/project-team'));
  const ro = !!state.project?.is_parent;
  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, 'Project team'),
    h('div', { class: 'sub' }, 'Who is on the project, against the people the complexity band asks for. Levels sit on the person (Stakeholders, Employees), so they follow them from project to project.')),
    h('span', { class: 'sp' }), ro ? null : h('button', { class: 'btn', onclick: () => slotDialog(t, { role_key: 'pe' }) }, 'Add a team member...'),
    isDirector() ? h('button', { class: 'btn ghost', title: 'Who signs and approves the resourcing paper', onclick: signoffDialog }, 'Paper sign-off...') : null,
    isDirector() ? h('button', { class: 'btn ghost', title: 'The resourcing paper in Word: score, profile, basis, requirements, summary and sign-off', onclick: () => window.open(p('/project-team/paper.docx')) }, 'Resourcing paper (Word)') : null,
    h('button', { class: 'btn ghost', onclick: () => go('directory', { tab: 'employees' }) }, 'People and levels')));

  // the band, the rating and the reasons
  const rate = RATING[t.risk.rating];
  root.append(h('div', { class: 'card', style: { marginBottom: '14px' } }, h('div', { class: 'ch' }, h('h2', {}, 'Team risk'), h('span', { class: 'sp' }), badge(rate[0], rate[1])),
    h('div', { class: 'row', style: { gap: '12px', flexWrap: 'wrap', marginBottom: '6px' } }, t.band ? badge(t.band.name, t.band.code === 'C1' ? 'good' : t.band.code === 'C2' ? '' : t.band.code === 'C3' ? 'warn' : 'bad') : badge('No band yet'), t.band ? h('span', { class: 'small muted' }, `Typical ${t.band.typical}`) : null),
    t.risk.reasons.length ? h('ul', { class: 'small', style: { margin: '4px 0 0 18px' } }, t.risk.reasons.map((x) => h('li', {}, x))) : h('div', { class: 'small good' }, 'Every role the band asks for is filled at the level asked for.'),
    h('div', { class: 'small muted', style: { marginTop: '8px' } }, 'Red: the PM or a mandatory role is vacant or below the level asked for, or the PM now assesses the project in a higher band than the baseline. Amber: another dedicated role is vacant, below or has no level recorded. Shared roles, and roles marked "if applicable", are not gaps when empty.')));

  // the next months: a joiner or a leaver with a date changes the rating (judged on the 15th of each month)
  if (t.band && t.ahead.months.length) {
    const cell = (m) => h('div', { style: { flex: 1, minWidth: '84px', padding: '8px 6px', borderRadius: '8px', textAlign: 'center', background: { green: '#e4f4ec', amber: '#fff3d6', red: '#fdeceb', unknown: '#f1f4f6' }[m.rating] }, title: m.reasons.join('\n') || 'Every role is covered' },
      h('div', { class: 'small', style: { fontWeight: 700 } }, fmt.month(m.month)), h('div', { class: 'small ' + ({ green: 'good', amber: 'warn', red: 'bad' }[m.rating] || '') }, RATING[m.rating][0]));
    root.append(h('div', { class: 'card', style: { marginBottom: '14px' } }, h('div', { class: 'ch' }, h('h2', {}, 'Looking ahead'), h('span', { class: 'sp' }), h('span', { class: 'small muted' }, 'Hover a month for the reasons')),
      h('div', { class: 'row', style: { gap: '6px', flexWrap: 'wrap' } }, t.ahead.months.map(cell)),
      t.ahead.first_gap ? h('div', { class: 'note warn', style: { marginTop: '10px' } }, `From ${fmt.month(t.ahead.first_gap.month)} the rating becomes ${RATING[t.ahead.first_gap.rating][0]}: ${t.ahead.first_gap.reasons.join('; ')}. A leaver\'s end date and a joiner\'s start date are set on the team member.`) : h('div', { class: 'small muted', style: { marginTop: '8px' } }, 'No change in the next six months with the dates entered now.')));
  }
  // the PM confirms the team at each month-end
  const month = statusMonth(); const done = t.reviews.find((r) => r.month === month);
  const note = h('input', { type: 'text', value: done?.note || '', placeholder: 'Joiners, leavers and what they mean for the project (optional)', style: { flex: 1 } });
  if (!ro) root.append(h('div', { class: 'card', style: { marginBottom: '14px' } }, h('div', { class: 'ch' }, h('h2', {}, `Team review for ${fmt.month(month)}`), h('span', { class: 'sp' }), done ? badge(`Confirmed, rated ${RATING[done.rating][0]}`, 'good') : badge('Not confirmed yet', 'warn')),
    h('div', { class: 'small muted', style: { marginBottom: '8px' } }, 'At each month-end, record any joiners and leavers above (with their dates), then confirm the team. The rating at that moment is kept with your note.'),
    h('div', { class: 'row', style: { gap: '8px' } }, note, h('button', { class: 'btn', onclick: async () => { await api.put(p('/project-team/review'), { month, note: note.value }); toast('Team confirmed for ' + fmt.month(month)); render(); } }, done ? 'Confirm again' : 'Confirm the team')),
    t.reviews.length > (done ? 1 : 0) ? h('div', { class: 'tw', style: { marginTop: '10px' } }, h('table', { class: 't nogroup notools' }, h('thead', {}, h('tr', {}, ['Month', 'Rating', 'Note', 'By'].map((x) => h('th', {}, x)))),
      h('tbody', {}, t.reviews.map((r) => h('tr', {}, h('td', {}, fmt.month(r.month)), h('td', {}, badge(RATING[r.rating]?.[0] || r.rating, RATING[r.rating]?.[1] || '')), h('td', { class: 'small wrap' }, r.note || ''), h('td', { class: 'small muted' }, r.by || '')))))) : null));
  root.append(h('div', { class: 'card', style: { marginBottom: '14px' } }, h('div', { class: 'ch' }, h('h2', {}, 'Team chart')), chartSvg(t, ro)));
  if (isDirector()) await competencyCard(root);

  // role by role
  const rows = [];
  t.rows.forEach((r) => {
    const mem = r.members.length ? r.members : [null];
    mem.forEach((m, i) => rows.push(h('tr', { class: r.role_key !== 'pm' && m?.id ? 'click' : '', onclick: r.role_key !== 'pm' && m?.id && !ro ? () => slotDialog(t, m) : null },
      h('td', {}, i ? '' : h('b', {}, r.role)), h('td', { class: 'small' }, i ? '' : (r.required ? r.required.label : h('span', { class: 'muted' }, 'set by the baseline'))),
      h('td', {}, m?.person ? [m.person, m.ecf ? h('div', { class: 'small muted', title: m.ecf.text }, `${m.ecf.role} (L${m.ecf.level})${m.ecf.title ? ', ' + m.ecf.title : ''}`) : null, m.leaving_date ? h('div', { class: 'small warn' }, 'Leaves ' + fmt.date(m.leaving_date)) : m.serving_notice ? h('div', { class: 'small warn' }, 'Serving notice, last day not recorded') : null] : h('span', { class: 'muted' }, m ? m.status_label : 'Nobody yet')),
      h('td', { class: 'small' }, m ? [m.level ? (r.level_labels[m.level] || `Level ${m.level}`) + (m.level_source === 'ECF' ? ' (from the classification)' : '') : '', m.start_date || m.end_date ? ` ${m.start_date ? 'from ' + fmt.date(m.start_date) : ''}${m.end_date ? ' until ' + fmt.date(m.end_date) : ''}` : ''] : ''),
      h('td', {}, m && m.role_key !== 'pm' ? badge(m.status_label, m.status === 'selected' ? 'good' : 'warn') : ''),
      h('td', {}, i ? '' : badge(FIT[r.fit][0], FIT[r.fit][1])),
      h('td', { class: 'nowrap' }, ro ? null : r.role_key === 'pm' ? (i ? '' : h('a', { class: 'small', onclick: () => go('setup', { step: 'project' }) }, 'Set on Project setup')) : (i ? null : h('button', { class: 'btn ghost sm', onclick: (e) => { e.stopPropagation(); slotDialog(t, { role_key: r.role_key }); } }, '+ Add'))))));
  });
  root.append(h('div', { class: 'card' }, h('h2', {}, 'Role by role'),
    h('div', { class: 'tw' }, h('table', { class: 't nogroup notools' }, h('thead', {}, h('tr', {}, ['Role', 'Asked for', 'Person', 'Their level for this role', 'Status', 'Fit', ''].map((x) => h('th', {}, x)))), h('tbody', {}, rows))),
    h('div', { class: 'small muted', style: { marginTop: '8px' } }, 'Levels for the Project Engineer, Design Manager, Construction Manager, Test & Commissioning, Project Controls and Project Coordinator roles run 1 to 4 and read like the columns of the requirement table (1 = the C1 wording, 4 = the C4 wording). The Project Manager uses PM Level 1 to 5 (EPEC-PM-FW-0002).')));
}

// the team chart: director, PM, then the other roles in a row; the colour of a box is its fit
function chartSvg(t, ro) {
  const W = 156; const H = 82; const GAP = 14;
  const boxes = []; t.rows.filter((r) => r.role_key !== 'pm').forEach((r) => { (r.members.length ? r.members : [null]).forEach((m) => boxes.push({ r, m })); });
  const total = Math.max(boxes.length * W + (boxes.length - 1) * GAP, 460); const left = 10;
  const svg = sv('svg', { viewBox: `0 0 ${total + 20} 300`, width: Math.max(total + 20, 700), height: 300, style: 'max-width:none' });
  const box = (x, y, role, person, sub, fit, onClick, tag) => {
    const g = sv('g', { style: onClick ? 'cursor:pointer' : '' });
    g.append(sv('rect', { x, y, width: W, height: H, rx: 10, fill: '#fff', stroke: COLOUR[fit] || '#9aa9b3', 'stroke-width': 2.4, 'stroke-dasharray': fit === 'not_required' || fit === 'no_band' ? '5 4' : null }),
      sv('text', { x: x + 10, y: y + 18, 'font-size': 10.5, fill: '#5d7080' }, role.length > 26 ? role.slice(0, 25) + '…' : role),
      sv('text', { x: x + 10, y: y + 40, 'font-size': 13, 'font-weight': 700, fill: person ? '#102361' : '#9aa9b3' }, (person || 'Nobody yet').slice(0, 20)),
      sv('text', { x: x + 10, y: y + 58, 'font-size': 10.5, fill: '#335062' }, (sub || '').length > 25 ? sub.slice(0, 24) + '\u2026' : (sub || ''), ),
      sv('text', { x: x + 10, y: y + 73, 'font-size': 10, 'font-weight': 700, fill: COLOUR[fit] || '#9aa9b3' }, tag ?? FIT[fit][0]));
    if (onClick) g.onclick = onClick;
    return g;
  };
  const cx = left + total / 2 - W / 2;
  const pmRow = t.rows.find((r) => r.role_key === 'pm'); const pm = pmRow.members[0];
  svg.append(sv('line', { x1: cx + W / 2, y1: 92, x2: cx + W / 2, y2: 110, stroke: '#9aa9b3', 'stroke-width': 2 }));
  svg.append(sv('line', { x1: cx + W / 2, y1: 192, x2: cx + W / 2, y2: 208, stroke: '#9aa9b3', 'stroke-width': 2 }));
  svg.append(box(cx, 10, 'Project Director', t.project.director, 'Sets the complexity baseline', 'no_band', null, ''));
  svg.append(box(cx, 110, 'Project Manager', pm.person, pm.ecf ? `${pm.ecf.role} (L${pm.ecf.level})` : pm.level ? pmRow.level_labels[pm.level] : '', pmRow.fit, null));
  const x0 = left; const bus = 208;
  if (boxes.length > 1) svg.append(sv('line', { x1: x0 + W / 2, y1: bus, x2: x0 + (boxes.length - 1) * (W + GAP) + W / 2, y2: bus, stroke: '#9aa9b3', 'stroke-width': 2 }));
  boxes.forEach(({ r, m }, i) => {
    const x = x0 + i * (W + GAP);
    svg.append(sv('line', { x1: x + W / 2, y1: bus, x2: x + W / 2, y2: 218, stroke: '#9aa9b3', 'stroke-width': 2 }));
    const fit = m ? (m.status === 'selected' && m.person ? (m.level ? (r.required && r.required.level && m.level < r.required.level ? 'below' : 'meets') : 'unrated') : 'vacant') : r.fit;
    svg.append(box(x, 218, r.role, m?.person, m ? (m.ecf ? `${m.ecf.role} (L${m.ecf.level})` : m.level ? (r.level_labels[m.level] || '') : m.status_label) : (r.required ? r.required.label : ''), r.fit === 'not_required' && !m ? 'not_required' : fit, ro ? null : () => slotDialog(t, m?.id ? m : { role_key: r.role_key })));
  });
  return h('div', { style: { overflowX: 'auto' } }, svg);
}

function slotDialog(t, s) {
  const isNew = !s.id;
  const roles = t.rows.filter((r) => r.role_key !== 'pm');
  const role = select(roles.map((r) => [r.role_key, r.role]), s.role_key || 'pe');
  const person = lookup('employee', s.person || '', { placeholder: 'Type to search the employees, or a new name' });
  const status = select([['selected', 'Selected'], ['recruitment', 'Recruitment'], ['tbc', 'To be confirmed']], s.status || 'selected');
  const start = h('input', { type: 'date', value: s.start_date || '' }); const end = h('input', { type: 'date', value: s.end_date || '' });
  const note = h('input', { type: 'text', value: s.note || '', placeholder: 'Optional' });
  const levelBox = h('div'); let level = s.level || '';
  const drawLevel = () => {
    const r = roles.find((x) => x.role_key === role.value);
    const sel = select([['', '(use the classification, else not recorded)'], ...Object.entries(r.level_labels).map(([k, v]) => [k, `${k} · ${v}`])], level);
    sel.onchange = () => { level = sel.value; };
    clear(levelBox).append(field('Their level for this role', sel, r.required ? `Asked for: ${r.required.label}` : 'The band sets what is asked for'));
  };
  role.onchange = drawLevel; drawLevel();
  modal({ title: isNew ? 'Add a team member' : `${s.role}: ${s.person || s.status_label}`, body: h('div', { class: 'grid' }, h('div', { class: 'grid g3' }, field('Role', role), field('Person', person), field('Status', status)),
    levelBox, h('div', { class: 'grid g3' }, field('In post from', start), field('Until', end, 'A leaver: the role counts as empty after this date'), field('Note', note))),
  actions: [...(isNew ? [] : [{ label: 'Remove', kind: 'ghost', onClick: async () => { if (!(await confirmBox('Remove this person from the project team?', 'Remove', true))) return false; await api.del(p(`/project-team/slots/${s.id}`)); toast('Removed'); render(); } }]),
    { label: 'Cancel', kind: 'ghost', onClick: () => {} },
    { label: 'Save', onClick: async () => { await api.put(p('/project-team/slots'), { id: s.id, role_key: role.value, person_name: person.querySelector('input').value, status: status.value, level, start_date: start.value, end_date: end.value, note: note.value }); toast('Saved'); render(); } }] });
}

// For the director: the PM's level in each complexity dimension against what the baseline asks of the PM (Complexity Matrix levels). It shows the
// director's dimension scores, so the PM does not get it.
async function competencyCard(root) {
  const c = await api.get(p('/pm-competency')).catch(() => null);
  if (!c || !c.director) return;
  const FITS = { meets: ['Meets', 'good'], above: ['Above', 'good'], below: ['Below', 'bad'], unrated: ['No level', 'warn'], no_level: ['Matrix names no level', ''] };
  if (!c.ready) { root.append(h('div', { class: 'card', style: { marginBottom: '14px' } }, h('h2', {}, 'PM competency by dimension'), h('div', { class: 'small muted' }, c.reason || 'Set the baseline and name the project manager first.'))); return; }
  const rbox = h('div', { style: { height: '400px' } });
  const asks = (r) => (r.asked ? (r.asked[0] === r.asked[1] ? 'L' + r.asked[0] : 'L' + r.asked[0] + ' to ' + r.asked[1]) : '');
  root.append(h('div', { class: 'card', style: { marginBottom: '14px' } }, h('div', { class: 'ch' }, h('h2', {}, `${c.pm}: competency against the project's dimensions`), h('span', { class: 'sp' }),
    c.gaps ? badge(`${c.gaps} below`, 'bad') : badge('No dimension below', 'good')),
    h('div', { class: 'small muted', style: { marginBottom: '8px' } }, "What the baseline asks in each dimension comes from the Complexity Matrix (the PM level written for the dimension's band; the lowest level is the minimum). The PM level in a dimension is set on their card, otherwise their overall PM level. This is for you: it does not change the team rating, and the PM does not see it."),
    h('div', { class: 'grid g2' }, h('div', { class: 'tw' }, h('table', { class: 't nogroup notools' }, h('thead', {}, h('tr', {}, ['Dimension', 'Score', 'Asks (PM level)', 'PM level', 'Fit'].map((x) => h('th', {}, x)))),
      h('tbody', {}, c.rows.map((r) => h('tr', {}, h('td', {}, r.label), h('td', { class: 'small' }, `${r.score} (${r.band})`), h('td', {}, asks(r)),
        h('td', {}, r.level ? 'L' + r.level + (r.source === 'set' ? '' : ' (overall)') : ''), h('td', {}, badge(FITS[r.fit][0], FITS[r.fit][1]))))))), rbox)));
  setTimeout(() => {
    const sc = (f) => Object.fromEntries(c.rows.filter((r) => f(r) != null).map((r) => [r.key, { score: f(r) }]));
    radar(rbox, c.rows.map((r) => ({ key: r.key, label: r.label })), [{ label: 'Asked (lowest level)', scores: sc((r) => (r.asked ? r.asked[0] : null)), colour: PALETTE[0], dashed: true }, { label: c.pm, scores: sc((r) => r.level), colour: PALETTE[1] }]);
  }, 30);
}


// The resourcing paper's Authorisation rows and Approval row. Names are filled from the project and from business titles; the approver is yours to choose
// (GM Projects is vacant since the 21/10/2026 re-organisation, so it is not assumed).
async function signoffDialog() {
  const s = await api.get(p('/project-team/signoff'));
  const rows = s.authorisers.map((a) => ({ ...a }));
  const approver = { ...s.approver };
  const box = h('div');
  const draw = () => {
    clear(box).append(h('h3', { style: { margin: '0 0 6px' } }, 'Authorisation'),
      ...rows.map((r, i) => h('div', { class: 'row', style: { gap: '8px', marginBottom: '6px' } },
        h('input', { type: 'text', value: r.role, placeholder: 'Role', style: { flex: 1 }, oninput: (e) => { r.role = e.target.value; } }),
        (() => { const l = lookup('employee', r.name || '', { placeholder: 'Name', onPick: (n) => { r.name = n; } }); l.querySelector('input').addEventListener('input', (e) => { r.name = e.target.value; }); return l; })(),
        h('button', { class: 'btn ghost sm', onclick: () => { rows.splice(i, 1); draw(); } }, 'x'))),
      h('button', { class: 'btn ghost sm', onclick: () => { rows.push({ role: '', name: '' }); draw(); } }, '+ Add a row'),
      h('h3', { style: { margin: '14px 0 6px' } }, 'Approval'),
      h('div', { class: 'row', style: { gap: '8px' } }, h('input', { type: 'text', value: approver.role, placeholder: 'Approver role (for example Head of Delivery)', style: { flex: 1 }, oninput: (e) => { approver.role = e.target.value; } }),
        (() => { const l = lookup('employee', approver.name || '', { placeholder: 'Name', onPick: (n) => { approver.name = n; } }); l.querySelector('input').addEventListener('input', (e) => { approver.name = e.target.value; }); return l; })()),
      s.saved ? h('div', { class: 'small muted', style: { marginTop: '8px' } }, 'Saved for this project.') : h('div', { class: 'small muted', style: { marginTop: '8px' } }, 'Filled in from the project and from business titles. Saving keeps these rows for this project.'));
  };
  draw();
  modal({ title: 'Resourcing paper: sign-off', body: box, actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} }, { label: 'Save', onClick: async () => { await api.put(p('/project-team/signoff'), { authorisers: rows, approver }); toast('Saved'); } }] });
}
