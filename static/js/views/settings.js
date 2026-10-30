import { h, clear, fmt, modal, toast, field, select, table, num, confirmBox, badge, empty } from '../ui.js';
import { api, state, p, PREFS, pref, VIEW_KEYS } from '../api.js';
import { go, render, boot, setArchived, resetMenu } from '../app.js';

export default async function settings(root) {
  const pr = state.project; const s = pr.settings || {};
  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, 'Settings'), h('div', { class: 'sub' }, 'Defaults for this project, templates, and the tools for clearing data so a project can be reused.'))));
  root.append(yourDefaults());
  // EPEC's details as they appear on claims
  const co = await api.get('/api/company');
  const cf = { name: h('input', { type: 'text', value: co.name }), abn: h('input', { type: 'text', value: co.abn, placeholder: 'e.g. 12 345 678 901' }), address: h('input', { type: 'text', value: co.address, style: { width: '100%' } }), claim_layout: select([['a', 'A: client | contract and claim | EPEC'], ['b', 'B: client with contract below | claim | EPEC']], co.claim_layout) };
  root.append(h('div', { class: 'card', style: { marginBottom: '14px' } }, h('h2', {}, 'Company details on claims'), h('p', { class: 'muted' }, 'EPEC\'s name, ABN and address as printed on the progress claim PDF. Shared by everyone using this database.'),
    h('div', { class: 'grid g3' }, field('Company name', cf.name), field('ABN', cf.abn), h('div', { style: { gridColumn: 'span 3' } }, field('Address', cf.address)), h('div', { style: { gridColumn: 'span 3' } }, field('Claim PDF layout', cf.claim_layout, 'How the client, contract, claim and EPEC details are arranged at the top of the progress claim'))),
    h('div', { style: { marginTop: '8px' } }, h('button', { class: 'btn', onclick: async () => { await api.put('/api/company', Object.fromEntries(Object.entries(cf).map(([k, i]) => [k, i.value]))); toast('Company details saved'); } }, 'Save company details'))));
  root.append(h('div', { class: 'card', style: { marginBottom: '14px' } }, h('h2', {}, 'Menu and tile layout'), h('p', { class: 'muted' }, 'You can drag the menu groups, and the tiles on each page, into your own order. This puts the menu and all tiles back in the default layout. It is kept in your profile and does not touch any project data.'),
    h('button', { class: 'btn ghost', onclick: async () => { if (await confirmBox('Put the menu and all tiles back in their default layout?', 'Reset layout')) { resetMenu(); toast('Menu and tiles reset to default'); } } }, 'Reset menu and tiles to default')));
  const dm = s.default_methods || {};
  const sels = {}; ['PL', 'PS', 'PM', 'PE'].forEach((g) => (sels[g] = select(Object.keys(state.tax.methods), dm[g] || 'AT-BUDGET')));
  const rev = h('input', { type: 'checkbox', checked: s.accrual_auto_reverse !== false }); const wt = h('input', { type: 'checkbox', checked: s.accrual_work_timing !== false }); const atol = h('input', { type: 'number', step: '0.01', value: s.accrual_tolerance ?? 1 }); const tol = h('input', { type: 'number', step: '0.01', value: pr.tolerance ?? 1 });
  const stages = h('input', { type: 'text', value: (s.stages || []).join(', ') });
  const ntDay = h('input', { type: 'number', step: '0.1', value: s.normal_hours_day ?? 8 });
  const cterms = h('input', { type: 'number', step: '1', value: s.client_terms_days ?? '', placeholder: 'from Pronto history' }); const sterms = h('input', { type: 'number', step: '1', value: s.supplier_terms_days ?? 30 }); const labBills = h('input', { type: 'checkbox', checked: !!s.bills_include_labour });
  root.append(h('div', { class: 'card', style: { marginBottom: '14px' } }, h('h2', {}, 'Forecast and tolerance defaults'),
    h('p', { class: 'muted' }, 'Default forecast method per category. Applied to lines when cost control is initialised, and to lines created later from Pronto.'),
    h('div', { class: 'grid g4' }, field('Labour (PL)', sels.PL), field('Subcontractors (PS)', sels.PS), field('Materials (PM)', sels.PM), field('Expenses (PE)', sels.PE)),
    h('div', { class: 'grid g4', style: { marginTop: '10px' } }, field('Budget tolerance ($)', tol, 'Within this a line counts as on budget'), field('Accrual match tolerance ($)', atol, 'Invoice within this of the accrual reverses it'), field('Contract stages', stages, 'Comma separated, for example Early Works, EPC'), h('label', { class: 'row small', style: { marginTop: '22px' } }, rev, 'Reverse accruals automatically when the invoice lands')),
    h('label', { class: 'row small', style: { marginTop: '8px' } }, wt, 'Count a matched invoice in the month the work was accrued (reversed in the month it lands in Pronto), so months show when the work was done'),
    h('div', { class: 'grid g4', style: { marginTop: '10px' } }, field('Normal hours a day (staff)', ntDay, 'Hours above this are overtime when the labour calendar splits a timesheet into NT and OT')),
    h('h3', { style: { margin: '16px 0 8px' } }, 'Cash and invoicing'),
    h('div', { class: 'grid g4' }, field('Client payment terms (days)', cterms, 'Blank uses the average days to pay from the Pronto claims, else 30'), field('Supplier payment terms (days)', sterms, 'Pronto\'s GL report has no payment dates, so payments are modelled from this'), h('label', { class: 'row small', style: { marginTop: '22px' } }, labBills, 'Count labour as bills received'), h('span')),
    h('div', { style: { marginTop: '12px' } }, h('button', { class: 'btn', onclick: async () => { await api.put(`/api/projects/${state.pid}`, { tolerance: num(tol.value), settings: { default_methods: Object.fromEntries(Object.entries(sels).map(([k, v]) => [k, v.value])), accrual_auto_reverse: rev.checked, accrual_work_timing: wt.checked, accrual_tolerance: num(atol.value), client_terms_days: cterms.value === '' ? null : num(cterms.value), supplier_terms_days: num(sterms.value) || 30, bills_include_labour: labBills.checked, normal_hours_day: num(ntDay.value) || 8, stages: stages.value.split(',').map((x) => x.trim()).filter(Boolean) } }); toast('Settings saved'); render(); } }, 'Save settings'))));

  root.append(h('div', { class: 'card', style: { marginBottom: '14px' } }, h('h2', {}, 'Templates and new projects'),
    h('p', { class: 'muted' }, 'A template keeps the structure and drops the data. Mark this project as a template, or start a new project from it with the options you want. Pronto data, claims, accruals and history are never copied.'),
    h('div', { class: 'row' }, h('label', { class: 'row' }, h('input', { type: 'checkbox', checked: !!pr.is_template, onchange: async (e) => { await api.post(`/api/projects/${state.pid}/template`, { value: e.target.checked }); toast(e.target.checked ? 'Marked as a template' : 'No longer a template'); } }), 'This project is a template'),
      h('button', { class: 'btn ghost', onclick: () => window.open(p('/template.xlsx?blank=1')) }, 'Download blank Excel template'), h('button', { class: 'btn ghost', onclick: () => window.open(p('/template.xlsx')) }, 'Export this project\'s structure to Excel'))));

  root.append(h('div', { class: 'card', style: { marginBottom: '14px' } }, h('h2', {}, 'Demonstration data'),
    h('p', { class: 'muted' }, 'Fictional data to try PMT with. The demo team: project director Taylor Brooks over a junior PM (Riley Chen, 1 project), two PMs (Jordan Reyes and Priya Nair, 2 projects each) and a senior PM (Sam Whitlock, 3 projects); Priya\'s and Sam\'s Bellbird projects are children of one parent project. Each project is fully loaded (CBS, Pronto, forecast, claims). Takes about half a minute; delete the projects named "Demo team: ..." when done.'),
    h('div', { class: 'row' }, h('button', { class: 'btn', onclick: async (e) => {
      const b = e.currentTarget; b.disabled = true; toast('Building the demo team (about half a minute)...');
      try { await api.post('/api/demo/team'); toast('Demo team loaded: see OVERVIEW > Portfolio, Program (directed) by Taylor Brooks'); await boot(); go('portfolio'); } catch (err) { toast(err.message, 'bad'); }
      b.disabled = false;
    } }, 'Load the demo team (8 projects, 4 PMs, 1 director)'))));

  root.append(h('div', { class: 'card', style: { marginBottom: '14px' } }, h('h2', {}, 'Archive'),
    pr.archived_at
      ? h('div', {}, h('p', {}, `This project was archived ${fmt.date(pr.archived_at.slice(0, 10))}${pr.archived_by ? ' by ' + pr.archived_by : ''}. It is in the Archive, apart from the running projects; everything in it is kept.`),
        h('button', { class: 'btn', onclick: () => setArchived(state.pid, false) }, 'Restore to the running projects'))
      : h('div', {}, h('p', { class: 'muted' }, 'Finished with this project? Archive it: it moves from the running projects to the Archive (for everyone sharing it), with its contract value, final cost and margin as they stand. Nothing is deleted; you can open it from the library or restore it any time.'),
        h('button', { class: 'btn ghost', onclick: async () => { if (await confirmBox(`Archive ${pr.name}? It moves to the Archive; nothing is deleted and you can restore it any time.`, 'Archive')) await setArchived(state.pid, true); } }, 'Archive this project'))));

  const hols = await api.get(p('/holidays'));
  const yNow = new Date().getFullYear();
  const yFrom = h('input', { type: 'number', min: 2000, max: 2100, value: yNow, style: { width: '86px' } }); const yTo = h('input', { type: 'number', min: 2000, max: 2100, value: yNow + 3, style: { width: '86px' } });
  async function loadHols(btn, mode) {
    btn.disabled = true; const old = btn.textContent; btn.textContent = mode.internet ? 'Fetching...' : 'Loading...';
    try {
      const r = await api.post(p('/holidays'), { ...mode, from_year: +yFrom.value, to_year: +yTo.value });
      toast(`${r.added} public holidays added for ${r.years[0]} to ${r.years[r.years.length - 1]}${r.errors.length ? `; not available: ${r.errors.map((x) => x.split(':')[0]).join(', ')}` : ''}`, r.errors.length ? 'warn' : undefined); render();
    } catch (e) { toast(e.message, 'bad'); btn.disabled = false; btn.textContent = old; }
  }
  const hDay = h('input', { type: 'date' }); const hName = h('input', { type: 'text', placeholder: 'e.g. Show day (local)' });
  const holList = h('div', { class: 'row', style: { gap: '6px', marginTop: '10px', maxHeight: '180px', overflow: 'auto' } }, hols.map((x) => h('span', { class: 'chip', title: x.name || '' }, fmt.date(x.day) + ' ' + (x.name || ''), h('b', { style: { marginLeft: '4px', cursor: 'pointer' }, onclick: async () => { await api.del(p(`/holidays/${x.id}`)); render(); } }, '×'))));
  root.append(h('div', { class: 'card', style: { marginBottom: '14px' } }, h('h2', {}, `Public holidays (${hols.length})`),
    h('p', { class: 'muted' }, 'Shaded on the forecast calendars and the labour calendar. A roster can skip them.'),
    h('div', { class: 'row' }, h('span', { class: 'small' }, 'From year'), yFrom, h('span', { class: 'small' }, 'to'), yTo,
      h('button', { class: 'btn ghost', title: 'Pulls the national and Queensland public holidays for these years from the Nager.Date public holiday service. Needs internet.', onclick: (e) => loadHols(e.currentTarget, { internet: true }) }, 'Load Queensland public holidays from the internet'),
      h('button', { class: 'btn ghost', title: 'The built-in list, 2024 to 2035, works offline', onclick: (e) => loadHols(e.currentTarget, { standard: true }) }, 'Use the built-in list (offline)')),
    h('div', { class: 'row', style: { marginTop: '8px' } }, hDay, hName, h('button', { class: 'btn ghost', onclick: async () => { await api.post(p('/holidays'), { day: hDay.value, name: hName.value }); render(); } }, 'Add one day')), holList));

  const scopes = [['pronto', 'Pronto data (transactions, labour, POs, claims, CTD) and import history'], ['forecast', 'Forecast items, manual months and accruals'], ['revenue', 'Contract items and claims'], ['variations', 'Variations'], ['subcontracts', 'Subcontracts'], ['programme', 'Milestones and the uploaded programme'], ['history', 'Snapshots, CMT entries and the change log'], ['allowances', 'All allowance entries (unlocks initialisation)'], ['structure', 'Custom CBS lines and groups, resources (standard CBS stays)']];
  const chk = scopes.map(([k]) => h('input', { type: 'checkbox', dataset: { k } }));
  const all = await api.get('/api/projects');
  const label = (x) => `${x.name}${x.number ? ' (' + x.number + ')' : ''}${x.archived_at ? ' \u00b7 archived' : ''}${x.is_template ? ' \u00b7 template' : ''}${x.id === state.pid ? ' \u00b7 open now' : ''}`;
  const clearPick = select([['', 'Choose the project to clear...'], ...all.map((x) => [String(x.id), label(x)])], '');
  root.append(h('div', { class: 'card', style: { borderColor: 'var(--bad)' } }, h('h2', { style: { color: 'var(--bad)' } }, 'Clear project data'),
    h('p', {}, 'Use this to wipe a live project back to a clean shell, keeping the project identity and the standard CBS, so it can be reused as a template. ', h('b', {}, 'This cannot be undone.'), ' Download an Excel export first if you may want the structure again.'),
    h('div', { class: 'grid g2' }, scopes.map(([k, l], i) => h('label', { class: 'row small' }, chk[i], l))),
    h('div', { class: 'row', style: { marginTop: '12px' } }, clearPick, h('button', { class: 'btn danger', onclick: async () => {
      const picked = scopes.filter((_, i) => chk[i].checked).map(([k]) => k);
      const x = all.find((y) => String(y.id) === clearPick.value);
      if (!picked.length) return toast('Tick what to clear', 'bad');
      if (!x) return toast('Choose a project from the list', 'bad');
      const ok = await confirmBox(`Clear the selected data from "${x.name}"? ${picked.length} area${picked.length === 1 ? '' : 's'} are wiped for everyone sharing it. This cannot be undone.`, 'OK, clear it', true);
      if (!ok) return;
      try { const r = await api.post(`/api/projects/${x.id}/wipe`, { scopes: picked, confirm: x.name }); toast('Cleared: ' + r.wiped.join(', ')); await boot(); } catch (e) { toast(e.message, 'bad'); } } }, 'Clear selected data'))));

  // ---- delete a project for good: pick it from the list, then OK on the confirmation -----------------------------
  const pick = select([['', 'Choose the project to delete...'], ...all.map((x) => [String(x.id), label(x)])], '');
  root.append(h('div', { class: 'card', style: { borderColor: 'var(--bad)', marginTop: '14px' } }, h('h2', { style: { color: 'var(--bad)' } }, 'Delete a project'),
    h('p', {}, 'Removes the project and everything in it: CBS, allowances, Pronto data, forecast, accruals, claims, variations and history. ', h('b', {}, 'This cannot be undone.'),
      ' To keep a finished project for the record, archive it instead.'),
    h('div', { class: 'row' }, pick, h('button', { class: 'btn danger', onclick: async () => {
      const x = all.find((y) => String(y.id) === pick.value);
      if (!x) return toast('Choose a project from the list', 'bad');
      const ok = await confirmBox(`Delete "${x.name}" permanently? Its CBS, Pronto data (${fmt.n(x.tx)} transactions), forecast, accruals, claims, variations and history are removed for everyone sharing it. This cannot be undone.`, 'OK, delete permanently', true);
      if (!ok) return;
      try {
        await api.del(`/api/projects/${x.id}?confirm=${encodeURIComponent(x.name)}`);
        toast(`${x.name} deleted`);
        if (x.id === state.pid) state.pid = null;
        await boot();
      } catch (e) { toast(e.message, 'bad'); }
    } }, 'Delete...'))));
}

