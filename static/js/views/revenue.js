import { h, clear, fmt, modal, toast, field, select, table, num, calc, confirmBox, badge, tabs, empty, todayISO, fillHandle } from '../ui.js';
import { api, state, p, loadRows, pref, statusMonth } from '../api.js';
import { go, render, openIn } from '../app.js';
import { monthInput } from '../monthplan.js';
import { outlineState, outlineStrip, visible as olVisible, MONTH_LEVELS } from '../outline.js';

// Download the claim as a PDF: the user chooses the file name first (the project, claim number and month are suggested)
function claimPdfDialog(c) {
  const pr = state.project || {};
  const suggest = [pr.number || pr.code, pr.name, 'Progress claim', c.claim_no, c.period ? fmt.month(c.period) : ''].filter(Boolean).join(' ').replace(/[\\/:*?"<>|]+/g, ' ').replace(/\s+/g, ' ').trim();
  const name = h('input', { type: 'text', value: suggest, style: { width: '100%' } });
  modal({ title: 'Download the claim as a PDF', body: h('div', {}, field('File name', name, 'Without .pdf; it is added for you'), h('div', { class: 'small muted' }, 'The PDF carries the EPEC logo, EPEC and client project details and every line of the claim.')),
    actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} }, { label: 'Download', onClick: () => { window.open(p(`/claims/${c.id}.pdf?name=${encodeURIComponent(name.value.replace(/\.pdf$/i, ''))}`)); } }] });
  setTimeout(() => { name.focus(); name.select(); }, 50);
}

export default async function revenue(root, params) {
  const tab = params.tab || 'contract';
  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, 'Contract and claims'), h('div', { class: 'sub' }, 'The revenue side: contract value, the claim schedule, progress claims to the client and their reconciliation to Pronto.'))));
  const parent = !!state.project?.is_parent;   // a parent has no claims of its own: the contract value total only
  root.append(tabs(parent ? [['contract', 'Contract value']] : [['contract', 'Contract value'], ['schedule', 'Claim schedule'], ['claims', 'Progress claims'], ['pronto', 'Pronto reconciliation']], parent ? 'contract' : tab, (k) => go('revenue', { tab: k })));
  const body = h('div'); root.append(body);
  if (tab === 'contract' || parent) await contractEditor(body, { only: params.only });
  else if (tab === 'schedule') await scheduleTab(body);
  else if (tab === 'claims') await claimsTab(body, params);
  else await pronto(body);
}

// nested rows: a top-level group is the grandparent, then parent and sub-group (EPEC colours in app.css)
const nestClass = (i) => (i.is_leaf ? '' : ['gp', 'par'][i.depth || 0] || 'par2');
const STATUS = [['offered', 'Offered'], ['confirmed', 'Confirmed'], ['cancelled', 'Cancelled']];
const VSTATUS = [['approved', 'Approved'], ['pending', 'Pending'], ['declined', 'Declined']];
const statusOpts = (kind) => (kind === 'variation' ? VSTATUS : STATUS);
const kpi = (l, v, s = '', c = '') => h('div', { class: 'kpi ' + c }, h('div', { class: 'l' }, l), h('div', { class: 'v' }, v), s ? h('div', { class: 's' }, s) : null);

// ---- import a client claim schedule from Excel, whatever its layout ---------------------------------
export function scheduleImport() {
  const file = h('input', { type: 'file', accept: '.xlsx,.xlsm', class: 'hide' });
  file.onchange = async () => {
    if (!file.files[0]) return;
    try { const r = await api.upload(p('/schedule/analyse'), file.files[0]); previewDialog(r); } catch (e) { toast(e.message, 'bad'); }
  };
  document.body.append(file); file.click(); setTimeout(() => file.remove(), 60000);
}

function previewDialog(r) {
  const c = r.counts;
  const kpi2 = (l, v, sub) => h('div', { class: 'kpi' }, h('div', { class: 'l' }, l), h('div', { class: 'v', style: { fontSize: '17px' } }, v), sub ? h('div', { class: 's' }, sub) : null);
  const H = r.history;                      // the file has month columns: claims made, this month's claim, the forecast
  const modes = [['merge', 'Update matching items and add the rest'], ['replace', 'Replace the whole current schedule']];
  if (H) modes.push(['overwrite', 'Overwrite the claim schedule and claims with this file']);
  const mode = select(modes, H && !r.existing_items && !r.existing_claims ? 'overwrite' : r.existing_items ? 'merge' : 'replace');
  const overNote = () => `Everything in the claim schedule${r.existing_claims ? ` and the ${r.existing_claims} claim${r.existing_claims === 1 ? '' : 's'}` : ''} now in this project is replaced by this file: months before ${fmt.month(H.status_month)} become ${H.n_claims} claims already made, ${fmt.month(H.status_month)} becomes this month's draft claim, and later months are the forecast. Undo is on Project setup.`;
  const note = h('div', { class: 'small muted', style: { marginTop: '6px' } });
  // are the schedule's variations and optional prices part of the original contract value, or on top of it?
  const varIn = select([['0', 'Not in the original contract value: added on top (revised value)'], ['1', 'Already in the original contract value']], '0');
  const optIn = select([['1', 'In the original contract value: one not taken (cancelled) is deducted from the revised value'], ['0', 'Not in the original contract value: added on top once taken']], '1');
  const asks = h('div', { class: 'grid g2', style: { marginTop: '12px', gap: '14px' } },
    r.totals.variation ? field(`Variations in this schedule (${fmt.money(r.totals.variation)})`, varIn, 'Decides whether they count in the original or only in the revised contract value') : null,
    r.totals.optional ? field(`Optional prices in this schedule (${fmt.money(r.totals.optional)})`, optIn, 'An option included at award and cancelled later comes off the revised value') : null);
  const sync = () => { note.textContent = !r.existing_items ? 'The project has no schedule yet, so everything is added.' : mode.value === 'merge' ? 'Items match on item number and description. Existing claims are untouched.' : r.claim_lines ? `Not available: ${r.claim_lines} claim lines already refer to the current schedule.` : 'The current schedule is removed first. Items from the variation register are kept.'; };
  const syncAll = () => { sync(); if (mode.value === 'overwrite' && H) note.textContent = overNote(); }; mode.onchange = syncAll; syncAll();
  const maprows = Object.entries(r.columns).map(([k, v]) => ({ k, v }));
  const first = r.months.length ? `${fmt.month(r.months[0])} to ${fmt.month(r.months[r.months.length - 1])}` : 'none found';
  const histBlock = H ? h('div', { style: { marginBottom: '12px' } },
    h('h3', { style: { margin: '0 0 6px' } }, `How the months load (status month ${fmt.month(H.status_month)})`),
    h('div', { class: 'grid g3', style: { marginBottom: '8px' } }, kpi2('Claims already made', fmt.money(H.past_total), `${H.n_claims} claims from the months before ${fmt.month(H.status_month)}`), kpi2(`Claim for ${fmt.month(H.status_month)}`, fmt.money(H.current_total), 'Loaded as this month\'s draft claim'), kpi2('Forecast revenue', fmt.money(H.future_total), `Months after ${fmt.month(H.status_month)}`)),
    H.period && H.period.slice(0, 7) !== H.status_month ? h('div', { class: 'note warn', style: { marginBottom: '8px' } }, `The sheet says it is at ${fmt.date(H.period)}, but this project's status date is ${fmt.date(r.project_status_date)}. Months load as claimed up to the project's status month, so check the status date first.`) : null,
    H.unmatched.length ? h('div', { class: 'note warn', style: { marginBottom: '8px' } }, `${H.unmatched.length} claim${H.unmatched.length > 1 ? 's' : ''} in the sheet's register (${H.unmatched.map((u) => '#' + u.no).join(', ')}) did not match any month's total, so they were not used.`) : null,
    H.claimed_column !== null && Math.abs(H.claimed_column - H.past_total) > 5 ? h('div', { class: 'note warn', style: { marginBottom: '8px' } }, `The sheet's claimed-to-date column adds to ${fmt.money(H.claimed_column)}, the past months to ${fmt.money(H.past_total)}.`) : null,
    r.existing_claims ? h('div', { class: 'note bad', style: { marginBottom: '8px' } }, `Overwrite deletes the ${r.existing_claims} claim${r.existing_claims === 1 ? '' : 's'} already in this project.`) : null,
    table([{ label: 'Claim', f: (x) => 'CLAIM' + String(x.no).padStart(3, '0') }, { label: 'Month', f: (x) => x.months.map((m) => fmt.month(m)).join(', ') }, { label: 'Amount', r: 1, f: (x) => fmt.money(x.total) }, { label: 'Submitted', f: (x) => fmt.date(x.submitted) }, { label: 'Invoice', f: (x) => x.inv_ref || '' },
      { label: 'Status', f: (x) => badge(x.approved ? 'certified' : 'submitted', x.approved ? 'navy' : 'warn') }, { label: '', f: (x) => (x.note ? h('span', { class: 'muted small' }, x.note) : '') }], H.claims, { maxHeight: '22vh' })) : null;
  const body = h('div', {},
    h('div', { class: 'note', style: { marginBottom: '10px' } }, `Read sheet "${r.sheet}", header on row ${r.header_row}. Check that the columns below were matched correctly before importing.`),
    h('div', { class: 'grid g4', style: { marginBottom: '12px' } }, kpi2('Claim items', fmt.n(c.items), `${fmt.n(c.groups)} groups`), kpi2('With monthly amounts', fmt.n(c.with_monthly), first), kpi2('With dates', fmt.n(c.with_dates)),
      kpi2('Value by section', Object.entries(r.totals).map(([k, v]) => `${k} ${fmt.m(v)}`).join(' | ') || 'none')),
    h('div', { style: { marginBottom: '12px' } }, field('How to load it', mode), note),
    histBlock,
    h('div', { style: { maxWidth: '520px' } }, table([{ label: 'Tool field', f: (x) => x.k }, { label: 'Your column', f: (x) => x.v }], maprows)),
    (r.totals.variation || r.totals.optional) ? asks : null,
    r.grid ? h('div', { class: 'note', style: { marginTop: '12px' } }, h('b', {}, 'Claim schedule grid (Claimed | Approved per month). '),
      `${r.grid.claim_months} month(s) up to the status month become progress claims to the client: ${fmt.money(r.grid.claimed)} claimed, ${fmt.money(r.grid.approved)} approved. `,
      `${r.grid.plan_months} later month(s) become the planned claims. Existing claims for those months are updated, not duplicated.`) : null,
    r.n_warnings ? h('div', { style: { marginTop: '12px' } }, h('h3', { style: { margin: '0 0 6px' } }, `Worth a look (${r.n_warnings})`), table([{ label: 'Row', f: (x) => x.row }, { label: 'Note', cls: 'wrap', f: (x) => x.text }], r.warnings, { maxHeight: '18vh' })) : h('div', { class: 'note good', style: { marginTop: '12px' } }, 'Group totals and monthly amounts agree with the item values.'),
    r.duplicate_refs.length ? h('div', { class: 'note warn', style: { marginTop: '10px' } }, `Item numbers used more than once: ${r.duplicate_refs.join(', ')}. They are loaded as separate items.`) : null,
    r.n_skipped ? h('div', { class: 'small muted', style: { marginTop: '10px' } }, `${r.n_skipped} rows were left out because they are totals or section headings: `, r.skipped.slice(0, 6).map((x) => x.text).join('; '), r.n_skipped > 6 ? '...' : '') : null,
    h('h3', { style: { margin: '12px 0 6px' } }, 'First rows as they will load'),
    table([{ label: 'Item', f: (x) => h('span', { class: 'mono', style: { paddingLeft: x.depth * 12 + 'px', fontWeight: x.is_leaf ? 400 : 700 } }, x.ref) }, { label: 'Description', cls: 'wrap', f: (x) => x.description }, { label: 'Stage', f: (x) => x.stage || '' },
      { label: 'Section', f: (x) => x.kind }, { label: 'Start', f: (x) => fmt.date(x.start) }, { label: 'End', f: (x) => fmt.date(x.end) }, { label: 'Value', r: 1, f: (x) => (x.is_leaf ? fmt.money(x.value) : '') }], r.sample, { maxHeight: '26vh', rowClass: (x) => (x.is_leaf ? '' : 'par') }));
  modal({ title: 'Import claim schedule', size: 'wide', body, actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} },
    { label: 'Import', onClick: async () => {
      if (mode.value === 'overwrite' && r.existing_claims && !(await confirmBox(`Overwrite the claim schedule? This deletes the ${r.existing_claims} claim${r.existing_claims === 1 ? '' : 's'} in this project and loads the file's instead. You can undo it from Project setup.`, 'Overwrite', true))) return false;
      const res = await api.post(p('/schedule/commit'), { token: r.token, filename: r.filename, mode: mode.value, variations_in_original: varIn.value === '1', optionals_in_original: optIn.value === '1' });
      if (mode.value === 'overwrite' && !res.grid) {                 // a plain file with month columns: past months became claims, the status month the draft claim
        toast(`${res.claims_created} claims loaded (${fmt.money(res.past_total)}), ${fmt.month(r.status_month)} claim ${fmt.money(res.current_total)}, forecast ${fmt.money(res.forecast_total)}.`);
        if (res.over_scheduled) toast(`${res.over_scheduled} lines are scheduled for more than their price. The claim schedule shows them; use "Trim the excess" there.`);
        go('revenue', { tab: 'schedule' }); await render(); return;
      }
      toast(`${res.created} items added, ${res.updated} updated, ${fmt.n(res.plan_months)} monthly amounts loaded` + (res.grid ? `; ${res.grid.claims_created} claims created, ${res.grid.claim_lines} claim lines, ${res.grid.plan_months} planned months` : ''));
      if (res.grid?.not_found?.length) toast(`Not matched to a payment milestone: ${res.grid.not_found.slice(0, 6).join(', ')}`, 'bad');
      if (res.optional_taken) toast(`${res.optional_taken} optional items with a value were set to "confirmed". Review their status on this page.`);
      await render(); } }] });
}

