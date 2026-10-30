import { assessDialog } from './_assess.js';
import { h, clear, fmt, modal, toast, field, select, table, num, confirmBox, badge, tabs, empty , lookup } from '../ui.js';
import { api, state, p, loadRows, loadProjects } from '../api.js';
import { go, render, draft, commitDraft } from '../app.js';
import { contractEditor } from './revenue.js';
import { scheduleDrop } from './programme.js';
import { cmtUpload } from './_cmt.js';
import { allowanceBody } from './allowance.js';
import { TYPES, pickMap, geocode, canonType } from '../map.js';

const STEPS = [['project', 'Project', 'Identity and dates'], ['contract', 'Contract value', 'Payment Milestones'], ['cbs', 'CBS and allowances', 'Structure and proposal allowances'], ['programme', 'Project schedule', 'Baseline milestones and phases'], ['pronto', 'Pronto data', 'Only if Pronto already has cost'], ['allowance', 'Allowance', 'Link resources to buckets'], ['initialise', 'Initialise', 'Lock the baseline']];

export default async function setup(root, params) {
  const proj = state.project; const step = params.step || 'project';
  const chk = await api.get(p('/init-check'));
  const rps = await api.get(p('/restore-points'));
  const last = rps.find((r) => !r.undone_at);
  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, 'Project setup'), h('div', { class: 'sub' }, 'Set up a contract once, then Pronto uploads keep it current. Everything you enter here can be reused as a template for the next project.')), h('div', { class: 'sp' }),
    last ? h('button', { class: 'btn ghost', title: `${last.label}, ${fmt.date(last.created_at)}${last.created_by ? ' by ' + last.created_by : ''}`, onclick: () => undoLoad(last) }, `Undo: ${last.label.replace(/^Excel load: .*/, 'last Excel load').replace(/^Erase: /, 'erase ')}`) : null,
    // the whole-project template buttons show on the steps that have no Excel row of their own (the other steps carry theirs below)
    ...(['contract', 'cbs', 'programme'].includes(step) ? [] : [h('button', { class: 'btn ghost', onclick: () => window.open(p('/template.xlsx?blank=1')) }, 'Blank Excel template'), h('button', { class: 'btn ghost', onclick: () => window.open(p('/template.xlsx')) }, 'Export current setup')]),
    h('button', { class: 'btn ghost', title: 'Compare a Cost Management Tool with cost control, then reject or align each difference', onclick: cmtUpload }, 'Load a CMT'), ...(['contract', 'cbs', 'programme'].includes(step) ? [] : [h('button', { class: 'btn', onclick: loadExcel }, 'Load from Excel')])));
  const doneMap = { project: !!(proj.name && proj.status_date && proj.project_start && proj.project_end), contract: !!chk.info.contract_value, cbs: chk.info.budget > 0, programme: false, pronto: false, initialise: proj.initialised };
  const mc = await api.get(p('/milestones')); doneMap.programme = mc.length > 0;
  doneMap.pronto = (await api.get(p('/pronto/batches')).catch(() => [])).length > 0;
  // the Allowance step shows how many resources with cost are still not linked (worked out only on the steps that need it)
  let aov = null; if (step === 'allowance') aov = await api.get(p('/allowance/overview'));
  doneMap.allowance = aov ? !aov.resources.length && aov.buckets.length > 0 : false;
  root.append(h('div', { class: 'steps' }, STEPS.map(([k, t, s], i) => h('button', { class: (k === step ? 'on ' : '') + (doneMap[k] ? 'done' : ''), onclick: () => leave(() => go('setup', { step: k })) }, `${i + 1}. ${t}${doneMap[k] ? ' ✓' : ''}`, h('small', {}, k === 'allowance' && aov ? (aov.resources.length ? `${aov.resources.length} resources not linked` : s) : s)))));
  // wrong data uploaded? erase just this part of the set-up (Undo at the top puts it back)
  const ERASE = { project: ['Project details', 'Every field on this page except the project name and status date'],
    contract: ['Payment Milestones', 'Every payment milestone not linked to the variation register, with its claim schedule months. Milestones that already have claims are kept.'],
    cbs: ['CBS and allowances', 'The CBS items you or a load added (not the standard categories or the lines from Pronto) and the original estimate. Items carrying Pronto cost, accruals, forecast, transfers, subcontracts or risk are kept.'],
    programme: ['Project schedule', 'The project schedule milestones and phases.'] };
  if (ERASE[step]) root.append(h('div', { class: 'row', style: { justifyContent: 'flex-end', margin: '-4px 0 8px' } }, h('button', { class: 'btn danger sm', onclick: async () => {
    const [name, what] = ERASE[step];
    if (!(await confirmBox(`Erase ${name}? ${what} "Undo: erase ${name}" at the top of this page puts it back.`, `Erase ${name}`, true))) return;
    try {
      const r = await api.post(p('/setup/erase'), { section: step });
      const gone = Object.entries(r.removed).map(([k, v]) => `${v} ${k}`).join(', ') || 'nothing to erase';
      toast(`Erased: ${gone}${r.kept.length ? `; ${r.kept.length} kept because they carry data` : ''}`);
      if (r.kept.length) modal({ title: `${r.kept.length} item(s) kept`, body: h('ul', {}, r.kept.map((k) => h('li', {}, k))), actions: [{ label: 'Close', onClick: () => {} }] });
      await loadProjects(); await render();
    } catch (e) { toast(e.message, 'bad'); }
  } }, `Erase this section (${ERASE[step][0]})`)));
  const reg = { dirty: false, save: null };
  // moving on with unsaved changes asks first
  async function leave(next) {
    if (!reg.dirty || !reg.save) return next();
    const choice = await new Promise((res) => modal({ title: 'Save this step first?', onClose: () => res('stay'), body: h('p', {}, `You changed ${STEPS.find((x) => x[0] === step)[1]} but have not saved it. Are you happy to save it before moving on?`),
      actions: [{ label: 'Stay on this step', kind: 'ghost', onClick: () => res('stay') }, { label: 'Move on without saving', kind: 'ghost', onClick: () => res('discard') }, { label: 'Save and move on', onClick: async () => { const ok = await reg.save(); if (!ok) return false; res('save'); } }] }));
    if (choice !== 'stay') { reg.dirty = false; await next(); }
  }
  if (['contract', 'cbs', 'programme'].includes(step)) root.append(h('div', { class: 'row', style: { margin: '0 0 10px', gap: '8px', flexWrap: 'wrap' } }, h('span', { class: 'small muted' }, `Excel template for this step (${ERASE[step][0]}):`),
    h('button', { class: 'btn ghost sm', onclick: () => window.open(p(`/template.xlsx?blank=1&step=${step}`)) }, 'Blank template'), h('button', { class: 'btn ghost sm', onclick: () => window.open(p(`/template.xlsx?step=${step}`)) }, 'Export current data'), h('button', { class: 'btn sm', onclick: loadExcel }, 'Load from Excel')));
  const body = h('div'); root.append(body);
  if (step === 'project') projectStep(body, reg);
  else if (step === 'contract') await contractEditor(body, { setup: true });
  else if (step === 'cbs') cbsStep(body, chk);
  else if (step === 'programme') await programmeStep(body, mc);
  else if (step === 'allowance') {
    body.append(h('div', { class: 'note', style: { marginBottom: '12px' } }, 'Before you initialise: give each resource with cost a line with allowance, so the baseline is by line and not parked on a pool. Tick several resources and cover their cost so far in one action. Nothing here is locked: transfers on Cost control change it later.'));
    allowanceBody(body, aov);
  }
  else if (step === 'pronto') {
    body.append(h('div', { class: 'note', style: { marginBottom: '12px' } }, 'Only for a project that already has cost in Pronto. Load the exports once here so the opening actuals, commitments and timesheets are in before you initialise. Later monthly uploads are not done in Project setup: use Pronto data under COST.'));
    await (await import('./pronto.js')).default(body, {});
  }
  else await initStep(body, chk);
  const si = STEPS.findIndex((x) => x[0] === step);
  // Back, Save and Next: above the step (so they are in sight) and below it
  const navRow = (style) => h('div', { class: 'row', style: { gap: '8px', ...style } },
    si > 0 ? h('button', { class: 'btn ghost', onclick: () => leave(() => go('setup', { step: STEPS[si - 1][0] })) }, `Back: ${STEPS[si - 1][1]}`) : null,
    h('span', { class: 'sp', style: { flex: 1 } }),
    draft.rid && draft.step === step ? badge('Unsaved changes: Save keeps them, leaving the step asks first', 'warn') : null,
    step !== 'initialise' && step !== 'pronto' && step !== 'allowance' ? h('button', { class: 'btn', onclick: async () => {
      if (reg.save) { if (await reg.save()) await render(); return; }
      if (await commitDraft()) { toast(`${STEPS[si][1]} saved`); await render(); } else toast(`Nothing to save on ${STEPS[si][1]}: no changes since it was last saved`);
    } }, 'Save') : null,
    si < STEPS.length - 1 ? h('button', { class: 'btn ghost', onclick: () => leave(() => go('setup', { step: STEPS[si + 1][0] })) }, `Next: ${STEPS[si + 1][1]}`) : null);
  root.insertBefore(navRow({ margin: '0 0 10px' }), root.querySelector('.steps').nextSibling);
  root.insertBefore(h('div', { class: 'small muted', style: { margin: '6px 0 10px' } }, 'Project setup keeps your changes as a draft until you press Save, and asks before you leave a step with unsaved changes. Everywhere else in the app (forecasting, claims, cost control and the rest) a change is saved the moment you make it.'), root.querySelector('.steps').nextSibling);
  root.append(navRow({ margin: '16px 0' }));

  // Load from Excel: preview first (nothing is written), Save writes it and keeps a restore point to undo it
  function loadExcel() {
    const f = h('input', { type: 'file', accept: '.xlsx' });
    const ident = h('input', { type: 'checkbox' });
    const mode = select([['merge', 'Update and add: change what the file lists, keep everything else'], ['replace', 'Replace: the file becomes the project setup (items it does not list are removed)']], 'merge');
    const out = h('div');
    let token = null; let fname = '';
    const counts = (o) => Object.entries(o || {}).map(([k, v]) => `${v} ${k}`).join(', ') || 'nothing';
    const show = (r) => {
      token = r.token; fname = r.filename || fname;
      clear(out).append(
        ...(r.warning ? [h('div', { class: 'note bad', style: { marginTop: '10px' } }, h('b', {}, 'Another project\'s file. '), r.warning)] : []),
        h('div', { class: 'note', style: { marginTop: '10px' } }, `Would create: ${counts(r.report.created)}. Would update: ${counts(r.report.updated)}.`,
          mode.value === 'replace' ? ` Would remove: ${counts(r.report.removed)}.` : '', r.report.errors.length ? ` ${r.report.errors.length} row(s) would be skipped.` : ''),
        ...(r.report.kept.length ? [h('div', { class: 'note', style: { marginTop: '6px' } }, h('b', {}, `${r.report.kept.length} item(s) not in the file are kept because they carry data: `), r.report.kept.slice(0, 8).join('; '), r.report.kept.length > 8 ? ' ...' : '')] : []),
        r.changes.length ? table([{ label: 'Project field', f: (c) => c.field }, { label: 'Now', f: (c) => c.now ?? '' }, { label: 'From the file', f: (c) => h('b', {}, c.file ?? '') }], r.changes) : h('div', { class: 'small muted', style: { marginTop: '8px' } }, 'No project fields change.'),
        h('div', { class: 'small muted', style: { marginTop: '8px' } }, 'Nothing has changed yet. Save writes it; "Undo last Excel load" on this page puts the project back as it was.'));
    };
    const run = async () => {
      clear(out).append(h('div', { class: 'muted' }, 'Reading...'));
      try { show(token ? await api.post(p(`/load-template/preview/${token}?mode=${mode.value}&identity=${ident.checked ? 1 : 0}`), {}) : await api.upload(p(`/load-template/preview?mode=${mode.value}&identity=${ident.checked ? 1 : 0}`), f.files[0])); }
      catch (e) { token = null; clear(out).append(h('div', { class: 'note bad' }, e.message)); }
    };
    f.onchange = () => { token = null; if (f.files[0]) run(); };
    mode.onchange = () => { if (token || f.files[0]) run(); };
    ident.onchange = () => { if (token || f.files[0]) run(); };
    modal({ title: 'Load project setup from Excel', size: 'wide', body: h('div', { class: 'grid' }, h('div', { class: 'note' }, 'Download the template, fill in the blue cells, then choose it here. You see what it would change before anything is written.'), f, field('Loading mode', mode), h('label', { class: 'row small', title: 'Off: the project keeps its own name, code, number, status date, start and end (blank ones are filled from the file)' }, ident, 'Also update this project\'s name, code, number and dates from the file'), out),
      actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} }, { label: 'Save', onClick: async () => {
        if (!token) throw new Error('Choose the filled-in template first');
        const r = await api.post(p('/load-template/apply'), { token, filename: fname, mode: mode.value, identity: ident.checked });
        const made = Object.entries(r.created).map(([k, v]) => `${v} ${k}`).join(', ');
        const gone = Object.entries(r.removed || {}).map(([k, v]) => `${v} ${k}`).join(', ');
        toast(`Loaded${made ? ': created ' + made : ''}${gone ? '; removed ' + gone : ''}. Undo last Excel load puts it back.`);
        if (r.errors.length) modal({ title: `${r.errors.length} rows were skipped`, body: h('ul', {}, r.errors.map((e) => h('li', {}, e))), actions: [{ label: 'Close', onClick: () => {} }] });
        await loadProjects(); await render(); } }] });
  }

  async function undoLoad(rp) {
    if (!(await confirmBox(`Undo "${rp.label}" (${fmt.date(rp.created_at)})? The project's details, CBS items and allowances, payment milestones with their claim schedule, resources, rate card and schedule go back to how they were just before it. Anything it created is removed.`, 'Undo', true))) return;
    try { const r = await api.post(p(`/restore-points/${rp.id}/undo`), {}); toast(`Put back as before "${rp.label}": ${r.name}`); await loadProjects(); await render(); } catch (e) { toast(e.message, 'bad'); }
  }
}

