import { h, clear, fmt, modal, toast, field, select, table, num, confirmBox, badge, tabs, empty, debounce } from '../ui.js';
import { api, state, p, loadRows, loadProject } from '../api.js';
import { pickNode } from '../scope.js';
import { render, go } from '../app.js';

const KIND_HELP = {
  transactions: 'The GL transaction report. Actuals (CTD) come from here.',
  labour: 'Timesheets (Cognos). Gives hours per person and the unposted timesheets that become accruals.',
  po: 'The purchase order report. Gives commitments and open POs.',
  claims: 'Customer claims. Reconciles the claims you issue with what Pronto invoiced and was paid.',
  variations: 'Pronto variations, used to cross-check the register.',
  ctd: 'Category CTD overview, used to prove the GL import ties out.',
};

export default async function pronto(root, params = {}) {
  await loadRows();
  if (params.inspect) return inspect(root, params);
  const status = await api.get(p('/pronto/status'));
  const sug = await api.get(p('/pronto/suggestions'));
  const miss = await api.get(p('/pronto/missing-categories'));
  const batches = await api.get(p('/pronto/batches'));
  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, 'Pronto data'), h('div', { class: 'sub' }, 'Upload the Pronto exports. The tool recognises each report by its columns, loads it, and places every cost row on the CBS.'))));

  // the project's code in Pronto: an upload for any other code is flagged before it is loaded
  const pcode = h('input', { type: 'text', value: state.project.settings?.pronto_project || '', placeholder: 'e.g. 0185', style: { width: '140px' } });
  root.append(h('div', { class: 'card', style: { padding: '10px 14px', marginBottom: '12px' } }, h('div', { class: 'row', style: { gap: '10px', flexWrap: 'wrap' } }, h('b', {}, 'This project\'s Pronto project code'), pcode,
    h('button', { class: 'btn ghost sm', onclick: async () => { await api.put(p('/pronto/project'), { code: pcode.value }); toast(pcode.value ? 'Pronto project code saved' : 'Pronto project code cleared'); await loadProject(); } }, 'Save'),
    h('span', { class: 'small muted' }, 'Set it so the tool warns you if a Pronto file from another project is uploaded here by mistake.'))));

  // ---- whole workbook (optional) --------------------------------------------------------------
  const file = h('input', { type: 'file', accept: '.xlsx,.xlsm,.ods,.csv', class: 'hide' });
  const dz = h('div', { class: 'dz' }, h('b', {}, 'Drop a Pronto export here, or click to choose'), h('div', { class: 'small' }, '.xlsx, .xlsm, .ods or .csv. A workbook holding several reports is fine: each recognised sheet is offered below.'));
  const result = h('div');
  dz.onclick = () => file.click();
  dz.ondragover = (e) => { e.preventDefault(); dz.classList.add('over'); }; dz.ondragleave = () => dz.classList.remove('over');
  dz.ondrop = (e) => { e.preventDefault(); dz.classList.remove('over'); if (e.dataTransfer.files[0]) analyse(e.dataTransfer.files[0]); };
  file.onchange = () => file.files[0] && analyse(file.files[0]);

  async function analyse(f) {
    clear(result).append(h('div', { class: 'muted', style: { marginTop: '10px' } }, `Reading ${f.name}...`));
    try {
      const a = await api.upload(p('/pronto/analyse'), f);
      if (a.warning && !(await confirmBox(`${a.warning} Load it into ${state.project.name} anyway?`, 'Load anyway', true))) { clear(result); return; }
      const sel = {};
      const tbody = h('tbody');
      a.sheets.forEach((s) => {
        const on = h('input', { type: 'checkbox', checked: !s.missing.length && s.score >= 0.8 });
        const mode = select([['replace', 'Replace all'], ['merge', 'Add new rows only']], 'replace');
        const proj = select([['', 'All rows'], ...Object.entries(s.projects || {}).map(([k, n]) => [k, `${k} (${n} rows)`])], s.default_project || '');
        sel[s.sheet] = { s, on, mode, proj };
        tbody.append(h('tr', {}, h('td', {}, on), h('td', {}, s.sheet), h('td', {}, badge(s.label, 'navy'), ' ', h('span', { class: 'small muted' }, KIND_HELP[s.kind])), h('td', {}, s.missing.length ? badge('Missing: ' + s.missing.join(', '), 'bad') : badge('Columns matched', 'good')),
          h('td', {}, Object.keys(s.projects || {}).length ? proj : h('span', { class: 'muted' }, 'n/a')), h('td', {}, mode)));
      });
      const newcat = h('input', { type: 'checkbox', checked: true }); const newlines = h('input', { type: 'checkbox', checked: false });
      clear(result).append(h('h2', { style: { margin: '14px 0 8px' } }, `Found ${a.sheets.length} report${a.sheets.length > 1 ? 's' : ''} in ${a.filename}`),
        h('div', { class: 'tw' }, h('table', { class: 't' }, h('thead', {}, h('tr', {}, ['Load', 'Sheet', 'Report', 'Check', 'Pronto project', 'Mode'].map((x) => h('th', {}, x)))), tbody)),
        h('div', { class: 'note', style: { margin: '10px 0' } }, 'Replace all is right for the cumulative dumps Pronto normally gives. Add new rows only suits incremental files and skips rows already loaded.'),
        h('div', { class: 'row' }, h('label', { class: 'row small' }, newcat, 'Add Pronto categories that are not yet in the CBS'), h('label', { class: 'row small' }, newlines, 'Create a CBS line for every new employee or subcontractor found')),
        h('div', { class: 'stickybar' }, h('button', { class: 'btn', onclick: async (e) => {
          const items = Object.values(sel).filter((x) => x.on.checked).map((x) => ({ sheet: x.s.sheet, kind: x.s.kind, header_row: x.s.header_row, mode: x.mode.value, pronto_project: x.proj.value || null }));
          if (!items.length) return toast('Tick at least one report', 'bad');
          e.target.disabled = true; e.target.textContent = 'Loading...';
          try {
            const r = await api.post(p('/pronto/commit'), { token: a.token, filename: a.filename, items, create_categories: newcat.checked, create_lines: newlines.checked, pronto_project: items.find((i) => i.pronto_project)?.pronto_project });
            toast(r.results.map((x) => `${x.kind}: ${fmt.n(x.rows_new)} rows`).join('; ') + (r.lines_created ? `; ${r.lines_created} CBS lines created` : ''));
            await render();
          } catch (err) { toast(err.message, 'bad'); e.target.disabled = false; e.target.textContent = 'Load selected reports'; }
        } }, 'Load selected reports')));
      result.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (e) { clear(result).append(h('div', { class: 'note bad', style: { marginTop: '10px' } }, e.message)); }
  }

  // ---- one placeholder per report: drop the sheet onto the report it belongs to -----------------------------
  const labels = { transactions: 'GL transactions', labour: 'Labour timesheets', po: 'Purchase orders', claims: 'Customer claims', variations: 'Variations', ctd: 'CTD overview' };
  const hints = { transactions: 'GL transaction report (Pronto). Source of actuals and CTD.', labour: 'Timesheet Cognos report. Hours and unposted timesheets.', po: 'Purchase order report. Commitments.', claims: 'Customer claims report. Reconciles to the claims you issue.', variations: 'Variations report.', ctd: 'Category CTD overview. Used to prove the GL ties out.' };
  const order = ['transactions', 'labour', 'po', 'claims', 'variations', 'ctd'];
  root.append(h('div', { class: 'ch', style: { marginTop: '4px' } }, h('h2', {}, 'Drop each report onto its placeholder'), h('span', { class: 'sp' }), h('span', { class: 'small muted' }, 'Each report loads on its own, so you can refresh just the one that changed.')));
  root.append(h('div', { class: 'grid g3', style: { marginBottom: '14px' } }, order.map((k) => placeholder(k, status[k]))));

  // ---- checks on the loaded rows -------------------------------------------------------------------------
  const checks = await api.get(p('/pronto/checks'));
  if (checks.length) {
    const lv = { ok: 'good', warn: 'warn', bad: 'bad' };
    root.append(h('div', { class: 'card', style: { marginBottom: '14px' } }, h('div', { class: 'ch' }, h('h2', {}, 'Checks on the loaded rows'), h('span', { class: 'sp' }),
      h('span', { class: 'small muted' }, 'Totals rows, future dates, keying errors reversed later, identical rows. Click a check to see its rows.')),
      h('div', { class: 'tw' }, h('table', { class: 't' }, h('thead', {}, h('tr', {}, ['Report', '', 'Check', 'Rows', 'Amount', ''].map((x, i) => h('th', { class: i === 3 || i === 4 ? 'r' : '' }, x)))),
        h('tbody', {}, checks.filter((c) => c.level !== 'ok' || c.id.endsWith(':totals')).map((c) => h('tr', { class: c.count ? 'click' : '', onclick: c.count ? () => go('pronto', { inspect: c.kind, check: c.id }) : null },
          h('td', {}, labels[c.kind]), h('td', {}, badge(c.level === 'ok' ? 'OK' : c.level === 'bad' ? 'Check' : 'Look', lv[c.level])), h('td', { style: { whiteSpace: 'normal' } }, h('div', {}, c.title), h('div', { class: 'small muted' }, c.detail)),
          h('td', { class: 'r' }, c.count ? fmt.n(c.count) : ''), h('td', { class: 'r num' }, c.count ? fmt.money(c.amount) : ''), h('td', {}, c.count ? h('button', { class: 'btn ghost sm' }, 'Show rows') : '')))))))); 
  }

  root.append(h('div', { class: 'card', style: { marginBottom: '14px' } }, h('div', { class: 'ch' }, h('h2', {}, 'Or drop a whole workbook'), h('span', { class: 'sp' }), h('span', { class: 'small muted' }, 'Handy for a first load: every recognised sheet is offered.')), dz, file, result));

  function placeholder(kind, st) {
    const input = h('input', { type: 'file', accept: '.xlsx,.xlsm,.ods,.csv', class: 'hide' });
    const loaded = st.rows > 0;
    const box = h('div', { class: 'dz', style: { textAlign: 'left', padding: '14px 16px', borderStyle: loaded ? 'solid' : 'dashed', background: loaded ? '#fff' : '#f5f8ff' } },
      h('div', { class: 'row', style: { justifyContent: 'space-between', flexWrap: 'nowrap' } }, h('b', { style: { color: 'var(--navy)' } }, labels[kind]), loaded ? badge('Loaded', 'good') : badge('Empty', 'warn')),
      h('div', { class: 'small muted', style: { margin: '4px 0 8px' } }, hints[kind]),
      loaded ? h('div', {}, h('span', { class: 'num', style: { fontSize: '20px', fontWeight: 700, color: 'var(--navy)' } }, fmt.n(st.rows)), ' rows', h('div', { class: 'small muted' }, `${st.batch?.filename || ''}${(st.last || st.batch?.as_of) ? ' \u00b7 to ' + fmt.date(st.last || st.batch.as_of) : ''}`),
        st.future ? h('div', { class: 'small', style: { color: 'var(--warn)' } }, `+ ${fmt.n(st.future)} row${st.future > 1 ? 's' : ''} dated in the future`) : null) : h('div', { class: 'small' }, 'Drop the file here or click to choose'),
      loaded ? h('div', { class: 'row', style: { marginTop: '6px', justifyContent: 'space-between' } }, h('span', { class: 'small', style: { color: 'var(--navy)' } }, 'Drop a newer file here to refresh'),
        h('button', { class: 'btn ghost sm', onclick: (e) => { e.stopPropagation(); go('pronto', { inspect: kind }); } }, 'Inspect rows')) : null, input);
    box.onclick = () => input.click();
    box.ondragover = (e) => { e.preventDefault(); box.classList.add('over'); }; box.ondragleave = () => box.classList.remove('over');
    box.ondrop = (e) => { e.preventDefault(); box.classList.remove('over'); if (e.dataTransfer.files[0]) forKind(kind, e.dataTransfer.files[0]); };
    input.onclick = (e) => e.stopPropagation();
    input.onchange = () => input.files[0] && forKind(kind, input.files[0]);
    return box;
  }

  async function forKind(kind, f) {
    toast(`Reading ${f.name}...`);
    let a;
    try { a = await api.upload(p('/pronto/analyse'), f); } catch (e) { return toast(e.message, 'bad'); }
    if (a.warning && !(await confirmBox(`${a.warning} Load it into ${state.project.name} anyway?`, 'Load anyway', true))) return;
    const hits = a.sheets.filter((s) => s.kind === kind && !s.missing.length).sort((x, y) => y.score - x.score);
    if (!hits.length) {
      const seen = a.sheets.map((s) => `${s.sheet} looks like ${s.label}`).join('; ');
      return toast(`That file does not look like the ${labels[kind]} report. ${seen}`, 'bad');
    }
    const s = hits[0];
    const mode = select([['replace', 'Replace everything already loaded (a cumulative dump)'], ['merge', 'Add only rows not already loaded (an incremental file)']], 'replace');
    const projs = Object.entries(s.projects || {});
    const proj = select([['', 'All rows'], ...projs.map(([k, n]) => [k, `${k} (${fmt.n(n)} rows)`])], s.default_project || '');
    const newcat = h('input', { type: 'checkbox', checked: true }); const newlines = h('input', { type: 'checkbox' });
    const gl = kind === 'transactions' || kind === 'labour' || kind === 'po';
    modal({ title: `Load ${labels[kind]}`, size: 'wide', body: h('div', { class: 'grid' },
      h('div', { class: 'note' }, `${f.name}, sheet "${s.sheet}": columns matched.${hits.length > 1 ? ' Other sheets of this type in the file are ignored.' : ''}`),
      h('div', { class: 'tw' }, h('table', { class: 't' }, h('thead', {}, h('tr', {}, h('th', {}, 'Tool field'), h('th', {}, 'Pronto column'))), h('tbody', {}, Object.entries(s.mapped).slice(0, 14).map(([k, v]) => h('tr', {}, h('td', { class: 'mono' }, k), h('td', {}, v)))))),
      field('Loading mode', mode), projs.length ? field('Pronto project', proj, 'The file holds more than one project: only this one is loaded') : null,
      kind === 'transactions' ? h('label', { class: 'row small' }, newcat, 'Add Pronto categories that are not yet in the CBS') : null,
      gl ? h('label', { class: 'row small' }, newlines, 'Create a CBS line for every new employee or subcontractor found') : null),
      actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} }, { label: 'Load', onClick: async () => {
        const r = await api.post(p('/pronto/commit'), { token: a.token, filename: a.filename, items: [{ sheet: s.sheet, kind, header_row: s.header_row, mode: mode.value, pronto_project: proj.value || null }], create_categories: kind === 'transactions' && newcat.checked, create_lines: gl && newlines.checked, pronto_project: proj.value || null });
        const x = r.results[0]; toast(`${labels[kind]}: ${fmt.n(x.rows_new)} rows loaded${x.rows_skipped ? `, ${fmt.n(x.rows_skipped)} skipped` : ''}${r.lines_created ? `; ${r.lines_created} CBS lines created` : ''}`); await render(); } }] });
  }

  // ---- missing categories ---------------------------------------------------------------------
  if (miss.length) root.append(h('div', { class: 'card', style: { marginBottom: '14px', borderColor: 'var(--bad)' } }, h('div', { class: 'ch' }, h('h2', {}, `Categories in Pronto that are not in the CBS (${miss.length})`), h('span', { class: 'sp' }), h('button', { class: 'btn', onclick: async () => { for (const c of miss) await api.post(p('/categories'), { code: c.code, name: c.name }); toast('Categories added'); render(); } }, 'Add all to the CBS')),
    h('div', { class: 'small muted', style: { marginBottom: '8px' } }, 'These are usually project-specific variation trackers (for example PL10). Until they exist in the CBS their cost cannot be placed and CTD will not tie out.'),
    table([{ label: 'Code', f: (c) => h('span', { class: 'mono' }, c.code) }, { label: 'Description from Pronto', f: (c) => c.name }, { label: 'Rows', r: 1, f: (c) => fmt.n(c.rows) }, { label: 'Cost', r: 1, f: (c) => fmt.money(c.cost) }], miss)));

  // ---- new resources --------------------------------------------------------------------------
  const items = sug.items;
  const box = h('div', { class: 'card', style: { marginBottom: '14px' } });
  box.append(h('div', { class: 'ch' }, h('h2', {}, `New employees and subcontractors (${items.length})`), h('span', { class: 'sp' })));
  if (!items.length) box.append(h('div', { class: 'good' }, 'Every resource posting cost already has a CBS line.'));
  else {
    const chk = items.map((it) => h('input', { type: 'checkbox', checked: Math.abs(it.cost) > 1 }));
    const all = h('input', { type: 'checkbox', checked: true, onchange: (e) => chk.forEach((c) => (c.checked = e.target.checked)) });
    box.querySelector('.ch').append(h('button', { class: 'btn', onclick: async () => {
      const pick = items.filter((_, i) => chk[i].checked);
      if (!pick.length) return toast('Tick the resources to add', 'bad');
      const r = await api.post(p('/pronto/suggestions/apply'), { items: pick }); toast(`${r.created} CBS lines created`); render();
    } }, 'Create CBS lines for ticked resources'));
    box.append(h('div', { class: 'small muted', style: { marginBottom: '8px' } }, 'Their cost is parked on the (Unallocated) pot of its category until a line exists. Created lines start with no allowance; fund them with a transfer on the CBS page.'),
      h('div', { class: 'tw', style: { maxHeight: '320px' } }, h('table', { class: 't' }, h('thead', {}, h('tr', {}, [h('th', {}, all), ...['Category', 'Type', 'Code', 'Name', 'Rows', 'Cost', 'First', 'Last'].map((x, i) => h('th', { class: i >= 4 && i <= 5 ? 'r' : '' }, x))])),
        h('tbody', {}, items.map((it, i) => h('tr', {}, h('td', {}, chk[i]), h('td', { class: 'mono' }, it.category), h('td', {}, it.kind), h('td', { class: 'mono' }, it.resource_code), h('td', {}, it.name || ''), h('td', { class: 'r' }, fmt.n(it.rows)), h('td', { class: 'r num' }, fmt.money(it.cost)), h('td', {}, fmt.date(it.first)), h('td', {}, fmt.date(it.last))))))));
  }
  root.append(box);

  // ---- batches --------------------------------------------------------------------------------
  root.append(h('div', { class: 'card' }, h('h2', {}, 'Import history'),
    batches.length ? table([{ label: 'When', f: (b) => b.uploaded_at }, { label: 'Report', f: (b) => labels[b.kind] }, { label: 'File', f: (b) => b.filename || '' }, { label: 'Sheet', f: (b) => b.sheet || '' }, { label: 'Mode', f: (b) => b.mode }, { label: 'Read', r: 1, f: (b) => fmt.n(b.rows_read) }, { label: 'Loaded', r: 1, f: (b) => fmt.n(b.rows_new) }, { label: 'Skipped', r: 1, f: (b) => fmt.n(b.rows_skipped) }, { label: 'To', f: (b) => fmt.date(b.as_of) },
      { label: '', f: (b) => h('button', { class: 'btn danger sm', onclick: async () => { if (await confirmBox('Remove the rows loaded by this import? Earlier imports are not restored.', 'Remove rows', true)) { await api.del(p(`/pronto/batches/${b.id}`)); render(); } } }, 'Undo') }], batches) : h('div', { class: 'muted' }, 'Nothing uploaded yet.')));
}

