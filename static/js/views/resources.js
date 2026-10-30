import { h, clear, fmt, modal, toast, field, select, table, num, confirmBox, badge, tabs, empty, debounce , lookup } from '../ui.js';
import { api, state, p } from '../api.js';
import { go, render } from '../app.js';

// The project's resources (Pronto codes, work rates, CBS lines), rate card and supplier rates. They live on the Stakeholders page
// (OVERVIEW > Stakeholders): Employees and Companies show the project's own list under the company list; Rate card and Supplier rates are their own tabs.
export default async function resources(root, params) {   // the old address #/resources?tab=... goes to Stakeholders
  const to = { employee: 'employees', supplier: 'companies', rates: 'rates', srates: 'srates' }[params.tab] || 'employees';
  go('directory', { tab: to });
}

export async function projectResources(body, tab) {   // tab: 'employee' | 'supplier'
  const list = await api.get(p('/resources?kind=' + tab));
  let q = '';
  const out = h('div');
  const search = h('input', { type: 'search', placeholder: 'Search...', style: { width: '240px' }, oninput: debounce(() => { q = search.value.toLowerCase(); draw(); }, 150) });
  body.append(h('div', { class: 'row', style: { marginBottom: '10px' } }, search, h('span', { class: 'sp', style: { flex: 1 } }), h('button', { class: 'btn', onclick: () => edit() }, '+ Add ' + (tab === 'employee' ? 'employee' : 'supplier'))), out);
  function draw() {
    const l = list.filter((r) => !q || `${r.code} ${r.name} ${r.function}`.toLowerCase().includes(q));
    clear(out).append(l.length ? table([{ label: 'Code', f: (r) => h('span', { class: 'mono' }, r.code) }, { label: 'Name', f: (r) => r.name }, { label: tab === 'employee' ? 'Role (work rate)' : 'Trade', f: (r) => r.function || '' },
      ...(tab === 'employee' ? [{ label: 'Rate code', f: (r) => r.work_rate_code || '' }, { label: 'Cost rate', r: 1, f: (r) => r.cost_rate ? fmt.money(r.cost_rate, 2) : '' }, { label: 'Sell rate', r: 1, f: (r) => r.sell_rate ? fmt.money(r.sell_rate, 2) : '' }, { label: 'Hours (Pronto)', r: 1, f: (r) => fmt.n(r.hours, 1) }] : []),
      { label: 'CBS lines', r: 1, f: (r) => r.lines ? r.lines : h('span', { class: 'warn' }, 'none') }, { label: 'Source', f: (r) => badge(r.source) }, { label: '', f: (r) => h('button', { class: 'btn ghost sm', onclick: () => edit(r) }, 'Edit') }], l, { maxHeight: '68vh' }) : empty('Nothing here yet', 'Upload Pronto data or add one manually.'));
  }
  draw();
  function edit(r = {}) {
    const f = { code: h('input', { type: 'text', value: r.code || '', disabled: !!r.id }), name: lookup(tab === 'employee' ? 'employee' : 'company', r.name || '', { placeholder: tab === 'employee' ? 'Pick an employee or type a new name' : 'Pick a company or type a new name' }), func: h('input', { type: 'text', value: r.function || '' }), wrc: h('input', { type: 'text', value: r.work_rate_code || '' }), cost: h('input', { type: 'number', step: '0.01', value: r.cost_rate ?? '' }), sell: h('input', { type: 'number', step: '0.01', value: r.sell_rate ?? '' }) };
    modal({ title: r.id ? r.name : 'Add resource', body: h('div', { class: 'grid g2' }, field('Pronto code', f.code), field('Name', f.name), field(tab === 'employee' ? 'Role' : 'Trade', f.func), tab === 'employee' ? field('Work rate code', f.wrc) : h('span'), tab === 'employee' ? field('Cost rate / hr', f.cost) : h('span'), tab === 'employee' ? field('Sell rate / hr', f.sell) : h('span')),
      actions: [r.id ? { label: 'Delete', kind: 'danger', onClick: async () => { await api.del(p(`/resources/${r.id}`)); await render(); } } : { label: 'Cancel', kind: 'ghost', onClick: () => {} }, { label: 'Save', onClick: async () => { if (r.id) await api.put(p(`/resources/${r.id}`), { name: f.name.value, function: f.func.value, work_rate_code: f.wrc.value, cost_rate: f.cost.value === '' ? null : num(f.cost.value), sell_rate: f.sell.value === '' ? null : num(f.sell.value) }); else await api.post(p('/resources'), { kind: tab, code: f.code.value, name: f.name.value, function: f.func.value, work_rate_code: f.wrc.value, cost_rate: f.cost.value === '' ? null : num(f.cost.value), sell_rate: f.sell.value === '' ? null : num(f.sell.value) }); await render(); } }] });
  }
}