function projectStep(body, reg) {
  const pr = state.project;
  const f = (k, type = 'text') => h('input', { type, value: pr[k] ?? '', dataset: { k } });
  const inputs = {
    name: f('name'), code: f('code'), number: f('number'), client_name: lookup('client', pr.client_name, { placeholder: 'Pick a client or type a new one' }), client_project_name: f('client_project_name'), client_project_code: f('client_project_code'), client_po: f('client_po'),
    client_pm: f('client_pm'), epec_pm: lookup('pm', pr.epec_pm, { placeholder: 'Pick or type a name' }), project_director: lookup('director', pr.project_director, { placeholder: 'Pick or type a name' }), location: f('location'), contract_ref: f('contract_ref'), early_works_ref: f('early_works_ref'),
    status_date: f('status_date', 'date'), project_start: f('project_start', 'date'), project_end: f('project_end', 'date'), grid_start: f('grid_start', 'date'), grid_end: f('grid_end', 'date'),
    default_risk_pct: h('input', { type: 'number', step: '0.1', value: ((pr.default_risk_pct ?? 0.07) * 100).toFixed(1) }),
    project_type: select([['', '(choose)'], ...TYPES.map((t) => [t, t])], canonType(pr.project_type) || ''),
    capacity_mw: f('capacity_mw', 'number'), storage_mwh: f('storage_mwh', 'number'), voltage: h('input', { type: 'text', value: pr.voltage || '', placeholder: 'e.g. 33/330' }),
    complexity: select([['', 'Suggested (from value, voltage, type)'], [1, '1 - simple'], [2, '2'], [3, '3 - typical'], [4, '4'], [5, '5 - very complex']], pr.complexity ?? ''),
    lat: f('lat', 'number'), lon: f('lon', 'number'),
    contract_law: select([['', '(not stated)'], ...['Queensland', 'New South Wales', 'Victoria', 'Western Australia', 'South Australia', 'Tasmania', 'Northern Territory', 'Australian Capital Territory', 'Other'].map((x) => [x, x])], pr.contract_law || ''),
    review_days: h('input', { type: 'number', min: '0', step: '1', value: pr.review_days ?? '', style: { width: '80px' } }),
    review_basis: select([['business', 'business days'], ['calendar', 'calendar days']], pr.review_basis || 'business'),
    claim_act: select([['', 'Automatic: from the site address and the contract law'], ['qld', 'Always show the BIF Act statement'], ['none', 'Never show it']], pr.claim_act || ''),
  };
  api.get(p('/claim-act')).then((a) => { const n = document.getElementById('actnote'); if (n) n.textContent = `Payment claims: ${a.show ? 'WILL carry' : 'will NOT carry'} the BIF Act statement. ${a.reason} (Save the project to refresh this line.)`; }).catch(() => {});
  // the site: type a place to find it (online), or click on the map
  const mapBox = h('div', { style: { height: '300px', marginTop: '6px' } });
  const place = h('input', { type: 'search', placeholder: 'Find a town or place, e.g. Wandoan QLD', style: { width: '260px' } });
  const found = h('div', { class: 'small' });
  let picker = null;
  const find = async () => {
    try { const r = await geocode(place.value); clear(found).append(...(r.length ? r.map((x) => h('div', {}, h('a', { onclick: () => { inputs.lat.value = x.lat; inputs.lon.value = x.lon; if (!inputs.location.value) inputs.location.value = place.value; picker?.set(x.lat, x.lon); clear(found); } }, x.label))) : [h('span', { class: 'muted' }, 'Nothing found')])); } catch (e) { found.textContent = e.message + '. Click the site on the map instead.'; }
  };
  place.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); find(); } });
  body.append(h('div', { class: 'card' }, h('div', { class: 'grid g3' },
    field('Project name', inputs.name), field('EPEC project code', inputs.code), field('EPEC project number', inputs.number),
    field('Client', inputs.client_name), field('Client project name', inputs.client_project_name), field('Client project code', inputs.client_project_code),
    field('Client PO number', inputs.client_po), field('Client project manager', inputs.client_pm), field('EPEC project manager', inputs.epec_pm, 'Their Portfolio lists this project'), field('EPEC project director', inputs.project_director, 'Their Portfolio (program) lists this project'), field('Location', inputs.location, 'Site or town, e.g. Wandoan QLD'),
    ),
    h('h3', { style: { margin: '18px 0 8px' } }, 'Dates'),
    h('div', { class: 'grid g4' }, field('Status date', inputs.status_date, 'Month-end you are reporting to'), field('Project start', inputs.project_start), field('Project end', inputs.project_end), field('Default risk (% of budget)', inputs.default_risk_pct, 'Applied to estimates when risk is left blank')),
    h('div', { class: 'grid g4', style: { marginTop: '10px' } }, field('Month grid starts', inputs.grid_start, 'Blank = project start'), field('Month grid ends', inputs.grid_end, 'Blank = project end plus 2 months'), h('span'), h('span')),
    h('details', { class: 'legal', style: { marginTop: '16px' } }, h('summary', { style: { cursor: 'pointer', fontWeight: 700, color: 'var(--navy)' } }, 'Contract and legal'), h('div', { class: 'grid g3', style: { marginTop: '10px' } },
    field('Contract reference', inputs.contract_ref), field('Early works reference', inputs.early_works_ref), field('Law governing the contract', inputs.contract_law, 'With the site address this decides whether the payment claim carries the Queensland BIF Act statement'), field('BIF Act statement on claims', inputs.claim_act, 'Leave on Automatic unless legal advice says otherwise'),
    field('Client review period for a payment claim', h('div', { class: 'row', style: { gap: '6px' } }, inputs.review_days, inputs.review_basis), 'From the contract. Each claim shows its review deadline (submission date plus this period)'),
    h('div', { style: { gridColumn: '1 / -1' }, class: 'small muted', id: 'actnote' }, 'Checking...'))),
    h('h3', { style: { margin: '18px 0 8px' } }, 'Asset and site'),
    h('p', { class: 'small muted', style: { marginTop: 0 } }, 'Used by the Portfolio (map, metrics) and to work out the PM\'s workload. Complexity 1 to 5: how hard the project is to run; left blank, PMT suggests one from the contract value, the voltage and the type.'),
    h('div', { class: 'grid g5' }, field('Type', inputs.project_type), field('Capacity (MW)', inputs.capacity_mw), field('Energy storage (MWh)', inputs.storage_mwh, 'BESS: 2,000 MWh = 2 GWh'), field('Voltage levels (kV)', inputs.voltage, 'e.g. 33/330'), field('Project complexity', inputs.complexity)),
    h('div', { class: 'grid g4', style: { marginTop: '10px' } }, field('Site latitude', inputs.lat, 'Click the map, or find a place'), field('Site longitude', inputs.lon), h('div', { style: { gridColumn: 'span 2' } }, field('Find the site', h('div', { class: 'row' }, place, h('button', { class: 'btn ghost sm', onclick: find }, 'Find'))), found)),
    mapBox,
    ));
  reg.save = async () => {
    const b = {}; Object.entries(inputs).forEach(([k, i]) => (b[k] = i.value === '' ? null : i.value)); b.default_risk_pct = num(inputs.default_risk_pct.value) / 100;
    if (!b.name) { toast('Project name is required', 'bad'); return false; }
    await api.put(`/api/projects/${state.pid}`, b); reg.dirty = false; toast('Project saved'); await loadProjects(); return true;
  };
  body.addEventListener('input', () => { reg.dirty = true; }); body.addEventListener('change', () => { reg.dirty = true; });
  // the client PM and project complexity, assessed each month through the project (feeds the client's challenge rating)
  body.append(h('div', { class: 'card', style: { marginTop: '14px' } }, h('div', { class: 'ch' }, h('h2', {}, 'Client PM and complexity through the project'), h('span', { class: 'sp' }),
    h('button', { class: 'btn', onclick: () => assessDialog({ id: state.pid, name: pr.name, client_pm: pr.client_pm }, () => {}) }, 'Assess this month')),
    h('div', { class: 'small muted' }, 'Each month, rate how hard the client\'s project manager is to work with and how complex the project is. Together with where the client sits on the knowledge and difficulty grid (Stakeholders), this sets how challenging the client is, which the project directors see in Portfolio.')));
  pickMap(mapBox, { lat: pr.lat, lon: pr.lon }, (la, lo) => { inputs.lat.value = la; inputs.lon.value = lo; reg.dirty = true; })
    .then((pk) => { picker = pk; [inputs.lat, inputs.lon].forEach((i) => i.addEventListener('change', () => { if (num(inputs.lat.value) && num(inputs.lon.value)) pk.set(num(inputs.lat.value), num(inputs.lon.value)); })); })
    .catch((e) => { mapBox.replaceChildren(h('div', { class: 'note warn' }, 'The map could not load: ' + e.message)); });
}