// ---- Pronto data > Inspect: the rows exactly as loaded ---------------------------------------------------------
const LABELS = { transactions: 'GL transactions', labour: 'Labour timesheets', po: 'Purchase orders', claims: 'Customer claims', variations: 'Variations', ctd: 'CTD overview' };

async function inspect(root, params) {
  const kind = params.inspect;
  const st = { q: params.q || '', check: params.check || '', sort: '', desc: 1, offset: 0 };
  const checks = await api.get(p('/pronto/checks'));
  const mine = checks.filter((c) => c.kind === kind && c.count);
  const q = h('input', { type: 'search', placeholder: 'Search every column (several words narrow it down)', value: st.q, style: { minWidth: '320px' } });
  const chk = select([['', 'All rows'], ...mine.map((c) => [c.id, c.title])], st.check);
  const info = h('div', { class: 'small muted' });
  const body = h('div');
  const note = h('div', { class: 'note', style: { marginBottom: '10px' } });
  const showNote = () => { const sel = mine.filter((c) => !st.check || c.id === st.check); clear(note).append(...sel.map((c) => h('div', {}, h('b', {}, c.title), ' \u2013 ', c.detail))); note.style.display = sel.length ? '' : 'none'; };
  const qs = () => new URLSearchParams({ q: st.q, check: st.check, sort: st.sort, desc: st.desc, offset: st.offset, limit: 500 });
  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, `${LABELS[kind]}: rows as loaded`), h('div', { class: 'sub' }, 'Exactly what PMT read from the Pronto report, before any rollup. Use it to find a totals row, a date keyed in the wrong year or a keying error.')),
    h('div', { class: 'sp' }), h('button', { class: 'btn ghost', onclick: () => window.open(p(`/pronto/raw-xlsx/${kind}?`) + new URLSearchParams({ q: st.q, check: st.check })) }, 'Export to Excel'), h('button', { class: 'btn ghost', onclick: () => go('pronto') }, 'Back to Pronto data')),
    h('div', { class: 'row', style: { marginBottom: '10px' } }, q, chk, h('span', { class: 'sp' }), info),
    note, body);
  q.oninput = debounce(() => { st.q = q.value; st.offset = 0; load(); }, 300);
  chk.onchange = () => { st.check = chk.value; st.offset = 0; showNote(); load(); };
  showNote();
  async function load() {
    const d = await api.get(p(`/pronto/raw/${kind}?${qs()}`));
    clear(info).append(`${fmt.n(d.count)} row${d.count === 1 ? '' : 's'} \u00b7 total ${fmt.money(d.amount)}`);
    const head = h('tr', {}, d.columns.map((c) => h('th', { class: c.money ? 'r' : '', style: { cursor: 'pointer' }, title: 'Sort', onclick: () => { st.desc = st.sort === c.key ? 1 - st.desc : 1; st.sort = c.key; st.offset = 0; load(); } }, c.label, st.sort === c.key ? (st.desc ? ' \u25be' : ' \u25b4') : '')));
    const cell = (c, v) => v == null ? '' : c.money ? fmt.money(v) : /date|worked|ordered|due|submitted|certified|created|paid|approved_date|received_date/.test(c.key) && /^\d{4}-\d\d-\d\d/.test(v) ? fmt.date(v) : String(v);
    const pager = d.count > 500 ? h('div', { class: 'row', style: { marginTop: '8px' } },
      h('button', { class: 'btn ghost sm', disabled: !d.offset, onclick: () => { st.offset = Math.max(0, d.offset - 500); load(); } }, 'Previous 500'),
      h('span', { class: 'small muted' }, `Rows ${fmt.n(d.offset + 1)} to ${fmt.n(Math.min(d.count, d.offset + 500))} of ${fmt.n(d.count)}`),
      h('button', { class: 'btn ghost sm', disabled: d.offset + 500 >= d.count, onclick: () => { st.offset = d.offset + 500; load(); } }, 'Next 500')) : null;
    clear(body).append(d.rows.length ? h('div', { class: 'tw', style: { maxHeight: '70vh' } }, h('table', { class: 't' }, h('thead', {}, head),
      h('tbody', {}, d.rows.map((r) => h('tr', {}, d.columns.map((c) => h('td', { class: c.money ? 'r num' : (c.key === 'description' || c.key === 'notes' ? '' : 'nowrap') }, cell(c, r[c.key])))))))) : empty('No rows match.'), ...(pager ? [pager] : []));
  }
  await load();
}
