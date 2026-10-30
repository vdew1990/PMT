import { h, clear, fmt, modal, toast, field, select, table, num, confirmBox, badge, tabs, empty, todayISO, chart, PALETTE } from '../ui.js';
import { api, state, p, loadRows, statusMonth } from '../api.js';
import { pickNode } from '../scope.js';
import { render, go } from '../app.js';
import { historyDialog, stamp } from '../history.js';
import { supplierPicker } from './_supplier.js';

// COST > Accruals. How an accrual comes about, and how it ties out (app/accruals.py):
//   Estimate of work done      the PM's valuation of a month's work: the least certain, reversed by the PM
//   Invoice awaiting approval  supplier + PO / invoice / quote number: matched automatically when the invoice lands
//   Timesheet hours            per person per day on the labour calendar: reversed by the posted timesheet
//   Subcontract claims         automatic, from the claims received on Subcontracts
// and what is already accrued elsewhere: finance's accruals in Pronto (Work in Progress) and unposted timesheets.
const KIND = { work: ['Your estimate (highest risk)', 'warn'], invoice: ['Awaiting approval', ''], hours: ['Timesheet hours', ''], claim: ['Subcontract claim', ''] };
const SRC_TONE = { estimate: 'warn', approval: '', claim: '', finance: 'navy', timesheet: '' };
const STATUS = { open: ['Open', 'warn'], partial: ['Part landed, rest open', 'warn'], matched: ['Matched to the invoice', 'good'], investigate: ['Invoice differs: review', 'bad'], cancelled: ['Cancelled', ''] };

// Shared by the cost-control drawer, the month-end review and this page.
export async function accrualDialog(nodeId, rows, onDone, existing = null, preset = {}) {
  const node = rows.find((r) => String(r.id) === String(nodeId) || String(r.node_id) === String(nodeId));
  let target = node ? node.node_id : nodeId;
  let kind = existing?.kind || preset.kind || (existing?.inv_ref || existing?.quote_ref ? 'invoice' : 'work');
  const cbsBtn = h('button', { class: 'btn ghost', onclick: () => pickNode({ title: 'Accrue against which line?', kinds: ['line', 'pot'], onPick: (r) => { target = r.node_id; cbsBtn.textContent = `${r.code} ${r.name}`; check(); } }) }, node ? `${node.code} ${node.name}` : 'Choose a CBS line...');
  const month = h('input', { type: 'month', value: existing?.month || preset.month || statusMonth() || todayISO().slice(0, 7) });
  const amount = h('input', { type: 'number', step: '0.01', value: existing?.amount ?? preset.amount ?? '' });
  const reason = select(['', ...state.tax.accrual_reasons], existing?.reason || preset.reason || (kind === 'invoice' ? 'Work done, invoice not yet received' : ''));
  const inv = h('input', { type: 'text', value: existing?.inv_ref || '', placeholder: 'e.g. INV-2261', onchange: () => check() });
  const quote = h('input', { type: 'text', value: existing?.quote_ref || '', placeholder: 'Quote number' });
  const note = h('input', { type: 'text', value: existing?.note || preset.note || '' });
  const why = existing ? h('textarea', { rows: 2, style: { width: '100%' }, placeholder: 'Why is this being changed? (required: it is kept in the history)' }) : null;
  const risks = await api.get(p('/risk')).then((r) => r.risks).catch(() => []);
  const riskSel = select([['', '(not risk related)'], ...risks.map((r) => [r.id, `${r.ref} ${r.title}`])], existing?.risk_id || '');
  const sup = await supplierPicker({ supplier_code: existing?.supplier_code, supplier_name: existing?.supplier_name, po_no: existing?.po_no });
  sup.el.addEventListener('change', () => check());
  const warnBox = h('div');
  const kindBox = h('div', { class: 'row', style: { gap: '8px' } });
  const invBox = h('div', { class: 'grid' }, sup.el, h('div', { class: 'grid g2' }, field('Invoice number', inv, 'Matches the invoice when it lands in Pronto'), field('Quote number', quote, 'Matches if the invoice quotes it')));
  const workNote = h('div', { class: 'note warn small' }, 'An estimate of the work done this month, with nothing to match it to: it stays accrued until you reverse it (or an invoice accrual replaces it). The least certain kind: keep the note specific.');
  const drawKind = () => {
    clear(kindBox).append(...[['work', 'Estimate of work done'], ['invoice', 'Invoice awaiting approval']].map(([k, l]) => h('span', { class: 'chip' + (kind === k ? ' on' : ''), onclick: () => { kind = k; drawKind(); } }, l)),
      h('a', { class: 'small', style: { marginLeft: '10px' }, onclick: () => { document.querySelector('.ov')?.remove(); go('calendar'); } }, 'Hours? Accrue them on the labour calendar'));
    invBox.style.display = kind === 'invoice' ? '' : 'none';
    workNote.style.display = kind === 'work' ? '' : 'none';
    check();
  };
  let timer = null;
  function check() {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      if (!target) return;
      const v = sup.value();
      const r = await api.post(p('/accruals/check'), { id: existing?.id, node_id: target, inv_ref: kind === 'invoice' ? inv.value : '', po_no: v.po_no, supplier_name: v.supplier_name }).catch(() => null);
      clear(warnBox);
      if (r?.error) warnBox.append(h('div', { class: 'note bad small' }, r.error));
      (r?.warnings || []).forEach((x) => warnBox.append(h('div', { class: 'note warn small' }, x)));
    }, 250);
  }
  modal({ title: existing ? 'Edit accrual' : 'Add accrual', size: 'wide', body: h('div', { class: 'grid' },
    h('div', {}, h('div', { class: 'small muted', style: { marginBottom: '4px' } }, 'What is this accrual?'), kindBox), workNote,
    field('CBS line', cbsBtn), h('div', { class: 'grid g2' }, field('Month the work was done', month, 'Matched invoices count in this month, whenever they land'), field('Amount (excl. GST)', amount)),
    invBox, warnBox,
    h('div', { class: 'grid g2' }, field('Reason', reason), field('Risk (if this cost landed because of a risk)', riskSel)), field('Note', note), why ? field('Why you are changing it (kept in the history)', why) : null),
  actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} }, { label: 'Save accrual', onClick: async () => {
    if (!target) throw new Error('Choose a CBS line');
    if (why && why.value.trim().length < 3) throw new Error('Give a reason for the change: it is kept in the history');
    const v = sup.value();
    const body = { id: existing?.id, kind, node_id: target, month: month.value, amount: num(amount.value), reason: reason.value, risk_id: riskSel.value ? +riskSel.value : null, note: note.value,
      po_no: v.po_no, supplier_code: v.supplier_code, supplier_name: v.supplier_name, inv_ref: kind === 'invoice' ? inv.value : null, quote_ref: kind === 'invoice' ? quote.value : null, change_reason: why ? why.value.trim() : undefined };
    const r = await api.post(p('/accruals'), body);
    toast((r.warnings || []).length ? r.warnings[0] : 'Accrual saved', (r.warnings || []).length ? 'warn' : undefined); onDone && onDone(); } }] });
  drawKind();
}

