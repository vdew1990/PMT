import { h, clear, fmt, modal, toast, field, select, table, num, confirmBox, badge, tabs, empty, debounce, sortableRows } from '../ui.js';
import { api, state, p, loadRows, isCompany, pref } from '../api.js';
import { pickNode, indexRows } from '../scope.js';
import { go, render } from '../app.js';

// CBS and allowances: build the structure, enter proposal allowances, add lines as people and subcontractors join.
export default async function cbs(root, params) {
  const data = await loadRows();
  const rows = data.rows;
  const init = !!data.initialised;
  const { kids } = indexRows(rows);
  const lv0 = +pref('cbs_level');  // Settings > Your defaults
  const expanded = new Set(JSON.parse(sessionStorage.getItem('cbsExp') || 'null') || rows.filter((r) => r.kind === 'group' && (lv0 ? r.level < lv0 : r.level === 1)).map((r) => String(r.id)));
  let tab = params.tab || 'tree';
  let q = '';
  const t = state.rows.total;
  const showRisk = !init || isCompany();   // before initialising the baseline is being set; afterwards the PM does not see the risk bucket

  root.append(h('div', { class: 'pagehead' },
    h('div', {}, h('h1', {}, 'CBS and allowances'),
      h('div', { class: 'sub' }, init ? 'Cost control is live: the original estimate is locked. Move allowance with transfers; add lines when people and subcontractors join.' : 'Build the structure and enter the proposal allowances. Budget and risk are editable until you initialise cost control.')),
    h('div', { class: 'sp' }),
    h('button', { class: 'btn ghost', onclick: () => addDialog(null) }, '+ Add line or group'),
    h('button', { class: 'btn ghost', onclick: () => window.open(p('/template.xlsx')) }, 'Excel template'),
    h('button', { class: 'btn ghost', title: 'Take allowance per line, transfers, forecast and accruals from the PMT Excel workbook', onclick: loadWorkbook }, 'Load PMT workbook...'),
    init ? h('button', { class: 'btn ghost', onclick: unlock }, 'Unlock estimate') : null));
  root.append(h('div', { class: 'grid g4', style: { marginBottom: '14px' } },
    kpi('Original budget', fmt.money(t.orig_budget)), showRisk ? kpi('Original risk', fmt.money(t.orig_risk)) : kpi('Contingency held', fmt.money(t.cont_earmark)),
    kpi('Approved variations', fmt.money(t.variations)), kpi(isCompany() ? 'Current allowance' : 'Current budget', fmt.money(t.allowance))));

  const body = h('div');
  root.append(tabs([['tree', 'Structure and estimate'], ['ledger', 'Allowance movements']], tab, (k) => { sessionStorage.setItem('cbsExp', JSON.stringify([...expanded])); go('cbs', { tab: k }); }), body);
  if (tab === 'ledger') return ledgerTab(body);

  const search = h('input', { type: 'search', placeholder: 'Search the CBS...', oninput: debounce(() => { q = search.value.trim().toLowerCase(); draw(); }, 150), style: { width: '260px' } });
  const tw = h('div');
  let lvl = +(sessionStorage.getItem('cbsLvl') || lv0 || 0);
  const lvChips = [1, 2, 3, 4, 5].map((n) => h('span', { class: 'chip' + (lvl === n ? ' on' : ''), onclick: () => {
    lvl = n; sessionStorage.setItem('cbsLvl', String(n)); expanded.clear();
    rows.forEach((r) => { if (r.kind === 'group' && r.level < n) expanded.add(String(r.id)); });
    lvChips.forEach((c, i) => c.classList.toggle('on', i + 1 === n)); draw(); } }, `Level ${n}`));
  body.append(h('div', { class: 'row', style: { marginBottom: '10px' } }, search,
    // same as cost control: show the tree down to a level (each row's arrow still opens or closes it on its own)
    h('span', { class: 'small muted' }, 'Expand to'), ...lvChips,
    h('span', { class: 'muted small' }, 'Blue-bordered cells are inputs. An (Unallocated) row is allowance held on the group itself, not yet moved to a named line.')), tw);

  function kpi(l, v) { return h('div', { class: 'kpi' }, h('div', { class: 'l' }, l), h('div', { class: 'v' }, v)); }

  async function saveEstimate(r, b, k) {
    const nodeId = r.kind === 'pot' ? r.node_id : r.id;
    try { await api.put(p(`/nodes/${nodeId}/estimate`), { budget: num(b), risk: k === '' ? null : num(k) }); toast('Estimate saved'); await refresh(); } catch (e) { toast(e.message, 'bad'); }
  }
  async function refresh() { sessionStorage.setItem('cbsExp', JSON.stringify([...expanded])); await render(); }

  function draw() {
    const match = (r) => !q || `${r.code} ${r.name} ${r.function || ''} ${r.resource_code || ''}`.toLowerCase().includes(q);
    const has = (r) => match(r) || (kids.get(String(r.id)) || []).some(has) || (r.kind === 'group' && rows.some((x) => x.kind === 'pot' && x.parent_id === r.id && match(x)));
    const trs = [];
    const walk = (r) => {
      if (q && !has(r)) return;
      const ch = rows.filter((x) => x.parent_id === r.id && (x.kind !== 'pot' || true));
      trs.push(r);
      const open = q ? true : expanded.has(String(r.id));
      if (r.kind === 'group' && open) ch.forEach((c) => (c.kind === 'pot' ? trs.push(c) : walk(c)));
    };
    rows.filter((r) => r.level === 1).forEach(walk);
    const tbody = h('tbody');
    const trEls = [];
    trs.forEach((r) => {
      const editable = !init && r.level >= 2;
      const isPot = r.kind === 'pot';
      const cls = r.level === 1 ? 'gp' : r.kind !== 'group' ? '' : r.level === 2 ? 'par' : 'par2';
      const open = expanded.has(String(r.id));
      const hasKids = r.kind === 'group' && rows.some((x) => x.parent_id === r.id);
      const tog = h('span', { class: 'tog', onclick: () => { open ? expanded.delete(String(r.id)) : expanded.add(String(r.id)); draw(); } }, hasKids ? (open ? '▾' : '▸') : '');
      const own = isPot || r.kind === 'line';
      const b = h('input', { type: 'number', step: '0.01', value: isPot || r.kind === 'line' ? Math.round((r.orig_budget || 0) * 100) / 100 : '' });
      const k = h('input', { type: 'number', step: '0.01', value: isPot || r.kind === 'line' ? Math.round((r.orig_risk || 0) * 100) / 100 : '', placeholder: 'auto' });
      const commit = () => { if (editable && own) saveEstimate(r, b.value, k.value); };
      b.onchange = commit; k.onchange = commit;
      const tr = h('tr', { class: cls },
        h('td', { class: 'mono' }, h('span', { style: { paddingLeft: (r.level - 1) * 16 + 'px' } }), tog, r.code),
        h('td', {}, r.name, r.kind === 'line' && r.origin === 'pronto' ? h('span', { class: 'badge', style: { marginLeft: '6px' } }, 'from Pronto') : null),
        h('td', { class: 'muted' }, r.function || ''),
        h('td', { class: 'mono muted' }, r.resource_code || ''),
        dateCell(r, 'start'), dateCell(r, 'end'),
        own && editable ? h('td', { class: 'in r' }, b) : h('td', { class: 'r num' }, own ? fmt.money(r.orig_budget) : fmt.money(r.orig_budget)),
        showRisk ? (own && editable ? h('td', { class: 'in r' }, k) : h('td', { class: 'r num' }, fmt.money(r.orig_risk))) : null,
        h('td', { class: 'r num' }, fmt.money(r.allowance - r.orig_budget - (isCompany() || !init ? r.orig_risk : 0) - r.variations)),
        h('td', { class: 'r num' }, fmt.money(r.variations)),
        h('td', { class: 'r num', style: { fontWeight: 700 } }, fmt.money(r.allowance)),
        contCell(r),
        h('td', { class: 'r num ' + (r.allowance < -1 ? 'bad' : '') }, r.kind === 'group' ? fmt.n(r.n_lines || 0) : ''),
        h('td', { class: 'nowrap' }, r.level >= 2 ? rowActions(r) : ''));
      tbody.append(tr);
      trEls.push(tr);
    });
    // drag a group or line among its siblings (the standard categories and the (Unallocated) pots stay put)
    sortableRows(trEls, trs, { group: (r) => r.parent_id, canDrag: (r) => r.kind !== 'pot' && r.level >= 2,
      save: async (ids) => { await api.post(p('/reorder/cbs'), { ids }); sessionStorage.setItem('cbsExp', JSON.stringify([...expanded])); await render(); } });
    const th = ['CBS', 'Name', 'Function / trade', 'Resource', 'Start', 'End', 'Original budget', ...(showRisk ? ['Original risk'] : []), 'Transfers and adj.', 'Variations', isCompany() ? 'Total allowance' : 'Current allowance', 'Contingency', 'Lines', ''];
    const tbl = h('table', { class: 't' }, h('thead', {}, h('tr', {}, th.map((x, i) => h('th', { class: i >= 6 && i <= 11 + (showRisk ? 1 : 0) ? 'r' : '', title: x === 'Contingency' ? 'The part of the budget you hold back for market movements. It can be moved into risk cover once a risk cost has occurred.' : '', title: i === 4 || i === 5 ? 'When the activity starts and ends. A group\'s dates apply to every line below it that has none of its own.' : '' }, x)))), tbody);
    // total line: the top-level groups add up to the whole project (whatever is expanded or filtered)
    const top = rows.filter((r) => r.level === 1); const sum = (f) => top.reduce((a, r) => a + (f(r) || 0), 0);
    const tc = (v, bold) => h('td', { class: 'r num', style: bold ? { fontWeight: 700 } : {} }, fmt.money(v));
    tbl.append(h('tfoot', {}, h('tr', { class: 'total' }, h('td', {}, 'TOTAL'), h('td', {}, 'Whole project'), h('td'), h('td'), h('td'), h('td'),
      tc(sum((r) => r.orig_budget)), showRisk ? tc(sum((r) => r.orig_risk)) : null,
      tc(sum((r) => r.allowance - r.orig_budget - (isCompany() || !init ? r.orig_risk : 0) - r.variations)), tc(sum((r) => r.variations)), tc(sum((r) => r.allowance), true),
      tc(sum((r) => r.cont_earmark)), h('td', { class: 'r num' }, fmt.n(sum((r) => r.n_lines))), h('td'))));
    clear(tw).append(h('div', { class: 'tw', style: { maxHeight: '68vh' } }, tbl));
  }

  // Contingency the PM holds back inside the budget (market fluctuations). Risk cover is funded from it, then from the company bucket.
  function contCell(r) {
    if (r.level < 2 || r.kind === 'group' && r.n_lines > 0 && false) return h('td');
    const inp = h('input', { type: 'number', step: '0.01', value: r.cont_earmark ? Math.round(r.cont_earmark * 100) / 100 : '', placeholder: '0', style: { width: '104px' }, disabled: r.kind === 'group' });
    if (r.kind === 'group') return h('td', { class: 'r num muted' }, r.cont_earmark ? fmt.money(r.cont_earmark) : '');
    inp.onchange = async () => { try { await api.post(p('/risk/contingency'), { node_id: r.node_id, amount: num(inp.value) }); toast('Contingency saved'); await refresh(); } catch (e) { toast(e.message, 'bad'); refresh(); } };
    return h('td', { class: 'in' }, inp);
  }

  // Start and end of the activity. Blank inherits from the group above, then the project dates.
  function dateCell(r, which) {
    if (r.level < 2 || r.kind === 'pot') return h('td');
    const own = which === 'start' ? r.start_own : r.end_own; const eff = which === 'start' ? r.start : r.end;
    const inp = h('input', { type: 'date', value: own || '', title: own ? 'Set on this item' : (eff ? `Inherited: ${eff}` : 'Uses the project dates'), style: { width: '132px', opacity: own ? 1 : .55 } });
    inp.onchange = async () => { try { await api.put(p(`/nodes/${r.node_id}`), { [which === 'start' ? 'start_date' : 'end_date']: inp.value || null }); toast('Dates saved'); await refresh(); } catch (e) { toast(e.message, 'bad'); } };
    return h('td', { class: 'in' }, inp);
  }

  function rowActions(r) {
    const out = h('span', { class: 'row', style: { gap: '4px', flexWrap: 'nowrap' } });
    if (r.kind === 'group') out.append(h('button', { class: 'btn ghost sm', title: 'Add a line or sub-group here', onclick: () => addDialog(r) }, '+'));
    if (r.kind !== 'group' || r.level >= 2) out.append(h('button', { class: 'btn ghost sm', title: 'Move allowance', onclick: () => transferDialog(r) }, 'Transfer'));
    if (r.kind === 'line') out.append(h('button', { class: 'btn ghost sm', onclick: () => editDialog(r) }, 'Edit'));
    if ((r.kind === 'line' || (r.kind === 'group' && r.origin !== 'standard'))) out.append(h('button', { class: 'btn danger sm', onclick: () => remove(r) }, '×'));
    return out;
  }

  async function remove(r) {
    if (!(await confirmBox(`Remove ${r.code} ${r.name}? Lines with actuals or movements cannot be removed; deactivate them instead.`, 'Remove', true))) return;
    try { await api.del(p(`/nodes/${r.node_id}`)); await refresh(); } catch (e) { toast(e.message, 'bad'); }
  }

  async function unlock() {
    if (!(await confirmBox('Unlocking lets you change the original estimate. Use it only to correct set-up errors; later changes belong in transfers.', 'Unlock', true))) return;
    await api.post(p('/unlock-estimate')); await refresh();
  }

  function groupsFor(parent) {
    return rows.filter((r) => r.kind === 'group' && r.level >= 2).map((r) => [r.id, `${r.code}  ${r.name}`]);
  }

  async function addDialog(parent) {
    const res = await api.get(p('/resources'));
    const parentSel = select(groupsFor(), parent ? parent.id : '');
    const kind = select([['line', 'Line: a named employee or company'], ['group', 'Group: a role, trade or sub-category allowance']], 'line');
    const name = h('input', { type: 'text', placeholder: 'Name shown in the CBS' });
    const rkind = select([['supplier', 'Supplier / subcontractor'], ['employee', 'Employee']], parent && parent.gp === 'PL' ? 'employee' : 'supplier');
    const pick = h('select'); const code = h('input', { type: 'text', placeholder: 'Pronto code, e.g. S30ABC01 or JSMI01' }); const rname = h('input', { type: 'text' }); const func = h('input', { type: 'text', placeholder: 'Role or trade' });
    const budget = h('input', { type: 'number', step: '0.01', placeholder: '0' }); const risk = h('input', { type: 'number', step: '0.01', placeholder: 'default %' });
    const start = h('input', { type: 'date' }); const end = h('input', { type: 'date' });
    const methods = select([['', 'Default for category'], ...Object.keys(state.tax.methods)], '');
    const fillPick = () => { clear(pick).append(h('option', { value: '' }, '(new resource: type the code below)')); res.filter((x) => x.kind === rkind.value).forEach((x) => pick.append(h('option', { value: x.code }, `${x.name || ''}  [${x.code}]`))); };
    rkind.onchange = fillPick; fillPick();
    pick.onchange = () => { const x = res.find((y) => y.kind === rkind.value && y.code === pick.value); if (x) { code.value = x.code; rname.value = x.name || ''; func.value = x.function || ''; if (!name.value) name.value = x.name || ''; } };
    const lineOnly = h('div', { class: 'grid' }, h('div', { class: 'grid g2' }, field('Resource type', rkind), field('Pick an existing resource', pick)),
      h('div', { class: 'grid g3' }, field('Pronto code', code), field('Resource name', rname), field('Function / trade', func)),
      h('div', { class: 'grid g3' }, field('Forecast method', methods), field('Start', start), field('End', end)));
    kind.onchange = () => lineOnly.classList.toggle('hide', kind.value !== 'line');
    modal({
      title: 'Add to the CBS', size: 'wide',
      body: h('div', { class: 'grid' }, field('Parent group', parentSel), field('What are you adding?', kind), field('Display name', name, 'Leave blank to use the resource name'),
        lineOnly, h('div', { class: 'grid g2' }, field('Budget (proposal allowance)', budget, init ? 'Cost control is live, so use a transfer to fund it' : ''), field('Risk', risk, 'Blank applies the project default %')),
        h('div', { class: 'note' }, 'New subcontractors and employees can also be created in one go from the Pronto page, which lists every resource posting cost without a CBS line.')),
      actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} }, {
        label: 'Add', onClick: async () => {
          const body = { parent_id: +parentSel.value, kind: kind.value, name: name.value || rname.value, budget: init ? 0 : num(budget.value), risk: init || risk.value === '' ? null : num(risk.value) };
          if (kind.value === 'line') Object.assign(body, { resource_kind: rkind.value, resource_code: code.value || undefined, resource_name: rname.value || name.value, function: func.value, method: methods.value || undefined, start_date: start.value || undefined, end_date: end.value || undefined });
          const r = await api.post(p('/nodes'), body);
          if (init && num(budget.value)) { const par = rows.find((x) => x.id === +parentSel.value); await api.post(p('/ledger/transfer'), { from_id: +parentSel.value, to_id: r.id, budget: num(budget.value), risk: num(risk.value), note: 'Funded at creation' }); }
          toast('Added'); expanded.add(parentSel.value); await refresh();
        } }],
    });
  }

  function editDialog(r) {
    const name = h('input', { type: 'text', value: r.name }); const func = h('input', { type: 'text', value: r.function || '' }); const scope = h('input', { type: 'text', value: r.scope || '' });
    const po = h('input', { type: 'text', value: r.po_no || '', placeholder: 'e.g. 1953, 2114' }); const start = h('input', { type: 'date', value: r.start || '' }); const end = h('input', { type: 'date', value: r.end || '' });
    const active = h('input', { type: 'checkbox', checked: r.active !== 0 });
    modal({ title: `Edit ${r.code}`, body: h('div', { class: 'grid' }, field('Name', name), h('div', { class: 'grid g2' }, field('Function / trade', func), field('Scope', scope)),
      field('PO numbers bound to this line', po, 'Use when a supplier has several lines and each PO belongs to one of them'), h('div', { class: 'grid g2' }, field('Start', start), field('End', end)),
      h('label', { class: 'row' }, active, 'Active (untick when the resource leaves the project)')),
      actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} }, { label: 'Save', onClick: async () => { await api.put(p(`/nodes/${r.id}`), { name: name.value, function: func.value, scope: scope.value, po_no: po.value, start_date: start.value || null, end_date: end.value || null, active: active.checked ? 1 : 0 }); await api.post(p('/pronto/resolve')); await refresh(); } }] });
  }

  function transferDialog(r) {
    const nodeId = r.node_id;
    const to = h('input', { type: 'text', readOnly: true, value: `${r.code} ${r.name}` });
    let toId = nodeId; let fromId = null;
    const fromBtn = h('button', { class: 'btn ghost', onclick: () => pickNode({ title: 'Move allowance from', kinds: ['group', 'line', 'pot'], showEac: false, onPick: (x) => { fromId = x.node_id ?? x.id; fromBtn.textContent = `${x.code} ${x.name}`; } }) }, 'Choose source...');
    const b = h('input', { type: 'number', step: '0.01' }); const k = h('input', { type: 'number', step: '0.01', value: 0 });
    const ref = h('input', { type: 'text', placeholder: 'Reference or approval' }); const note = h('input', { type: 'text' });
    modal({ title: 'Move allowance', body: h('div', { class: 'grid' },
      h('div', { class: 'note' }, 'A transfer moves budget and risk between CBS items. The total allowance does not change, and the movement stays in the ledger.'),
      field('From', fromBtn), field('To', to), h('div', { class: 'grid g2' }, field('Budget', b), field('Risk', k)), field('Reference', ref), field('Reason', note)),
      actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} }, { label: 'Post transfer', onClick: async () => {
        if (!fromId) throw new Error('Choose where the allowance comes from');
        await api.post(p('/ledger/transfer'), { from_id: fromId, to_id: toId, budget: num(b.value), risk: num(k.value), ref: ref.value, note: note.value });
        toast('Transfer posted'); await refresh(); } }] });
  }

  draw();
}