// Collapse / expand the contract items tree (same as cost control and the CBS): level buttons plus an arrow per group.
// Shared by the Contract value and Claim schedule tabs; what is open is remembered for the session.
function itemTree(items, redraw) {
  const byId = new Map(items.map((i) => [i.id, i]));
  const hasKids = new Set(items.filter((i) => i.parent_id != null).map((i) => i.parent_id));
  const maxLevel = Math.max(1, ...items.map((i) => (i.depth || 0) + 1));
  let saved = null; try { saved = JSON.parse(sessionStorage.getItem('revExp') || 'null'); } catch (e) { /* ignore */ }
  const lv0 = +pref('rev_level');  // Settings > Your defaults
  const open = new Set(saved || items.filter((i) => hasKids.has(i.id) && (!lv0 || (i.depth || 0) + 1 < lv0)).map((i) => i.id));
  let level = +(sessionStorage.getItem('revLvl') || lv0 || 0);
  const keep = () => { try { sessionStorage.setItem('revExp', JSON.stringify([...open])); sessionStorage.setItem('revLvl', String(level)); } catch (e) { /* ignore */ } };
  const visible = (i) => { let p = byId.get(i.parent_id); while (p) { if (!open.has(p.id)) return false; p = byId.get(p.parent_id); } return true; };
  const chips = h('span', { class: 'row', style: { gap: '6px' } }, h('span', { class: 'small muted' }, 'Expand to'),
    ...Array.from({ length: Math.min(5, maxLevel) }, (_, k) => k + 1).map((n) => h('span', { class: 'chip' + (level === n ? ' on' : ''), onclick: () => {
      level = n; open.clear(); items.forEach((i) => { if (hasKids.has(i.id) && (i.depth || 0) < n - 1) open.add(i.id); }); keep(); redraw(); } }, `Level ${n}`)));
  const ref = (i, text) => h('span', { class: 'mono', style: { paddingLeft: (i.depth || 0) * 14 + 'px', fontWeight: i.is_leaf ? 400 : 700 } },
    h('span', { class: 'tog', style: { cursor: hasKids.has(i.id) ? 'pointer' : 'default', display: 'inline-block', width: '14px' }, onclick: (e) => { if (!hasKids.has(i.id)) return; e.stopPropagation(); open.has(i.id) ? open.delete(i.id) : open.add(i.id); level = 0; keep(); redraw(); } }, hasKids.has(i.id) ? (open.has(i.id) ? '▾' : '▸') : ''), text);
  return { visible, chips: () => { if (maxLevel < 2) return h('span'); chips.querySelectorAll('.chip').forEach((c, k) => c.classList.toggle('on', level === k + 1)); return chips; }, ref };
}

