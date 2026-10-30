import { h, clear, fmt, modal, toast, table, badge, select } from '../ui.js';
import { api, p, loadProjects } from '../api.js';
import { render } from '../app.js';

const KIND = { budget: 'Budget differs', forecast: 'Forecast differs', new_line: 'In the CMT, not in the app', app_only: 'In the app, not in the CMT' };

// Upload a CMT: first a gap analysis against cost control (nothing is written), then the user chooses per item to reject or align.
export function cmtUpload() {
  const f = h('input', { type: 'file', accept: '.xlsx,.xlsm' });
  f.onchange = async () => {
    if (!f.files[0]) return;
    toast('Reading the CMT...');
    try { review(await api.upload(p('/cmt/analyse'), f.files[0])); } catch (e) { toast(e.message, 'bad'); }
  };
  f.click();
}

function review(a) {
  const s = a.summary;
  const dec = {}; const tgt = {}; let show = 'review'; let fcat = ''; let fkind = '';
  a.items.forEach((i) => { dec[i.id] = 'reject'; if (i.match === 'weak' && i.kind === 'forecast') tgt[i.id] = i.node_id; });
  const can = (i) => i.kind === 'forecast' || ((i.kind === 'new_line' || i.kind === 'budget') && i.parent_id);
  const canCmt = (i) => (i.kind === 'forecast' || i.kind === 'new_line') && i.cmt_ok && i.row;   // the CMT line can be written back to
  const choose = (i, v) => { if (v === 'align' && !can(i)) return; if (v === 'cmt' && !canCmt(i)) return; dec[i.id] = v; draw(); };
  const box = h('div');
  // redrawing rebuilds the dialog; keep the table (and dialog) where the user was scrolled to
  const draw = () => {
    const scrolls = [...box.querySelectorAll('.tw')].map((el) => el.scrollTop); const outer = box.closest('.mb'); const outerTop = outer ? outer.scrollTop : 0;
    drawNow();
    [...box.querySelectorAll('.tw')].forEach((el, i) => { el.scrollTop = scrolls[i] || 0; }); if (outer) outer.scrollTop = outerTop;
  };
  // Excel-style fill: drag the handle at the corner of a Decision cell down to copy its choice to the rows it passes over
  function startFill(e, origin, shown) {
    e.preventDefault(); e.stopPropagation();
    const tw = [...box.querySelectorAll('.tw')].pop(); const rows = () => [...tw.querySelectorAll('tbody tr')];
    const from = shown.indexOf(origin); let to = from; let timer = null; let py = e.clientY; let px = e.clientX;
    const mark = () => rows().forEach((tr, k) => tr.classList.toggle('fillsel', k >= Math.min(from, to) && k <= Math.max(from, to) && from !== to));
    const at = (y) => { const r = rows(); const el = document.elementFromPoint(px, y)?.closest('tr'); const k = r.indexOf(el); return k >= 0 ? k : to; };
    const move = (ev) => { py = ev.clientY; px = ev.clientX; to = at(py); mark(); };
    timer = setInterval(() => { const b = tw?.getBoundingClientRect(); if (!b) return; if (py > b.bottom - 28) tw.scrollTop += 18; else if (py < b.top + 28) tw.scrollTop -= 18; to = at(Math.min(Math.max(py, b.top + 4), b.bottom - 4)); mark(); }, 40);
    const up = () => {
      document.removeEventListener('mousemove', move); document.removeEventListener('mouseup', up); clearInterval(timer); document.body.classList.remove('filling');
      const lo = Math.min(from, to); const hi = Math.max(from, to);
      for (let k = lo; k <= hi; k++) if (dec[origin.id] === 'cmt' ? canCmt(shown[k]) : dec[origin.id] === 'align' ? can(shown[k]) : (can(shown[k]) || canCmt(shown[k]))) { dec[shown[k].id] = dec[origin.id]; const t = tgt[origin.id]; if (t && shown[k].candidates?.some((c) => String(c.node_id) === String(t))) tgt[shown[k].id] = t; }
      draw();
    };
    document.body.classList.add('filling');
    document.addEventListener('mousemove', move); document.addEventListener('mouseup', up);
  }
  const drawNow = () => {
    const nAlign = Object.values(dec).filter((v) => v === 'align').length; const nCmt = Object.values(dec).filter((v) => v === 'cmt').length;
    const nReview = a.items.filter((i) => i.match === 'weak').length; const nExact = a.items.filter((i) => i.match === 'exact').length;
    const shown = a.items.filter((i) => show === 'all' || (show === 'review' ? i.match !== 'exact' : i.match === 'exact'));
    clear(box).append(
      h('div', { class: 'note' }, h('b', {}, s.project || 'CMT'), `: CMT period ${s.period_cmt}, app status month ${s.period_app}. ${s.cmt_lines} CMT lines read, ${s.matched} matched to a CBS line. `,
        s.period_cmt !== s.period_app ? h('b', { style: { color: 'var(--bad)' } }, 'The periods differ: check this is the right CMT. ') : '',
        'Nothing changes until you choose, for each line, to use the CMT (the app is updated), use the app (the CMT is updated, and you download it at the end) or keep the gap, and press Apply. Click a figure or a button to choose. Only exact matches (same resource code or PO number, one CMT line to one app line) are trusted: check the others and pick the CBS line each belongs to. Aligning sets the line to MANUAL and loads the CMT months from the status month on.'),
      h('h3', { style: { margin: '14px 0 6px' } }, 'Totals by category (reported only: budgets move by transfers, actuals come from Pronto)'),
      table([{ label: 'Category', f: (c) => `${c.cat} ${c.name}` }, { label: 'Budget CMT', r: 1, f: (c) => fmt.money(c.budget_cmt) }, { label: 'Allowance app', r: 1, f: (c) => fmt.money(c.budget_app) },
        { label: 'CTD CMT', r: 1, f: (c) => fmt.money(c.ctd_cmt) }, { label: 'CTD app', r: 1, f: (c) => fmt.money(c.ctd_app) }, { label: 'CTC CMT', r: 1, f: (c) => fmt.money(c.ctc_cmt) }, { label: 'CTC app', r: 1, f: (c) => fmt.money(c.ctc_app) },
        { label: 'EAC CMT', r: 1, f: (c) => fmt.money(c.eac_cmt) }, { label: 'EAC app', r: 1, f: (c) => fmt.money(c.eac_app) }], s.categories, { maxHeight: '26vh' }),
      h('div', { class: 'small muted', style: { marginTop: '6px' } }, `Revenue: CMT revised contract ${fmt.money(s.revenue.cmt_revised)}, claimed ${fmt.money(s.revenue.cmt_claimed)}; app recognised ${fmt.money(s.revenue.app_recognised)}. Revenue is reported only; align it on the claim schedule.`),
      h('div', { class: 'row', style: { margin: '14px 0 6px', gap: '8px' } }, h('h3', { style: { margin: 0 } }, `Differences (${a.items.length})`),
        ...[['review', `Needs your review (${nReview})`], ['exact', `Exact matches (${nExact})`], ['all', 'All']].map(([k, l]) => h('span', { class: 'chip' + (show === k ? ' on' : ''), onclick: () => { show = k; draw(); } }, l)), select([['', 'All categories'], ...[...new Set(a.items.map((i) => i.cat).filter(Boolean))].sort().map((c) => [c, c])], fcat, { onchange: (e) => { fcat = e.target.value; draw(); } }),
        select([['', 'All kinds'], ...Object.entries(KIND)], fkind, { onchange: (e) => { fkind = e.target.value; draw(); } }), h('span', { class: 'sp', style: { flex: 1 } }),
        h('a', { class: 'btn ghost sm', href: p(`/cmt/report?token=${a.token}`), title: 'The category totals and every difference as an Excel workbook' }, 'Download gap report'),
        h('button', { class: 'btn ghost sm', onclick: () => { a.items.forEach((i) => { if (i.match === 'exact' && i.last === 'align' && can(i)) dec[i.id] = 'align'; }); draw(); } }, 'Repeat last time\'s Align choices'),
        h('button', { class: 'btn ghost sm', title: 'Only exact matches (same resource code or PO number, one CMT line to one app line). Weak matches are never changed in bulk.', onclick: () => { a.items.forEach((i) => { if (i.match === 'exact' && can(i)) dec[i.id] = 'align'; }); draw(); } }, 'Exact matches: use CMT'),
        h('button', { class: 'btn ghost sm', title: 'Write the app\'s figures into the CMT for every exact match', onclick: () => { a.items.forEach((i) => { if (i.match === 'exact' && canCmt(i)) dec[i.id] = 'cmt'; }); draw(); } }, 'Exact matches: use app'),
        h('button', { class: 'btn ghost sm', onclick: () => { a.items.forEach((i) => { dec[i.id] = 'reject'; }); draw(); } }, 'Keep every gap')),
      shown.length ? table([
        { label: 'Item', f: (i) => h('div', {}, h('b', {}, i.title), i.last ? h('span', { style: { marginLeft: '6px' } }, badge(`last time: ${i.last}`, i.last === 'align' ? 'good' : '')) : null, h('div', { class: 'small muted' }, KIND[i.kind], i.cmt_label ? ` · CMT: ${i.cmt_label}` : '', i.method ? ` · now ${i.method}` : '', i.note ? ` · ${i.note}` : '')) },
        { label: 'Decision', f: (i) => (can(i) || canCmt(i)) ? h('div', { class: 'fillcell' }, h('div', { class: 'seg3' },
          h('button', { type: 'button', class: dec[i.id] === 'align' ? 'on' : '', disabled: !can(i), title: 'Update the app to the CMT: the line forecasts the CMT\'s months', onclick: () => choose(i, 'align') }, 'Use CMT'),
          h('button', { type: 'button', class: dec[i.id] === 'cmt' ? 'on cmt' : '', disabled: !canCmt(i), title: canCmt(i) ? 'Update the CMT to the app: the app\'s figures are written into this CMT line (you download the updated CMT at the end)' : 'The CMT cannot take the app\'s figures for this line (several CMT lines share one app line, or the line has no CMT row)', onclick: () => choose(i, 'cmt') }, 'Use app'),
          h('button', { type: 'button', class: dec[i.id] === 'reject' ? 'on rej' : '', title: 'Reject: nothing changes and the gap remains', onclick: () => choose(i, 'reject') }, 'Keep gap')),
          h('span', { class: 'fillh', title: 'Drag down to copy this choice to the rows below', onmousedown: (e) => startFill(e, i, shown) })) : badge('reported only') },
        { label: 'Match', f: (i) => (i.match === 'exact' ? badge('exact', 'good') : i.match === 'weak' ? h('div', {}, badge('review', 'warn'), h('div', { class: 'small muted' }, i.why || ''),
          i.candidates?.length ? select([...(i.kind === 'new_line' ? [['', 'Create a new CBS line']] : []), ...i.candidates.map((c) => [c.node_id, `${c.label} (${Math.round(c.score * 100)}%)`])], tgt[i.id] ?? '', { onchange: (e) => { tgt[i.id] = e.target.value; } })
            : h('div', { class: 'small muted' }, 'No similar CBS line')) : '') },
        { label: 'App (forecast or budget)', r: 1, f: (i) => h('span', { class: 'pickv' + (dec[i.id] === 'cmt' ? ' win' : ''), title: canCmt(i) ? 'Click: update the CMT to this figure' : '', onclick: () => choose(i, 'cmt') }, fmt.money(i.app_total)) },
        { label: 'CMT', r: 1, f: (i) => h('span', { class: 'pickv' + (dec[i.id] === 'align' ? ' win' : ''), title: can(i) ? 'Click: update the app to this figure' : '', onclick: () => choose(i, 'align') }, fmt.money(i.cmt_total)) },
        { label: 'Months that differ (app → CMT)', f: (i) => i.kind === 'budget' ? h('span', { class: 'small' }, `Adjust ${fmt.money(i.delta)} on the category group`) : h('span', { class: 'small' }, i.months.slice(0, 6).map((m) => `${fmt.month(m.month)} ${fmt.n(m.app, 0)}→${fmt.n(m.cmt, 0)}`).join('; '), i.months.length > 6 ? ` ... +${i.months.length - 6}` : '') },
      ], shown, { maxHeight: '44vh' }) : h('div', { class: 'good' }, a.items.length ? 'Nothing in this list.' : 'No differences in the forecast: the app already matches the CMT.'),
      h('div', { class: 'small', style: { marginTop: '8px' } }, `${nAlign} item(s) will update the app to the CMT, ${nCmt} will update the CMT to the app; the rest keep their gap.`));
  };
  draw();
  modal({ title: 'Load a CMT: gap analysis', size: 'wide', body: box, actions: [
    { label: 'Close without changing', kind: 'ghost', onClick: () => {} },
    { label: 'Apply the chosen items', onClick: async () => {
      const n = Object.values(dec).filter((v) => v === 'align' || v === 'cmt').length;
      if (!n) throw new Error('Nothing is set to use the CMT or the app: every gap is being kept');
      const r = await api.post(p('/cmt/apply'), { token: a.token, decisions: dec, targets: tgt });
      await loadProjects(); await render();
      modal({ title: 'CMT applied', body: h('div', {}, h('p', {}, `${r.forecast} forecast(s) updated to the CMT, ${r.new_lines} line(s) created and ${r.budgets || 0} budget adjustment(s) posted. They now forecast from typed months (MANUAL).`),
          r.cmt_edits ? h('p', {}, `${r.cmt_edits} CMT cell(s) are ready to take the app's figures. `, h('a', { class: 'btn', href: p(`/cmt/updated?token=${a.token}`), title: 'The CMT you loaded, with the app\'s figures written into the lines you chose. Excel recalculates it when you open it.' }, 'Download the updated CMT')) : null,
          r.cmt_edits ? h('p', { class: 'small muted' }, 'The download is your CMT file with only those cells changed (charts, pivots and comments are kept). Excel recalculates the totals when it opens it. Check it before it replaces the master.') : null,
          r.skipped.length ? h('p', { class: 'muted' }, `Skipped: ${r.skipped.join('; ')}`) : null),
        actions: [{ label: 'Undo this alignment', kind: 'ghost', onClick: async () => { const u = await api.post(p('/cmt/undo'), {}); toast(`${u.restored} change(s) put back`); await render(); } }, { label: 'Close', onClick: () => {} }] });
    } }] });
}