async function ledgerTab(body) {
  const led = await api.get(p('/ledger'));
  if (!led.length) { body.append(empty('No allowance movements yet', 'Transfers, risk releases, adjustments and approved variations will be listed here.')); return; }
  body.append(table([
    { label: 'Date', f: (r) => fmt.date(r.date) || fmt.date((r.created_at || '').slice(0, 10)) }, { label: 'Type', f: (r) => badge(r.kind.replace('_', ' '), r.kind === 'variation' ? 'navy' : '') },
    { label: 'CBS', f: (r) => h('span', { class: 'mono' }, r.code) }, { label: 'Name', f: (r) => r.name }, { label: 'Budget', r: 1, f: (r) => h('span', { class: r.budget < 0 ? 'bad' : '' }, fmt.money(r.budget, 2)) },
    { label: 'Risk', r: 1, f: (r) => fmt.money(r.risk, 2) }, { label: 'Ref', f: (r) => r.ref || '' }, { label: 'Reason', f: (r) => r.note || '' },
    { label: '', f: (r) => ['estimate', 'variation'].includes(r.kind) ? '' : h('button', { class: 'btn danger sm', onclick: async () => { if (await confirmBox('Reverse this movement (both sides of a transfer)?', 'Reverse', true)) { await api.del(p(`/ledger/${r.id}`)); await render(); } } }, 'Reverse') },
  ], led, { maxHeight: '70vh' }));
}