export default async function accruals(root, params = {}) {
  const tab = params.tab || 'register';
  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, 'Accruals'), h('div', { class: 'sub' }, 'Cost incurred but not yet in Pronto: they feed ACC, so EAC includes them. And what is accrued already, in Pronto or automatically.')),
    h('div', { class: 'sp' }), h('button', { class: 'btn', onclick: async () => accrualDialog(null, (await loadRows()).rows, render) }, '+ Add accrual')));
  root.append(tabs([['register', 'Register'], ['master', 'All accruals'], ['timelines', 'Work, billing and cash'], ['history', 'By month and history']], tab, (k) => { location.hash = '#/accruals?tab=' + k; }));
  if (tab === 'history') {
    const { historyPage } = await import('./_history.js');
    return historyPage(root, params, 'x', { title: 'Accruals by month', sub: 'Accrued cost by CBS line and month, as it stood at each month-end close: what was accrued then, and how the accrued balance moved.' });
  }
  if (tab === 'master') return masterList(root);
  if (tab === 'timelines') return timelines(root);
  const data = await loadRows();
  const d = await api.get(p('/accruals'));
  root.append(h('details', { style: { margin: '-4px 0 12px' } }, h('summary', { style: { cursor: 'pointer', fontWeight: 700, color: 'var(--navy)' } }, 'Where accruals come from, and how risky each is'),
    h('div', { class: 'small', style: { marginTop: '6px', lineHeight: 1.6 } }, ...Object.entries(SOURCES).flatMap(([k, v]) => [h('div', {}, badge(v.label, SRC_TONE[k]), ' ' + v.risk)]))));
  if (params.code) root.append(h('div', { class: 'note', style: { marginBottom: '10px' } }, `Showing the accruals of ${params.code}. `, h('a', { onclick: () => { location.hash = '#/accruals'; } }, 'Show all')));
  const pm = d.manual.filter((x) => (x.hours == null || x.inv_ref) && (!params.code || x.code === params.code));
  const sum = (l, k = 'amount') => l.reduce((a, x) => a + (x[k] || 0), 0);
  const open = pm.filter((x) => x.status === 'open' || x.status === 'partial');
  const review = pm.filter((x) => x.status === 'investigate');
  const prOpen = d.pronto.filter((x) => x.open > 0.5);
  const unp = d.unposted.filter((x) => x.state !== 'journal requested');
  const kpi = (l, v, s, c = '') => h('div', { class: 'kpi ' + c }, h('div', { class: 'l' }, l), h('div', { class: 'v' }, v), h('div', { class: 's' }, s));
  root.append(h('div', { class: 'grid g5', style: { marginBottom: '14px' } },
    kpi('Your open accruals', fmt.money(sum(open) - sum(open, 'cover')), `${open.length} items: ${open.filter((x) => x.kind === 'work').length} estimates, ${open.filter((x) => x.kind === 'invoice').length} invoices`),
    kpi('Invoice differs: review', String(review.length), review.length ? fmt.money(sum(review, 'matched_amount') - sum(review)) + ' difference' : 'none', 't2'),
    kpi('Accrued by finance in Pronto', fmt.money(sum(prOpen, 'open')), `${prOpen.length} open on Work in Progress: do not accrue again`, 't3'),
    kpi('Unposted timesheets', fmt.money(sum(unp, 'auto')), `${unp.length} person-months; ${d.unposted.length - unp.length} asked to move`, 't4'),
    kpi('Subcontract claims', fmt.money(sum(d.claims || [])), `${(d.claims || []).length} received, not yet invoiced`, 't5')));

  // ---- your accruals ------------------------------------------------------------------------------------------
  const refs = (x) => [x.po_no && `PO ${x.po_no}`, x.inv_ref && `Inv ${x.inv_ref}`, x.quote_ref && `Quote ${x.quote_ref}`].filter(Boolean).join(' · ');
  const tie = (x) => {
    if (!x.matched_via) return x.cover ? h('span', { class: 'small' }, `${fmt.money(x.cover)} of it already accrued by finance in Pronto: counts ${fmt.money(x.amount - x.cover)}`) : (x.kind === 'work' ? h('span', { class: 'small muted' }, 'Reverse it when the cost lands') : '');
    const r = JSON.parse(x.matched_refs || '[]').join(', ');
    return h('span', { class: 'small' }, `${fmt.money(x.matched_amount)} landed ${fmt.month(x.matched_month)} (${r}, by ${x.matched_via}). `,
      x.matched_month !== x.month ? h('span', { class: 'muted' }, `Counts in ${fmt.month(x.month)}, reversed in ${fmt.month(x.matched_month)}.`) : null);
  };
  root.append(h('div', { class: 'card' }, h('div', { class: 'ch' }, h('h2', {}, 'Your accruals'), h('span', { class: 'sp' }), h('span', { class: 'small muted' }, 'Click one for its history')),
    pm.length ? table([
      { label: 'Kind', f: (x) => badge(KIND[x.kind]?.[0] || x.kind, KIND[x.kind]?.[1] || '') },
      { label: 'CBS', f: (x) => h('span', { class: 'mono' }, x.code) }, { label: 'Line', f: (x) => x.name },
      { label: 'Work month', f: (x) => fmt.month(x.month) }, { label: 'Amount', r: 1, f: (x) => fmt.money(x.amount) },
      { label: 'Supplier', f: (x) => x.supplier_name || '' }, { label: 'PO', f: (x) => h('span', { class: 'small mono' }, x.po_no || '') }, { label: 'Quote', f: (x) => h('span', { class: 'small mono' }, x.quote_ref || '') }, { label: 'Invoice', f: (x) => h('span', { class: 'small mono' }, x.inv_ref || '') },
      { label: 'Status', f: (x) => badge(STATUS[x.status]?.[0] || x.status, STATUS[x.status]?.[1] || '') },
      { label: 'How it ties out', f: (x) => h('div', {}, tie(x), x.hint ? h('div', { class: 'small bad', style: { marginTop: '3px' } }, x.hint) : null, x.status === 'investigate' ? h('div', { class: 'row', style: { gap: '4px', marginTop: '4px' }, onclick: (e) => e.stopPropagation() },
        h('button', { class: 'btn sm', title: 'The invoice is the right amount: the accrual is trued up to it', onclick: async () => { await api.post(p(`/accruals/${x.id}/resolve`), { resolution: 'accept' }); render(); } }, 'Accept the invoice amount'),
        x.matched_amount < x.amount ? h('button', { class: 'btn ghost sm', title: 'Part of the work is still to be invoiced: the difference stays accrued', onclick: async () => { await api.post(p(`/accruals/${x.id}/resolve`), { resolution: 'rest_open' }); render(); } }, 'Keep the rest open') : null) : null) },
      { label: 'Raised by', f: (x) => stamp(x.created_by, x.created_at) },
      { label: '', f: (x) => h('span', { class: 'row', style: { gap: '4px' }, onclick: (e) => e.stopPropagation() }, h('button', { class: 'btn ghost sm', onclick: () => accrualDialog(x.node_id, data.rows, render, x) }, 'Edit'),
        h('button', { class: 'btn danger sm', title: 'Delete (a reason is required and kept)', onclick: () => deleteAccrual(x) }, '×')) },
    ], pm, { onRow: (x) => historyDialog('accrual', x.id, `Accrual ${fmt.money(x.amount)} on ${x.code} ${x.name}`) }) : empty('No accruals yet', 'Add one for work done, or for an invoice you have been asked to approve before it reaches Pronto.')));

  // ---- finance's accruals in Pronto ----------------------------------------------------------------------------
  root.append(h('div', { class: 'card', style: { marginTop: '14px' } }, h('h2', {}, 'Accrued by finance in Pronto (Work in Progress)'),
    h('div', { class: 'small muted', style: { marginBottom: '8px' } }, 'Month-end accrual journals finance posted in Pronto, and their reversals. Read only here: change them in Pronto. They are in cost to date already: do not accrue the same work again. An accrual of yours on the same line and PO or supplier counts only above finance\'s. Click a payroll row to see whose timesheets it covers.'),
    d.pronto.length ? table([{ label: 'CBS', f: (x) => h('span', { class: 'mono' }, x.cbs || x.category) }, { label: 'For', f: (x) => x.supplier },
      { label: 'Reference', f: (x) => h('span', { class: 'mono small' }, x.reference || '') }, { label: 'PO', f: (x) => h('span', { class: 'mono small' }, x.po || '') }, { label: 'Month', f: (x) => fmt.month(x.month) },
      { label: 'Accrued', r: 1, f: (x) => fmt.money(x.accrued) }, { label: 'Reversed', r: 1, f: (x) => fmt.money(x.reversed) },
      { label: 'Open', r: 1, f: (x) => h('b', { class: x.open > 0.5 ? 'warn' : '' }, fmt.money(x.open)) },
      { label: '', f: (x) => h('span', { class: 'row', style: { gap: '6px' } }, x.open > 0.5 ? badge('Already accrued: do not accrue again', 'warn') : badge('Reversed', 'good'), x.kind === 'timesheet' ? h('a', { class: 'small', onclick: () => peopleDialog({ category: x.category, month: x.month, amount: x.accrued }) }, 'Whose timesheets?') : null) }], d.pronto, { onRow: (x) => (x.kind === 'timesheet' ? peopleDialog({ category: x.category, month: x.month, amount: x.accrued }) : null) })
      : h('div', { class: 'muted' }, 'No accrual journals in the Pronto data.')));

  // ---- unposted timesheets ---------------------------------------------------------------------------------------
  root.append(h('div', { class: 'card', style: { marginTop: '14px' } }, h('h2', {}, 'Unposted timesheets'),
    h('div', { class: 'small muted', style: { marginBottom: '8px' } }, 'Hours entered in Pronto, waiting for approval, often with no cost yet. PMT accrues them at the person\'s cost rate until they are posted. If the hours do not belong to this project, ask for them to be journalled to another one: they stop accruing here.'),
    d.unposted.length ? table([{ label: 'Person', f: (x) => h('span', {}, h('b', {}, x.person || x.resource_code), h('div', { class: 'small muted mono' }, x.resource_code)) },
      { label: 'Month', f: (x) => fmt.month(x.month) }, { label: 'Days', f: (x) => `${fmt.date(x.d0)}${x.d1 !== x.d0 ? ' to ' + fmt.date(x.d1) : ''}` },
      { label: 'CBS', f: (x) => h('span', { class: 'mono' }, x.code || 'unplaced') }, { label: 'Hours', r: 1, f: (x) => fmt.n(x.hours, 2) },
      { label: 'Worth', r: 1, f: (x) => (x.amount ? fmt.money(x.amount) : h('span', { class: 'bad small' }, 'no rate')) },
      { label: 'Status', f: (x) => badge(x.state, x.state === 'journal requested' ? 'warn' : x.state === 'accrued by you' ? 'good' : '') },
      { label: '', f: (x) => h('span', { class: 'row', style: { gap: '4px' } },
        x.state === 'accrued automatically' && x.node_id ? h('button', { class: 'btn ghost sm', title: 'Accrue these hours yourself (hours x rate), day by day; they reverse when the timesheet is posted', onclick: async () => { try { await api.post(p('/accruals/unposted'), { resource_code: x.resource_code, month: x.month, node_id: x.node_id }); toast('Accrued'); render(); } catch (e) { toast(e.message, 'bad'); } } }, 'Accrue') : null,
        x.state !== 'journal requested' ? h('button', { class: 'btn ghost sm', onclick: () => journalRequest(x) }, 'Not ours: move...') : null,
        x.requests.filter((q) => q.status === 'requested').map((q) => h('button', { class: 'btn ghost sm', title: `Asked ${fmt.date(q.requested_at?.slice(0, 10))}: to ${q.target || 'another project'}`, onclick: async () => { await api.put(p(`/timesheet-requests/${q.id}`), { status: 'withdrawn' }); render(); } }, 'Withdraw request'))) }], d.unposted)
      : h('div', { class: 'muted' }, 'Every timesheet in the export is posted.'),
    d.requests.length ? h('div', { style: { marginTop: '10px' } }, h('b', { class: 'small' }, 'Journal requests'), table([{ label: 'Person', f: (q) => q.person || q.resource_code }, { label: 'Days', f: (q) => `${fmt.date(q.date_from)} to ${fmt.date(q.date_to)}` },
      { label: 'Hours', r: 1, f: (q) => fmt.n(q.hours, 2) }, { label: 'To', f: (q) => q.target || '' }, { label: 'Asked', f: (q) => fmt.date(q.requested_at?.slice(0, 10)) },
      { label: 'Status', f: (q) => badge(q.status === 'done' ? 'Done: moved in Pronto' : q.status, q.status === 'done' ? 'good' : q.status === 'requested' ? 'warn' : '') }, { label: 'Note', f: (q) => q.note || '' }], d.requests)) : null));

  // ---- subcontract claims ------------------------------------------------------------------------------------------
  root.append(h('div', { class: 'card', style: { marginTop: '14px' } }, h('h2', {}, 'Subcontract claims not yet invoiced in Pronto (accrued automatically)'),
    h('div', { class: 'small muted', style: { marginBottom: '8px' } }, 'Each received claim accrues at its approved amount (claimed where not yet approved), net of retention, in the claim month. When its invoice lands it counts in the claim month and reverses in the invoice month.'),
    (d.claims || []).length ? table([{ label: 'CBS', f: (x) => h('span', { class: 'mono' }, x.code) }, { label: 'Line', f: (x) => x.name }, { label: 'Subcontract', f: (x) => x.subcontract },
      { label: 'Claim', f: (x) => x.claim_no }, { label: 'Month', f: (x) => fmt.month(x.month) }, { label: 'Accrued', r: 1, f: (x) => fmt.money(x.amount) },
      { label: 'Basis', f: (x) => badge(x.basis, x.basis === 'approved' ? 'good' : 'warn') }, { label: 'Invoice ref', f: (x) => x.inv_ref || '' }], d.claims, { onRow: (x) => go('subcontracts', { open: x.sub_id }) })
      : h('div', { class: 'muted' }, 'No subcontract claims waiting for their invoice.')));
}