function cbsStep(body, chk) {
  const i = chk.info;
  body.append(h('div', { class: 'card' }, h('h2', {}, 'CBS and allowances'),
    h('p', {}, 'The four grandparents (PL, PS, PM, PE) and their parents are the EPEC standard and are already loaded. Add project-specific groups and named lines below them, and enter the proposal allowance against each.'),
    h('div', { class: 'grid g4', style: { margin: '12px 0' } }, kpi('Budget entered', fmt.money(i.budget)), kpi('Risk', fmt.money(i.risk)), kpi('Allowance', fmt.money(i.allowance)), kpi('CBS lines', fmt.n(i.lines))),
    h('div', { class: 'row' }, h('button', { class: 'btn', onclick: () => go('cbs') }, 'Open the CBS editor'), h('button', { class: 'btn ghost', onclick: () => window.open(p('/template.xlsx?blank=1')) }, 'Bulk load via the Excel template')),
    h('div', { class: 'note', style: { marginTop: '14px' } }, 'Tip: enter the proposal allowance on role or trade groups (for example Commercial Manager, Civil works). When a named person or subcontractor joins, add a line and transfer allowance to it. Nothing is lost: the original estimate stays in the ledger.')));
  function kpi(l, v) { return h('div', { class: 'kpi' }, h('div', { class: 'l' }, l), h('div', { class: 'v' }, v)); }
}