export async function contractEditor(body, opts) {
  const d = await api.get(p('/contract'));
  const s = d.summary;
  body.append(h('div', { class: 'grid g6', style: { marginBottom: '14px' } }, kpi('Original contract', fmt.money(s.original), `Base${s.optional_in_original ? ' + optional prices' : ''}${s.variations_in_original ? ' + variations' : ''}`), kpi('Optional prices', fmt.money(s.optional_taken), [['confirmed', s.optional_confirmed], ['offered', s.optional_offered], ['cancelled', s.optional_cancelled]].filter(([, v]) => v).map(([k, v]) => `${fmt.m(v)} ${k}`).join(' · ') || 'none in the schedule', 't2'),
    kpi('Variations', fmt.money(s.variations_approved), [['approved', s.variations_approved_value], ['pending', s.variations_pending], ['declined', s.variations_declined]].filter(([, v]) => v).map(([k, v]) => `${fmt.m(v)} ${k}`).join(' · ') || 'none yet', 't3'), kpi('Recognised revenue', fmt.money(s.recognised), 'Drives gross margin', 't4'), kpi('Official value', fmt.money(s.official), 'Excludes deed-pending variations', 't5'),
    kpi('Stages', h('div', { style: { fontSize: '15px', lineHeight: '1.35', whiteSpace: 'normal' } }, ...(Object.entries(s.stages).map(([k, v]) => h('div', {}, `${k} ${fmt.m(v)}`)))) , Object.keys(s.stages).length ? '' : 'none', 't6')));
  const b = s.bridge || {};
  const step = (l, v) => (Math.abs(v || 0) > 0.5 ? [` ${v < 0 ? '−' : '+'} ${l} ${fmt.money(Math.abs(v))}`] : []);
  body.append(h('div', { class: 'small muted', style: { margin: '-6px 0 12px' } }, `Original ${fmt.money(b.original)}`,
    ...step('optional prices cancelled', b.optional_not_taken), ...step('optional prices confirmed', b.optional_added), ...step('variations', b.variations_added), ...step('variations declined', b.variations_declined), ...step('other', b.other),
    ` = recognised ${fmt.money(s.recognised)}. Whether an optional price or variation is in the original contract value is set when the claim schedule is imported, or per item.`));
  if (state.project?.is_parent) {   // a parent project reads its children's totals: their payment milestones and claims live in the child projects
    const kids = state.projects.filter((x) => x.parent_project_id === state.pid && !x.archived_at);
    body.append(h('div', { class: 'card' }, h('h2', {}, 'Payment milestones and claims'), h('p', { class: 'muted' }, 'They belong to the child projects. Open one to see or change its payment milestones, claim schedule and claims.'),
      h('div', { class: 'row' }, ...kids.map((k) => h('button', { class: 'btn ghost', onclick: () => openIn(k.id, 'revenue') }, k.name)))));
    return;
  }
  const wrap = h('div', { class: 'card' });
  // a tile opens this list in its own window showing only its part: only = original | optional | variation
  const ONLY = { original: ['In the original contract value', (i) => i.in_orig], optional: ['Optional prices', (i) => i.kind === 'optional'], variation: ['Variations', (i) => i.kind === 'variation'] };
  const only = ONLY[opts.only] ? opts.only : null;
  const all = d.items;
  const keep = new Set();
  if (only) {
    const byId = new Map(all.map((i) => [i.id, i]));
    all.filter((i) => i.is_leaf && ONLY[only][1](i)).forEach((i) => { let x = i; while (x && !keep.has(x.id)) { keep.add(x.id); x = byId.get(x.parent_id); } });
  }
  const items = only ? all.filter((i) => keep.has(i.id)) : all;
  const newKind = only === 'optional' ? 'optional' : only === 'variation' ? 'variation' : 'base';
  if (only) {
    const leaves = items.filter((i) => i.is_leaf && ONLY[only][1](i));
    body.append(h('div', { class: 'note', style: { marginBottom: '10px' } }, h('b', {}, `Showing only: ${ONLY[only][0]}`), ` (${leaves.length} item${leaves.length === 1 ? '' : 's'}, ${fmt.money(leaves.reduce((a, i) => a + (+i.value || 0), 0))}). Add, change or delete them here; the main window updates when you close this one. `,
      h('a', { href: '#/revenue?tab=contract' }, 'Show everything')));
  }
  const tree = itemTree(items, () => draw());
  const draw = () => {
    clear(wrap).append(h('div', { class: 'ch' }, h('h2', {}, only ? `Payment Milestones: ${ONLY[only][0].toLowerCase()}` : 'Payment Milestones'), h('span', { class: 'sp' }), items.length ? tree.chips() : null, h('span', { style: { width: '10px' } }), h('button', { class: 'btn ghost sm', style: { marginRight: '6px' }, title: 'The payment milestones (every field, no months) as an Excel template, to fill in and import back. Blank: hold Shift.', onclick: (e) => window.open(p(`/schedule/template.xlsx${e.shiftKey ? '?blank=1' : ''}`)) }, 'Payment milestones template'), h('button', { class: 'btn ghost sm', style: { marginRight: '10px' }, onclick: () => scheduleImport() }, 'Import payment milestones (Excel)'), h('span', { class: 'small muted' }, 'Child rows use a dotted reference (1.01.02 sits under 1.01). Variations arrive from the register.'), h('button', { class: 'btn sm', onclick: () => edit({ kind: newKind, in_original: only === 'original' ? 1 : null }) }, '+ Add item')),
      items.length ? table([
        { label: 'Ref', f: (i) => tree.ref(i, ro(i, true) ? (i.ref || '') : cell(i, 'ref', 'text', { width: '78px' })) },
        { label: 'Description', f: (i) => (ro(i, true) ? h('span', { style: { fontWeight: i.is_leaf ? 400 : 700 } }, i.description) : cell(i, 'description', 'text', { width: '220px', fontWeight: i.is_leaf ? 400 : 700 })) },
        { label: 'Stage', f: (i) => (ro(i) ? (i.stage || '') : cell(i, 'stage', 'text', { width: '96px' }, { list: 'stages' })) },
        { label: 'Kind', f: (i) => (ro(i) ? badge(i.kind, i.kind === 'variation' ? 'navy' : i.kind === 'optional' ? 'warn' : '') : cell(i, 'kind', [['base', 'base'], ['optional', 'optional'], ['variation', 'variation']])) },
        { label: 'Status', f: (i) => (!i.is_leaf ? '' : i.variation_id ? badge(`${i.status || 'Approved'} (register)`, 'navy') : (i.kind === 'optional' || i.kind === 'variation') ? cell(i, 'optional_status', statusOpts(i.kind)) : '') },
        { label: 'Original contract', title: 'Is this item part of the original contract value?', f: (i) => (ro(i) ? (i.in_orig ? 'included' : 'not included') : cell(i, 'in_original', [['', i.kind === 'variation' ? 'as kind (no)' : 'as kind (yes)'], ['1', 'included'], ['0', 'not included']])) },
        { label: 'Phase', f: (i) => (ro(i) ? (i.phase || '') : cell(i, 'phase', 'text', { width: '110px' })) },
        { label: 'Start', f: (i) => (!i.is_leaf ? '' : ro(i) ? fmt.date(i.start_date) : cell(i, 'start_date', 'date')) },
        { label: 'End', f: (i) => (!i.is_leaf ? '' : ro(i) ? fmt.date(i.end_date) : cell(i, 'end_date', 'date')) },
        { label: 'Phasing', f: (i) => (ro(i) ? '' : cell(i, 'method', [['even', 'even'], ['lump', 'lump sum'], ['manual', 'manual months']])) },
        { label: 'Claim requirement', f: (i) => (ro(i) ? (i.claim_requirement || '') : cell(i, 'claim_requirement', 'text', { width: '170px' })) },
        { label: 'Value', r: 1, f: (i) => (i.is_leaf && !i.variation_id ? cell(i, 'value', 'number', { width: '110px', textAlign: 'right' }) : h('span', { style: { fontWeight: i.is_leaf ? 400 : 700 } }, fmt.money(i.is_leaf ? i.value : i.value_calc))) },
        { label: '', f: (i) => i.variation_id ? h('span', { class: 'muted small' }, 'from register') : h('span', { class: 'row', style: { gap: '4px' } }, h('button', { class: 'btn ghost sm', onclick: (e) => { e.stopPropagation(); edit(i); } }, 'Edit'), h('button', { class: 'btn danger sm', onclick: async (e) => { e.stopPropagation(); if (await confirmBox('Delete this item and its children?', 'Delete', true)) { await api.del(p(`/contract/items/${i.id}`)); await render(); } } }, '×')) }], items.filter(tree.visible),
        { rowClass: nestClass,
          reorder: { group: (i) => i.parent_id ?? null, save: async (ids) => { await api.post(p('/reorder/contract'), { ids }); await render(); } }, foot: (c) => c.label === 'Description' ? (only ? `Total: ${ONLY[only][0].toLowerCase()}` : 'Total recognised') : c.label === 'Value' ? fmt.money(only ? items.filter((i) => i.is_leaf && ONLY[only][1](i)).reduce((a, i) => a + (+i.value || 0), 0) : s.recognised) : '' })
        : only ? empty(`No ${ONLY[only][0].toLowerCase()} yet`, 'Use + Add item above to add one.') : empty('No payment milestones', 'Use + Add item above to enter the proposal price breakdown, or import your payment milestones or claim schedule from Excel (the buttons above).'));
  };
  // the table is a grid: every field of the Edit form is a cell, saved when it changes; drag the small square at the
  // corner of a cell over other rows to give them the same value (as Excel's fill handle)
  const ro = (i, groupEditable) => !!i.variation_id || (!i.is_leaf && !groupEditable);
  const keepScroll = async () => { const y = (document.scrollingElement || document.documentElement).scrollTop; await render(); (document.scrollingElement || document.documentElement).scrollTop = y; };
  const toBody = (i, k, v) => {
    const b = { id: i.id, [k]: k === 'value' ? num(v) : k === 'in_original' ? (v === '' ? null : +v) : (v === '' ? null : v) };
    if (k === 'ref') { if (v && v.includes('.')) b.parent_ref = v.split('.').slice(0, -1).join('.'); else b.parent_id = null; }
    if (k === 'kind' && v !== i.kind) b.optional_status = v === 'optional' ? 'offered' : v === 'variation' ? 'approved' : null;
    return b;
  };
  function cell(i, k, type, style = {}, attrs = {}) {
    const cur = k === 'optional_status' ? (i.status || '') : k === 'in_original' ? (i.in_original == null ? '' : String(i.in_original)) : (i[k] ?? '');
    const el = Array.isArray(type) ? select(type, String(cur)) : h('input', { type, value: k === 'value' ? (Math.round((+cur || 0) * 100) / 100) : cur, step: type === 'number' ? '0.01' : null, ...attrs });
    el.classList.add('gc'); Object.assign(el.style, style);
    el.dataset.id = i.id; el.dataset.field = k;
    el.onclick = (e) => e.stopPropagation();
    el.onchange = async () => { try { await api.post(p('/contract/items'), toBody(i, k, el.value)); await keepScroll(); } catch (e) { toast(e.message, 'bad'); } };
    return el;
  }
  const byIdAll = new Map(all.map((x) => [x.id, x]));
  const fill = async (field, value, ids) => {
    if (field === 'ref') { toast('Item numbers are not filled down: each must be different', 'bad'); return; }
    const src = { value };
    const body = toBody(byIdAll.get(+ids[0]) || {}, field, value); delete body.id;
    try { const r = await api.post(p('/contract/items/bulk'), { ids: ids.map(Number), field, value: body[field], extra: field === 'kind' ? { optional_status: body.optional_status } : null }); toast(`${r.updated} row${r.updated === 1 ? '' : 's'} set to "${src.value || 'blank'}"`); await keepScroll(); } catch (e) { toast(e.message, 'bad'); }
  };
  // change a line's kind or status straight from the table (saved at once)
  function inline(i, k, opts) {
    const sel = select(opts, k === 'optional_status' ? (i.status || opts[0][0]) : i[k]);
    sel.onclick = (e) => e.stopPropagation();
    sel.onchange = async () => {
      const b = { id: i.id, [k]: sel.value };
      if (k === 'kind' && sel.value !== i.kind) b.optional_status = sel.value === 'optional' ? 'offered' : sel.value === 'variation' ? 'approved' : null;
      try { await api.post(p('/contract/items'), b); await render(); } catch (e) { toast(e.message, 'bad'); }
    };
    return sel;
  }
  function edit(i = {}) {
    const f = { ref: h('input', { type: 'text', value: i.ref || '' }), description: h('input', { type: 'text', value: i.description || '' }), stage: h('input', { type: 'text', value: i.stage || '', list: 'stages' }), kind: select(['base', 'optional', 'variation'], i.kind || 'base'), optional_status: select(statusOpts(i.kind), i.status || statusOpts(i.kind)[0][0]),
      value: h('input', { type: 'number', step: '0.01', value: i.value ?? 0 }), phase: h('input', { type: 'text', value: i.phase || '' }), claim_requirement: h('input', { type: 'text', value: i.claim_requirement || '' }), start_date: h('input', { type: 'date', value: i.start_date || '' }), end_date: h('input', { type: 'date', value: i.end_date || '' }), method: select([['even', 'Even across start to end'], ['lump', 'Lump sum in start month'], ['manual', 'Manual months (set on the Claim schedule tab)']], i.method || 'even'),
      in_original: select([['', 'As its kind (base and optional yes, variation no)'], ['1', 'Included in the original contract value'], ['0', 'Not included: on top of it']], i.in_original == null ? '' : String(i.in_original)) };
    f.kind.onchange = () => { const o = statusOpts(f.kind.value); clear(f.optional_status).append(...o.map(([v, l]) => h('option', { value: v }, l))); f.optional_status.disabled = f.kind.value === 'base'; };
    f.optional_status.disabled = (i.kind || 'base') === 'base';
    const dl = h('datalist', { id: 'stages' }, (state.project.settings?.stages || ['Early Works', 'EPC']).map((x) => h('option', { value: x })));
    modal({ title: i.id ? 'Edit item' : 'Add item', size: 'wide', body: h('div', { class: 'grid' }, dl, h('div', { class: 'grid g3' }, field('Ref', f.ref), field('Stage', f.stage), field('Kind', f.kind)), field('Description', f.description), h('div', { class: 'grid g3' }, field('Value (excl. GST)', f.value, 'Leave 0 on a heading row that has children'), field('Status', f.optional_status, 'Optional prices: offered (no answer yet), confirmed or cancelled. Variations: approved, pending or declined. Base scope has none.'), field('Phase', f.phase)),
      h('div', { class: 'grid g3' }, field('Start', f.start_date), field('End', f.end_date), field('Phasing', f.method)), field('Claim requirement', f.claim_requirement), field('Original contract value', f.in_original)),
      actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} }, { label: 'Save', onClick: async () => { const b = { id: i.id }; Object.entries(f).forEach(([k, e]) => (b[k] = k === 'value' ? num(e.value) : k === 'in_original' ? (e.value === '' ? null : +e.value) : (e.value || null))); if (b.ref && b.ref.includes('.')) b.parent_ref = b.ref.split('.').slice(0, -1).join('.'); else b.parent_id = null; await api.post(p('/contract/items'), b); await render(); } }] });
  }
  draw(); fillHandle(wrap, fill); body.append(wrap, h('datalist', { id: 'stages' }, (state.project.settings?.stages || ['Early Works', 'EPC']).map((x) => h('option', { value: x }))));
  if (opts.setup) body.append(h('div', { style: { marginTop: '12px' } }, h('button', { class: 'btn', onclick: () => go('setup', { step: 'cbs' }) }, 'Next: CBS and allowances')));
}