export async function rates(body) {
  const list = await api.get(p('/ratecard'));
  body.append(h('div', { class: 'note', style: { marginBottom: '10px' } }, 'Cost and sell rates by role, for pricing variations and day-works. Keep the revision and financial year with each rate. Internal cost rates are Commercial in Confidence; the variation proposal shows prices only.'),
    h('div', { class: 'row', style: { marginBottom: '10px' } }, h('button', { class: 'btn', onclick: () => edit() }, '+ Add rate')),
    list.length ? table([{ label: 'Department', f: (r) => r.department || '' }, { label: 'Role', f: (r) => r.role }, { label: 'Rate code', f: (r) => r.work_rate_code || '' }, { label: 'Cost / hr', r: 1, f: (r) => fmt.money(r.cost_rate, 2) }, { label: 'Sell / hr', r: 1, f: (r) => fmt.money(r.sell_rate, 2) }, { label: 'Markup', r: 1, f: (r) => r.cost_rate ? fmt.pct(r.sell_rate / r.cost_rate - 1) : '' }, { label: 'FY', f: (r) => r.fy || '' }, { label: 'Rev', f: (r) => r.rev || '' },
      { label: '', f: (r) => h('span', { class: 'row', style: { gap: '4px' } }, h('button', { class: 'btn ghost sm', onclick: () => edit(r) }, 'Edit'), h('button', { class: 'btn danger sm', onclick: async () => { await api.del(p(`/ratecard/${r.id}`)); render(); } }, '×')) }], list) : empty('No rates', 'Add the schedule of rates, or load it from the Excel template.'));
  function edit(r = {}) {
    const f = { department: h('input', { type: 'text', value: r.department || '' }), role: h('input', { type: 'text', value: r.role || '' }), wrc: h('input', { type: 'text', value: r.work_rate_code || '' }), cost: h('input', { type: 'number', step: '0.01', value: r.cost_rate ?? '' }), sell: h('input', { type: 'number', step: '0.01', value: r.sell_rate ?? '' }), fy: h('input', { type: 'text', value: r.fy || '' }), rev: h('input', { type: 'text', value: r.rev || '' }) };
    modal({ title: r.id ? 'Edit rate' : 'Add rate', body: h('div', { class: 'grid g2' }, field('Department', f.department), field('Role', f.role), field('Work rate code', f.wrc), field('Cost rate / hr', f.cost), field('Sell rate / hr', f.sell), field('Financial year', f.fy), field('Revision', f.rev)), actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} }, { label: 'Save', onClick: async () => { await api.post(p('/ratecard'), { id: r.id, department: f.department.value, role: f.role.value, work_rate_code: f.wrc.value, cost_rate: num(f.cost.value), sell_rate: num(f.sell.value), fy: f.fy.value, rev: f.rev.value }); await render(); } }] });
  }
}