async function programmeStep(body, list) {
  const wrap = h('div', { class: 'card' });
  const draw = (rows) => {
    clear(wrap).append(h('div', { class: 'ch' }, h('h2', {}, 'Milestones and phases'), h('span', { class: 'sp' }), h('button', { class: 'btn ghost sm', onclick: async () => { const r = await api.post(p('/milestones/derive-dates')); toast(r.a ? `Project dates set: ${fmt.date(r.a)} to ${fmt.date(r.b)}` : 'Add milestone dates first'); await render(); } }, 'Set project start and end from these'), h('button', { class: 'btn sm', onclick: () => edit() }, '+ Add')),
      rows.length ? table([{ label: 'Phase', f: (m) => m.phase || '' }, { label: 'Milestone / activity', f: (m) => m.name }, { label: 'Type', f: (m) => m.type }, { label: 'Baseline start', f: (m) => fmt.date(m.baseline_start) }, { label: 'Baseline end', f: (m) => fmt.date(m.baseline_end) }, { label: 'Forecast end', f: (m) => fmt.date(m.forecast_end) }, { label: 'Actual', f: (m) => fmt.date(m.actual_date) }, { label: 'PMR row', f: (m) => m.pmr_row || '' },
        { label: '', f: (m) => h('span', { class: 'row', style: { gap: '4px' } }, h('button', { class: 'btn ghost sm', onclick: () => edit(m) }, 'Edit'), h('button', { class: 'btn danger sm', onclick: async () => { await api.del(p(`/milestones/${m.id}`)); await render(); } }, '×')) }], rows,
          { reorder: { group: () => 'all', save: async (ids) => { await api.post(p('/reorder/milestones'), { ids }); await render(); } } })
        : empty('No milestones yet', 'Add the project schedule: award, design, procurement, construction and completion milestones.'));
  };
  function edit(m = {}) {
    const f = { phase: h('input', { type: 'text', value: m.phase || '' }), name: h('input', { type: 'text', value: m.name || '' }), type: select(['Milestone', 'Phase'], m.type || 'Milestone'), baseline_start: h('input', { type: 'date', value: m.baseline_start || '' }), baseline_end: h('input', { type: 'date', value: m.baseline_end || '' }), forecast_start: h('input', { type: 'date', value: m.forecast_start || '' }), forecast_end: h('input', { type: 'date', value: m.forecast_end || '' }), actual_date: h('input', { type: 'date', value: m.actual_date || '' }), pmr_row: h('input', { type: 'text', value: m.pmr_row || '' }) };
    modal({ title: m.id ? 'Edit milestone' : 'Add milestone', body: h('div', { class: 'grid g2' }, field('Phase', f.phase), field('Type', f.type), h('div', { style: { gridColumn: '1 / -1' } }, field('Milestone or activity', f.name)), field('Baseline start', f.baseline_start), field('Baseline end', f.baseline_end), field('Forecast start', f.forecast_start), field('Forecast end', f.forecast_end), field('Actual date', f.actual_date), field('PMR row', f.pmr_row)),
      actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} }, { label: 'Save', onClick: async () => { const b = { id: m.id }; Object.entries(f).forEach(([k, i]) => (b[k] = i.value || null)); if (!b.name) throw new Error('Name is required'); await api.post(p('/milestones'), b); await render(); } }] });
  }
  const info = state.project.settings || {};
  body.append(h('div', { class: 'grid g2', style: { marginBottom: '14px' } },
    h('div', { class: 'card' }, h('h2', {}, 'Internal project schedule'), h('div', { class: 'small muted', style: { marginBottom: '6px' } }, info.programme_file ? `Loaded: ${info.programme_file.name} (${info.programme_file.tasks} tasks). ` : '', 'EPEC\'s own baseline schedule (MS Project, Excel or PDF). It drives the claim schedule and cost forecast dates. Monthly updates are made later under Forecast > Project schedule, not here.'), scheduleDrop(),
      h('div', { class: 'row', style: { marginTop: '10px' } }, h('button', { class: 'btn ghost sm', onclick: async () => { const r = await api.post(p('/programme/to-milestones'), {}); toast(`${r.created} milestones and phases copied below`); await render(); } }, 'Copy its milestones and phases below'), h('button', { class: 'btn ghost sm', onclick: () => go('programme') }, 'Open Project schedule (Forecast)'), h('button', { class: 'btn ghost sm', title: 'Click a schedule item to choose the CBS lines whose start and stop it drives. Lines can also be set by hand on Cost control.', onclick: () => go('programme') }, 'Link cost lines to schedule items'))),
    h('div', { class: 'card' }, h('h2', {}, 'Upstream project schedule'), h('div', { class: 'small muted', style: { marginBottom: '6px' } }, info.programme_file_upstream ? `Loaded: ${info.programme_file_upstream.name} (${info.programme_file_upstream.tasks} tasks). ` : '', 'The client or head contract schedule, kept for reference. It does not change any dates.'), scheduleDrop(null, 'upstream'))));
  draw(list); body.append(wrap);
}