async function scheduleTab(body) {
  const rows0 = await loadRows();
  const grid = rows0.grid; const M = rows0.status_month;
  let d = await api.get(p('/contract'));
  const tplBtns = h('span', { class: 'row', style: { gap: '6px' } },
    h('button', { class: 'btn ghost sm', title: 'The payment milestones with a Claimed | Approved column per month: the claims to date and what the client approved, then the planned claims. Fill it in and import it back.', onclick: () => window.open(p('/schedule/template.xlsx?grid=1')) }, 'Claim schedule template'),
    h('button', { class: 'btn ghost sm', title: 'An empty claim schedule with numbered rows to start from', onclick: () => window.open(p('/schedule/template.xlsx?grid=1&blank=1')) }, 'Blank template'),
    h('button', { class: 'btn ghost sm', onclick: () => scheduleImport() }, 'Import claim schedule (Excel)'));
  if (!d.items.some((i) => i.is_leaf && i.value_calc)) { body.append(h('div', { class: 'row', style: { justifyContent: 'flex-end', marginBottom: '8px' } }, tplBtns), empty('No schedule yet', 'Add the payment milestones first, or fill in the template and import it.')); return; }
  let mode = sessionStorage.getItem('sgMode') || '$';
  const sg = Object.assign({ figs: true }, (() => { try { return JSON.parse(sessionStorage.getItem('sgui') || '{}'); } catch (e) { return {}; } })());
  const sgSave = () => { try { sessionStorage.setItem('sgui', JSON.stringify({ figs: sg.figs })); } catch (e) { /* ignore */ } };
  const ost = outlineState('sg');   // folded quarters and hidden months (kept on this PC)
  const colObjs = () => cols.map((m) => ({ id: m }));
  const plan = () => { const v = olVisible(colObjs(), cols.indexOf(M), ost, MONTH_LEVELS); return cols.map((m, i) => ({ kind: m === M ? 'cur' : 'm', i })).filter((c) => v[c.i]); };   // only the columns that show
  const olHost = h('div'); let olOff = null;
  const tw = h('div', { class: 'tw sg', style: { maxHeight: '64vh' } }); const chipBox = h('span'); const bar = h('div'); const kpis = h('div'); const hintBox = h('div'); const trimBox = h('div');
  const head = h('thead'); const tbody = h('tbody'); const foot = h('tfoot');
  let items = [], leaves = [], cm = {}, cols = [], tree = null, editing = null, target = null, drag = null, busy = false;
  const num2 = (v) => Math.round((+v || 0) * 100) / 100;
  const leftOf = (i) => i.value_calc - i.claimed - scheduled(i);
  const isOver = (i) => (i.value_calc >= 0 ? leftOf(i) < -1 : leftOf(i) > 1);       // a credit line is over when it is credited by more than its price
  const overBy = (i) => (i.value_calc >= 0 ? -leftOf(i) : leftOf(i));
  const mk = (m) => ({ issued: !!cm[m]?.issued, claim: cm[m] });
  function load(data) {
    d = data; cm = d.claim_months || {};
    items = d.items.filter((i) => i.value_calc);
    leaves = items.filter((i) => i.is_leaf);
    const used = grid.filter((m) => leaves.some((i) => i.plan[m] || i.claimed_m[m]));
    const first = used.length ? used[0] : M;
    cols = grid.filter((m) => m >= (first < M ? first : M));
  }
  const amountIn = (i, m) => (mk(m).issued ? (i.claimed_m[m] || 0) : (i.plan[m] || 0));   // what the cell shows: claimed if the month is issued, else scheduled
  const text = (i, v) => (!v ? '' : mode === '%' ? (i.value_calc ? fmt.pct(v / i.value_calc, 1).replace('.0%', '%') : '') : fmt.n(v));
  const scheduled = (i) => cols.reduce((a2, m) => a2 + (mk(m).issued ? 0 : (i.plan[m] || 0)), 0) + Object.entries(i.plan).filter(([m]) => !cols.includes(m) && !mk(m).issued).reduce((a2, [, v]) => a2 + v, 0);
  function parse(t) {
    t = String(t ?? '').trim();
    if (t === '') return { amount: 0 };
    if (/^(rest|remaining|r)$/i.test(t)) return { rest: true };
    const v = calc(t.replace(/\$/g, ''));
    if (v === null) return null;
    if (t.includes('%') || (mode === '%' && !t.includes('$'))) return { pct: v };
    return { amount: v };
  }
  function drawKpis() {
    const claimed = leaves.reduce((a2, i) => a2 + i.claimed, 0); const value = leaves.reduce((a2, i) => a2 + i.value_calc, 0);
    const thisM = leaves.reduce((a2, i) => a2 + amountIn(i, M), 0);
    const fut = leaves.reduce((a2, i) => a2 + Object.entries(i.plan).filter(([m]) => m > M && !mk(m).issued).reduce((x, [, v]) => x + v, 0), 0);
    const sched = leaves.reduce((a2, i) => a2 + scheduled(i), 0);
    const left = value - claimed - sched; const overAmt = leaves.filter(isOver).reduce((a2, i) => a2 + overBy(i), 0);
    kpis.replaceChildren(h('div', { class: 'grid g5', style: { marginBottom: '12px', gridTemplateColumns: 'repeat(5, minmax(0, 1fr))' } },
      kpi('Contract value', fmt.money(value), 'Sum of the payment milestones'), kpi('Claimed to date', fmt.money(claimed), `${fmt.pct(value ? claimed / value : 0, 1)} of the price`, 't2'),
      kpi(`Claim for ${fmt.month(M)}`, fmt.money(thisM), mk(M).issued ? 'Already claimed' : 'Typed in the status month', 't3'),
      kpi('Forecast revenue', fmt.money(fut), `Months after ${fmt.month(M)}`, 't4'), overAmt > 1 ? kpi('Scheduled beyond the price', fmt.money(overAmt), 'Over the cap: trim it below', 't2') : kpi('Not scheduled yet', fmt.money(Math.abs(left) < 0.5 ? 0 : left), Math.abs(left) < 1 ? 'Everything is scheduled' : 'Type it into a month', Math.abs(left) < 1 ? 't3' : 't5')));
  }
  function drawBar() {
    const c = cm[M];
    const over = leaves.filter(isOver);
    trimBox.replaceChildren(over.length ? h('div', { class: 'note warn', style: { marginBottom: '10px', display: 'flex', gap: '12px', alignItems: 'center' } }, h('span', { style: { flex: 1 } }, `${over.length} line${over.length > 1 ? 's are' : ' is'} scheduled for more than ${over.length > 1 ? 'their' : 'its'} price once claims are counted (${fmt.money(over.reduce((a2, i) => a2 + overBy(i), 0))} in all). That overstates forecast revenue.`),
      h('button', { class: 'btn sm', onclick: async () => { const r = await api.post(p('/contract/trim-excess')); toast(`Took ${fmt.money(r.total)} off the latest months of ${r.trimmed.length} line${r.trimmed.length === 1 ? '' : 's'}.${r.stuck.length ? ` ${r.stuck.length} still over because the claims alone exceed the price.` : ''}`); await refresh(); } }, 'Trim the excess from the last months')) : '');
    const pdf = (claim) => h('button', { class: 'btn sm', onclick: () => claimPdfDialog(claim) }, 'PDF'); const xl = (id) => h('button', { class: 'btn ghost sm', onclick: () => window.open(p(`/claims/${id}.xlsx`)) }, 'Excel');
    const thisM = leaves.reduce((a2, i) => a2 + amountIn(i, M), 0);
    bar.replaceChildren(h('div', { class: 'card', style: { padding: '10px 14px', marginBottom: '10px' } }, h('div', { class: 'row' },
      h('b', {}, `Claim for ${fmt.month(M)}`), h('span', { class: 'muted small' }, c ? `${c.claim_no} (${c.status})` : 'not created yet'), h('span', { class: 'sp' }),
      !c ? h('button', { class: 'btn', disabled: !thisM, title: thisM ? '' : 'Type amounts in the status month first', onclick: async () => { const r = await api.post(p('/claims'), { period: M }); go('revenue', { tab: 'claims', claim: r.id }); } }, `Create the ${fmt.month(M)} claim from this column`)
        : [h('button', { class: 'btn', onclick: () => go('revenue', { tab: 'claims', claim: c.id }) }, c.issued ? 'Open the claim' : 'Open the claim to submit'), pdf(c), xl(c.id)])));
  }
  function drawHead() {
    const lab = ['Ref', 'Description', 'Start', 'End', 'Mths', ''].concat(sg.figs ? ['Price', 'Claimed', 'Scheduled', 'Not scheduled'] : []);
    const monthTh = (m) => { const st = mk(m); return h('th', { class: 'mth mhd ' + (st.issued ? 'mca' : m === M ? 'cur' : m > M ? 'mfu' : ''), 'data-col': m, title: st.issued ? `${st.claim.claim_no}: claimed` : m === M ? 'Status month: this is the claim' : m > M ? 'Forecast revenue' : 'Before the status month, not claimed' },
      fmt.month(m),
      m !== M ? h('span', { class: 'hx', title: `Hide ${fmt.month(m)} (a + on the strip above brings it back)`, onclick: (e) => { e.stopPropagation(); ost.hidden = [...new Set([...ost.hidden, m])]; ost.save(); rebuild(); } }, '\u00d7') : null,
      h('div', { style: { fontWeight: 400, fontSize: '9px' } }, st.issued ? 'claimed' : m === M ? 'this claim' : m > M ? 'forecast' : 'unclaimed')); };
    const mths = plan().map((c) => monthTh(cols[c.i]));
    head.replaceChildren(h('tr', {}, lab.map((x, k) => h('th', { class: sg.figs && k >= 6 ? 'r' : k === 4 ? 'r' : '' }, x)), mths));
  }
  function cellView(i, m) {
    const v = amountIn(i, m); const st = mk(m);
    const cls = 'r num ' + (st.issued ? 'cell-a locked' : !i.is_leaf ? '' : m === M ? 'cell-x' : m > M ? 'cell-f' : 'cell-p') + (m === M ? ' cur' : '');
    const td = h('td', { class: cls }, text(i, v));
    if (i.is_leaf && !st.issued) {
      td.dataset.i = i.id; td.dataset.m = m; td.classList.add('edit');
      if (v) { const g = h('span', { class: 'grip grip4', draggable: 'true', title: 'Drag by this grip to the status month or any other month of this line (earlier or later, never the past)' }); g.dataset.i = i.id; g.dataset.m = m; td.prepend(g); }
    } else if (st.issued && v) td.title = `${st.claim.claim_no} (${st.claim.status})`;
    return td;
  }
  // ---- a claim line's window: Start, End, Mths (its unclaimed price is spread over the open months), or linked to the client facing schedule ----
  const monthOf = (d) => String(d || '').slice(0, 7);
  const mdiff = (a, b) => { const [y1, m1] = a.split('-').map(Number); const [y2, m2] = b.split('-').map(Number); return (y2 - y1) * 12 + m2 - m1 + 1; };
  function windowCells(i) {
    if (!i.is_leaf) return [h('td'), h('td'), h('td'), h('td')];
    const lk = i.links || []; const up = lk.filter((x) => x.layer === 'upstream');
    const sIn = monthInput(monthOf(i.start_date)); const eIn = monthInput(monthOf(i.end_date));
    const mIn = h('input', { type: 'number', min: 1, step: 1, value: sIn.ym && eIn.ym ? mdiff(sIn.ym, eIn.ym) : '' });
    [sIn, eIn, mIn].forEach((x) => { x.classList.add('sg-inl'); x.addEventListener('click', (e) => e.stopPropagation()); if (lk.length) { x.classList.add('drv'); x.title = `Follows the ${up.length ? 'client facing' : 'project'} schedule: ${lk.map((t) => t.name).join(', ')}. Type to take it off the schedule.`; } });
    mIn.classList.add('mo'); mIn.title = lk.length ? mIn.title : 'Duration in months: the price not yet claimed is spread over the window';
    async function commit(which) {
      const sv = sIn.ym; const ev = eIn.ym; const m = +mIn.value || 0; let body;
      if (which === 'start') body = ev && (!sv || sv <= ev) ? { start: sv, stop: ev } : { start: sv, months: m || 1 };
      else if (which === 'stop') body = sv && (!ev || sv <= ev) ? { start: sv, stop: ev } : { stop: ev, months: m || 1 };
      else { if (m < 1) return; body = sv ? { start: sv, months: m } : ev ? { stop: ev, months: m } : null; if (!body) return toast('Fill in Start or End first, then the months', 'bad'); }
      try { const o = await api.post(p(`/contract/items/${i.id}/window`), body); if (o.unlinked) toast('This line is no longer linked to the schedule'); await refresh(); } catch (err) { toast(err.message, 'bad'); await refresh(); }
    }
    sIn.addEventListener('change', () => commit('start')); eIn.addEventListener('change', () => commit('stop')); mIn.addEventListener('change', () => commit('months'));
    const link = h('button', { class: 'sg-link' + (lk.length ? ' on' : ''), title: lk.length ? `Linked to: ${lk.map((t) => t.name).join(', ')}` : 'Link to the client facing project schedule', onclick: (e) => { e.stopPropagation(); linkDialog(i); } }, '⛓');
    return [h('td', { class: 'nowrap' }, sIn), h('td', { class: 'nowrap' }, eIn), h('td', {}, mIn), h('td', {}, link)];
  }
  async function linkDialog(i) {
    const tasks = (await api.get(p('/programme/tasks'))).filter((t) => !t.summary);
    if (!tasks.length) { toast('Upload the project schedule first (Setup, Project schedule)', 'bad'); return; }
    const mine = new Set(tasks.filter((t) => t.link_item_id === i.id).map((t) => t.id)); const chosen = new Set(mine); let q = '';
    const list = h('div', { class: 'tw', style: { maxHeight: '46vh' } });
    const draw = () => {
      const shown = tasks.filter((t) => !q || `${t.wbs || ''} ${t.name}`.toLowerCase().includes(q));
      list.replaceChildren(h('table', { class: 't' }, h('thead', {}, h('tr', {}, ['', 'Schedule', 'Task', 'Start', 'Finish', 'Linked to'].map((x) => h('th', {}, x)))),
        h('tbody', {}, shown.map((t) => h('tr', {}, h('td', {}, h('input', { type: 'checkbox', checked: chosen.has(t.id), onchange: (e) => { if (e.target.checked) chosen.add(t.id); else chosen.delete(t.id); } })),
          h('td', { class: 'small' }, (t.layer || 'internal') === 'upstream' ? 'Client facing' : 'Internal'), h('td', {}, `${t.wbs ? t.wbs + ' ' : ''}${t.name}`), h('td', { class: 'nowrap' }, fmt.date(t.start_date)), h('td', { class: 'nowrap' }, fmt.date(t.finish_date)),
          h('td', { class: 'small muted' }, t.link_item_id && t.link_item_id !== i.id ? `${t.item_ref || ''} ${t.item_desc || ''}` : ''))))));
    };
    draw();
    modal({ title: `Link ${i.ref || ''} ${i.description} to the project schedule`, size: 'wide', body: h('div', {},
      h('div', { class: 'note', style: { marginBottom: '8px' } }, 'The line follows the earliest start and latest finish of the tasks you tick, preferring the client facing schedule, and its price not yet claimed is spread over that window. Moving the schedule moves the line. Untick everything to type the window yourself.'),
      h('input', { type: 'search', placeholder: 'Search tasks', style: { width: '260px', marginBottom: '6px' }, oninput: (e) => { q = e.target.value.trim().toLowerCase(); draw(); } }), list),
      actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} }, { label: 'Save link', onClick: async () => {
        for (const t of tasks) { const was = mine.has(t.id); const now = chosen.has(t.id); if (was !== now) await api.put(p(`/programme/tasks/${t.id}`), { link_item_id: now ? i.id : null }); }
        await refresh();
      } }] });
  }
  function drawRows() {
    tbody.replaceChildren(); chipBox.replaceChildren(tree.chips());
    items.filter(tree.visible).forEach((i) => {
      const grp = !i.is_leaf; const sch = grp ? Object.entries(i.plan).filter(([m]) => !mk(m).issued).reduce((a2, [, v]) => a2 + v, 0) : scheduled(i); const left = i.value_calc - i.claimed - sch;
      const wc = windowCells(i);
      const figs = sg.figs ? [h('td', { class: 'r num' }, fmt.money(i.value_calc)), h('td', { class: 'r num' }, fmt.money(i.claimed)), h('td', { class: 'r num' }, fmt.money(sch)),
        h('td', { class: 'r num ' + (Math.abs(left) < 0.5 ? 'good' : (!grp && isOver(i)) ? 'bad' : 'warn') }, Math.abs(left) < 0.5 ? '100%' : fmt.money(left))] : [];
      const tr = h('tr', { class: nestClass(i) }, h('td', {}, tree.ref(i, i.ref || '')), h('td', { style: { fontWeight: grp ? 700 : 400 } }, i.description), ...wc, ...figs);
      plan().forEach((c) => tr.append(cellView(i, cols[c.i])));
      tbody.append(tr);
    });
    const tot = (m) => { const v = leaves.reduce((a2, i) => a2 + amountIn(i, m), 0); return v; };
    const fmtT = (v) => (mode === '%' ? fmt.pct(v / (leaves.reduce((a2, i) => a2 + i.value_calc, 0) || 1), 1) : fmt.n(v));
    const figT = sg.figs ? [...['value_calc', 'claimed'].map((k) => h('td', { class: 'r num' }, fmt.money(leaves.reduce((a2, i) => a2 + i[k], 0)))), h('td', { class: 'r num' }, fmt.money(leaves.reduce((a2, i) => a2 + scheduled(i), 0))),
      h('td', { class: 'r num' }, fmt.money(leaves.reduce((a2, i) => a2 + (i.value_calc - i.claimed - scheduled(i)), 0)))] : [];
    foot.replaceChildren(h('tr', {}, h('td'), h('td', {}, 'Total'), h('td'), h('td'), h('td'), h('td'), ...figT,
      ...plan().map((c) => h('td', { class: 'r num cell-t' }, fmtT(tot(cols[c.i]))))));
    drawKpis(); drawBar();
  }
  function rebuild(keepScroll = true) {
    const sl = tw.scrollLeft, st = tw.scrollTop; drawHead(); drawRows(); if (keepScroll) { tw.scrollLeft = sl; tw.scrollTop = st; }
    if (olOff) { olOff(); olOff = null; }
    const strip = outlineStrip({ cols: colObjs(), cur: cols.indexOf(M), levels: MONTH_LEVELS, st: ost, onChange: () => rebuild(), names: { 1: 'This quarter only', 2: 'Every month' } });
    olHost.replaceChildren(strip.el); const tbl = tw.querySelector('table'); if (tbl) olOff = strip.mount(tw, tbl);
    if (target) { const t = target; target = null; open(t.i, t.m); }
  }
  async function refresh() { load(await api.get(p('/contract'))); rebuild(); }
  // ---- editing: click a month to type; Enter, Tab and the arrow keys move on; a $ or % works anywhere ----
  function cellAt(i, m) { return tbody.querySelector(`td.edit[data-i="${i}"][data-m="${m}"]`); }
  function neighbour(td, dr, dc) {
    if (dr) { const rowsEl = [...tbody.querySelectorAll('tr')]; const tr = td.parentElement; let k = rowsEl.indexOf(tr) + dr; const c = [...tr.children].indexOf(td); while (rowsEl[k]) { const x = rowsEl[k].children[c]; if (x?.classList.contains('edit')) return x; k += dr; } return null; }
    let x = td; do { x = dc > 0 ? x.nextElementSibling : x.previousElementSibling; } while (x && !x.classList.contains('edit'));
    return x;
  }
  function open(i, m) {
    const td = cellAt(i, m); if (!td) return;
    const it = items.find((x) => x.id === +i); const v = amountIn(it, m);
    const shown = !v ? '' : mode === '%' ? String(num2(v / it.value_calc * 100)) + '%' : String(num2(v));
    const inp = h('input', { type: 'text', class: 'sgin', value: shown, placeholder: mode === '%' ? '25%' : '$ or %', autocomplete: 'off' });
    td.replaceChildren(inp); inp.focus(); inp.select();
    editing = { td, inp, i, m, orig: shown, done: false };
    inp.addEventListener('keydown', (e) => {
      const go2 = (dr, dc) => { e.preventDefault(); finish(neighbour(td, dr, dc)); };
      if (e.key === 'Enter' || e.key === 'ArrowDown') go2(1, 0); else if (e.key === 'ArrowUp') go2(-1, 0); else if (e.key === 'Tab') go2(0, e.shiftKey ? -1 : 1);
      else if (e.key === 'Escape') { e.preventDefault(); editing.done = true; editing = null; rebuild(); }
    });
    inp.addEventListener('blur', () => { if (editing && editing.inp === inp && !editing.done) finish(null); });
  }
  async function finish(next) {
    const e = editing; if (!e || e.done) return; e.done = true; editing = null;
    if (next) target = { i: next.dataset.i, m: next.dataset.m };
    const t = e.inp.value.trim();
    if (t === e.orig) { rebuild(); return; }
    const parsed = parse(t);
    if (!parsed) { toast('Type an amount, a percentage such as 25%, or "rest" for whatever is left.', 'bad'); rebuild(); return; }
    busy = true;
    try { await api.put(p(`/contract/items/${e.i}/cell`), { month: e.m, ...parsed }); } catch (err) { toast(err.message, 'bad'); }
    try { await refresh(); } finally { busy = false; }
  }
  tbody.addEventListener('click', (e) => {
    if (elOf(e)?.closest('.grip')) return;
    const td = elOf(e)?.closest('td.edit'); if (!td || td.querySelector('input')) return;
    if (editing || busy) { target = { i: td.dataset.i, m: td.dataset.m }; return; }   // the open cell saves first, then this one opens
    open(td.dataset.i, td.dataset.m);
  });
  const elOf = (e) => (e.target && e.target.nodeType === 1 ? e.target : e.target?.parentElement);   // a drag can start or end on a text node
  // ---- drag a value to a later month of the same line ----
  tbody.addEventListener('dragstart', (e) => { const g = elOf(e)?.closest('.grip'); if (!g) return; drag = { i: g.dataset.i, m: g.dataset.m }; e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', `${g.dataset.i}|${g.dataset.m}`); g.closest('td').classList.add('dragging'); });
  tbody.addEventListener('dragend', () => { drag = null; tbody.querySelectorAll('.dragging,.dropok').forEach((x) => x.classList.remove('dragging', 'dropok')); });
  tbody.addEventListener('dragover', (e) => { const td = elOf(e)?.closest('td.edit'); if (!drag || !td || td.dataset.i !== drag.i || td.dataset.m === drag.m || td.dataset.m < M) return; e.preventDefault(); e.dataTransfer.dropEffect = 'move'; });
  tbody.addEventListener('dragenter', (e) => { const td = elOf(e)?.closest('td.edit'); tbody.querySelectorAll('.dropok').forEach((x) => x.classList.remove('dropok')); if (drag && td && td.dataset.i === drag.i && td.dataset.m !== drag.m && td.dataset.m >= M) td.classList.add('dropok'); });
  tbody.addEventListener('drop', async (e) => {
    const td = elOf(e)?.closest('td.edit'); if (!drag || !td || td.dataset.i !== drag.i || td.dataset.m === drag.m || td.dataset.m < M) return; e.preventDefault();
    const mv = { from: drag.m, to: td.dataset.m }; const id = drag.i; drag = null;
    busy = true;
    try { await api.post(p(`/contract/items/${id}/move`), mv); toast(`Moved to ${fmt.month(mv.to)}`); } catch (err) { toast(err.message, 'bad'); }
    try { await refresh(); } finally { busy = false; }
  });
  load(d);
  tree = itemTree(items, () => rebuild());
  const modeChip = (k, label) => h('span', { class: 'chip' + (mode === k ? ' on' : ''), onclick: () => { mode = k; sessionStorage.setItem('sgMode', k); modeBox.replaceChildren(...modeChips()); rebuild(); } }, label);
  const modeChips = () => [h('span', { class: 'small muted' }, 'Show'), modeChip('$', '$ amounts'), modeChip('%', '% of the price')];
  const modeBox = h('span', { class: 'row', style: { gap: '6px' } }, ...modeChips());
  const ctl = h('span', { class: 'row small', style: { gap: '6px' } });
  function drawControls() {
    ctl.replaceChildren(h('label', { class: 'row small', style: { gap: '4px' } }, h('input', { type: 'checkbox', checked: sg.figs, onchange: (e) => { sg.figs = e.target.checked; sgSave(); rebuild(); } }), 'Price and balances'));
  }
  drawControls();
  hintBox.append(h('div', { class: 'note', style: { marginBottom: '10px' } }, `Click a month and type a dollar amount or a percentage of the line's price (for example 25% or 12000, or "rest" for whatever is left). A line can never be scheduled for more than its price in total. `,
    `${fmt.month(M)} is the status month: what you type there is this month's claim. Months after it are forecast revenue. Drag the ⠿ grip of a value onto the status month or another month of the same line, earlier or later but not into the past, to move it. Months already claimed are locked.`));
  body.append(kpis, trimBox, bar, hintBox, h('div', { class: 'row', style: { marginBottom: '8px', gap: '16px' } }, chipBox, modeBox, ctl, h('span', { class: 'sp', style: { flex: 1 } }), tplBtns), olHost, tw);
  tw.append(h('table', { class: 't fz6 notools sgrid' }, head, tbody, foot));  // Ref, Description and the line's window stay put while the months scroll
  rebuild(false);
  const cur = head.querySelector('th.cur'); if (cur) tw.scrollLeft = Math.max(0, cur.offsetLeft - 520);   // open at the status month
}

async function claimsTab(body, params) {
  const list = await api.get(p('/claims'));
  const M = statusMonth() || todayISO().slice(0, 7);
  const pst = list.length ? null : await api.get(p('/pronto/status')).catch(() => null);   // no claims here yet: does Pronto hold any?
  const head = h('div', { class: 'ch' }, h('h2', {}, 'Progress claims to the client'), h('span', { class: 'sp' }), h('button', { class: 'btn', onclick: newClaim }, '+ New claim'));
  const col = (s) => ({ draft: '', submitted: 'warn', certified: 'navy', paid: 'good' }[s] || '');
  body.append(h('div', { class: 'note', style: { marginBottom: '12px' } }, 'Each month claim against the schedule. When the client certifies, enter the certified amount line by line or in total. Revenue for the month counts at the certified amount where there is one, otherwise at the claimed amount; later months follow the remaining schedule.'),
    h('div', { class: 'card' }, head, list.length ? claimsTable() : empty('No claims yet', pst && pst.claims && pst.claims.rows ? `Create the first claim: lines are pre-filled from the claim schedule. Pronto holds ${pst.claims.rows} customer claims, but a Pronto claim has no split by claim schedule item, so they are not turned into claims here. To bring your past claims in with their lines, load your claim schedule with its claims register (Contract value > Import, then Overwrite). The Pronto claims are compared with yours on Reconcile.` : 'Create the first claim: lines are pre-filled from the claim schedule.', pst && pst.claims && pst.claims.rows ? h('button', { class: 'btn ghost', onclick: () => go('reconcile') }, 'Open Reconcile') : null)));
  // the claims as an editable table: change a cell and it is saved at once, the page stays where it is; double-click a row for the whole claim
  function claimsTable() {
    const save = async (c, patch, el, field) => {
      try { await api.put(p(`/claims/${c.id}`), patch); Object.assign(c, patch); }
      catch (e) { toast(e.message, 'bad'); if (el) el.value = c[field] ?? ''; }
    };
    const txt = (field, w = '110px', ph = '') => (c) => { const i = h('input', { type: 'text', value: c[field] || '', placeholder: ph, style: { width: w } }); i.addEventListener('change', () => save(c, { [field]: i.value.trim() || null }, i, field)); return i; };
    const date = (field) => (c) => { const i = h('input', { type: 'date', value: c[field] || '' }); i.addEventListener('change', () => save(c, { [field]: i.value || null }, i, field)); return i; };
    const tbl = table([
      { label: 'Claim', f: txt('claim_no', '104px') }, { label: 'Client claim no.', f: txt('client_claim_no', '104px', 'if different') }, { label: 'Period', f: (c) => fmt.month(c.period) },
      { label: 'Status', f: (c) => { const i = select(state.tax.claim_status, c.status); i.addEventListener('change', () => save(c, { status: i.value }, i, 'status')); return i; } },
      { label: 'Claimed', r: 1, f: (c) => fmt.money(c.total) }, { label: 'Certified', r: 1, f: (c) => c.certified_lines ? fmt.money(c.certified_total) : h('span', { class: 'muted' }, 'not yet') },
      { label: 'Counts as', r: 1, f: (c) => h('b', {}, fmt.money(c.effective)) }, { label: 'Basis', f: (c) => c.basis },
      { label: 'Submitted', f: date('submitted_date') }, { label: 'Client certificate', f: date('certified_date') },
      { label: 'Paid', r: 1, f: (c) => { const i = h('input', { type: 'number', step: '0.01', value: c.paid_amount ?? '', style: { width: '112px', textAlign: 'right' } }); i.addEventListener('change', () => save(c, { paid_amount: i.value === '' ? null : num(i.value) }, i, 'paid_amount')); return i; } },
      { label: 'Pronto claim', f: txt('pronto_claim_no', '104px') }], list, { rowClass: (c) => `claimrow-${c.id}` });
    tbl.addEventListener('dblclick', (e) => {
      if (e.target.closest('input, select, textarea, button, a')) return;
      const m = /claimrow-(\d+)/.exec(e.target.closest('tr')?.className || ''); if (m) open(+m[1]);
    });
    return h('div', {}, h('div', { class: 'small muted', style: { margin: '0 0 6px' } }, 'Edit a cell directly: it is saved when you leave it and the page stays where it is. Double-click a row (not a cell you can type in) for the whole claim.'), tbl);
  }
  function newClaim() {
    const per = h('input', { type: 'month', value: M });
    modal({ title: 'New progress claim', body: field('Claim period', per, 'Lines are suggested as the scheduled amount to this month less what has already been claimed.'), actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} }, { label: 'Create', onClick: async () => { const r = await api.post(p('/claims'), { period: per.value }); await open(r.id); } }] });
  }
  async function open(id) {
    const c = await api.get(p(`/claims/${id}`));
    const inputs = {}; const tbody = h('tbody'); const eff = h('div');
    c.lines.forEach((l) => {
      const cl = h('input', { type: 'number', step: '0.01', value: l.amount || '', style: { width: '116px' }, oninput: recalc }); const ce = h('input', { type: 'number', step: '0.01', value: l.certified ?? '', style: { width: '116px' }, oninput: recalc }); inputs[l.item_id] = { cl, ce };
      tbody.append(h('tr', {}, h('td', { class: 'mono' }, l.ref || ''), h('td', {}, l.description), h('td', { class: 'r num' }, fmt.money(l.value)), h('td', { class: 'r num' }, fmt.money(l.prior)), h('td', { class: 'r num muted' }, fmt.money(l.planned_this)), h('td', { class: 'r' }, h('a', { onclick: () => { cl.value = l.suggested || ''; recalc(); }, style: { cursor: 'pointer' }, title: 'Use suggestion' }, fmt.money(l.suggested))), h('td', { class: 'in' }, cl), h('td', { class: 'in' }, ce), h('td', {}, h('button', { class: 'btn ghost sm', title: 'Certified as claimed', onclick: () => { ce.value = cl.value; recalc(); } }, '='))));
    });
    const status = select(state.tax.claim_status, c.status); const sub = h('input', { type: 'date', value: c.submitted_date || '' }); const paid = h('input', { type: 'number', step: '0.01', value: c.paid_amount ?? '' }); const pc = h('input', { type: 'text', value: c.pronto_claim_no || '', placeholder: 'e.g. CLAIM012' }); const no = h('input', { type: 'text', value: c.claim_no }); const cc = h('input', { type: 'text', value: c.client_claim_no || '', placeholder: 'Only if the client numbers its claims differently' }); const rev = h('input', { type: 'number', step: '1', min: '0', value: c.revision ?? 0 }); const revd = h('input', { type: 'date', value: c.revision_date || '' }); const certd = h('input', { type: 'date', value: c.certified_date || '' }); const dl = h('div', { class: 'small muted', style: { marginTop: '4px' } }); const showDeadline = async () => { try { const r = await api.get(p(`/review-deadline?submitted=${sub.value || todayISO()}`)); dl.textContent = r.deadline ? `Client review deadline: ${fmt.date(r.deadline)} (${r.days} ${r.basis} days after ${sub.value ? 'submission' : 'today, if submitted today'}).` : 'No client review period is set on the project card (Project setup > Project).'; } catch (e) { dl.textContent = ''; } }; sub.addEventListener('change', showDeadline); showDeadline();
    const certn = h('input', { type: 'text', value: c.client_cert_no || '', placeholder: 'The client\'s payment certificate number' });
    function recalc() {
      const v = Object.values(inputs); const claimed = v.reduce((a, i) => a + num(i.cl.value), 0); const effv = v.reduce((a, i) => a + (i.ce.value !== '' ? num(i.ce.value) : num(i.cl.value)), 0); const nc = v.filter((i) => i.ce.value !== '').length;
      eff.replaceChildren(h('div', { class: 'grid g4' }, kpi('Claimed', fmt.money(claimed)), kpi('Certified', nc ? fmt.money(v.reduce((a, i) => a + (i.ce.value !== '' ? num(i.ce.value) : 0), 0)) : 'not yet', `${nc} of ${v.length} lines`, 't2'), kpi('Counts as revenue', fmt.money(effv), nc === v.length && v.length ? 'Certified' : nc ? 'Certified where available, else claimed' : 'Claimed', 't3'), kpi('Difference', fmt.money(claimed - effv), 'Claimed less counted', 't4')));
    }
    recalc();
    const gather = (extra = {}) => ({ claim_no: no.value, status: status.value, submitted_date: sub.value || null, paid_amount: paid.value === '' ? null : num(paid.value), pronto_claim_no: pc.value, client_claim_no: cc.value, revision: num(rev.value), revision_date: revd.value || null, certified_date: certd.value || null, client_cert_no: certn.value, today: todayISO(), lines: Object.entries(inputs).map(([item_id, i]) => ({ item_id, amount: num(i.cl.value), certified: i.ce.value === '' ? null : num(i.ce.value) })), ...extra });
    modal({ title: `${c.claim_no}: ${fmt.month(c.period)}`, size: 'xl', body: h('div', { class: 'grid' }, h('div', { class: 'grid g4' }, field('Claim number', no), field('Status', status), field('Submitted', sub), field('Pronto claim number', pc)), h('div', { class: 'grid g4' }, field('Paid amount', paid), field('Client\'s claim number', cc, 'Some clients restart at 0 or 1 for the EPC phase'), field('Revision', rev, 'Raise it when the claim is re-issued'), field('Revision date', revd)),
        h('div', {}, dl),
        h('div', { class: 'grid g4' }, field('Client payment certificate received', certd, 'The amounts the client certifies are what count as revenue'), field('Client payment certificate no.', certn), h('span'), h('span')),
      h('div', { class: 'tw', style: { maxHeight: '42vh' } }, h('table', { class: 't' }, h('thead', {}, h('tr', {}, ['Ref', 'Description', 'Contract', 'Previously claimed', 'Scheduled this month', 'Catch-up to date', 'Claimed', 'Certified', ''].map((x, i) => h('th', { class: i >= 2 && i <= 5 ? 'r' : '', title: x === 'Catch-up to date' ? 'What the claim schedule says should have been claimed up to and including this month, less what has already been claimed. It is larger than "Scheduled this month" when earlier months were not claimed in full.' : x === 'Scheduled this month' ? 'The amount typed in this month\'s column of the claim schedule' : null }, x)))), tbody)), eff),
      actions: [{ label: 'Delete', kind: 'danger', onClick: async () => { if (!(await confirmBox('Delete this claim?', 'Delete', true))) return false; await api.del(p(`/claims/${id}`)); await render(); } }, { label: 'PDF', kind: 'ghost', close: false, onClick: () => claimPdfDialog({ ...c, id }) }, { label: 'Excel', kind: 'ghost', close: false, onClick: () => window.open(p(`/claims/${id}.xlsx`)) },
        { label: 'Mark as submitted', kind: 'ghost', close: false, onClick: async () => { if (c.status !== 'draft' && c.status !== 'submitted') { toast('This claim is already past submitted.'); return; } await api.put(p(`/claims/${id}`), gather({ status: 'submitted', submitted_date: sub.value || todayISO() })); toast(`${c.claim_no} marked as submitted. ${fmt.month(c.period)} is now locked in the claim schedule.`); await render(); } },
        { label: 'Certify all as claimed', kind: 'ghost', close: false, onClick: async () => { await api.put(p(`/claims/${id}`), gather({ action: 'certify_all' })); toast('Certified as claimed'); await render(); } },
        { label: 'Certify a total...', kind: 'ghost', close: false, onClick: async () => { const t = prompt('Certified total (shared across the lines in proportion to what was claimed):', String(Object.values(inputs).reduce((a, i) => a + num(i.cl.value), 0))); if (t === null) return false; await api.put(p(`/claims/${id}`), gather({ action: 'certify_total', amount: num(t) })); toast('Certified total shared across the lines'); await render(); } },
        { label: 'Close', kind: 'ghost', onClick: () => {} }, { label: 'Save claim', onClick: async () => { await api.put(p(`/claims/${id}`), gather()); toast('Claim saved'); await render(); } }] });
  }
  if (params.claim) open(+params.claim);
}