// the sources, as the server describes them (accruals.SOURCES)
const SOURCES = {
  estimate: { label: 'Your estimate', risk: 'Highest risk: no document behind it. Adjust or reverse it when the invoice lands.' },
  approval: { label: 'Awaiting approval', risk: 'Invoice or claim received, not yet approved and entered in Pronto. Reverses itself when it lands.' },
  claim: { label: 'Subcontract claim', risk: 'From a received claim and its approval. Reverses itself when its invoice lands.' },
  finance: { label: 'Finance journal (Pronto)', risk: 'Work in Progress journal in Pronto. Read only: change it in Pronto.' },
  timesheet: { label: 'Unposted timesheet', risk: 'Hours listed but not yet costed at a rate. Reverses when the timesheet posts.' },
};

function deleteAccrual(x) {
  const why = h('textarea', { rows: 2, style: { width: '100%' }, placeholder: 'Why is this accrual being deleted? (required)' });
  modal({ title: `Delete the accrual on ${x.code} ${x.name}`, body: h('div', { class: 'grid' }, h('div', { class: 'note' }, `${fmt.money(x.amount)} for ${fmt.month(x.month)}. The deletion and your reason are kept in the history (Activity and history), and Undo in the top bar puts it back.`), field('Reason (kept for traceability)', why)),
    actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} }, { label: 'Delete', kind: 'danger', onClick: async () => {
      if (why.value.trim().length < 3) { toast('Give a reason for the deletion.', 'bad'); return false; }
      await api.del(p(`/accruals/${x.id}?reason=${encodeURIComponent(why.value.trim())}`)); toast('Accrual deleted'); render();
    } }] });
}