// Supplier schedule of rates by role: prices rosters and supplier calendars in the forecast.
export async function supplierRates(body) {
  const [list, sups] = await Promise.all([api.get(p('/supplier-rates')), api.get(p('/resources?kind=supplier'))]);
  body.append(h('div', { class: 'note', style: { marginBottom: '10px' } }, 'Each supplier\'s rates per role, from their schedule of rates or subcontract. Rosters and calendars on the Forecast pages look up the rate for the supplier and role: normal time up to the normal hours a day, overtime after that, plus a daily allowance per person (LAHA, meals, travel) where it applies.'),
    h('div', { class: 'row', style: { marginBottom: '10px' } }, h('button', { class: 'btn', onclick: () => edit() }, '+ Add supplier rate')),
    list.length ? table([{ label: 'Supplier', f: (r) => h('span', {}, r.name || '', ' ', h('span', { class: 'mono muted' }, r.code || '')) }, { label: 'Role', f: (r) => h('b', {}, r.role) }, { label: 'Unit', f: (r) => r.unit || 'hr' },
      { label: 'Rate', r: 1, f: (r) => fmt.money(r.rate, 2) }, { label: 'Overtime', r: 1, f: (r) => r.ot_rate ? fmt.money(r.ot_rate, 2) : '' }, { label: 'Normal hours a day', r: 1, f: (r) => r.nt_hours ?? '' },
      { label: 'Allowance a day', r: 1, f: (r) => r.allowance ? fmt.money(r.allowance, 2) : '' }, { label: 'Valid from', f: (r) => fmt.date(r.valid_from) }, { label: 'Reference', f: (r) => r.ref || '' },
      { label: '', f: (r) => h('span', { class: 'row', style: { gap: '4px' } }, h('button', { class: 'btn ghost sm', onclick: () => edit(r) }, 'Edit'), h('button', { class: 'btn danger sm', onclick: async () => { if (await confirmBox('Delete this rate?', 'Delete', true)) { await api.del(p(`/supplier-rates/${r.id}`)); render(); } } }, '×')) }], list)
      : empty('No supplier rates yet', 'Add the roles and rates from a supplier\'s schedule of rates, for example Electrician $95/hr, overtime $142.50 after 8 hours, LAHA $160 a day.'));
  function edit(r = {}) {
    const f = { sup: select([['', '(choose supplier)'], ...sups.map((x) => [x.id, `${x.name || x.code} [${x.code}]`])], r.resource_id || ''), role: h('input', { type: 'text', value: r.role || '', placeholder: 'Electrician' }),
      unit: select([['hr', 'per hour'], ['day', 'per day'], ['shift', 'per shift'], ['ea', 'each']], r.unit || 'hr'), rate: h('input', { type: 'number', step: '0.01', value: r.rate ?? '' }), ot: h('input', { type: 'number', step: '0.01', value: r.ot_rate ?? '' }),
      nt: h('input', { type: 'number', step: '0.5', value: r.nt_hours ?? '' }), al: h('input', { type: 'number', step: '0.01', value: r.allowance ?? '' }), from: h('input', { type: 'date', value: r.valid_from || '' }), ref: h('input', { type: 'text', value: r.ref || '', placeholder: 'SOR rev, subcontract no.' }), note: h('input', { type: 'text', value: r.note || '' }) };
    modal({ title: r.id ? 'Edit supplier rate' : 'Add supplier rate', body: h('div', { class: 'grid g2' }, field('Supplier', f.sup, sups.length ? '' : 'Add the supplier on the Suppliers tab first'), field('Role', f.role), field('Unit', f.unit), field('Rate (normal time)', f.rate),
      field('Overtime rate per hour', f.ot), field('Normal hours a day', f.nt, 'Hours beyond this are overtime'), field('Allowance per person per day', f.al), field('Valid from', f.from), field('Reference', f.ref), field('Note', f.note)),
    actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} }, { label: 'Save', onClick: async () => { await api.post(p('/supplier-rates'), { id: r.id, resource_id: f.sup.value ? +f.sup.value : null, role: f.role.value.trim(), unit: f.unit.value, rate: f.rate.value, ot_rate: f.ot.value, nt_hours: f.nt.value, allowance: f.al.value, valid_from: f.from.value || null, ref: f.ref.value, note: f.note.value }); await render(); } }] });
  }
}