// ---- the PMT Excel workbook: allowance per line, its ledger, the forecast grid and the accrual register -----------------
function loadWorkbook() {
  const input = h('input', { type: 'file', accept: '.xlsm,.xlsx' });
  const out = h('div', { style: { marginTop: '10px' } });
  let token = null;
  const money = (v) => fmt.money(v);
  input.onchange = async () => {
    if (!input.files[0]) return;
    clear(out).append(h('div', { class: 'muted' }, `Reading ${input.files[0].name} (a large workbook takes a minute)...`));
    try {
      const r = await api.upload(p('/pmt-workbook/preview'), input.files[0]);
      token = r.token;
      const t = r.totals;
      clear(out).append(...(r.status_month !== r.project_status_month ? [h('div', { class: 'note bad' }, `The workbook's status month is ${fmt.month(r.status_month)}, this project's is ${fmt.month(r.project_status_month)}. Set the status date in Project setup first so the forecast months line up.`)] : []),
        table([{ label: 'From the workbook', f: (x) => x[0] }, { label: '', r: 1, f: (x) => x[1] }], [
          ['Cost Control lines', `${fmt.n(r.lines)} (${fmt.n(r.matched)} matched to a Pronto line by resource code)`],
          ['Lines to create', r.create.length ? r.create.map((c) => `${c.cat} ${c.name}`).join(', ') : 'none'],
          ['Empty lines left out', fmt.n(r.skipped.length)],
          ['Ledger movements replayed', fmt.n(r.ledger)],
          ['Accrual register rows', `${fmt.n(r.accruals)} (${money(r.accrual_total)} before automatic reversals)`],
          ['Budget + risk = allowance', `${money(t.budget)} + ${money(t.risk)} = ${money(t.allowance)}`],
          ['CTD / ACC / CTC / EAC in the workbook', `${money(t.ctd)} / ${money(t.acc)} / ${money(t.ctc)} / ${money(t.eac)}`],
          ['Forecast grid from the status month', money(t.grid_forecast)]]),
        h('div', { class: 'note', style: { marginTop: '8px' } }, 'Applying sets every line\'s allowance to the workbook (the ledger is replayed as transfers, then trued up), makes each line MANUAL with the workbook\'s month grid from the status month, and loads the accrual register. Applying again replaces an earlier workbook import; nothing else changes.'));
    } catch (e) { clear(out).append(h('div', { class: 'note bad' }, e.message)); }
  };
  modal({ title: 'Load from the PMT workbook', size: 'wide', body: h('div', {}, h('div', { class: 'small muted', style: { marginBottom: '8px' } }, 'Choose the PMT Excel workbook (.xlsm). Nothing changes until you apply.'), input, out),
    actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} }, { label: 'Apply', onClick: async () => {
      if (!token) { toast('Choose the workbook first', 'bad'); return false; }
      const r = await api.post(p('/pmt-workbook/apply'), { token });
      const keys = ['budget', 'risk', 'ctd', 'acc', 'ctc', 'eac'];
      const diff = r.tieout.filter((c) => keys.some((k) => Math.abs(c['app_' + k] - c['wb_' + k]) > 1));
      const sum = (k) => r.tieout.reduce((a, c) => a + c[k], 0);
      modal({ title: 'Workbook loaded: tie-out', size: 'wide', body: h('div', {},
        h('div', { class: 'note' }, `${fmt.n(r.created)} lines created, ${fmt.n(r.accruals_loaded)} accruals loaded. Totals, workbook against PMT: allowance ${money(sum('wb_budget') + sum('wb_risk'))} / ${money(sum('app_budget') + sum('app_risk'))}, ACC ${money(sum('wb_acc'))} / ${money(sum('app_acc'))}, EAC ${money(sum('wb_eac'))} / ${money(sum('app_eac'))}.`),
        h('div', { class: 'small muted', style: { margin: '8px 0' } }, 'Categories that differ (PMT less workbook). CTC differs where the workbook\'s CTC leaves out the current month\'s forecast (its "CURRENT (F)" column, flagged in its EAC delta); CTD where Pronto has rows the workbook\'s extract did not.'),
        diff.length ? table([{ label: 'Category', f: (c) => c.category }, ...keys.map((k) => ({ label: k.toUpperCase(), r: 1, f: (c) => money(c['app_' + k] - c['wb_' + k]) }))], diff) : h('div', { class: 'good' }, 'Every category ties.')),
        actions: [{ label: 'Close', onClick: () => render() }] });
    } }] });
}