// whose timesheets a payroll accrual (or an unposted line) covers: Pronto's labour rows for that cost category and month
async function peopleDialog({ category, month, amount, resource_code }) {
  const rows = await api.get(p(`/accruals/people?category=${encodeURIComponent(category || '')}&month=${month || ''}${resource_code ? '&resource_code=' + encodeURIComponent(resource_code) : ''}`));
  const sum = (k) => rows.reduce((a, r) => a + (r[k] || 0), 0);
  modal({ title: `Whose timesheets: ${category || ''} ${fmt.month(month)}`, size: 'wide', body: h('div', { class: 'grid' },
    h('div', { class: 'note' }, 'Finance\'s payroll journal names nobody. This lists the people with timesheet hours in Pronto for the same cost category and work month. PMT links them by category and month, so check the total against the journal.'),
    rows.length ? table([{ label: 'Person', f: (r) => h('span', {}, h('b', {}, r.person || r.resource_code), h('div', { class: 'small muted mono' }, r.resource_code)) }, { label: 'Days', f: (r) => `${fmt.date(r.d0)}${r.d1 !== r.d0 ? ' to ' + fmt.date(r.d1) : ''}` },
      { label: 'Hours', r: 1, f: (r) => fmt.n(r.hours, 2) }, { label: 'Posted cost', r: 1, f: (r) => fmt.money(r.posted_cost) }, { label: 'Unposted hours', r: 1, f: (r) => fmt.n(r.unposted_hours, 2) },
      { label: 'Unposted worth', r: 1, f: (r) => (r.unposted_hours && !r.unposted_cost ? h('span', { class: 'bad small' }, 'no rate') : fmt.money(r.unposted_cost)) }], rows,
      { foot: (c) => ({ Person: 'Total', Hours: fmt.n(sum('hours'), 2), 'Posted cost': fmt.money(sum('posted_cost')), 'Unposted hours': fmt.n(sum('unposted_hours'), 2), 'Unposted worth': fmt.money(sum('unposted_cost')) }[c.label]) })
      : empty('No timesheets found', 'Pronto holds no labour rows for this cost category and month.'),
    amount != null ? h('div', { class: 'small' }, `The journal accrued ${fmt.money(amount)}. Hours that were unposted at month end were accrued by it and reversed once posted, so it is not expected to equal today's total. Still unposted now: ${fmt.money(sum('unposted_cost'))}.`) : null),
  actions: [{ label: 'Close', kind: 'ghost', onClick: () => {} }] });
}

