import { h, clear, modal, toast, field, badge, fmt } from '../ui.js';
import { api } from '../api.js';

// PMO > Classification framework: the EPEC Classification Framework (EPEC-HR-FW-0001_0) as reference data. The framework is HR's: this page shows it
// (levels 1 to 11 by job family, each role's profile and allowable business titles) and lets HR revise a role's levels and titles. Who holds which
// role is set on the person (Stakeholders, Employees).
let cache = null;
export async function loadEcf(fresh = false) { if (!cache || fresh) cache = await api.get('/api/ecf'); return cache; }

export default async function ecfPage(root) {
  const d = await loadEcf(true);
  const m = d.meta;
  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, 'Classification framework'),
    h('div', { class: 'sub' }, `EPEC Classification Framework ${m.number}, revision ${m.revision}, published ${fmt.date(m.published)}, approved by the ${m.approved_by}. Owned by HR: ${m.titles_note}`))));
  const fams = d.families.filter((f) => d.roles.some((r) => r.family === f.key));
  const rolesAt = (fam, lv) => d.roles.filter((r) => r.family === fam && r.level_from && r.level_from <= lv && lv <= (r.level_to || r.level_from));
  const cell = (fam, lv) => { const rs = rolesAt(fam, lv); return h('td', { style: { verticalAlign: 'top', minWidth: '118px' } }, rs.map((r) => h('div', { class: 'small' }, h('a', { onclick: () => roleDialog(r, d) }, r.name), r.level_to && r.level_to !== r.level_from ? h('span', { class: 'muted' }, ` (${r.level_from} to ${r.level_to})`) : null))); };
  root.append(h('div', { class: 'card' }, h('h2', {}, 'Levelling'), h('div', { class: 'tw' }, h('table', { class: 't nogroup notools' },
    h('thead', {}, h('tr', {}, h('th', {}, 'Level'), ...fams.map((f) => h('th', {}, f.name)))),
    h('tbody', {}, [11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1].map((lv) => h('tr', {}, h('td', {}, h('b', {}, String(lv))), ...fams.map((f) => cell(f.key, lv))))))),
  h('div', { class: 'small muted', style: { marginTop: '8px' } }, 'Click a role for its profile and allowable business titles. The Senior Construction Manager is shown at level 8 as set by Vincent: it is in the framework\'s allowable titles but not in its levelling table, so HR should confirm it.'),
  d.roles.filter((r) => !r.level_from).length ? h('div', { class: 'small muted', style: { marginTop: '4px' } }, 'No level in the framework: ', d.roles.filter((r) => !r.level_from).map((r) => r.name).join(', '), '.') : null));
}

export function roleDialog(r, d) {
  const prof = r.profile;
  const rows = prof ? [['Key objectives', 'key_objectives'], ['Experience', 'experience'], ['Leadership', 'leadership'], ['Autonomy', 'autonomy'], ['Dimensions', 'dimensions'], ['Qualifications', 'qualifications']] : [];
  const lo = h('input', { type: 'number', min: 1, max: 11, value: r.level_from ?? '' }); const hi = h('input', { type: 'number', min: 1, max: 11, value: r.level_to ?? '' });
  const titles = h('textarea', { rows: 6, style: { width: '100%' } }); titles.value = r.titles.join('\n');
  modal({ title: `${r.name}`, size: 'wide', body: h('div', {},
    h('div', { class: 'row', style: { gap: '10px', marginBottom: '8px' } }, badge(r.family_name), h('span', { class: 'small muted' }, r.level_from ? `Level ${r.level_from}${r.level_to && r.level_to !== r.level_from ? ' to ' + r.level_to : ''}` : 'No level in the framework')),
    prof ? h('div', { class: 'tw' }, h('table', { class: 't nogroup notools' }, h('tbody', {}, rows.map(([l, k]) => h('tr', {}, h('td', { style: { width: '150px' } }, h('b', {}, l)), h('td', { class: 'small' }, prof[k] || ''))))))
      : h('div', { class: 'small muted' }, 'The profile of this role is not loaded in PMT yet: see the framework (EPEC-HR-FW-0001_0).'),
    h('h3', { style: { margin: '12px 0 4px' } }, 'Revise this role (HR)'),
    h('div', { class: 'grid g4' }, field('Level from', lo), field('Level to', hi, 'Only where the role spans two levels')), field('Allowable business titles', titles, 'One per line. Every business title needs HR approval.')),
  actions: [{ label: 'Close', kind: 'ghost', onClick: () => {} }, { label: 'Save revision', onClick: async () => {
    await api.put(`/api/ecf/roles/${r.key}`, { level_from: lo.value, level_to: hi.value, titles: titles.value.split('\n') }); await loadEcf(true); toast('Saved'); location.reload(); } }] });
}
