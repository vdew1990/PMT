import { h, clear, fmt, modal, toast, field, table, num, badge, tone, todayISO } from '../ui.js';
import { api, state, p } from '../api.js';
import { render } from '../app.js';

export default async function reconcile(root) {
  const r = await api.get(p('/reconcile'));
  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, 'Reconcile'), h('div', { class: 'sub' }, 'Does this tool still agree with Finance? Margin against the CMT, Pronto and day zero, plus the category tie-out to Pronto.')), h('div', { class: 'sp' }), h('button', { class: 'btn', onclick: cmt }, 'Record CMT figures')));
  root.append(h('div', { class: 'card', style: { marginBottom: '14px' } }, h('h2', {}, 'Gross margin'),
    table([{ label: 'Source', f: (x) => h('b', {}, x.label) }, { label: 'As at', f: (x) => x.as_of ? (String(x.as_of).length === 7 ? fmt.month(x.as_of) : fmt.date(x.as_of)) : '' }, { label: 'Revenue', r: 1, f: (x) => fmt.money(x.revenue) }, { label: 'Cost (EAC or CTD)', r: 1, f: (x) => fmt.money(x.eac) }, { label: 'Gross profit', r: 1, f: (x) => fmt.money(x.gp) }, { label: 'Margin', r: 1, f: (x) => h('span', { class: tone(x.gm) }, fmt.pct(x.gm)) }], r.table),
    h('div', { class: 'note', style: { marginTop: '10px' } }, r.cmt_note, ` Accruals in this tool: ${fmt.money(r.accruals)}. CMT-style EAC here would be ${fmt.money(r.margin.eac_cmt_style)} and its margin ${fmt.pct(r.margin.gp_cmt_style / r.margin.revenue_recognised)}.`)));
  const tie = r.tie;
  const hasP = tie.some((t) => t.pronto !== null && t.pronto !== undefined);
  root.append(h('div', { class: 'card' }, h('div', { class: 'ch' }, h('h2', {}, 'CTD by category against the Pronto CTD overview'), h('span', { class: 'sp' }), hasP ? badge(tie.every((t) => t.diff === null || Math.abs(t.diff) < 2) ? 'Ties out' : 'Differences found', tie.every((t) => t.diff === null || Math.abs(t.diff) < 2) ? 'good' : 'bad') : null),
    hasP ? table([{ label: 'Category', f: (t) => h('span', { class: 'mono' }, t.category) }, { label: 'This tool (CTD)', r: 1, f: (t) => fmt.money(t.pmt) }, { label: 'Pronto actual', r: 1, f: (t) => fmt.money(t.pronto) }, { label: 'Difference', r: 1, f: (t) => t.diff === null ? '' : h('span', { class: Math.abs(t.diff) > 1 ? 'bad' : 'good' }, fmt.money(t.diff)) }, { label: 'Pronto budget', r: 1, f: (t) => fmt.money(t.pronto_budget) }], tie, { maxHeight: '60vh' })
      : h('div', { class: 'muted' }, 'Load the CTD overview report on the Pronto page to prove the GL import ties out by category.')));
  function cmt() {
    const d = h('input', { type: 'date', value: todayISO() }); const rev = h('input', { type: 'number', step: '0.01', value: r.cmt_entry?.revenue ?? '' }); const eac = h('input', { type: 'number', step: '0.01', value: r.cmt_entry?.eac ?? '' }); const ctd = h('input', { type: 'number', step: '0.01', value: r.cmt_entry?.ctd ?? '' }); const note = h('input', { type: 'text' });
    modal({ title: 'Record the CMT figures', body: h('div', { class: 'grid' }, h('div', { class: 'note' }, 'The CMT is owned by Finance, so its figures are typed in here for comparison. They never feed the forecast.'), h('div', { class: 'grid g2' }, field('As at', d), field('Revenue', rev), field('EAC', eac), field('Cost to date', ctd)), field('Note', note)),
      actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} }, { label: 'Save', onClick: async () => { await api.post(p('/cmt'), { as_of: d.value, revenue: num(rev.value), eac: num(eac.value), ctd: num(ctd.value), note: note.value }); await render(); } }] });
  }
}