// every accrual from every source in one list, to filter by employee or company
async function masterList(root) {
  const m = await api.get(p('/accruals/master'));
  const ui = { src: sessionStorage.getItem('amSrc') || '', party: sessionStorage.getItem('amParty') || '', q: '', open: true };
  const bar = h('div', { class: 'row', style: { margin: '0 0 10px', flexWrap: 'wrap', gap: '8px' } }); const tiles = h('div'); const out = h('div');
  root.append(h('div', { class: 'note', style: { marginBottom: '10px' } }, 'Every accrual from every source in one list. Pick a company or an employee to see everything accrued for them. The sections on the Register tab stay as they are; Pronto journals are read only here.'), bar, tiles, out);
  const party = h('select', { style: { minWidth: '220px' }, onchange: (e) => { ui.party = e.target.value; sessionStorage.setItem('amParty', ui.party); draw(); } },
    h('option', { value: '' }, 'Everyone: all companies and employees'),
    ...['company', 'employee'].map((t) => h('optgroup', { label: t === 'company' ? 'Companies' : 'Employees' }, ...m.parties.filter((x) => x.type === t).map((x) => h('option', { value: `${t}|${x.name}`, selected: ui.party === `${t}|${x.name}` }, `${x.name} (${x.n})`)))));
  const search = h('input', { type: 'search', placeholder: 'CBS, PO, quote, invoice, note...', style: { width: '220px' }, oninput: (e) => { ui.q = e.target.value.trim().toLowerCase(); draw(); } });
  const openOnly = h('label', { class: 'row small', style: { gap: '4px' } }, h('input', { type: 'checkbox', checked: true, onchange: (e) => { ui.open = e.target.checked; draw(); } }), 'Counting now only');
  const STAT = { open: 'Open', partial: 'Part landed', matched: 'Matched to the invoice', investigate: 'Invoice differs: review', reversed: 'Reversed', 'accrued automatically': 'Accrued automatically', 'accrued by you': 'Accrued by you', 'journal requested': 'Journal requested' };
  const mine = (r) => { if (!ui.party) return true; const [t, n] = ui.party.split('|'); return r.party_type === t && r.party === n || (t === 'employee' && r.people.includes(n)); };
  const detailOf = (r) => {
    const k = r.link || {};
    if (k.type === 'accrual') return historyDialog('accrual', k.id, `Accrual ${fmt.money(r.amount)} on ${r.code} ${r.line}`);
    if (k.type === 'claim') return go('subcontracts', { open: k.sub_id });
    if (k.type === 'people') return peopleDialog({ category: k.category, month: k.month, amount: k.amount, resource_code: k.resource_code });
    if (k.type === 'calendar') return go('calendar');
    return null;
  };
  function draw() {
    clear(bar).append(...[['', 'All sources'], ...Object.entries(SOURCES).map(([k, v]) => [k, v.label])].map(([k, l]) => h('span', { class: 'chip' + (ui.src === k ? ' on' : ''), title: SOURCES[k]?.risk || '', onclick: () => { ui.src = k; sessionStorage.setItem('amSrc', k); draw(); } }, `${l}${k ? ` (${m.rows.filter((r) => r.source === k && mine(r)).length})` : ''}`)), party, search, openOnly);
    const list = m.rows.filter((r) => mine(r) && (!ui.src || r.source === ui.src) && (!ui.open || r.counts > 0.5) && (!ui.q || `${r.code} ${r.line} ${r.po} ${r.quote} ${r.invoice} ${r.detail} ${r.party}`.toLowerCase().includes(ui.q)));
    const sum = (f, k = 'counts') => list.filter(f).reduce((a, r) => a + (r[k] || 0), 0);
    clear(tiles).append(h('div', { class: 'grid g5', style: { marginBottom: '12px' } },
      ...[['Counting now', fmt.money(sum(() => true)), `${list.length} accruals${ui.party ? ' for ' + ui.party.split('|')[1] : ''}`], ['Your estimates', fmt.money(sum((r) => r.source === 'estimate')), 'highest risk'], ['Approvals and claims', fmt.money(sum((r) => r.source === 'approval' || r.source === 'claim')), 'reverse when invoiced'],
        ['Finance journals', fmt.money(sum((r) => r.source === 'finance')), 'Pronto, read only'], ['Unposted timesheets', fmt.money(sum((r) => r.source === 'timesheet')), 'hours, rate pending']].map(([l, v, s], i) => h('div', { class: 'kpi t' + (i + 1) }, h('div', { class: 'l' }, l), h('div', { class: 'v', style: { fontSize: '18px' } }, v), h('div', { class: 's' }, s)))));
    if (ui.party.startsWith('employee') && list.some((r) => r.source === 'finance')) tiles.append(h('div', { class: 'small muted', style: { margin: '-6px 0 10px' } }, 'Payroll journals from finance cover several people and are shown whole: they are not split per person.'));
    clear(out).append(list.length ? table([
      { label: 'Source', f: (r) => h('span', { title: SOURCES[r.source].risk }, badge(SOURCES[r.source].label, SRC_TONE[r.source])) },
      { label: 'Party', f: (r) => h('span', {}, r.party, r.party_type === 'employee' ? h('span', { class: 'muted small' }, r.people.length > 1 ? ` · ${r.people.length} people` : ' · employee') : null) },
      { label: 'CBS', f: (r) => h('span', { class: 'mono' }, r.code) }, { label: 'Line', f: (r) => r.line }, { label: 'Work month', f: (r) => fmt.month(r.month) },
      { label: 'Accrued', r: 1, f: (r) => fmt.money(r.amount) }, { label: 'Counts now', r: 1, f: (r) => h('b', {}, fmt.money(r.counts)) },
      { label: 'PO', f: (r) => h('span', { class: 'small mono' }, r.po) }, { label: 'Quote', f: (r) => h('span', { class: 'small mono' }, r.quote) }, { label: 'Invoice', f: (r) => h('span', { class: 'small mono' }, r.invoice) },
      { label: 'Status', f: (r) => STAT[r.status] || r.status }, { label: 'Detail', cls: 'wrap', f: (r) => h('span', { class: 'small' }, r.detail, r.hint ? h('div', { class: 'bad' }, r.hint) : null) }],
      list, { cls: 'nogroup', onRow: detailOf, foot: (c) => ({ Party: `${list.length} accruals`, Accrued: fmt.money(sum(() => true, 'amount')), 'Counts now': fmt.money(sum(() => true)) }[c.label]) }) : empty('Nothing matches', ui.open ? 'Counting now only is ticked: untick it to include reversed and matched accruals, or change the filters.' : 'Change the filters.'));
  }
  draw();
}