async function initStep(body, chk) {
  const i = chk.info; const init = chk.initialised;
  const pre = init ? [] : (await api.get(p('/preflight'))).items;
  const MARK = { done: ['\u2713', 'good'], todo: ['!', 'bad'], warn: ['!', 'warn'], info: ['i', 'muted'] };
  const look = h('input', { type: 'checkbox', style: { width: 'auto' } });
  const open = pre.filter((x) => x.state === 'todo' || x.state === 'warn');
  const go1 = h('button', { class: 'btn', disabled: true, onclick: async () => {
    if (!(await confirmBox('Lock the original estimate and store the day-zero baseline? This cannot be undone from the page.' + (open.length ? ` ${open.length} item(s) above are still open.` : ''), 'Initialise'))) return;
    await api.post(p('/initialise'), {}); toast('Cost control initialised'); sessionStorage.setItem('whatnext', '1'); go('dashboard'); } }, 'Initialise cost control');
  const gate = () => { go1.disabled = !chk.ok || !look.checked; };
  look.onchange = gate;
  body.append(h('div', { class: 'card' }, h('h2', {}, init ? 'Cost control is live' : 'Initialise cost control'),
    h('div', { class: 'grid g4', style: { margin: '12px 0' } }, kpi('Contract value', fmt.money(i.contract_value)), kpi('Total allowance (budget + risk)', fmt.money(i.allowance)), kpi('Planned margin', i.planned_margin_pct !== null ? fmt.pct(i.planned_margin_pct) : 'n/a'), kpi('Lines', fmt.n(i.lines))),
    chk.issues.length ? h('div', { style: { marginBottom: '12px' } }, chk.issues.map((x) => h('div', { class: 'note ' + (x.level === 'error' ? 'bad' : x.level === 'warn' ? 'warn' : ''), style: { margin: '6px 0' } }, x.msg))) : null,
    init ? h('div', { class: 'note' }, 'The baseline (day zero) is stored and the original estimate is locked. Change allowance with transfers on the CBS page.') : h('div', {},
      h('h3', { style: { margin: '4px 0 6px' } }, 'Before you lock the baseline'),
      h('div', { style: { marginBottom: '12px' } }, pre.map((x) => h('div', { class: 'row', style: { gap: '10px', padding: '6px 0', borderBottom: '1px solid var(--hair)' } },
        h('span', { class: MARK[x.state][1], style: { width: '18px', fontWeight: 700, textAlign: 'center' } }, MARK[x.state][0]),
        h('div', { style: { flex: 1 } }, h('b', {}, x.title), h('div', { class: 'small muted' }, x.detail)),
        x.page ? h('button', { class: 'btn ghost sm', onclick: () => go(x.page, x.params) }, 'Open') : null))),
      h('p', {}, 'Initialising stores the day-zero baseline snapshot, locks the original estimate, and gives every line its default forecast method (labour: burn-rate; subcontractors: at-budget; materials: at-commit; expenses: burn-rate). You can change methods line by line afterwards.'),
      h('label', { class: 'row small', style: { gap: '6px', marginBottom: '10px' } }, look, 'I have read the items above'),
      go1, !chk.ok ? h('span', { class: 'muted small', style: { marginLeft: '10px' } }, 'Fix the errors above first.') : null)));
  function kpi(l, v) { return h('div', { class: 'kpi' }, h('div', { class: 'l' }, l), h('div', { class: 'v' }, v)); }
}
