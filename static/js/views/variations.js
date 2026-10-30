import { h, clear, fmt, modal, toast, field, select, table, num, confirmBox, badge, tabs, empty, drawer, todayISO } from '../ui.js';
import { api, state, p, loadRows } from '../api.js';
import { pickNode } from '../scope.js';
import { go, render } from '../app.js';

const csTone = { Approved: 'good', Denied: 'bad', Withdrawn: '', Pending: 'warn', 'Under Review': 'warn', 'In Discussion': 'warn' };

export default async function variations(root, params) {
  const list = await api.get(p('/variations'));
  const rows = await loadRows();
  let filter = { q: '', state: 'open' };
  const open = list.filter((v) => !v.closed);
  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, 'Variations'), h('div', { class: 'sub' }, 'Two negotiations run side by side: the client\'s view of the price and EPEC\'s own position. A variation is recognised, and its cost lands in the allowance, once the client has Approved and EPEC has Agreed.')), h('div', { class: 'sp' }),
    h('button', { class: 'btn ghost', title: 'The register in Excel: every variation, plus empty rows to add more', onclick: () => window.open(p('/variations/template.xlsx')) }, 'Download register'),
    h('button', { class: 'btn ghost', onclick: () => uploadRegister() }, 'Upload register...'),
    h('button', { class: 'btn', onclick: create }, '+ New variation')));
  // variations in the uploaded contract that the register does not hold yet: one click makes an entry for each, ready for its cost build-up
  const miss = (await api.get(p('/variations/from-schedule')).catch(() => ({ missing: 0 }))).missing;
  if (miss) root.append(h('div', { class: 'note', style: { marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '12px' } },
    h('span', { style: { flex: 1 } }, `${miss} variation${miss === 1 ? '' : 's'} in the contract ${miss === 1 ? 'has' : 'have'} no register entry yet. Create them to add the cost build-up, risk and markup, and to agree each one with the client. Revenue does not change.`),
    h('button', { class: 'btn', onclick: async () => { const r = await api.post(p('/variations/from-schedule')); toast(`${r.created} register entr${r.created === 1 ? 'y' : 'ies'} created. Open one to add its cost build-up.`); await render(); } }, 'Create register entries')));
  const sum = (f) => list.filter(f).reduce((a, v) => a + (v.value || 0), 0);
  root.append(h('div', { class: 'grid g6', style: { marginBottom: '14px' } },
    kpi('Open', String(open.length), fmt.m(sum((v) => !v.closed)) + ' in play'), kpi('Awaiting client', String(list.filter((v) => ['Pending', 'Under Review', 'In Discussion'].includes(v.client_status) && !v.closed).length), '', 't2'),
    kpi('Approved', fmt.money(sum((v) => v.client_status === 'Approved')), `${list.filter((v) => v.client_status === 'Approved').length} variations`, 't3'), kpi('Recognised', fmt.money(sum((v) => v.recognised)), 'Approved and agreed', 't4'), kpi('Official', fmt.money(sum((v) => v.official)), 'No deed outstanding', 't5'), kpi('Denied / withdrawn', String(list.filter((v) => ['Denied', 'Withdrawn'].includes(v.client_status)).length), '', 't6')));
  const out = h('div'); const q = h('input', { type: 'search', placeholder: 'Search variations...', style: { width: '240px' }, oninput: () => { filter.q = q.value.toLowerCase(); draw(); } });
  const st = select([['open', 'Open only'], ['all', 'All'], ['closed', 'Closed only']], 'open', { onchange: (e) => { filter.state = e.target.value; draw(); } });
  root.append(h('div', { class: 'row', style: { marginBottom: '10px' } }, q, st), out);
  function draw() {
    const l = list.filter((v) => (filter.state === 'all' || (filter.state === 'open') === !v.closed) && (!filter.q || `${v.ref} ${v.title} ${v.stage}`.toLowerCase().includes(filter.q)));
    clear(out).append(l.length ? table([{ label: 'Ref', f: (v) => h('b', {}, v.ref) }, { label: 'Title', f: (v) => v.title }, { label: 'Stage', f: (v) => v.stage || '' }, { label: 'Cost', r: 1, title: 'Cost of the priced lines', f: (v) => v.calc && v.calc.cost ? fmt.money(v.calc.cost) : (v.value ? badge('Build-up to be added', 'warn') : '') }, { label: 'Risk', r: 1, f: (v) => v.calc && v.calc.risk ? fmt.money(v.calc.risk) : '' }, { label: 'Calculated price', r: 1, f: (v) => v.calc && v.calc.price ? fmt.money(v.calc.price) : '' }, { label: 'Value', r: 1, title: 'Current revision value (revenue once recognised)', f: (v) => h('b', {}, fmt.money(v.value)) }, { label: 'Margin', r: 1, f: (v) => v.calc && v.calc.price ? fmt.pct(v.calc.margin) : '' }, { label: 'Client status', f: (v) => badge(v.client_status, csTone[v.client_status]) }, { label: 'EPEC status', f: (v) => badge(v.epec_status, v.epec_status === 'Agreed' ? 'good' : v.epec_status === 'In Dispute' ? 'bad' : '') },
      { label: 'Contract change', f: (v) => v.contract_change === 'Yes' ? `Yes: ${v.contract_status}` : 'No' }, { label: 'Recognised', f: (v) => v.recognised ? badge('Yes', 'good') : badge('No') }, { label: 'Official', f: (v) => v.official ? badge('Yes', 'good') : badge('No') }, { label: 'Pronto', f: (v) => v.pronto_ref || '' }], l, { onRow: (v) => openVar(v.id) })
      : empty('No variations', 'Raise one with + New variation, or download the register, fill it in and upload it to set up the variations you already have.'));
  }
  draw();
  function kpi(l, v, s = '', c = '') { return h('div', { class: 'kpi ' + c }, h('div', { class: 'l' }, l), h('div', { class: 'v' }, v), s ? h('div', { class: 's' }, s) : null); }

  function create() {
    const stage = h('input', { type: 'text', value: 'EPC', list: 'stg' }); const title = h('input', { type: 'text' }); const ref = h('input', { type: 'text', placeholder: 'auto' }); const by = h('input', { type: 'text', value: state.project.epec_pm || '' }); const val = h('input', { type: 'number', step: '0.01' });
    const dl = h('datalist', { id: 'stg' }, (state.project.settings?.stages || ['Early Works', 'EPC']).map((x) => h('option', { value: x })));
    modal({ title: 'New variation', body: h('div', { class: 'grid' }, dl, h('div', { class: 'grid g2' }, field('Reference', ref, 'Blank numbers it for you'), field('Stage', stage)), field('Title', title), h('div', { class: 'grid g2' }, field('Prepared by', by), field('Initial value (can be built up from lines)', val))),
      actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} }, { label: 'Create', onClick: async () => { if (!title.value) throw new Error('Enter a title'); const r = await api.post(p('/variations'), { ref: ref.value || undefined, stage: stage.value, title: title.value, prepared_by: by.value, value: num(val.value), submission_date: todayISO() }); await openVar(r.id, true); } }] });
  }

  async function openVar(id, fresh = false) {
    const v = await api.get(p(`/variations/${id}`));
    const body = h('div'); const dr = drawer({ title: `${v.ref}: ${v.title}`, sub: `${v.stage || ''} · ${v.recognised ? 'Recognised' : 'Not recognised'}${v.official ? ' · Official' : ''}`, body });
    let tab = fresh ? 'pricing' : 'status'; const pane = h('div'); const tb = h('div');
    const sw = () => { clear(tb).append(tabs([['status', 'Status'], ['pricing', 'Cost and price build-up'], ['funding', 'Funding the CBS'], ['history', 'History']], tab, (k) => { tab = k; sw(); })); clear(pane); ({ status: statusTab, pricing: pricingTab, funding: fundingTab, history: historyTab })[tab](); };
    body.append(tb, pane); sw();
    const save = async (patch) => { await api.put(p(`/variations/${id}`), { ...patch, today: todayISO(), who: state.project.epec_pm }); toast('Saved'); sessionStorage.setItem('reopenVar', id); dr.close(); await render(); };
    const openVarLater = (i, t) => { sessionStorage.setItem('reopenVar', i); };

    function statusTab() {
      const f = { title: h('input', { type: 'text', value: v.title || '' }), stage: h('input', { type: 'text', value: v.stage || '' }), client: select(state.tax.client_status, v.client_status), epec: select(state.tax.epec_status, v.epec_status), cc: select(['No', 'Yes'], v.contract_change), cs: select(state.tax.contract_status, v.contract_status),
        pm: select(Object.entries(state.tax.pricing_models).map(([k, n]) => [k, `${k}: ${n}`]), v.pricing_model), pronto: h('input', { type: 'text', value: v.pronto_ref || '' }), by: h('input', { type: 'text', value: v.prepared_by || '' }), val: h('input', { type: 'number', step: '0.01', value: v.value }), validity: h('input', { type: 'text', value: v.validity || '' }),
        sub: h('input', { type: 'date', value: v.submission_date || '' }), desc: h('textarea', { rows: 4, style: { width: '100%' } }, v.description || ''), closed: h('input', { type: 'checkbox', checked: !!v.closed }), outcome: h('input', { type: 'text', value: v.outcome || '' }) };
      pane.append(h('div', { class: 'note', style: { marginBottom: '12px' } }, 'Client status is the price negotiation as the client sees it. EPEC status is your own position. Recognised = client Approved and EPEC Agreed. Official = recognised and either no contract change is needed or the deed is Executed.'),
        h('div', { class: 'card' }, h('div', { class: 'grid g3' }, field('Title', f.title), field('Stage', f.stage), field('Pricing model', f.pm), field('Client status', f.client), field('EPEC status', f.epec), field('Current value', f.val, 'Use the calculated price on the Pricing tab if you build it up'),
          field('Contract change needed?', f.cc), field('Contract status', f.cs), field('Pronto variation no.', f.pronto), field('Prepared by', f.by), field('Validity', f.validity), field('Submission date', f.sub)), h('div', { style: { marginTop: '10px' } }, field('Scope description', f.desc)),
          h('div', { class: 'row', style: { marginTop: '10px' } }, h('label', { class: 'row' }, f.closed, 'Closed (settled or abandoned)'), field('Outcome', f.outcome)),
          h('div', { class: 'row', style: { marginTop: '14px' } }, h('button', { class: 'btn', onclick: () => save({ title: f.title.value, stage: f.stage.value, client_status: f.client.value, epec_status: f.epec.value, contract_change: f.cc.value, contract_status: f.cs.value, pricing_model: f.pm.value, pronto_ref: f.pronto.value, prepared_by: f.by.value, validity: f.validity.value, submission_date: f.sub.value || null, description: f.desc.value, closed: f.closed.checked ? 1 : 0, outcome: f.outcome.value, revs: v.revs.map((r) => ({ ...r, value: r.is_current ? num(f.val.value) : r.value })) }) }, 'Save'),
            h('button', { class: 'btn ghost', onclick: () => window.open(p(`/variations/${id}/proposal`)) }, 'Open proposal (print or PDF)'), h('button', { class: 'btn ghost', onclick: () => window.open(p(`/variations/${id}/proposal?breakdown=0`)) }, 'Proposal without breakdown'),
            h('button', { class: 'btn danger', onclick: async () => { if (await confirmBox('Delete this variation, its revenue item and allowance entries?', 'Delete', true)) { await api.del(p(`/variations/${id}`)); dr.close(); await render(); } } }, 'Delete'))));
      if (v.recognised) pane.append(h('div', { class: 'note', style: { marginTop: '12px' } }, 'Revenue and cost allowance from this variation are live. Cost lines post to the CBS nodes chosen on the Pricing tab.'));
    }

    // ---- cost and price build-up: sections > price items > cost lines (the workbook's Variation Engine) ----------
    function pricingTab() {
      let seq = 0; const key = () => 'n' + (++seq);
      const items = (v.items || []).map((i) => ({ ...i, k: String(i.id) }));
      const lines = v.lines.map((l) => ({ ...l, pk: String(l.price_id) }));
      if (!items.length) items.push({ k: key(), section: 'Labour', name: '', pricing_type: 'LS', selected: 'Pending', spread: 'none', spread_scope: 'all', carries: 1 });
      const open = new Set(items.map((i) => i.k));
      const level = select([['items', 'Price items only'], ['scope', 'Price items and the scope that makes them up'], ['contributions', 'Each line\'s price, without quantities and rates'], ['full', 'Full detail: quantities, units, rates']], v.detail_level || 'scope');
      const excl = h('textarea', { rows: 2, style: { width: '100%' }, placeholder: 'Exclusions shown on the proposal' }, v.exclusions || '');
      const box = h('div'); const totals = h('div'); const cbsBox = h('div'); const warn = h('div');
      let res = null; const refs = {};
      const pct = (x) => (x === null || x === undefined || x === '' ? '' : +(x * 100).toFixed(4));
      const payload = () => ({ items: items.map((i) => ({ ...i, id: /^\d+$/.test(i.k) ? +i.k : null, key: i.k })), lines: lines.map((l) => ({ ...l, price_id: /^\d+$/.test(l.pk) ? +l.pk : null, price_key: l.pk })) });
      let timer = null;
      const recalc = () => { clearTimeout(timer); timer = setTimeout(async () => { res = await api.post(p(`/variations/${id}/preview`), payload()); paint(); }, 200); };
      const typ = Object.keys(state.tax.pricing_models);
      function draw() {
        const tb = h('tbody');
        const secs = [...new Set(items.map((i) => i.section || 'Works'))];
        secs.forEach((sec) => {
          tb.append(h('tr', { class: 'gp' }, h('td', { colspan: 17 }, h('b', {}, sec))));
          items.filter((i) => (i.section || 'Works') === sec).forEach((it) => {
            const r = (refs[it.k] = { lines: {} });
            const I = (o, k, w, type = 'text', pc = false) => h('input', { type, step: 'any', value: pc ? pct(o[k]) : (o[k] ?? ''), style: { width: w + 'px' }, onchange: (e) => { const x = e.target.value; o[k] = type === 'number' ? (x === '' ? null : (pc ? num(x) / 100 : num(x))) : x; if (k === 'section') draw(); recalc(); } });
            const S = (o, k, opts) => select(opts, o[k] ?? opts[0][0], { onchange: (e) => { o[k] = e.target.value; recalc(); } });
            const isOpen = open.has(it.k);
            r.price = h('td', { class: 'r num', style: { fontWeight: 700 } }); r.cost = h('td', { class: 'r num' }); r.recv = h('td', { class: 'r num small' });
            tb.append(h('tr', { class: 'par' },
              h('td', {}, h('span', { class: 'tog', style: { cursor: 'pointer' }, onclick: () => { isOpen ? open.delete(it.k) : open.add(it.k); draw(); } }, isOpen ? '▾' : '▸')),
              h('td', { colspan: 2 }, I(it, 'name', 230), h('div', { class: 'small muted' }, 'Section ', I(it, 'section', 110))),
              h('td', { colspan: 2 }, S(it, 'pricing_type', typ.map((t) => [t, t])), ' ', select([['m', 'Mandatory'], ['Pending', 'Option: pending'], ['Yes', 'Option: selected'], ['No', 'Option: not taken']], it.optional ? (it.selected || 'Pending') : 'm', { onchange: (e) => { it.optional = e.target.value === 'm' ? 0 : 1; it.selected = e.target.value === 'm' ? 'Pending' : e.target.value; recalc(); } })),
              h('td', { colspan: 3 }, h('span', { class: 'small muted' }, 'Client sees '), S(it, 'detail', [['', '(as the variation)'], ['items', 'price only'], ['scope', 'scope'], ['contributions', 'contributions'], ['full', 'full']])),
              h('td', { colspan: 4 }, h('span', { class: 'small muted' }, 'Spread '), S(it, 'spread', [['none', 'no'], ['uniform', 'evenly over the carriers'], ['proportional', 'in proportion to their price']]), ' ', S(it, 'spread_scope', [['all', 'all sections'], ['section', 'own section']]),
                h('label', { class: 'small', style: { marginLeft: '6px' }, title: 'This item takes a share of other items’ spread' }, h('input', { type: 'checkbox', checked: it.carries !== 0, onchange: (e) => { it.carries = e.target.checked ? 1 : 0; recalc(); } }), ' carries')),
              r.cost, r.recv, h('td', {}), r.price,
              h('td', { class: 'nowrap' }, h('button', { class: 'btn ghost sm', title: 'Add a cost line', onclick: () => { lines.push({ pk: it.k, description: '', unit: 'ea', qty: 1, rate: 0, risk_pct: state.project.default_risk_pct ?? 0.07, markup_pct: 0.16 }); open.add(it.k); draw(); recalc(); } }, '+ line'),
                h('button', { class: 'btn danger sm', onclick: async () => { if (lines.some((l) => l.pk === it.k) && !(await confirmBox('Remove this price item and its cost lines?', 'Remove', true))) return; items.splice(items.indexOf(it), 1); for (let j = lines.length - 1; j >= 0; j--) if (lines[j].pk === it.k) lines.splice(j, 1); draw(); recalc(); } }, '×'))));
            if (!isOpen) return;
            lines.filter((l) => l.pk === it.k).forEach((l) => {
              const lr = (r.lines[lines.indexOf(l)] = { cost: h('td', { class: 'r num' }), price: h('td', { class: 'r num' }), qty: h('span', { class: 'muted small' }) });
              const nodeBtn = h('button', { class: 'btn ghost sm', onclick: () => pickNode({ title: 'Which CBS does this cost go to?', kinds: ['group', 'line', 'pot'], onPick: (n) => { l.node_id = n.node_id; l.node_code = n.code; draw(); recalc(); } }) }, l.node_code || l.category || 'CBS...');
              tb.append(h('tr', {}, h('td', {}), h('td', { class: 'in' }, I(l, 'description', 190)), h('td', {}, nodeBtn), h('td', { class: 'in' }, I(l, 'unit', 44)),
                h('td', { class: 'in' }, I(l, 'item_count', 40, 'number')), h('td', { class: 'in' }, I(l, 'hrs_day', 40, 'number')), h('td', { class: 'in' }, I(l, 'days_wk', 40, 'number')), h('td', { class: 'in' }, I(l, 'wks', 40, 'number')),
                h('td', { class: 'in', title: 'Quantity; with hours/days/weeks filled in, extra quantity added to that time' }, I(l, l.hrs_day || l.days_wk || l.wks ? 'extra_qty' : 'qty', 56, 'number'), ' ', lr.qty),
                h('td', { class: 'in' }, I(l, 'rate', 74, 'number')), h('td', { class: 'in' }, I(l, 'risk_pct', 44, 'number', true)), h('td', { class: 'in' }, I(l, 'markup_pct', 44, 'number', true)),
                lr.cost, h('td', { class: 'in', title: 'Contract (sell) rate: overrides the price' }, I(l, 'contract_rate', 66, 'number')), lr.price,
                h('td', {}, h('button', { class: 'btn danger sm', onclick: () => { lines.splice(lines.indexOf(l), 1); draw(); recalc(); } }, '×'))));
            });
          });
        });
        clear(box).append(h('div', { class: 'tw', style: { maxHeight: '58vh' } }, h('table', { class: 't' },
          h('thead', {}, h('tr', {}, ['', 'Description', 'CBS', 'Unit', 'No.', 'Hrs/d', 'Days/wk', 'Wks', 'Qty', 'Cost rate', 'Risk %', 'Markup %', 'Cost', 'Sell rate', 'Price', ''].map((x, i) => h('th', { class: [12, 14].includes(i) ? 'r' : '' }, x)))), tb)));
        paint();
      }
      function paint() {
        if (!res) return;
        res.items.forEach((it) => {
          const r = refs[String(it.id)]; if (!r) return;
          r.cost.textContent = fmt.money(it.cost); r.price.textContent = it.spread_out ? 'spread' : fmt.money(it.price);
          r.recv.textContent = it.received ? `+${fmt.money(it.received)} spread` : '';
        });
        // line figures in order of appearance per item
        res.items.forEach((it) => { const ls = lines.filter((l) => l.pk === String(it.id)); it.lines.forEach((c, j) => { const lr = refs[String(it.id)]?.lines[lines.indexOf(ls[j])]; if (lr) { lr.cost.textContent = fmt.money(c.cost); lr.price.textContent = fmt.money(c.price); lr.qty.textContent = `= ${(+c.qty).toLocaleString()}`; } }); });
        const t = res.total;
        totals.replaceChildren(h('div', { class: 'grid g6' }, kpi('Cost', fmt.money(t.cost)), kpi('Risk', fmt.money(t.risk), 'Posts to the allowance with the cost'), kpi('Allowance', fmt.money(t.allowance), 'Cost + risk', 't2'),
          kpi('Profit', fmt.money(t.profit), t.margin === null ? '' : `Margin ${fmt.pct(t.margin)}`, 't3'), kpi('Price', fmt.money(t.price), `Base ${fmt.money(t.base)}${t.provisional ? ` · provisional ${fmt.money(t.provisional)}` : ''}`, 't4'), kpi('Options not taken', fmt.money(t.optional), 'Not in the price', 't5')));
        warn.replaceChildren(...res.warnings.map((w) => h('div', { class: 'note warn', style: { marginTop: '6px' } }, w)));
        cbsBox.replaceChildren(table([{ label: 'CBS', f: (d) => d.node_code || d.code || d.category || h('span', { class: 'warn' }, 'no CBS chosen') }, { label: 'Cost', r: 1, f: (d) => fmt.money(d.cost) }, { label: 'Risk', r: 1, f: (d) => fmt.money(d.risk) }, { label: 'Allowance', r: 1, f: (d) => fmt.money(d.cost + d.risk) }, { label: 'Revenue (price incl. spread)', r: 1, f: (d) => fmt.money(d.revenue) }],
          res.by_node.map((d) => ({ ...d, node_code: (lines.find((l) => l.node_id === d.node_id) || {}).node_code }))));
      }
      pane.append(h('div', { class: 'note', style: { marginBottom: '10px' } }, 'Price items (what the client prices) are built from cost lines. Qty = No. × (hrs/day × days/wk × weeks + extra), or No. × Qty. Risk and markup are a % of cost. A sell rate overrides the price. A spread item’s price is shared over the items that carry it; its cost and risk stay on its own CBS.'),
        h('div', { class: 'grid g2', style: { marginBottom: '10px' } }, field('What the client sees on the proposal', level, 'A price item can show more or less detail itself'), field('Exclusions', excl)),
        box, h('div', { class: 'row', style: { margin: '8px 0' } }, h('button', { class: 'btn sm', onclick: () => { const k = key(); const last = items[items.length - 1]; items.push({ k, section: last?.section || 'Labour', name: '', pricing_type: 'LS', selected: 'Pending', spread: 'none', spread_scope: 'all', carries: 1 }); open.add(k); draw(); recalc(); } }, '+ Price item'), ratesSel()),
        warn, h('div', { style: { margin: '12px 0' } }, totals), h('div', { class: 'card', style: { marginBottom: '12px' } }, h('h2', {}, 'Cost and revenue by CBS'), cbsBox),
        h('div', { class: 'row' }, h('button', { class: 'btn', onclick: () => saveBuild(true) }, 'Save and use the calculated price'), h('button', { class: 'btn ghost', onclick: () => saveBuild(false) }, 'Save without changing the value'),
          h('button', { class: 'btn ghost', onclick: () => window.open(p(`/variations/${id}/proposal`)) }, 'Open proposal'), h('span', { class: 'muted small' }, 'Using the calculated price updates the current revision.')));
      function ratesSel() {
        const sel = h('select', {}, h('option', { value: '' }, 'Add a labour line from the rate card...'));
        api.get(p('/ratecard')).then((rc) => rc.forEach((r) => sel.append(h('option', { value: JSON.stringify(r) }, `${r.role} (${r.work_rate_code || ''}) cost ${r.cost_rate}`))));
        sel.onchange = () => { if (!sel.value) return; const r = JSON.parse(sel.value); const it = items.find((i) => i.section === 'Labour') || items[items.length - 1];
          lines.push({ pk: it.k, description: r.role, role: r.role, unit: 'hour', item_count: 1, hrs_day: 7.6, days_wk: 5, wks: 1, rate: r.cost_rate, risk_pct: state.project.default_risk_pct ?? 0.07, markup_pct: 0.16, category: 'PL03' }); open.add(it.k); sel.value = ''; draw(); recalc(); };
        return sel;
      }
      async function saveBuild(useCalc) {
        const pl = payload();
        const b = await api.post(p(`/variations/${id}/preview`), pl);
        const cur = v.revs.find((r) => r.is_current) || v.revs[v.revs.length - 1];
        await save({ ...pl, detail_level: level.value, exclusions: excl.value, ...(useCalc && b.total.price ? { revs: v.revs.map((r) => ({ ...r, value: r === cur ? Math.round(b.total.price * 100) / 100 : r.value })) } : {}) });
      }
      draw(); recalc();
    }

    // ---- funding: top up the CBS lines the costs are on, or track the variation on its own copy of the CBS ----------
    async function fundingTab() {
      const f = await api.get(p(`/variations/${id}/funding`));
      const mode = select([['topup', 'Top up the existing CBS lines (absorb the new funds)'], ['separate', 'Track this variation on its own CBS (a copy of the CBS)']], f.funding, { onchange: async (e) => { await api.put(p(`/variations/${id}/funding`), { funding: e.target.value }); clear(pane); fundingTab(); } });
      pane.append(h('div', { class: 'note', style: { marginBottom: '10px' } }, f.recognised ? 'This variation is recognised: its cost and risk are in the allowance as shown below.' : 'Not recognised yet. Once the client has Approved and EPEC has Agreed, the cost and risk below are added to the allowance where shown.'),
        h('div', { class: 'card', style: { marginBottom: '12px' } }, field('How the new funds are added to the CBS', mode),
          h('div', { class: 'small muted', style: { marginTop: '6px' } }, f.funding === 'separate'
            ? 'Copy the CBS groups or lines the variation uses: the copies sit next to the originals, with the same categories and resources. Funds go to the copies; Pronto cost coded to this variation (its Pronto ref or variation number) lands on the copies, other cost stays on the originals. Lines whose CBS was not copied still top up the original.'
            : 'The cost and risk of each line go onto the CBS line or group chosen on the build-up, and later cost keeps landing there.'),
          f.funding === 'separate' ? h('div', { class: 'row', style: { marginTop: '10px' } },
            h('button', { class: 'btn', title: 'Only the CBS lines (or groups) the cost lines of this variation point to: no empty placeholders', onclick: async () => {
              const r = await api.post(p(`/variations/${id}/duplicate-cbs`), { mode: 'used' }); toast(`${r.created} CBS item(s) copied for ${v.ref}`); clear(pane); fundingTab(); } }, 'Copy only the CBS lines this variation uses'),
            h('button', { class: 'btn ghost', title: 'A complete copy of a CBS group and everything under it (empty lines included)', onclick: () => pickNode({ title: 'Copy which CBS group (with everything under it) for this variation?', kinds: ['group', 'line', 'pot'], onPick: async (n) => {
              const r = await api.post(p(`/variations/${id}/duplicate-cbs`), { node_ids: [n.node_id] }); toast(`${r.created} CBS item(s) copied for ${v.ref}`); clear(pane); fundingTab(); } }) }, 'Copy a whole CBS group...')) : null),
        h('div', { class: 'card' }, h('h2', {}, 'Where the funds go'), f.rows.length ? table([{ label: 'CBS on the build-up', f: (r) => h('span', {}, h('span', { class: 'mono' }, r.code), ' ', r.name) }, { label: 'Cost', r: 1, f: (r) => fmt.money(r.cost) }, { label: 'Risk', r: 1, f: (r) => fmt.money(r.risk) }, { label: 'Revenue', r: 1, f: (r) => fmt.money(r.revenue) },
          { label: 'Funds go to', f: (r) => r.target_code ? h('span', {}, h('span', { class: 'mono' }, r.target_code), ' ', r.target_name, r.copied ? badge('variation copy', 'navy') : null) : h('span', { class: 'warn' }, 'choose a CBS on the build-up') }], f.rows) : empty('No cost lines yet', 'Build the variation up on the Cost and price build-up tab.')),
        ...(f.copies.length ? [h('div', { class: 'card', style: { marginTop: '12px' } }, h('h2', {}, `CBS copies for ${v.ref}`), table([{ label: 'Code', f: (c) => h('span', { class: 'mono' }, c.code) }, { label: 'Name', f: (c) => c.name }, { label: 'Kind', f: (c) => c.kind }], f.copies))] : []));
    }

    function historyTab() {
      const rv = h('div', { class: 'card', style: { marginBottom: '12px' } }, h('div', { class: 'ch' }, h('h2', {}, 'Revisions'), h('span', { class: 'sp' }), h('button', { class: 'btn sm', onclick: () => addRev() }, '+ New revision')), table([{ label: 'Rev', f: (r) => r.rev }, { label: 'Date', f: (r) => fmt.date(r.date) }, { label: 'Value', r: 1, f: (r) => fmt.money(r.value) }, { label: 'Note', f: (r) => r.note || '' }, { label: 'Current', f: (r) => r.is_current ? badge('Current', 'good') : '' }], v.revs));
      function addRev() { const val = h('input', { type: 'number', step: '0.01', value: v.value }); const note = h('input', { type: 'text' }); modal({ title: 'New revision', body: h('div', { class: 'grid' }, field('Value', val), field('What changed', note)), actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} }, { label: 'Add', onClick: async () => { const revs = v.revs.map((r) => ({ ...r, is_current: 0 })); revs.push({ rev: (revs[revs.length - 1]?.rev ?? -1) + 1, date: todayISO(), value: num(val.value), note: note.value, is_current: 1 }); await api.put(p(`/variations/${id}`), { revs }); dr.close(); await render(); } }] }); }
      const note = h('input', { type: 'text', placeholder: 'Add a meeting note or comment...', style: { width: '100%' } });
      pane.append(rv, h('div', { class: 'card' }, h('h2', {}, 'Meetings and status history'), h('div', { class: 'row', style: { margin: '8px 0' } }, note, h('button', { class: 'btn sm', onclick: async () => { if (!note.value) return; await api.post(p(`/variations/${id}/events`), { date: todayISO(), kind: 'meeting', text: note.value, who: state.project.epec_pm }); dr.close(); await openVar(id); } }, 'Add')),
        v.events.length ? table([{ label: 'Date', f: (e) => fmt.date(e.date) }, { label: 'Type', f: (e) => badge(e.kind) }, { label: 'Note', cls: 'wrap', f: (e) => e.text }, { label: 'By', f: (e) => e.who || '' }], [...v.events].reverse()) : h('div', { class: 'muted' }, 'No history yet.')));
    }
  }
  const re = sessionStorage.getItem('reopenVar'); if (re) { sessionStorage.removeItem('reopenVar'); openVar(+re); }
  if (params.open) openVar(+params.open);
}