function journalRequest(x) {
  const target = h('input', { type: 'text', placeholder: 'Project code or name the hours belong to' });
  const note = h('input', { type: 'text', placeholder: 'Why (e.g. worked on Tallawang that week)' });
  const from = h('input', { type: 'date', value: x.d0 }); const to = h('input', { type: 'date', value: x.d1 });
  const text = () => `Hi, please journal ${fmt.n(x.hours, 2)} h of ${x.person || x.resource_code} (${x.resource_code}) worked ${fmt.date(from.value)} to ${fmt.date(to.value)} from ${state.project?.code || state.project?.name} to ${target.value || '[project]'}${note.value ? ': ' + note.value : ''}. Thanks.`;
  modal({ title: `Hours that do not belong here: ${x.person || x.resource_code}`, body: h('div', { class: 'grid' },
    h('div', { class: 'small muted' }, 'While the request is open these hours stop accruing on this project. It closes by itself once Pronto no longer has them here.'),
    h('div', { class: 'grid g2' }, field('From', from), field('To', to)), field('Move them to', target), field('Note', note)),
  actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} },
    { label: 'Copy the request text', kind: 'ghost', close: false, onClick: async () => { try { await navigator.clipboard.writeText(text()); toast('Copied: paste it in your email to payroll'); } catch (e) { toast(text()); } } },
    { label: 'Save the request', onClick: async () => { await api.post(p('/timesheet-requests'), { resource_code: x.resource_code, person: x.person, date_from: from.value, date_to: to.value, hours: x.hours, target: target.value, note: note.value }); toast('Request saved: the hours stop accruing here'); render(); } }] });
}