async function pronto(body) {
  const r = await api.get(p('/reconcile'));
  const app = r.claims_app; const pr = r.claims_pronto;
  const t = (l, k) => l.reduce((a, x) => a + (x[k] || 0), 0);
  body.append(h('div', { class: 'grid g4', style: { marginBottom: '14px' } }, kpi('Claims in this tool', fmt.money(t(app.filter((c) => c.status !== 'draft'), 'total')), `${app.filter((c) => c.status !== 'draft').length} issued`), kpi('Pronto claims', fmt.money(t(pr, 'total')), `${pr.length} claims`, 't2'), kpi('Pronto paid', fmt.money(t(pr, 'paid')), '', 't3'), kpi('Difference', fmt.money(t(app.filter((c) => c.status !== 'draft'), 'total') - t(pr, 'total')), 'Tool less Pronto', 't4')));
  if (!pr.length) { body.append(empty('No Pronto claims loaded', 'Upload the customer claims report on the Pronto page.', h('button', { class: 'btn', onclick: () => go('pronto') }, 'Open Pronto data'))); return; }
  const byNo = Object.fromEntries(app.map((c) => [c.pronto_claim_no || c.claim_no, c]));
  body.append(h('div', { class: 'card' }, h('h2', {}, 'Pronto claims against this tool'), table([{ label: 'Pronto claim', f: (c) => c.claim_no }, { label: 'Status', f: (c) => badge(c.status_desc || c.status || '', c.status === 'P' ? 'good' : '') }, { label: 'Submitted', f: (c) => fmt.date(c.date_submitted) }, { label: 'Total', r: 1, f: (c) => fmt.money(c.total) }, { label: 'Certified', r: 1, f: (c) => fmt.money(c.certified) }, { label: 'Paid', r: 1, f: (c) => fmt.money(c.paid) },
    { label: 'In this tool', r: 1, f: (c) => byNo[c.claim_no] ? fmt.money(byNo[c.claim_no].total) : h('span', { class: 'muted' }, 'not matched') }, { label: 'Difference', r: 1, f: (c) => byNo[c.claim_no] ? h('span', { class: Math.abs(byNo[c.claim_no].total - c.total) > 1 ? 'bad' : 'good' }, fmt.money(byNo[c.claim_no].total - c.total)) : '' }], pr, { maxHeight: '60vh' })));
}
