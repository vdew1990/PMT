import { h, clear, fmt, modal, toast, field, select, table, num, confirmBox, badge, tabs, empty, drawer, chart, PALETTE, todayISO , pdfNameDialog } from '../ui.js';
import { api, state, p, loadRows } from '../api.js';
import { outlineState, outlineStrip, visible as olVisible, MONTH_LEVELS } from '../outline.js';
import { pickNode } from '../scope.js';
import { go, render } from '../app.js';
import { supplierPicker } from './_supplier.js';

const stTone = { draft: '', received: 'warn', approved: 'navy', paid: 'good' };
const stLabel = { draft: 'Draft', received: 'Received', approved: 'Approved', paid: 'Paid' };

// Subcontract register, schedule of values and monthly progress claims with approval.
export default async function subcontracts(root, params) {
  const list = await api.get(p('/subcontracts'));
  await loadRows();
  const M = state.rows.status_month;
  const awaiting = list.reduce((a, s) => a + s.awaiting_approval, 0);
  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, 'Subcontracts'), h('div', { class: 'sub' }, 'Each subcontractor claims monthly against a schedule. Approve the claim line by line or in total: approved amounts (claimed where nothing is approved yet) become this month\'s accrual, and what is still scheduled becomes forecast.')), h('div', { class: 'sp' }),
    h('button', { class: 'btn ghost', title: 'An Excel payment schedule to fill in: payment terms, price table, claims and plans by month', onclick: () => window.open(p('/subcontracts/template.xlsx')) }, 'Download template'),
    list.length ? h('button', { class: 'btn ghost', title: 'Every subcontract in the template layout, one sheet each, to update and upload again', onclick: () => window.open(p('/subcontracts/template.xlsx?sid=all')) }, 'Download all') : null,
    h('button', { class: 'btn ghost', onclick: () => uploadSchedule() }, 'Upload payment schedule...'),
    h('button', { class: 'btn', onclick: () => openSub() }, '+ New subcontract')));
  if (!list.length) { root.append(empty('No subcontracts yet', 'Add one here, or download the template, fill in the payment schedule and upload it.')); return; }
  const sum = (k) => list.reduce((a, s) => a + (s[k] || 0), 0);
  root.append(h('div', { class: 'grid g4', style: { marginBottom: '14px' } }, kpi('Subcontract value', fmt.money(sum('contract_value')), `${list.length} subcontracts`), kpi('Claimed to date (effective)', fmt.money(sum('claimed_gross')), 'Approved where approved, else claimed', 't2'), kpi('Retention held', fmt.money(sum('claimed_retention')), '', 't3'), kpi('Claims awaiting approval', String(awaiting), awaiting ? 'Review them so cost control uses approved amounts' : 'Nothing waiting', awaiting ? 't4' : 't6')));
  root.append(table([{ label: 'Subcontract', f: (s) => h('b', {}, s.name) }, { label: 'PO', f: (s) => h('span', {}, s.po_no || '', s.link && s.link.po === 'pending' ? badge('to be matched', 'warn') : null) }, { label: 'Supplier', f: (s) => h('span', {}, s.link?.supplier_name || '', s.link && s.link.supplier === 'pending' ? badge('to be matched', 'warn') : null) }, { label: 'CBS line', f: (s) => s.node_code ? h('span', { class: 'mono' }, `${s.node_code} ${s.node_name}`) : h('span', { class: 'warn' }, 'not linked') }, { label: 'Value', r: 1, f: (s) => fmt.money(s.contract_value) }, { label: 'Retention', r: 1, f: (s) => fmt.pct(s.retention_pct, 1) },
    { label: 'Scheduled', r: 1, f: (s) => fmt.money(s.scheduled_gross) }, { label: 'Claimed', r: 1, f: (s) => fmt.money(s.claimed_gross) }, { label: 'Still to claim', r: 1, f: (s) => fmt.money(s.to_claim) }, { label: 'Unscheduled', r: 1, f: (s) => h('span', { class: Math.abs(s.unscheduled) > 1 ? 'bad' : '' }, fmt.money(s.unscheduled)) },
    { label: 'Awaiting approval', f: (s) => s.awaiting_approval ? badge(String(s.awaiting_approval), 'warn') : '' }], list, { onRow: (s) => openSub(s) }));
  if (params.open) openSub(list.find((s) => s.id === +params.open));
  function kpi(l, v, s, c = '') { return h('div', { class: 'kpi ' + c }, h('div', { class: 'l' }, l), h('div', { class: 'v' }, v), h('div', { class: 's' }, s)); }

  // ---- one subcontract -----------------------------------------------------------------------------
  async function openSub(s = null, tab0 = 'sheet') {
    const isNew = !s;
    s = s || { name: '', milestones: [], claims: [], contract_value: 0, retention_pct: 0 };
    const body = h('div'); const d = drawer({ title: isNew ? 'New subcontract' : s.name, sub: s.node_code ? `Linked to ${s.node_code} ${s.node_name}` : 'Not yet linked to a CBS line', body });
    let tab = isNew ? 'setup' : tab0; const pane = h('div'); const tb = h('div');
    const sw = () => { clear(tb).append(tabs(isNew ? [['setup', 'Payment terms and prices']] : [['sheet', 'Claim sheet'], ['claims', 'Monthly claims'], ['setup', 'Payment terms and prices']], tab, (k) => { tab = k; sw(); })); clear(pane); ({ sheet: sheetTab, claims: claimsTab, setup: setupTab })[tab](); };
    body.append(tb, pane); sw();
    const reopen = async () => { sessionStorage.setItem('reopenSub', JSON.stringify({ id: s.id, tab })); d.close(); await render(); };

    function setupTab() {
      const f = { name: h('input', { type: 'text', value: s.name || '' }), po: h('input', { type: 'text', value: s.po_no || '' }), sup: h('input', { type: 'text', value: s.supplier_code || '', placeholder: 'Pronto code' }), cv: h('input', { type: 'number', step: '0.01', value: s.contract_value ?? '' }), ret: h('input', { type: 'number', step: '0.1', value: ((s.retention_pct || 0) * 100) }), rel: h('input', { type: 'month', value: s.retention_release_month || '' }) };
      // supplier and PO: a known Pronto supplier and one of its orders, or entered ahead of Pronto (matched on Diagnostics)
      const supBox = h('div', { class: 'card', style: { padding: '10px 12px' } }, h('span', { class: 'muted small' }, 'Loading suppliers...')); let picker = null;
      supplierPicker({ supplier_code: s.supplier_code, supplier_name: s.supplier_name, po_no: s.po_no }).then((pk) => { picker = pk; supBox.replaceChildren(pk.el); }).catch(() => supBox.replaceChildren(h('div', { class: 'grid g2' }, field('Supplier code', f.sup), field('PO number', f.po))));
      let node = s.node_id || null; const nodeBtn = h('button', { class: 'btn ghost', onclick: () => pickNode({ title: 'Link to a CBS line', kinds: ['line'], onPick: (r) => { node = r.node_id; nodeBtn.textContent = `${r.code} ${r.name}`; } }) }, s.node_code ? `${s.node_code} ${s.node_name}` : 'Choose a CBS line...');
      // Payment terms (milestones and progress as % of the contract), the price table (items claimed by progress x the
      // progress share) and variations. One list of schedule lines; each table shows its own types.
      const ms = (s.milestones || []).map((m) => ({ ...m }));
      const cvNow = () => num(f.cv.value) || ms.filter((m) => m.type === 'Price').reduce((a, m) => a + num(m.value), 0);
      const pctOf = (m) => num(m.pct) || (cvNow() ? num(m.value) / cvNow() : 0);
      const share = () => { if (!ms.some((m) => m.type === 'Price')) return 1; const pr = ms.filter((m) => m.type === 'Progress'); return pr.length ? pr.reduce((a, m) => a + pctOf(m), 0) : Math.max(0, 1 - ms.filter((m) => m.type === 'Milestone').reduce((a, m) => a + pctOf(m), 0)); };
      const termsBox = h('div'); const priceBox = h('div'); const varBox = h('div');
      const inp = (m, k, type = 'text', w = 100, after) => h('input', { type, step: 'any', value: k === 'pct' ? (m.pct ? +(m.pct * 100).toFixed(4) : '') : (k === 'value' && !m.value ? '' : (m[k] ?? '')), style: { width: w + 'px' },
        placeholder: k === 'value' && (m.type === 'Milestone' || m.type === 'Progress') && m.pct ? fmt.money(m.pct * cvNow()) : '',
        onchange: (e) => { m[k] = k === 'pct' ? num(e.target.value) / 100 : type === 'number' ? num(e.target.value) : e.target.value; if (k === 'pct') m.value = 0; if (k === 'value' && m.type !== 'Price' && m.type !== 'Variation') m.pct = 0; drawAll(); after && after(); } });
      const del = (m) => h('button', { class: 'btn danger sm', onclick: () => { ms.splice(ms.indexOf(m), 1); drawAll(); } }, '×');
      const foot = (cells) => h('tfoot', {}, h('tr', {}, cells.map((c) => (c && c.nodeType ? c : h('td', { class: typeof c === 'number' ? 'r num' : '' }, typeof c === 'number' ? fmt.money(c) : (c ?? ''))))));
      function drawAll() {
        const cv = cvNow(); const y = share(); const hasPrice = ms.some((m) => m.type === 'Price');
        const terms = ms.filter((m) => m.type === 'Milestone' || m.type === 'Progress');
        const tPct = terms.reduce((a, m) => a + pctOf(m), 0) + (hasPrice && !ms.some((m) => m.type === 'Progress') ? y : 0);
        clear(termsBox).append(h('div', { class: 'tw' }, h('table', { class: 't' },
          h('thead', {}, h('tr', {}, ['Portion', 'Claimed', '% of contract', 'Value', 'Planned month', 'Progress until', 'Trigger / evidence', ''].map((x, i) => h('th', { class: i === 2 || i === 3 ? 'r' : '' }, x)))),
          h('tbody', {}, terms.map((m) => h('tr', {}, h('td', { class: 'in' }, inp(m, 'name', 'text', 190)),
            h('td', {}, select([['Milestone', 'On a milestone'], ['Progress', 'By progress (monthly)']], m.type, { onchange: (e) => { m.type = e.target.value; drawAll(); } })),
            h('td', { class: 'in r' }, inp(m, 'pct', 'number', 70)), h('td', { class: 'in r' }, inp(m, 'value', 'number', 110)),
            h('td', { class: 'in' }, inp(m, 'start_month', 'month', 130)), h('td', { class: 'in' }, m.type === 'Progress' && !hasPrice ? inp(m, 'end_month', 'month', 130) : h('span', { class: 'muted small' }, m.type === 'Progress' ? 'per price item' : '')),
            h('td', { class: 'in' }, inp(m, 'trigger_note', 'text', 170)), h('td', {}, del(m)))),
            hasPrice && !ms.some((m) => m.type === 'Progress') ? h('tr', {}, h('td', { class: 'muted' }, 'Progress (rest of the contract)'), h('td', { class: 'muted' }, 'By progress (monthly)'), h('td', { class: 'r num muted' }, fmt.pct(y, 1)), h('td', { class: 'r num muted' }, fmt.money(y * cv)), h('td', { colspan: 4, class: 'small muted' }, 'Claimed through the price table')) : null),
          terms.length || hasPrice ? foot([h('td', {}, 'Total'), '', h('td', { class: 'r num ' + (Math.abs(tPct - 1) > 0.0005 ? 'bad' : '') }, fmt.pct(tPct, 1)), tPct * cv, '', '', Math.abs(tPct - 1) > 0.0005 ? h('td', { class: 'bad small' }, 'should be 100%') : '', '']) : null)));
        const price = ms.filter((m) => m.type === 'Price'); const pTot = price.reduce((a, m) => a + num(m.value), 0);
        clear(priceBox).append(price.length ? h('div', { class: 'tw' }, h('table', { class: 't' },
          h('thead', {}, h('tr', {}, ['Item', 'Price', `Claimable by progress (× ${fmt.pct(y, 1)})`, 'Progress from', 'Progress until', ''].map((x, i) => h('th', { class: i === 1 || i === 2 ? 'r' : '' }, x)))),
          h('tbody', {}, price.map((m) => h('tr', {}, h('td', { class: 'in' }, inp(m, 'name', 'text', 260)), h('td', { class: 'in r' }, inp(m, 'value', 'number', 120)), h('td', { class: 'r num' }, fmt.money(num(m.value) * y)),
            h('td', { class: 'in' }, inp(m, 'start_month', 'month', 130)), h('td', { class: 'in' }, inp(m, 'end_month', 'month', 130)), h('td', {}, del(m))))),
          foot([h('td', {}, 'Total'), pTot, pTot * y, h('td', { colspan: 3, class: 'small ' + (num(f.cv.value) && Math.abs(pTot - num(f.cv.value)) > 1 ? 'bad' : 'muted') }, num(f.cv.value) && Math.abs(pTot - num(f.cv.value)) > 1 ? `Contract value is ${fmt.money(num(f.cv.value))}` : 'Adds up to the contract value')])))
          : h('div', { class: 'muted small' }, 'No price table: progress is claimed on the Progress portion as a % of the contract value.'));
        const vars = ms.filter((m) => m.type === 'Variation');
        clear(varBox).append(vars.length ? h('div', { class: 'tw' }, h('table', { class: 't' },
          h('thead', {}, h('tr', {}, ['Variation', 'Value', 'Month', ''].map((x, i) => h('th', { class: i === 1 ? 'r' : '' }, x)))),
          h('tbody', {}, vars.map((m) => h('tr', {}, h('td', { class: 'in' }, inp(m, 'name', 'text', 260)), h('td', { class: 'in r' }, inp(m, 'value', 'number', 120)), h('td', { class: 'in' }, inp(m, 'start_month', 'month', 130)), h('td', {}, del(m))))),
          foot([h('td', {}, 'Total'), vars.reduce((a, m) => a + num(m.value), 0), '', ''])))
          : h('div', { class: 'muted small' }, 'No variations.'));
      }
      f.cv.addEventListener('change', () => drawAll());
      drawAll();
      const chartBox = h('div', { class: 'chartbox short' });
      pane.append(h('div', { class: 'grid' }, h('div', { class: 'grid g3' }, field('Subcontract name', f.name), h('span'), h('span')), supBox, h('div', { class: 'grid g4' }, field('Contract value', f.cv), field('Retention %', f.ret, 'Held from each claim'), field('Retention release month', f.rel), field('CBS line', nodeBtn)),
        h('div', { class: 'card' }, h('div', { class: 'ch' }, h('h2', {}, 'Payment terms'), h('span', { class: 'sp' }), h('span', { class: 'small muted' }, 'Split the price into portions, e.g. 10% on order, 80% by progress, 10% on QA documents = 100%.'),
          h('button', { class: 'btn sm', onclick: () => { ms.push({ type: 'Milestone', name: '' }); drawAll(); } }, '+ Milestone'), h('button', { class: 'btn sm', onclick: () => { ms.push({ type: 'Progress', name: 'Progress' }); drawAll(); } }, '+ Progress')), termsBox),
        h('div', { class: 'card' }, h('div', { class: 'ch' }, h('h2', {}, 'Price table'), h('span', { class: 'sp' }), h('span', { class: 'small muted' }, 'Optional. Progress is claimed per item: progress × price × the progress %.'),
          h('button', { class: 'btn sm', onclick: () => { ms.push({ type: 'Price', name: '' }); drawAll(); } }, '+ Price item')), priceBox),
        h('div', { class: 'card' }, h('div', { class: 'ch' }, h('h2', {}, 'Variations'), h('span', { class: 'sp' }), h('button', { class: 'btn sm', onclick: () => { ms.push({ type: 'Variation', name: '' }); drawAll(); } }, '+ Variation')), varBox),
        s.schedule && Object.keys(s.schedule).length ? h('div', { class: 'card' }, h('h2', {}, 'Scheduled net payments (after retention)'), chartBox) : null,
        h('div', { class: 'row' }, !isNew ? h('button', { class: 'btn ghost', title: 'This subcontract in the Excel template layout: update it and upload it on the Subcontracts page', onclick: () => window.open(p(`/subcontracts/template.xlsx?sid=${s.id}`)) }, 'Download to Excel') : null,
          !isNew ? h('button', { class: 'btn danger', onclick: async () => { if (await confirmBox('Delete this subcontract and its claims?', 'Delete', true)) { await api.del(p(`/subcontracts/${s.id}`)); d.close(); await render(); } } }, 'Delete') : null, h('span', { style: { flex: 1 } }),
          h('button', { class: 'btn', onclick: async () => {
            if (!f.name.value) return toast('Enter a name', 'bad');
            const r = await api.post(p('/subcontracts'), { id: s.id, name: f.name.value, ...(picker ? picker.value() : { po_no: f.po.value, supplier_code: f.sup.value }), node_id: node, contract_value: num(f.cv.value), retention_pct: num(f.ret.value) / 100, retention_release_month: f.rel.value || null, milestones: ms });
            if (node && (await api.get(p(`/nodes/${node}`))).method !== 'CLAIM' && await confirmBox('Switch the linked CBS line to the CLAIM forecast method, so the unclaimed schedule drives its cost to complete?', 'Use CLAIM')) await api.put(p(`/nodes/${node}`), { method: 'CLAIM' });
            toast('Subcontract saved'); s.id = r.id; sessionStorage.setItem('reopenSub', JSON.stringify({ id: r.id, tab: 'claims' })); d.close(); await render(); } }, 'Save subcontract'))));
      if (s.schedule && Object.keys(s.schedule).length) { const ks = Object.keys(s.schedule); const claimedBy = {}; (s.claims || []).filter((c) => c.status !== 'draft').forEach((c) => { claimedBy[c.month] = (claimedBy[c.month] || 0) + c.net; }); setTimeout(() => chart(chartBox, { type: 'bar', data: { labels: ks.map(fmt.month), datasets: [{ label: 'Scheduled', data: ks.map((k) => s.schedule[k]), backgroundColor: PALETTE[3] }, { label: 'Claimed (approved or claimed)', data: ks.map((k) => claimedBy[k] || 0), backgroundColor: PALETTE[0] }] } }), 40); }
    }

    // ---- claim sheet: per schedule line, invoiced and claimed by month next to the PM's forecast of future claims ----
    async function sheetTab() {
      const d = await api.get(p(`/subcontracts/${s.id}/sheet`));
      const M = d.month; const g = d.grid; const gi = g.indexOf(M);
      const ost = outlineState('sub', { folded: [] }); const gc = g.map((m) => ({ id: m })); const gv = olVisible(gc, gi, ost, MONTH_LEVELS);   // folded and hidden months take no room
      const cells = new Map(); let timer = null; const status = h('span', { class: 'small muted' });
      const queue = (iid, m, v, row) => {
        // the first typed month on a line takes the rest of that line's shown forecast with it, so the line keeps its total
        if (!Object.keys(row.forecast).length && !cells.has(iid)) cells.set(iid, Object.fromEntries(Object.entries(row.future).map(([k, x]) => [k, Math.round(x * 100) / 100])));
        const c = cells.get(iid) || {}; c[m] = v; cells.set(iid, c);
        status.textContent = 'Saving...'; clearTimeout(timer); timer = setTimeout(flush, 600);
      };
      async function flush() { const body = Object.fromEntries(cells); cells.clear(); try { await api.put(p(`/subcontracts/${s.id}/forecast`), { cells: body }); status.textContent = 'Saved ' + new Date().toLocaleTimeString(); await refresh(); } catch (e) { toast(e.message, 'bad'); } }
      const refresh = async () => { if (document.activeElement && document.activeElement.closest('.csheet')) return; clear(pane); await sheetTab(); };
      const head = h('tr', {}, h('th', { class: 'sticky1', style: { left: 0, zIndex: 4 } }, 'Schedule line'), h('th', { class: 'r' }, 'Contract'), h('th', { class: 'r' }, 'Claimed before'),
        ...g.flatMap((m, i) => !gv[i] ? [] : i === gi ? [h('th', { class: 'mth mcf', 'data-col': m, title: 'What the PM forecast for this month' }, fmt.month(m) + ' (F)'), h('th', { class: 'mth mca', 'data-col': m, title: 'Claimed this month: approved, claimed underneath' }, fmt.month(m))] : [h('th', { class: 'mth ' + (i < gi ? 'mpa' : 'mfu'), 'data-col': m }, fmt.month(m))]),
        h('th', { class: 'r' }, 'Claimed to date'), h('th', { class: 'r' }, 'Forecast'), h('th', { class: 'r' }, 'Not forecast'));
      const tbody = h('tbody');
      d.rows.forEach((row) => {
        const tr = h('tr', {}, h('td', { class: 'sticky1 cname', style: { left: 0 } }, h('b', {}, row.name), ' ', badge(row.type)), h('td', { class: 'r num' }, fmt.money(row.value)), h('td', { class: 'r num' }, fmt.money(row.prior)));
        g.forEach((m, i) => {
          if (!gv[i]) return;
          const c = row.claims[m];
          if (i < gi) tr.append(h('td', { class: 'r num mg ' + (c ? (c.invoiced ? 'mg-act' : 'mg-acc') : 'mg-pa'), title: c ? `Claimed ${fmt.money(c.claimed)}, approved ${c.approved === null ? 'not yet' : fmt.money(c.approved)}. ${c.invoiced ? 'Invoiced (in Pronto).' : 'Accrued: invoice not in Pronto yet.'}` : '' }, c ? fmt.n(c.effective) : ''));
          else if (i === gi) {
            const fM = row.forecast[m] ?? row.schedule[m] ?? 0;
            tr.append(h('td', { class: 'r num mg mg-fcd', title: 'Forecast for this month' }, fM ? fmt.n(fM) : ''),
              h('td', { class: 'r num mg ' + (c ? (c.invoiced ? 'mg-act' : 'mg-acd') : 'mg-acd'), title: c ? `Claimed ${fmt.money(c.claimed)}; approved ${c.approved === null ? 'not yet' : fmt.money(c.approved)}` : 'No claim for this month yet' },
                c ? h('span', {}, h('b', {}, fmt.n(c.approved ?? c.claimed)), h('div', { class: 'small muted' }, c.approved === null ? 'claimed, not approved' : `claimed ${fmt.n(c.claimed)}`)) : ''));
          } else {
            const v = row.future[m];
            const inp = h('input', { type: 'text', inputmode: 'decimal', value: v ? fmt.n(v) : '', placeholder: ' ', title: 'Your forecast of what they will claim in ' + fmt.month(m) });
            inp.onchange = () => { const t = inp.value.trim(); queue(row.item_id, m, t === '' ? null : num(t), row); inp.classList.add('dirty'); };
            tr.append(h('td', { class: 'mg mg-fc cin' }, inp));
          }
        });
        tr.append(h('td', { class: 'r num' }, fmt.money(row.claimed)), h('td', { class: 'r num' }, fmt.money(row.forecast_total)), h('td', { class: 'r num ' + (Math.abs(row.unforecast) > 1 ? 'bad' : 'muted') }, fmt.money(row.unforecast)));
        tbody.append(tr);
      });
      const t = d.total;
      const foot = h('tr', {}, h('td', { class: 'sticky1', style: { left: 0 } }, 'Total'), h('td', { class: 'r num' }, fmt.money(t.value)), h('td', { class: 'r num' }, fmt.money(t.prior)), ...g.flatMap((m, i) => {
        if (!gv[i]) return [];
        const sumC = d.rows.reduce((a, r) => a + (r.claims[m]?.effective || 0), 0); const sumF = d.rows.reduce((a, r) => a + (r.future[m] || 0), 0);
        if (i < gi) return [h('td', { class: 'r num' }, sumC ? fmt.n(sumC) : '')];
        if (i === gi) return [h('td', { class: 'r num' }, fmt.n(d.rows.reduce((a, r) => a + (r.forecast[m] ?? r.schedule[m] ?? 0), 0)) || ''), h('td', { class: 'r num' }, sumC ? fmt.n(sumC) : '')];
        return [h('td', { class: 'r num' }, sumF ? fmt.n(sumF) : '')];
      }), h('td', { class: 'r num' }, fmt.money(t.claimed)), h('td', { class: 'r num' }, fmt.money(t.forecast_total)), h('td', { class: 'r num ' + (Math.abs(t.unforecast) > 1 ? 'bad' : '') }, fmt.money(t.unforecast)));
      const sheetTbl = h('table', { class: 't' }, h('thead', {}, head), tbody, h('tfoot', {}, foot)); const sheetTw = h('div', { class: 'tw csheet', style: { maxHeight: '58vh' } }, sheetTbl);
      const ol = outlineStrip({ cols: gc, cur: gi, levels: MONTH_LEVELS, st: ost, onChange: () => { clear(pane); sheetTab(); }, names: { 1: 'This quarter only', 2: 'Every month' } });
      pane.append(h('div', { class: 'note', style: { marginBottom: '10px' } }, d.pm_forecast
        ? `Cost control uses your forecast below for the months after the claims, net of ${fmt.pct(d.retention_pct, 1)} retention. Lines you have not forecast follow their unclaimed schedule.`
        : 'The green months show the unclaimed schedule. Type what you expect them to claim and month: from then on cost control follows your forecast for this subcontract.'),
        h('div', { class: 'row', style: { marginBottom: '8px' } },
          !d.pm_forecast ? h('button', { class: 'btn sm', onclick: async () => { await api.post(p(`/subcontracts/${s.id}/forecast/seed`)); toast('Forecast started from the schedule'); clear(pane); sheetTab(); } }, 'Start my forecast from the schedule') : null,
          d.pm_forecast ? h('button', { class: 'btn ghost sm', title: 'Everything forecast from this month on moves one month later', onclick: async () => { await api.post(p(`/subcontracts/${s.id}/forecast/shift`), { months: 1 }); toast('Forecast slipped one month'); clear(pane); sheetTab(); } }, 'Slip my forecast one month') : null,
          d.pm_forecast ? h('button', { class: 'btn ghost sm', onclick: async () => { if (await confirmBox('Clear your forecast and go back to the schedule?', 'Clear')) { await api.post(p(`/subcontracts/${s.id}/forecast/clear`)); clear(pane); sheetTab(); } } }, 'Back to the schedule') : null,
          h('button', { class: 'btn ghost sm', onclick: () => { tab = 'claims'; sw(); } }, `Claims (${(s.claims || []).length})`), h('span', { class: 'sp', style: { flex: 1 } }), status),
        ...(g.length > 1 ? [ol.el] : []), sheetTw,
        h('div', { class: 'legend', style: { marginTop: '8px' } }, h('span', {}, h('i', { class: 'mg-act' }), 'Invoiced (in Pronto)'), h('span', {}, h('i', { class: 'mg-acc' }), 'Claimed, invoice not in yet (accrued)'),
          h('span', {}, h('i', { class: 'mg-fcd' }), 'This month as forecast'), h('span', {}, h('i', { class: 'mg-acd' }), 'This month claimed / approved'), h('span', {}, h('i', { class: 'mg-fc' }), 'Your forecast of future claims (type to change)')));
      if (g.length > 1) ol.mount(sheetTw, sheetTbl);
    }

    function claimsTab() {
      const cl = s.claims || [];
      const pending = cl.filter((c) => c.status === 'received');
      pane.append(h('div', { class: 'grid g4', style: { marginBottom: '12px' } },
        kpi('Contract value', fmt.money(s.contract_value), `Retention ${fmt.pct(s.retention_pct, 1)}`), kpi('Claimed (effective)', fmt.money(s.claimed_gross), `${fmt.pct(s.contract_value ? s.claimed_gross / s.contract_value : 0, 0)} of contract`, 't2'),
        kpi('Retention held', fmt.money(s.claimed_retention), '', 't3'), kpi('Still to claim', fmt.money(s.to_claim), s.node_id ? 'Flows to the forecast for later months' : 'Link a CBS line to feed cost control', 't4')));
      if (!s.node_id) pane.append(h('div', { class: 'note warn', style: { marginBottom: '10px' } }, 'This subcontract is not linked to a CBS line yet, so its claims cannot update cost control. Link it on the Schedule and terms tab.'));
      pane.append(h('div', { class: 'card' }, h('div', { class: 'ch' }, h('h2', {}, 'Monthly claims'), h('span', { class: 'sp' }), pending.length ? badge(`${pending.length} awaiting approval`, 'warn') : null, h('button', { class: 'btn', onclick: newClaim }, '+ New claim')),
        cl.length ? table([{ label: 'Claim', f: (c) => c.claim_no }, { label: 'Month', f: (c) => fmt.month(c.month) }, { label: 'Status', f: (c) => badge(stLabel[c.status] || c.status, stTone[c.status]) }, { label: 'Claimed', r: 1, f: (c) => fmt.money(c.claimed) }, { label: 'Approved', r: 1, f: (c) => c.approved_lines ? fmt.money(c.approved) : h('span', { class: 'muted' }, 'not yet') },
          { label: 'Counts as', r: 1, f: (c) => h('b', {}, fmt.money(c.effective)) }, { label: 'Retention', r: 1, f: (c) => fmt.money(c.retention) }, { label: 'Net', r: 1, f: (c) => fmt.money(c.net) }, { label: 'Certificate', f: (c) => c.cert_no ? badge(c.cert_no, 'good') : (c.status === 'approved' || c.status === 'paid' ? h('span', { class: 'muted' }, 'not issued') : '') }, { label: 'Invoice ref', f: (c) => c.inv_ref || '' },
          { label: 'Cost control', f: (c) => c.status === 'draft' ? h('span', { class: 'muted' }, 'not counted') : c.status === 'paid' ? h('span', { class: 'muted' }, 'in Pronto') : h('span', { class: 'warn' }, `accrual, ${c.basis}`) }], cl, { onRow: (c) => openClaim(c.id) })
          : empty('No claims yet', 'Create the first monthly claim: lines are filled from the schedule.')));
    }

    function newClaim() {
      const mo = h('input', { type: 'month', value: M }); const no = h('input', { type: 'text', placeholder: 'auto' });
      modal({ title: 'New subcontractor claim', body: h('div', { class: 'grid' }, field('Claim month', mo, 'The month the work was done'), field('Claim number', no)), actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} }, { label: 'Create', onClick: async () => { const r = await api.post(p(`/subcontracts/${s.id}/claims`), { month: mo.value, claim_no: no.value || undefined }); await reopen2(r.id); } }] });
    }
    async function reopen2(cid) { sessionStorage.setItem('reopenSub', JSON.stringify({ id: s.id, tab: 'claims', claim: cid })); d.close(); await render(); }

    async function openClaim(cid) {
      const c = await api.get(p(`/subcontracts/${s.id}/claims/${cid}`));
      const status = select(Object.entries(stLabel), c.status); const no = h('input', { type: 'text', value: c.claim_no || '' }); const mo = h('input', { type: 'month', value: c.month }); const inv = h('input', { type: 'text', value: c.inv_ref || '', placeholder: 'Subcontractor invoice number' });
      const rcv = h('input', { type: 'date', value: c.received_date || '' }); const apd = h('input', { type: 'date', value: c.approved_date || '' }); const rel = h('input', { type: 'number', step: '0.01', value: c.retention_release || '' });
      const certNote = h('textarea', { rows: 3, style: { width: '100%' }, placeholder: 'Notes for the subcontractor on the payment certificate: why the approved amount differs from the claimed amount, items held back, what is needed to release them' }); certNote.value = c.cert_note || '';
      const inputs = {}; const tbody = h('tbody'); const eff = h('div'); const hasLines = c.lines.length > 0;
      c.lines.forEach((l) => {
        const cl = h('input', { type: 'number', step: '0.01', value: l.claimed || '', style: { width: '116px' }, oninput: recalc }); const ap = h('input', { type: 'number', step: '0.01', value: l.approved ?? '', style: { width: '116px' }, oninput: recalc }); const rs = h('input', { type: 'text', value: l.note || '', placeholder: 'Reason, if approved differs', style: { width: '190px' } }); inputs[l.item_id] = { cl, ap, rs };
        const pc = (l.type === 'Price' || l.type === 'Progress') && l.value ? h('input', { type: 'number', step: 'any', placeholder: '%', title: '% complete to date: fills the claim with that share of the line less what was claimed before', style: { width: '64px' },
          onchange: () => { if (pc.value === '') return; cl.value = String(Math.round((num(pc.value) / 100 * l.value - l.prior) * 100) / 100); recalc(); } }) : null;
        tbody.append(h('tr', {}, h('td', {}, l.name), h('td', {}, badge(l.type === 'Price' ? `Price × ${fmt.pct(l.share, 0)}` : l.type)), h('td', { class: 'r num', title: l.type === 'Price' ? `Price ${fmt.money(l.price)} × progress share ${fmt.pct(l.share, 1)}` : '' }, fmt.money(l.value)), h('td', { class: 'in' }, pc || ''), h('td', { class: 'r num' }, fmt.money(l.prior)), h('td', { class: 'r num muted' }, fmt.money(l.planned_this)), h('td', { class: 'r' }, h('a', { style: { cursor: 'pointer' }, title: 'Use the scheduled amount', onclick: () => { cl.value = l.suggested || ''; recalc(); } }, fmt.money(l.suggested))), h('td', { class: 'in' }, cl),
          h('td', { class: 'in' }, ap), h('td', {}, h('button', { class: 'btn ghost sm', title: 'Approve as claimed', onclick: () => { ap.value = cl.value; recalc(); } }, '=')), h('td', { class: 'in' }, rs)));
      });
      const pct = c.retention_pct || 0;
      function recalc() {
        const v = Object.values(inputs); const claimed = v.reduce((a, i) => a + num(i.cl.value), 0);
        const effv = v.reduce((a, i) => a + (i.ap.value !== '' ? num(i.ap.value) : num(i.cl.value)), 0); const nAp = v.filter((i) => i.ap.value !== '').length; const held = effv * pct; const net = effv - held + num(rel.value);
        const basis = nAp === v.length && v.length ? 'approved' : nAp ? 'part approved' : 'claimed';
        eff.replaceChildren(h('div', { class: 'grid g4' }, kpi('Claimed', fmt.money(claimed), ''), kpi('Counts as', fmt.money(effv), `Basis: ${basis}`, 't2'), kpi('Retention held', fmt.money(held), fmt.pct(pct, 1), 't3'), kpi('Net payable', fmt.money(net), '', 't4')),
          h('div', { class: 'note', style: { marginTop: '10px' } }, s.node_id ? `On save: ${fmt.month(mo.value)} carries an accrual of ${fmt.money(net)} on ${s.node_code} (${basis} amounts) until invoice ${inv.value || '[reference]'} lands in Pronto, when it reverses itself. The unclaimed schedule stays in the forecast for later months.` : 'Link this subcontract to a CBS line so the claim updates cost control.'));
      }
      rel.oninput = recalc; mo.onchange = recalc; inv.oninput = recalc; recalc();
      const gather = (extra = {}) => ({ claim_no: no.value, month: mo.value, status: status.value, inv_ref: inv.value, received_date: rcv.value || null, approved_date: apd.value || null, retention_release: num(rel.value), today: todayISO(),
        lines: Object.entries(inputs).map(([item_id, i]) => ({ item_id, claimed: num(i.cl.value), approved: i.ap.value === '' ? null : num(i.ap.value), note: i.rs.value || null })), cert_note: certNote.value || null, ...extra });
      const done = async (msg) => { toast(msg); sessionStorage.setItem('reopenSub', JSON.stringify({ id: s.id, tab: 'claims' })); d.close(); await render(); };
      modal({ title: `${c.claim_no}: ${fmt.month(c.month)}`, size: 'xl', body: h('div', { class: 'grid' },
        h('div', { class: 'grid g4' }, field('Claim number', no), field('Claim month', mo), field('Status', status), field('Invoice reference', inv, 'Reverses the accrual when it lands in Pronto')),
        h('div', { class: 'grid g4' }, field('Received', rcv), field('Approved', apd), field('Retention released this claim', rel), h('span')),
        field('Notes on the payment certificate', certNote, 'Printed on the certificate, with each line\'s reason where the approved amount differs'),
        hasLines ? h('div', { class: 'tw', style: { maxHeight: '40vh' } }, h('table', { class: 't' }, h('thead', {}, h('tr', {}, ['Schedule line', 'Type', 'Claimable', '% complete', 'Previously claimed', 'Scheduled this month', 'Suggested', 'Claimed', 'Approved', '', 'Reason (on the certificate)'].map((x, i) => h('th', { class: i === 2 || (i >= 4 && i <= 6) ? 'r' : '' }, x)))), tbody))
          : h('div', { class: 'note' }, 'This claim was recorded as a lump amount without lines. Gross ' + fmt.money(c.gross) + '. Re-create it from the schedule to approve line by line.'), eff),
        actions: [{ label: 'Delete', kind: 'danger', onClick: async () => { if (!(await confirmBox('Delete this claim?', 'Delete', true))) return false; await api.del(p(`/subcontracts/${s.id}/claims/${cid}`)); await done('Claim deleted'); } },
          { label: 'Approve all as claimed', kind: 'ghost', close: false, onClick: async () => { await api.put(p(`/subcontracts/${s.id}/claims/${cid}`), gather({ action: 'approve_all' })); await done('Approved as claimed: its payment certificate is issued (open the claim to download it)'); } },
          { label: 'Approve a total...', kind: 'ghost', close: false, onClick: async () => { const t = prompt('Approve a total amount (shared across the lines in proportion to what was claimed):', String(Object.values(inputs).reduce((a, i) => a + num(i.cl.value), 0))); if (t === null) return false; await api.put(p(`/subcontracts/${s.id}/claims/${cid}`), gather({ action: 'approve_total', amount: num(t) })); await done('Approved total shared across the lines'); } },
          ...(c.status === 'approved' || c.status === 'paid' || c.cert_no ? [{ label: c.cert_no ? `Payment certificate ${c.cert_no}` : 'Issue payment certificate', kind: 'ghost', close: false, onClick: async () => {
            if (!c.supplier?.abn || !c.supplier?.address) toast('The subcontractor\'s ABN or address is not in the company directory (Stakeholders > Companies): the certificate will show it as not recorded.', 'warn');
            let cert = { cert_no: c.cert_no };
            if (!cert.cert_no) { cert = await api.post(p(`/subcontracts/${s.id}/claims/${cid}/certificate`), { today: todayISO() }); toast(`Payment certificate ${cert.cert_no} issued`); }
            pdfNameDialog({ title: 'Download the payment certificate', suggest: `${state.project.number || state.project.code || ''} ${s.name} Payment certificate ${cert.cert_no}`, url: p(`/subcontracts/${s.id}/claims/${cid}/certificate.pdf`), hint: 'Approving a claim issues its certificate. The PDF carries the EPEC logo, the subcontractor and subcontract details and the amount payable.' });
          } }] : []),
          { label: 'Close', kind: 'ghost', onClick: () => {} }, { label: 'Save claim', onClick: async () => { await api.put(p(`/subcontracts/${s.id}/claims/${cid}`), gather()); await done('Claim saved'); } }] });
    }
    if (params.__claim) openClaim(params.__claim);
    d.__openClaim = openClaim;
    return d;
  }

  // Excel payment schedule: preview what the file would change, then apply it
  function uploadSchedule() {
    const file = h('input', { type: 'file', accept: '.xlsx,.xlsm' }); const out = h('div'); const pickers = {};
    const stateBadge = (k, v) => badge(`${k}: ${v === 'pronto' ? 'in Pronto' : v === 'pending' ? 'to be matched' : 'none'}`, v === 'pronto' ? 'good' : v === 'pending' ? 'warn' : 'bad');
    async function show(x) {
      out.replaceChildren();
      for (const r of x.subcontracts) {
        const box = h('div'); const card = h('div', { class: 'card', style: { marginTop: '8px' } },
          h('div', { class: 'ch' }, h('b', {}, r.name), h('span', { class: 'sp' }), r.skipped ? badge('skipped', 'warn') : badge(r.action === 'created' ? (x.applied ? 'created' : 'will be created') : (x.applied ? 'updated' : 'will be updated'), r.action === 'created' ? 'good' : 'navy'),
            r.link ? stateBadge('Supplier', r.link.supplier) : null, r.link ? stateBadge('PO', r.link.po) : null),
          r.skipped ? null : h('div', { class: 'small' }, `Sheet "${r.sheet}". Contract ${fmt.money(r.contract_value)}; progress share on the price table ${fmt.pct(r.share, 1)}. `,
            `Lines: ${r.lines_new} new, ${r.lines_updated} updated. Claims: ${r.claims_new} new, ${r.claims_updated} updated. Planned claims: ${r.plan_cells} cells. Planned approval (forecast): ${r.forecast_cells} cells.`),
          box, ...(r.notes || []).map((n) => h('div', { class: 'note warn', style: { marginTop: '6px' } }, n)));
        out.append(card);
        if (r.skipped || x.applied) continue;
        // link to a known supplier and PO, or keep it as new (to be matched when the Pronto data comes through)
        const prev = pickers[r.sheet]?.value();
        const pk = await supplierPicker(prev || r.link || {}); pickers[r.sheet] = pk;
        box.append(h('div', { style: { marginTop: '8px' } }, h('div', { class: 'small', style: { fontWeight: 700, marginBottom: '4px' } }, 'Supplier and purchase order'), pk.el,
          (r.link?.suggest || []).length ? h('div', { class: 'small', style: { marginTop: '4px' } }, 'Closest Pronto suppliers: ', ...r.link.suggest.map((g) => h('a', { style: { cursor: 'pointer', marginRight: '10px' }, onclick: async () => {
            const keep = pickers[r.sheet].value(); const pk2 = await supplierPicker({ ...keep, supplier_code: g.code, supplier_name: g.name, po_no: null }); pickers[r.sheet] = pk2; box.replaceChildren(h('div', { style: { marginTop: '8px' } }, pk2.el)); } }, `${g.name} (${g.code})`))) : null));
      }
    }
    const links = () => JSON.stringify(Object.fromEntries(Object.entries(pickers).map(([k, v]) => [k, v.value()])));
    modal({ title: 'Upload a subcontract payment schedule', size: 'xl', body: h('div', { class: 'grid' },
      h('div', { class: 'note' }, 'Use the template from this page (one sheet per subcontract). At the start of a job it loads the payment terms, price table and planned claims; mid-project it also loads the claims and approvals to date. Preview first: link each subcontract to a known Pronto supplier and purchase order, or keep it as a new supplier / PO to be matched when the Pronto data comes through. Nothing is saved until you apply it.'),
      field('Payment schedule file', file), out),
    actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} },
      { label: 'Preview', kind: 'ghost', close: false, onClick: async () => { if (!file.files[0]) throw new Error('Choose the file'); await show(await api.upload(p('/subcontracts/upload'), file.files[0], { apply: '0', links: links() })); return false; } },
      { label: 'Apply', onClick: async () => { if (!file.files[0]) throw new Error('Choose the file'); if (!Object.keys(pickers).length) await show(await api.upload(p('/subcontracts/upload'), file.files[0], { apply: '0' }));
        const x = await api.upload(p('/subcontracts/upload'), file.files[0], { apply: '1', links: links() }); toast(`Payment schedule loaded: ${x.subcontracts.filter((r) => !r.skipped).length} subcontract(s)`); await render(); } }] });
  }

  const re = sessionStorage.getItem('reopenSub');
  if (re) { sessionStorage.removeItem('reopenSub'); const o = JSON.parse(re); const sub = list.find((x) => x.id === o.id); if (sub) { const d = await openSub(sub, o.tab || 'claims'); if (o.claim) d.__openClaim(o.claim); } }
}