async function timelines(root) {
  const ui = { group: sessionStorage.getItem('tlGroup') || '' };
  const out = h('div');
  const bar = h('div', { class: 'row', style: { margin: '6px 0 12px' } });
  root.append(h('div', { class: 'note', style: { marginBottom: '10px' } },
    h('b', {}, 'Three timelines of the same cost. '), 'Work performed: when the work was done (Pronto cost by month, plus accruals in their work month; an invoice that lands later counts in the month it was accrued). ',
    'Billed: when it reached Pronto (invoices by invoice date, timesheets, journals). Paid: when the money leaves (invoices at their date plus the supplier terms in Settings; labour the month it is billed). ',
    'The PM reports on the first; finance on the other two.'), bar, out);
  const draw = async () => {
    clear(bar).append(...[['', 'Whole project'], ['PL', 'Labour'], ['PS', 'Subcontractors'], ['PM', 'Materials'], ['PE', 'Expenses']].map(([k, l]) => h('span', { class: 'chip' + (ui.group === k ? ' on' : ''), onclick: () => { ui.group = k; sessionStorage.setItem('tlGroup', k); draw(); } }, l)));
    const t = await api.get(p('/accruals/timelines' + (ui.group ? '?group=' + ui.group : '')));
    clear(out);
    if (!t.months.length) { out.append(empty('Nothing yet', 'Upload the Pronto data first.')); return; }
    const i = t.months.indexOf(t.status_month); const at = (a) => (i >= 0 ? a[i] : a[a.length - 1]);
    const tile = (l, v, s, c = '') => h('div', { class: 'kpi ' + c }, h('div', { class: 'l' }, l), h('div', { class: 'v' }, v), h('div', { class: 's' }, s));
    out.append(h('div', { class: 'grid g5', style: { marginBottom: '14px' } },
      tile('Work performed to date', fmt.m(at(t.cum_work)), `as at ${fmt.month(t.status_month)}`),
      tile('Billed to date', fmt.m(at(t.cum_billed)), 'in Pronto', 't2'),
      tile('Paid to date', fmt.m(at(t.cum_paid)), `invoices + ${t.terms_days} days`, 't3'),
      tile('Done, not yet billed', fmt.m(at(t.cum_work) - at(t.cum_billed)), 'the accrued position', 't4'),
      tile('Billed, not yet paid', fmt.m(at(t.cum_billed) - at(t.cum_paid)), 'payable to suppliers', 't5')));
    const b1 = h('div', { class: 'chartbox tall' }); const b2 = h('div', { class: 'chartbox tall' });
    out.append(h('div', { class: 'grid g2', style: { marginBottom: '14px' } }, h('div', { class: 'card' }, h('h2', {}, 'By month'), b1), h('div', { class: 'card' }, h('h2', {}, 'Cumulative'), b2)));
    const ds = (lab, data, col, extra = {}) => ({ label: lab, data, backgroundColor: col, borderColor: col, ...extra });
    chart(b1, { type: 'bar', data: { labels: t.months.map(fmt.month), datasets: [ds('Work performed', t.work, PALETTE[0], { borderRadius: 2 }), ds('Billed', t.billed, PALETTE[1], { borderRadius: 2 }), ds('Paid', t.paid, PALETTE[3], { borderRadius: 2 })] } });
    chart(b2, { type: 'line', data: { labels: t.months.map(fmt.month), datasets: [ds('Work performed', t.cum_work, PALETTE[0], { pointRadius: 0, borderWidth: 2 }), ds('Billed', t.cum_billed, PALETTE[1], { pointRadius: 0, borderWidth: 2 }), ds('Paid', t.cum_paid, PALETTE[3], { pointRadius: 0, borderWidth: 2, borderDash: [5, 4] })] },
      options: { interaction: { mode: 'index', intersect: false } } });
    out.append(h('div', { class: 'card' }, h('h2', {}, 'Month by month'), h('div', { class: 'tw' }, h('table', { class: 't' },
      h('thead', {}, h('tr', {}, ['Month', 'Work performed', 'of which accrued', 'Billed', 'Paid', 'Done not billed (cum.)', 'Billed not paid (cum.)'].map((x, k) => h('th', { class: k ? 'r' : '' }, x)))),
      h('tbody', {}, t.months.map((m, k) => h('tr', { class: m === t.status_month ? 'sel' : '' }, h('td', {}, fmt.month(m)), h('td', { class: 'r num' }, fmt.money(t.work[k])), h('td', { class: 'r num small' }, fmt.money(t.accrued[k])),
        h('td', { class: 'r num' }, fmt.money(t.billed[k])), h('td', { class: 'r num' }, fmt.money(t.paid[k])), h('td', { class: 'r num' }, fmt.money(t.cum_work[k] - t.cum_billed[k])), h('td', { class: 'r num' }, fmt.money(t.cum_billed[k] - t.cum_paid[k])))))))));
  };
  await draw();
}