// Variation register in Excel: preview what the file would change, then apply it
function uploadRegister() {
  const file = h('input', { type: 'file', accept: '.xlsx,.xlsm' }); const out = h('div');
  const show = (x) => out.replaceChildren(h('div', { class: 'card', style: { marginTop: '8px' } },
    h('div', { class: 'small' }, h('b', {}, x.applied ? 'Loaded: ' : 'This file would: '), `add ${x.created.length}, update ${x.updated.length} (${x.revisions} new value revision${x.revisions === 1 ? '' : 's'}), leave ${x.unchanged} as they are.`),
    x.created.length ? h('div', { class: 'small', style: { marginTop: '6px' } }, h('b', {}, 'New: '), x.created.join(' \u00b7 ')) : null,
    x.updated.length ? h('div', { class: 'small', style: { marginTop: '6px' } }, h('b', {}, 'Changed: '), x.updated.join(' \u00b7 ')) : null,
    ...x.notes.map((n) => h('div', { class: 'note warn', style: { marginTop: '6px' } }, n))));
  modal({ title: 'Upload the variation register', size: 'lg', body: h('div', { class: 'grid' },
    h('div', { class: 'note' }, 'Use the register from this page. Rows are matched by Ref: a new Ref adds a variation, a known one is updated, a blank Ref gets the next number. A changed value becomes a new revision and status changes go into each variation\'s history. Variations missing from the file are left as they are. Preview first; nothing is saved until you apply it.'),
    field('Register file', file), out),
  actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} },
    { label: 'Preview', kind: 'ghost', close: false, onClick: async () => { if (!file.files[0]) throw new Error('Choose the file'); show(await api.upload(p('/variations/upload'), file.files[0], { apply: '0', today: todayISO() })); return false; } },
    { label: 'Apply', onClick: async () => { if (!file.files[0]) throw new Error('Choose the file'); const x = await api.upload(p('/variations/upload'), file.files[0], { apply: '1', today: todayISO() }); toast(`Register loaded: ${x.created.length} added, ${x.updated.length} updated`); await render(); } }] });
}