// Your defaults: how each page opens for you (kept for you on this PC, not shared with the team)
function yourDefaults() {
  const inputs = {};
  const groups = [...new Set(PREFS.map((x) => x[5]))];
  const ctl = ([key, , kind, , opts]) => {
    const v = pref(key);
    const el = kind === 'bool' ? h('input', { type: 'checkbox', checked: !!v }) : kind === 'text' ? h('input', { type: 'text', value: v || '', placeholder: 'https://...' }) : select(opts, v);
    inputs[key] = { el, kind, opts };
    return el;
  };
  const read = (key) => { const { el, kind, opts } = inputs[key]; if (kind === 'bool') return el.checked; if (kind === 'text') return el.value.trim(); const o = opts.find((x) => String(x[0]) === el.value); return o ? o[0] : el.value; };
  return h('div', { class: 'card', style: { marginBottom: '14px' } },
    h('div', { class: 'ch' }, h('h2', {}, 'Your defaults'), h('span', { class: 'sp' }), h('span', { class: 'small muted' }, `For ${state.me?.name || 'you'} on this PC, every project`)),
    h('p', { class: 'muted' }, 'How each page opens. What you change on a page while you work is kept until PMT is closed; the next time it opens with these.'),
    h('div', { class: 'grid g3' }, groups.map((g) => h('div', { class: 'prefgrp' }, h('h3', {}, g),
      ...PREFS.filter((x) => x[5] === g).map((x) => (x[2] === 'bool' ? h('label', { class: 'row small' }, ctl(x), x[1]) : h('label', { class: 'f' }, x[1], ctl(x))))))),
    h('div', { class: 'row', style: { marginTop: '12px' } },
      h('button', { class: 'btn', onclick: async () => {
        const prefs = Object.fromEntries(PREFS.map(([k]) => [k, read(k)]));
        state.me = { ...(state.me || {}), prefs: await api.put('/api/me/prefs', { prefs }) };
        try { VIEW_KEYS.forEach((k) => sessionStorage.removeItem(k)); localStorage.removeItem('calPoolsShut'); } catch (e) { /* ignore */ }
        toast('Your defaults are saved. Pages now open this way.'); } }, 'Save my defaults'),
      h('button', { class: 'btn ghost', onclick: async () => {
        state.me = { ...(state.me || {}), prefs: await api.put('/api/me/prefs', { prefs: {} }) };
        try { VIEW_KEYS.forEach((k) => sessionStorage.removeItem(k)); localStorage.removeItem('calPoolsShut'); } catch (e) { /* ignore */ }
        toast('Back to the PMT defaults'); render(); } }, 'Back to the PMT defaults')));
}
