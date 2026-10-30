import { h, fmt, badge, empty, toast } from '../ui.js';
import { api, p } from '../api.js';
import { go, render } from '../app.js';

// Diagnostics: everything where PMT and Pronto disagree, by section, worst first. Each check links to the page that
// fixes it; subcontract suppliers and POs entered ahead of Pronto can be matched here in one click.
const LEVEL = { error: ['Does not tie', 'bad'], warn: ['To review', 'warn'], ok: ['OK', 'good'] };
const PAGE = { pronto: 'Pronto data', subcontracts: 'Subcontracts', reconcile: 'Reconcile', cbs: 'CBS and allowances', costcontrol: 'Cost control', accruals: 'Accruals', calendar: 'Labour calendar', revenue: 'Contract and claims', variations: 'Variations', allowance: 'CBS and allowances', claims: 'Contract and claims' };

export default async function diagnostics(root) {
  const d = await api.get(p('/diagnostics'));
  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, 'Diagnostics'),
    h('div', { class: 'sub' }, `Everything where PMT and Pronto disagree, in one place. Status month ${fmt.month(d.status_month)}. Work down the list: each check opens the page that fixes it.`)),
    h('div', { class: 'sp' }), h('button', { class: 'btn ghost', onclick: () => render() }, 'Check again')));
  root.append(h('div', { class: 'grid g3', style: { marginBottom: '14px' } },
    h('div', { class: 'kpi' + (d.errors ? ' t2' : '') }, h('div', { class: 'l' }, 'Do not tie'), h('div', { class: 'v' }, String(d.errors)), h('div', { class: 's' }, 'PMT and Pronto disagree')),
    h('div', { class: 'kpi t3' }, h('div', { class: 'l' }, 'To review or match'), h('div', { class: 'v' }, String(d.warnings)), h('div', { class: 's' }, 'Entered ahead of Pronto, or worth a look')),
    h('div', { class: 'kpi t4' }, h('div', { class: 'l' }, 'Checked and fine'), h('div', { class: 'v' }, String(d.checks.filter((c) => c.level === 'ok').length)), h('div', { class: 's' }, ''))));
  if (!d.checks.length) { root.append(empty('Nothing to check yet', 'Load the Pronto data first.')); return; }
  const money = (v) => (typeof v === 'number' ? fmt.money(v) : (v ?? ''));
  d.sections.forEach((sec) => {
    const cs = d.checks.filter((c) => c.section === sec);
    if (!cs.length) return;
    root.append(h('h2', { style: { margin: '18px 0 8px' } }, sec));
    cs.forEach((c) => {
      const [lab, tone] = LEVEL[c.level] || [c.level, ''];
      const card = h('div', { class: 'card', style: { marginBottom: '10px', borderLeft: `4px solid ${tone === 'bad' ? '#c62828' : tone === 'warn' ? '#ffb500' : '#3c8d40'}` } },
        h('div', { class: 'ch' }, badge(lab, tone), h('b', { style: { marginLeft: '8px' } }, c.title), c.count ? h('span', { class: 'muted small', style: { marginLeft: '8px' } }, `${c.count}`) : null, h('span', { class: 'sp' }),
          c.link ? h('button', { class: 'btn ghost sm', onclick: () => go(c.link) }, 'Open ' + (PAGE[c.link.split('?')[0]] || c.link)) : null),
        c.detail ? h('div', { class: 'small muted', style: { marginBottom: c.rows.length ? '8px' : 0 } }, c.detail) : null);
      if (c.rows.length) {
        const hasDiff = c.rows.some((r) => r.diff !== undefined && r.diff !== null);
        card.append(h('div', { class: 'tw', style: { maxHeight: '40vh' } }, h('table', { class: 't' },
          h('thead', {}, h('tr', {}, h('th', {}, 'Item'), h('th', { class: 'r' }, 'PMT'), h('th', { class: 'r' }, 'Pronto'), hasDiff ? h('th', { class: 'r' }, 'Difference') : null, h('th', {}, ''))),
          h('tbody', {}, c.rows.map((r) => h('tr', {}, h('td', {}, r.item, r.note ? h('span', { class: 'muted small' }, ` · ${r.note}`) : null),
            h('td', { class: 'r num' }, money(r.pmt)), h('td', { class: 'r num' }, money(r.pronto)), hasDiff ? h('td', { class: 'r num ' + (r.diff && Math.abs(r.diff) > 0.5 ? 'bad' : '') }, r.diff === undefined || r.diff === null ? '' : fmt.money(r.diff)) : null,
            h('td', { class: 'nowrap' }, ...actions(r))))))));
      }
      root.append(card);
    });
  });

  function actions(r) {
    const out = [];
    (r.match || []).forEach((m) => out.push(h('button', { class: 'btn sm', title: `Score ${m.score}`, onclick: async () => { await api.post(p(`/subcontracts/${r.sub_id}/match`), { supplier_code: m.code }); toast(`Matched to ${m.name}`); render(); } }, `Match to ${m.name}`)));
    (r.match_po || []).slice(0, 3).forEach((po) => out.push(h('button', { class: 'btn ghost sm', onclick: async () => { await api.post(p(`/subcontracts/${r.sub_id}/match`), { po_no: po }); toast(`PO ${po} linked`); render(); } }, `Use PO ${po}`)));
    if (r.sub_id) out.push(h('button', { class: 'btn ghost sm', onclick: () => go('subcontracts', { open: r.sub_id }) }, 'Open'));
    return out;
  }
}
