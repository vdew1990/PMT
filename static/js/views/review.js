import { h, clear, fmt, toast, select, badge, empty, debounce, tone } from '../ui.js';
import { api, state, p, loadRows, pref } from '../api.js';
import { go, render } from '../app.js';
import { accrualDialog } from './accruals.js';
import { historyDialog, stamp } from '../history.js';
import { assessDialog } from './_assess.js';

// MONTH-END > Review lines: for each CBS line, what was forecast to land this month against what has landed.
// Walk the lines one by one: it happened, so accrue what has no invoice yet; or it slipped, so reforecast it.
export default async function reviewView(root, params) {
  const ui = JSON.parse(sessionStorage.getItem('revui') || '{}');
  ui.month = params.month || ui.month || ''; ui.only = ui.only ?? pref('review_only'); ui.gp = ui.gp || ''; ui.q = '';
  const save = () => sessionStorage.setItem('revui', JSON.stringify({ month: ui.month, only: ui.only, gp: ui.gp }));
  const d = await api.get(p('/month-review' + (ui.month ? '?month=' + ui.month : '')));
  const rowsData = (await loadRows()).rows;
  const M = d.month; const tol = Math.max(1, state.project.tolerance || 1);
  const isDiff = (r) => Math.abs(r.variance) > tol || (r.planned > tol && r.landed < tol);

  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, `Month-end review ${fmt.month(M)}`),
    h('div', { class: 'sub' }, d.snapshot ? `Forecast for ${fmt.month(M)} as it stood at ${d.snapshot.label}, against what has landed (actual + accrued). For each line: did it happen as planned? If yes and the invoice is not in, accrue it. If not, reforecast it to when it will happen.`
      : `No month-end close before ${fmt.month(M)} yet, so the plan shown is the current forecast. Close a month on the Month-end page to keep a plan to review against.`)),
  h('div', { class: 'sp' }), select(d.grid.filter((m) => m <= d.status_month).slice(-12).reverse().map((m) => [m, fmt.month(m) + (m === d.status_month ? ' (status month)' : '')]), M, { onchange: (e) => { ui.month = e.target.value; save(); render(); } })));
  const t = d.total;
  const k = (l, v, s, cls = '') => h('div', { class: 'kpi ' + cls }, h('div', { class: 'l' }, l), h('div', { class: 'v' }, v), h('div', { class: 's' }, s));
  root.append(h('div', { class: 'grid', style: { marginBottom: '14px', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))' } },
    k('Landed (actual + accrual)', fmt.m(t.actual + t.accrued), `${fmt.m(t.actual)} in Pronto, ${fmt.m(t.accrued)} accrued`, 'rk-acd'), k('Actual', fmt.m(t.actual), 'In Pronto', 'rk-act'), k('Accrued', fmt.m(t.accrued), 'Not yet in Pronto', 'rk-acc'),
    k('Planned (previous forecast)', fmt.m(t.planned), d.snapshot ? d.snapshot.label : 'current forecast', 'rk-fcd'),
    k('Landed vs plan', fmt.m(t.variance), t.variance < 0 ? 'less landed than planned' : 'more landed than planned', 'rk-acd'),
    k('Still forecast this month', fmt.m(t.forecast_now), 'counted in the status month', 'rk-fc'), k('Reviewed', `${d.reviewed} / ${d.rows.length}`, 'lines with a decision')));
  const assess = (await api.get(p('/assessments'))).summary;
  // the monthly log of project complexity and client behaviour (feeds the client challenge rating in Portfolio)
  root.append(h('div', { class: 'grid g6', style: { marginBottom: '14px' } }, h('div', { class: 'kpi click', style: { cursor: 'pointer', gridColumn: 'span 2' }, title: 'Log this month\'s project complexity and client behaviour',
    onclick: () => assessDialog({ id: state.pid, name: state.project.name, client_pm: state.project.client_pm }, () => {}) },
    h('div', { class: 'l' }, 'Project complexity and client behaviour'), h('div', { class: 'v', style: { fontSize: '17px' } }, assess.latest_month ? `Last logged ${fmt.month(assess.latest_month)}` : 'Not logged yet'),
    h('div', { class: 's' }, assess.latest_month ? `Client PM difficulty ${assess.latest_pm_difficulty ?? 'n/a'}, complexity ${assess.latest_complexity ?? 'n/a'}.${assess.latest_month < M ? ` Nothing logged for ${fmt.month(M)} yet: click to log it.` : ' Click to update.'}` : 'Click to log this month\'s assessment'))));

  const bar = h('div', { class: 'card row', style: { padding: '10px 14px', marginBottom: '12px' } });
  const wrap = h('div', { class: 'revgrid' }); const list = h('div'); const pane = h('div', { class: 'revpane' });
  wrap.append(list, pane); root.append(bar, wrap);
  const chip = (key, v, label) => h('span', { class: 'chip' + (ui[key] === v ? ' on' : ''), onclick: () => { ui[key] = ui[key] === v && key === 'gp' ? '' : v; save(); drawBar(); draw(); } }, label);
  const search = h('input', { type: 'search', placeholder: 'Search code or name...', style: { width: '200px' }, oninput: debounce(() => { ui.q = search.value.trim().toLowerCase(); draw(); }, 150) });
  function drawBar() {
    clear(bar).append(search, chip('only', 'diff', 'Plan and landed differ'), chip('only', 'open', 'Not reviewed yet'), chip('only', 'all', 'All lines'), h('span', { style: { width: '8px' } }),
      ...['PL', 'PS', 'PM', 'PE'].map((g) => chip('gp', g, g)), h('span', { class: 'sp', style: { flex: 1 } }), h('span', { class: 'small muted' }, 'Keys: ↓ / ↑ next and previous line'));
  }
  let visible = []; let cur = params.node ? String(params.node) : null;
  function draw() {
    visible = d.rows.filter((r) => (ui.only === 'all' || (ui.only === 'diff' ? isDiff(r) : !r.decision)) && (!ui.gp || r.gp === ui.gp) && (!ui.q || `${r.code} ${r.name}`.toLowerCase().includes(ui.q)));
    if (params.node && !visible.some((r) => r.id === String(params.node))) { const r = d.rows.find((x) => x.id === String(params.node)); if (r) visible.unshift(r); }
    if (!cur || !visible.some((r) => r.id === cur)) cur = visible[0]?.id || null;
    const tb = h('tbody');
    visible.forEach((r) => tb.append(h('tr', { class: 'click' + (r.id === cur ? ' sel' : ''), onclick: () => { cur = r.id; draw(); } },
      h('td', { class: 'mono' }, r.code), h('td', { class: 'wrap' }, r.name), h('td', {}, h('span', { class: 'badge m-' + (r.method || 'AT-BUDGET') }, r.method || 'AT-BUDGET')),
      h('td', { class: 'r num mg mg-' + (r.state === 'hybrid' ? 'hyb' : r.state === 'actual' ? 'act' : r.state === 'accrual' ? 'acc' : 'acd') }, fmt.money(r.landed)), h('td', { class: 'r num mg mg-fcd' }, fmt.money(r.planned)),
      h('td', { class: 'r num ' + tone(-r.variance, tol), title: 'Landed less planned: positive means more cost landed than planned' }, fmt.money(r.variance)), h('td', {}, r.decision ? badge(d.decisions[r.decision], r.decision === 'delayed' || r.decision === 'partial' ? 'warn' : 'good') : h('span', { class: 'muted small' }, 'to review')))));
    clear(list).append(visible.length ? h('div', { class: 'tw', style: { maxHeight: '64vh' } }, h('table', { class: 't' }, h('thead', {}, h('tr', {}, ['CBS', 'Line', 'Method', 'Landed (actual + accrual)', 'Planned (previous forecast)', 'Difference', 'Decision'].map((x, i) => h('th', { class: i >= 3 && i <= 5 ? 'r' : '' }, x)))), tb))
      : empty('Nothing to review', ui.only === 'diff' ? 'Every line landed as planned this month.' : 'No lines match the filters.'));
    drawPane();
    const sel = list.querySelector('tr.sel'); if (sel) sel.scrollIntoView({ block: 'nearest' });
  }
  function move(n) { const i = visible.findIndex((r) => r.id === cur); const j = Math.max(0, Math.min(visible.length - 1, i + n)); if (visible[j]) { cur = visible[j].id; draw(); } }
  const onKey = (e) => { if (!document.body.contains(root)) { document.removeEventListener('keydown', onKey); return; } if (e.target.closest('input,textarea,select') || document.querySelector('.ov')) return; if (e.key === 'ArrowDown' || e.key === 'j') { e.preventDefault(); move(1); } if (e.key === 'ArrowUp' || e.key === 'k') { e.preventDefault(); move(-1); } };
  document.addEventListener('keydown', onKey);

  function drawPane() {
    clear(pane);
    const r = d.rows.find((x) => x.id === cur);
    if (!r) return;
    const tile = (l, v, cls, s) => h('div', { class: 'kpi ' + cls }, h('div', { class: 'l' }, l), h('div', { class: 'v', style: { fontSize: '19px' } }, fmt.money(v)), s ? h('div', { class: 's' }, s) : null);
    const gap = r.planned - r.landed;
    const note = h('input', { type: 'text', value: r.decision_note || '', placeholder: 'Why (optional): e.g. FAT moved to November, invoice due 20/10' });
    const decide = async (dec) => { await api.post(p('/month-review'), { node_ref: r.id, month: M, decision: dec, note: note.value || null }); r.decision = dec; r.decision_note = note.value; d.reviewed = d.rows.filter((x) => x.decision).length; toast('Decision saved'); move(1); draw(); };
    const lineRow = rowsData.find((x) => String(x.id) === r.id);
    pane.append(h('div', { class: 'card' },
      h('div', { class: 'ch' }, h('h2', {}, `${r.code}  ${r.name}`), h('span', { class: 'sp' }), h('button', { class: 'btn ghost sm', onclick: () => move(-1) }, '↑ Previous'), h('button', { class: 'btn ghost sm', onclick: () => move(1) }, 'Next ↓')),
      h('div', { class: 'grid g4', style: { marginBottom: '10px' } }, tile('Planned', r.planned, 'rk-fcd', d.snapshot ? `at ${d.snapshot.label}` : 'current forecast'), tile('Actual', r.actual, 'rk-act', 'in Pronto'), tile('Accrued', r.accrued, 'rk-acc', 'not yet in Pronto'),
        tile('Difference', r.variance, 'rk-acd', Math.abs(r.variance) <= tol ? 'landed as planned' : r.variance < 0 ? `${fmt.money(-r.variance)} less than planned` : `${fmt.money(r.variance)} more than planned`)),
      h('div', { class: 'small muted', style: { marginBottom: '10px' } }, `Method ${r.method || 'AT-BUDGET'}. Still forecast in ${fmt.month(M)}: ${fmt.money(r.forecast_now)}. Next month: ${fmt.money(r.forecast_next)}. CTC ${fmt.money(r.ctc)}, EAC ${fmt.money(r.eac)}.`, r.note ? ` ${r.note}` : ''),
      h('h3', { style: { margin: '6px 0' } }, 'Did it happen as planned?'),
      h('div', { class: 'row', style: { marginBottom: '8px' } },
        h('button', { class: 'btn', disabled: gap <= tol, title: 'Work was done but the invoice or timesheet is not in Pronto yet', onclick: () => accrualDialog(r.kind === 'pot' ? r.node_id : r.node_id, rowsData, async () => { await decide('accrued'); render(); }, null,
          { amount: gap, month: M, reason: 'Work done, invoice not yet received', note: `Month-end review ${fmt.month(M)}: planned ${fmt.money(r.planned)}, landed ${fmt.money(r.landed)}` }) }, gap > tol ? `Yes: accrue the ${fmt.money(gap)} not landed` : 'Nothing left to accrue'),
        h('button', { class: 'btn ghost', title: 'Open where this line is forecast to move the work to later months', onclick: async () => { await decide('delayed'); reforecast(r); } }, 'No: it slipped, reforecast'),
        r.sub ? h('button', { class: 'btn ghost', onclick: () => go('subcontracts', { open: r.sub.id }) }, `Claim sheet: ${r.sub.name}`) : null,
        lineRow && lineRow.kind === 'line' && r.method === 'GROUND-UP' ? h('button', { class: 'btn ghost', onclick: () => go('forecast', { node: r.node_id }) }, 'Ground-up detail') : null,
        h('button', { class: 'btn ghost', onclick: () => go('costcontrol', { open: r.id }) }, 'Cost control')),
      h('div', { class: 'row' }, note),
      h('div', { class: 'row', style: { marginTop: '8px' } }, h('span', { class: 'small muted' }, 'Record the decision:'), ...Object.entries(d.decisions).map(([kk, l]) => h('span', { class: 'chip' + (r.decision === kk ? ' on' : ''), onclick: () => decide(r.decision === kk ? null : kk) }, l))),
      r.decision ? h('div', { class: 'small', style: { marginTop: '8px' } }, `Decided: ${d.decisions[r.decision]}`, r.decision_note ? ` · ${r.decision_note}` : '', r.reviewed_by ? h('span', { class: 'muted' }, ` · by `, stamp(r.reviewed_by, r.reviewed_at)) : null,
        r.review_id ? h('a', { style: { marginLeft: '8px' }, onclick: () => historyDialog('month_review', r.review_id, `${r.code} review ${fmt.month(M)}`) }, 'history') : null) : null,
      h('div', { class: 'small muted', style: { marginTop: '10px' } }, reforecastHint(r))));
  }
  function reforecastHint(r) {
    return ({ 'AT-BUDGET': 'AT-BUDGET spreads what is left of the allowance over the remaining months, so a slip moves forward by itself: nothing to edit unless the total changes.',
      'BURN-RATE': 'BURN-RATE projects the average monthly spend: a slip moves forward by itself.',
      'GROUND-UP': 'GROUND-UP: move the days, milestones or roster start on the line\'s forecast items.',
      'CLAIM': 'CLAIM: move the unclaimed schedule on the subcontract (claim sheet).',
      'MANUAL': 'MANUAL: move the typed amount to the later month on the line.',
      'TOP-DOWN': 'TOP-DOWN: the EAC stays; the remainder spreads over the remaining months.',
      'AT-COMMIT': 'AT-COMMIT: the open PO value spreads over the remaining months.' })[r.method || 'AT-BUDGET'] || '';
  }
  function reforecast(r) {
    if (r.method === 'CLAIM' && r.sub) return go('subcontracts', { open: r.sub.id });
    if (['GROUND-UP', 'MANUAL'].includes(r.method)) return go('forecast', { node: r.kind === 'pot' ? 'p' + r.node_id : r.node_id });
    toast(reforecastHint(r));
  }
  drawBar(); draw();
}
