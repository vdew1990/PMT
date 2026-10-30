import { h, clear, fmt, modal, toast, field, select, table, num, confirmBox, badge, tabs, empty, drawer, chart, PALETTE, tone, todayISO, statusPill } from '../ui.js';
import { api, state, p, loadRows, isCompany } from '../api.js';
import { pickNode } from '../scope.js';
import { go, render } from '../app.js';

const STATUS_TONE = { 'INFUSION NEEDED': 'bad', 'RELEASE DUE': 'warn', 'TRANSFER CONTINGENCY': 'warn', 'AWAITING INVOICE': 'warn', COVERED: 'good', 'SAVED FOR RISK': 'good', 'NO RISK COSTS': '' };

// Risk and contingency. The PM works to the budget; the company holds the risk bucket. Risk cost lands first, then it is funded: contingency
// (PM), then a release from the bucket (company), then new funds (company).
export default async function risk(root, params) {
  await loadRows();
  const d = await api.get(p('/risk'));
  if (params.tab === 'closeout') { go('closeout'); return; }   // close-out has its own page (CLOSE-OUT)
  let tab = params.tab || 'allowance'; if (tab === 'buckets') tab = 'allowance';
  document.body.classList.toggle('ws-solo', params.solo === '1' && tab === 'allowance');   // the workspace alone, in its own window
  const lit = { allowance: 'allowance', register: 'register', tagging: 'register', ledger: 'ledger', contingency: 'contingency', release: 'contingency' }[tab] || 'allowance';
  const t = d.totals; const co = isCompany();
  const [ov, led] = await Promise.all([api.get(p('/allowance/overview')).catch(() => ({ buckets: [] })), api.get(p('/ledger')).catch(() => [])]);
  const free = ov.buckets.reduce((a, b) => a + b.available, 0); const nPots = ov.buckets.filter((b) => b.available > 0.5 || b.risk > 0.5).length;
  const open = (d.risks || []).filter((r) => r.status === 'open' || !r.status).length;
  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, 'Allowances'), h('div', { class: 'sub' }, 'Where the money is held and who it is assigned to: the estimate and what comes in later (approved variations, risk the company releases), the risk register, every movement, and where the budget is over or under.'))));
  const tile = (key, label, big, sub) => h('div', { class: 'kpi hub' + (lit === key ? ' on' : ''), role: 'button', tabindex: 0, onclick: () => go('risk', { tab: key }), onkeydown: (e) => { if (e.key === 'Enter') go('risk', { tab: key }); } },
    h('div', { class: 'l' }, label), h('div', { class: 'v', style: { fontSize: '20px' } }, big), h('div', { class: 's' }, sub));
  root.append(h('div', { class: 'grid g4 hubtiles', style: { marginBottom: '14px' } },
    tile('allowance', 'Allowance', fmt.m(free), `${nPots} pots with money still to assign`),
    tile('register', 'Risk register', `${open} open`, `${(d.risks || []).length} risks, ${fmt.m(t.occurred)} occurred`),
    tile('ledger', 'Ledger', `${led.length} moves`, 'every movement of money, with a pivot'),
    tile('contingency', 'Contingency', fmt.m(t.contingency), t.uncovered > 1 ? `${fmt.m(t.uncovered)} of risk cost not yet covered` : 'over and underruns')));
  const sub = { register: [['register', 'Risk register'], ['tagging', 'Tag costs to risks']], contingency: [['contingency', 'Over and underruns'], ['release', 'Funding risk costs']] }[lit];
  if (sub) root.append(tabs(sub, tab, (k) => go('risk', { tab: k })));
  if (lit === 'register' || lit === 'contingency') {
    const kpi = (l, v, s, c = '') => h('div', { class: 'kpi ' + c }, h('div', { class: 'l' }, l), h('div', { class: 'v', style: { fontSize: '19px' } }, v), s ? h('div', { class: 's' }, s) : null);
    const tiles = [kpi('Contingency held', fmt.m(t.contingency), 'Separated inside your budgets'), kpi('Risk cost occurred', fmt.m(t.occurred), 'Landed or accrued, tagged to risks', 't2'), kpi('Risk cover set aside', fmt.m(t.cover), `${fmt.m(t.from_contingency)} contingency, ${fmt.m(t.released)} released, ${fmt.m(t.infused)} infused; ${fmt.m(t.saved)} saved ahead`, 't3'),
      kpi('Still uncovered', fmt.m(t.uncovered), t.uncovered > 1 ? `${fmt.m(t.uncovered_landed)} landed in Pronto; next ${fmt.m(t.step_contingency)} contingency, ${fmt.m(t.step_release)} release, ${fmt.m(t.step_infuse)} infusion` : 'Every occurred risk cost is covered', t.uncovered > 1 ? 't2' : 't6')];
    if (co) tiles.splice(1, 0, kpi('Company risk bucket', fmt.m(t.bucket), `${fmt.m(t.remaining)} still held`, 't4'));
    root.append(h('div', { class: 'grid', style: { marginBottom: '14px', gridTemplateColumns: `repeat(${tiles.length}, minmax(0, 1fr))` } }, tiles));
    if (!co) root.append(h('div', { class: 'note', style: { marginBottom: '12px' } }, 'You are in the PM view: the company risk bucket is not shown. Switch the view at the top to see it.'));
  }
  const body = h('div'); root.append(body);
  if (tab === 'allowance') { const { allowanceTab } = await import('./_allowances.js'); await allowanceTab(body); return; }
  await ({ contingency: contingencyTab, ledger: ledgerTab, register: registerTab, tagging: taggingTab, release: releaseTab })[tab](body, d, params);
}

// ---- contingency: where the budget is over or under (allowance less EAC per CBS line), grouped by CBS ----------------
async function contingencyTab(body) {
  const res = await api.get(p('/cost-control?months=0'));
  const rows = res.rows;
  const lines = rows.filter((r) => r.kind !== 'group' && (Math.abs(r.contingency) > 0.5 || r.allowance || r.eac));
  const over = lines.filter((r) => r.contingency < -0.5), under = lines.filter((r) => r.contingency > 0.5);
  const S = (xs, k) => xs.reduce((a, r) => a + (r[k] || 0), 0);
  const kpi = (l, v, s, c = '', vc = '') => h('div', { class: 'kpi ' + c }, h('div', { class: 'l' }, l), h('div', { class: 'v ' + vc, style: { fontSize: '19px' } }, v), s ? h('div', { class: 's' }, s) : null);
  body.append(h('div', { class: 'grid g4', style: { marginBottom: '14px' } },
    kpi('Overruns', fmt.m(S(over, 'contingency')), `${over.length} line${over.length === 1 ? '' : 's'} forecast above allowance`, '', 'bad'),
    kpi('Underruns', fmt.m(S(under, 'contingency')), `${under.length} line${under.length === 1 ? '' : 's'} forecast below allowance`, 't2', 'good'),
    kpi('Net contingency', fmt.m(res.total.contingency), 'Allowance less EAC, whole project', 't3', tone(res.total.contingency)),
    kpi('Contingency earmarked', fmt.m(S(lines, 'cont_earmark')), `Risk cover set aside ${fmt.m(S(lines, 'risk_cover'))}`, 't4')));
  let only = sessionStorage.getItem('contOnly') || 'both';
  const bar = h('div', { class: 'row', style: { marginBottom: '8px' } });
  const box = h('div');
  body.append(h('div', { class: 'card' }, h('div', { class: 'ch' }, h('h2', {}, 'Over and underruns by CBS'), h('span', { class: 'sp' }), bar), box));
  const byId = new Map(rows.map((r) => [String(r.id), r]));
  function draw() {
    bar.replaceChildren(...[['both', 'Both'], ['over', 'Overruns'], ['under', 'Underruns']].map(([k, l]) => h('span', { class: 'chip' + (only === k ? ' on' : ''), onclick: () => { only = k; try { sessionStorage.setItem('contOnly', k); } catch (e) { /* ignore */ } draw(); } }, l)));
    const pick = only === 'over' ? over : only === 'under' ? under : [...over, ...under];
    // the groups above the lines picked, each with the subtotal of its picked lines
    const keep = new Set();
    pick.forEach((r) => { let x = r; while (x) { keep.add(String(x.id)); x = x.parent_id != null ? byId.get(String(x.parent_id)) : null; } });
    const inPick = new Set(pick.map((r) => String(r.id)));
    const sumUnder = (g) => { const out = { allowance: 0, eac: 0, contingency: 0, cont_earmark: 0 }; const walk = (id) => rows.filter((r) => String(r.parent_id) === String(id)).forEach((c) => { if (c.kind === 'group') walk(c.node_id); else if (inPick.has(String(c.id))) Object.keys(out).forEach((k) => { out[k] += c[k] || 0; }); }); walk(g.node_id); return out; };
    const shown = rows.filter((r) => keep.has(String(r.id)));
    clear(box).append(shown.length ? h('div', { class: 'tw', style: { maxHeight: '64vh' } }, h('table', { class: 't' },
      h('thead', {}, h('tr', {}, ['CBS', 'Name', 'Allowance', 'EAC', 'Over (−) / under (+)', 'Status', 'Contingency earmarked', 'Note'].map((x, i) => h('th', { class: i >= 2 && i !== 5 && i !== 7 ? 'r' : '' }, x)))),
      h('tbody', {}, shown.map((r) => {
        const g = r.kind === 'group'; const v = g ? sumUnder(r) : r;
        return h('tr', { class: (g ? (r.level === 1 ? 'gp' : r.level === 2 ? 'par' : 'par2') : '') + ' click', title: 'Open in cost control', onclick: () => go('costcontrol', g ? { node: r.id } : { open: r.id }) },
          h('td', { class: 'mono', style: { paddingLeft: `${8 + (r.level - 1) * 14}px` } }, r.code), h('td', {}, r.name),
          h('td', { class: 'r num' }, fmt.money(v.allowance)), h('td', { class: 'r num' }, fmt.money(v.eac)),
          h('td', { class: 'r num ' + tone(v.contingency) }, fmt.money(v.contingency)), h('td', {}, g ? '' : statusPill(r.budget_status)),
          h('td', { class: 'r num' }, v.cont_earmark ? fmt.money(v.cont_earmark) : ''), h('td', { class: 'small muted' }, g ? '' : (r.note || '').slice(0, 80)));
      })),
      h('tfoot', {}, h('tr', {}, h('td', {}, h('b', {}, 'Total')), h('td'), h('td', { class: 'r num' }, h('b', {}, fmt.money(S(pick, 'allowance')))), h('td', { class: 'r num' }, h('b', {}, fmt.money(S(pick, 'eac')))),
        h('td', { class: 'r num ' + tone(S(pick, 'contingency')) }, h('b', {}, fmt.money(S(pick, 'contingency')))), h('td'), h('td', { class: 'r num' }, fmt.money(S(pick, 'cont_earmark'))), h('td')))))
      : empty('Nothing to show', only === 'over' ? 'No line is forecast above its allowance.' : 'No line is forecast below its allowance.'));
  }
  draw();
}

// ---- ledger: every movement of money per CBS line, with its reason and date ---------------------------------------
const KIND_LABEL = { estimate: 'Original estimate', transfer: 'Transfer', variation: 'Variation', risk_release: 'Risk release', adjustment: 'Adjustment',
  contingency_set: 'Contingency set aside', contingency_to_risk: 'Contingency to risk cover', risk_infusion: 'New funds (infusion)', risk_saved: 'Saved for risk' };
const kindLabel = (k) => KIND_LABEL[k] || (k.charAt(0).toUpperCase() + k.slice(1)).replace(/_/g, ' ');
async function ledgerTab(body, d, params = {}) {
  const led = await api.get(p('/ledger?all=1'));
  if (!led.length) { body.append(empty('No allowance yet', 'Load the estimate on Project setup; every movement after it is listed here.')); return; }
  const store = `ledOpen:${state.pid}`;
  let by = sessionStorage.getItem('ledBy') || 'cbs'; let kind = ''; let q = '';
  const focus = new Set(String(params.node || '').split(',').filter(Boolean).map(Number));   // opened from the Allowances workspace: these lines
  let open = null; try { const s = sessionStorage.getItem(store); open = s ? new Set(JSON.parse(s)) : null; } catch (e) { open = null; }
  const saveOpen = () => { try { sessionStorage.setItem(store, JSON.stringify([...open])); } catch (e) { /* ignore */ } };
  const bar = h('div', { class: 'row', style: { marginBottom: '8px', flexWrap: 'wrap' } });
  const scroller = h('div', { class: 'tw', style: { maxHeight: '66vh' } });
  const box = h('div', {}, scroller);
  body.append(h('div', { class: 'card' }, h('div', { class: 'ch' }, h('h2', {}, 'Ledger: every movement of budget, risk and contingency'), h('span', { class: 'sp' }), bar), box));
  const search = h('input', { type: 'search', placeholder: 'CBS code, name, note, ref, funded by...', style: { width: '230px' }, oninput: (e) => { q = e.target.value.trim().toLowerCase(); draw(); } });
  let showC = true; let showR = true;   // the contingency and risk cover columns show only when something in view uses them
  const money = (v, cls = '') => h('td', { class: 'r num ' + cls }, v ? fmt.money(v, 2) : '');
  const counterText = (r) => {
    const c = r.counter || []; if (!c.length) return '';
    const dir = (r.budget || 0) + (r.risk || 0) + (r.contingency || 0) + (r.risk_cover || 0) >= 0 ? 'from' : 'to';
    return `${dir} ${c.length > 2 ? `${c.length} lines` : c.map((x) => `${x.code} ${x.name}`).join(', ')}`;
  };
  // which pots (and what) funded a line: the positive legs of its transfers, grouped by the other side
  const fundedBy = (rs) => {
    const m = new Map();
    rs.forEach((r) => { if ((r.budget || 0) + (r.risk || 0) > 0 && r.counter?.length === 1) { const c = r.counter[0]; m.set(c.code, { name: c.name, v: (m.get(c.code)?.v || 0) + (r.budget || 0) + (r.risk || 0) }); } });
    return [...m.entries()].map(([code, o]) => ({ code, name: o.name, v: o.v }));
  };
  async function after() { const fresh = await api.get(p('/ledger?all=1')); led.length = 0; led.push(...fresh); draw(); }
  function reasonBox(label) { return h('textarea', { rows: 2, style: { width: '100%' }, placeholder: label }); }
  function delEntry(r) {
    const why = reasonBox('Why is this entry being deleted? (required)');
    modal({ title: `Delete ${kindLabel(r.kind)} entry on ${r.code} ${r.name}`, body: h('div', { class: 'grid' },
      h('div', { class: 'note' }, `Budget ${fmt.money(r.budget, 2)}, risk ${fmt.money(r.risk, 2)}${r.pair_id ? '. The other side of the move is deleted too' : ''}. The deletion and your reason are kept in the entry's history, and Undo in the top bar puts it back.`), field('Reason (kept for traceability)', why)),
      actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} }, { label: 'Delete', kind: 'danger', onClick: async () => {
        if (why.value.trim().length < 3) { toast('Give a reason for the deletion.', 'bad'); return false; }
        await api.del(p(`/ledger/${r.id}?reason=${encodeURIComponent(why.value.trim())}`)); toast('Entry deleted'); await after();
      } }] });
  }
  function editEntry(r) {
    const inp = (v, w = '110px') => h('input', { type: 'text', inputmode: 'decimal', value: v || v === 0 ? String(v) : '', style: { width: w, textAlign: 'right' } });
    const f = { budget: inp(r.budget), risk: inp(r.risk), contingency: inp(r.contingency), risk_cover: inp(r.risk_cover) };
    const date = h('input', { type: 'date', value: (r.date || '').slice(0, 10) }); const ref = h('input', { type: 'text', value: r.ref || '' }); const note = h('input', { type: 'text', value: r.note || '', style: { width: '100%' } });
    const why = reasonBox('Why is this being corrected? (required)');
    modal({ title: `Correct ${kindLabel(r.kind)} entry on ${r.code} ${r.name}`, body: h('div', { class: 'grid' },
      h('div', { class: 'note' }, r.pair_id ? 'This entry is one side of a move. Changing an amount changes the other side by the opposite amount, so the move stays balanced.' : 'A single-sided entry: only this CBS line changes.'),
      r.kind === 'estimate' ? h('div', { class: 'note', style: { background: '#fff4e5' } }, 'This is the original estimate. Changing it changes the project\'s original budget.') : null,
      h('div', { class: 'grid g2' }, field('Budget', f.budget), field('Risk', f.risk), field('Contingency', f.contingency), field('Risk cover', f.risk_cover), field('Date', date), field('Reference', ref)),
      field('Note on the entry', note), field('Why you are correcting it (kept in the history)', why)),
      actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} }, { label: 'Save', onClick: async () => {
        if (why.value.trim().length < 3) { toast('Give a reason for the correction.', 'bad'); return false; }
        const b = { date: date.value || null, ref: ref.value, note: note.value, reason: why.value.trim() };
        for (const k of Object.keys(f)) b[k] = num(f[k].value);
        await api.put(p(`/ledger/${r.id}`), b); toast('Entry corrected'); await after();
      } }] });
  }
  async function history(r) {
    const ed = await api.get(p(`/ledger/${r.id}/edits`));
    const what = (e) => { try { const o = JSON.parse(e.old_json || '{}'); const n = e.new_json ? JSON.parse(e.new_json) : null; if (!n) return 'Entry deleted'; return Object.keys(n).map((k) => `${k}: ${o[k] ?? ''} to ${n[k] ?? ''}`).join('; ') || 'No field changed'; } catch (x) { return ''; } };
    modal({ title: `History of ${r.code} ${r.name}`, size: 'wide', body: ed.length ? table([{ label: 'When', f: (e) => (e.at || '').slice(0, 16) }, { label: 'Who', f: (e) => e.by || '' }, { label: 'What', f: (e) => e.action === 'delete' ? 'Deleted' : 'Corrected' }, { label: 'Change', cls: 'wrap', f: what }, { label: 'Reason', cls: 'wrap', f: (e) => e.reason }], ed) : empty('No corrections', 'This entry has not been changed.'), actions: [{ label: 'Close', kind: 'ghost', onClick: () => {} }] });
  }
  const rowOf = (r, bal, cls = '') => h('tr', { class: cls },
    h('td', { class: 'nowrap' }, fmt.date(r.date) || fmt.date((r.created_at || '').slice(0, 10))),
    by === 'date' ? h('td', { class: 'mono' }, r.code) : null, by === 'date' ? h('td', {}, r.name) : null,
    h('td', {}, badge(kindLabel(r.kind), r.kind === 'variation' ? 'navy' : r.kind === 'estimate' ? '' : r.kind === 'risk_release' ? 'warn' : '')),
    h('td', { class: 'small', title: counterText(r) }, counterText(r)),
    money(r.budget, r.budget < 0 ? 'bad' : ''), money(r.risk), showC ? money(r.contingency) : null, showR ? money(r.risk_cover) : null,
    bal != null ? h('td', { class: 'r num' }, h('b', {}, fmt.money(bal, 2))) : null,
    h('td', { class: 'small' }, r.ref || ''), h('td', { class: 'small' }, r.note || ''), h('td', { class: 'small muted' }, r.by || ''),
    h('td', { class: 'nowrap' }, h('button', { class: 'btn ghost sm', title: 'Correct this entry (a reason is required and kept)', onclick: () => editEntry(r) }, 'Edit'),
      r.kind === 'estimate' || r.kind === 'variation' ? null : h('button', { class: 'btn ghost sm', title: 'Delete this entry and the other side of the move (a reason is required and kept)', onclick: () => delEntry(r) }, 'Delete'),
      r.edits ? h('button', { class: 'btn ghost sm', title: 'Who corrected this entry, when and why', onclick: () => history(r) }, `History (${r.edits})`) : null));
  // the CBS tree of the lines that have entries: grandparent > parent > child, in CBS order
  function buildTree(list) {
    const nodes = new Map();
    const get = (id, code, name, ord) => { if (!nodes.has(id)) nodes.set(id, { id, code, name, ord, kids: [], rows: [] }); return nodes.get(id); };
    const roots = [];
    list.forEach((r) => {
      let parent = null;
      [...(r.anc || []), { id: r.node_id, code: r.code, name: r.name, self: true }].forEach((a, i) => {
        const fresh = !nodes.has(a.id); const n = get(a.id, a.code, a.name, a.self ? r.ord : null);
        if (a.self) { n.ord = r.ord; n.rows.push(r); }
        if (fresh) (parent ? parent.kids : roots).push(n);
        parent = n;
      });
    });
    const sortRec = (ns) => { ns.sort((a, b) => (a.ord ?? 1e9) - (b.ord ?? 1e9) || a.code.localeCompare(b.code, undefined, { numeric: true })); ns.forEach((n) => { if (n.ord == null) n.ord = Math.min(...n.kids.map((k) => k.ord ?? 1e9)); sortRec(n.kids); }); };
    const fix = (n) => { n.kids.forEach(fix); if (n.ord == null) n.ord = Math.min(...n.kids.map((k) => k.ord)); }; roots.forEach(fix); sortRec(roots);
    const sum = (n, k) => n.rows.reduce((a, r) => a + (r[k] || 0), 0) + n.kids.reduce((a, c) => a + sum(c, k), 0);
    const count = (n) => n.rows.length + n.kids.reduce((a, c) => a + count(c), 0);
    const all = (n) => [...n.rows, ...n.kids.flatMap(all)];
    return { roots, sum, count, all };
  }
  function draw() {
    bar.replaceChildren(...[
      ...[['cbs', 'Per CBS line'], ['date', 'By date']].map(([k, l]) => h('span', { class: 'chip' + (by === k ? ' on' : ''), onclick: () => { by = k; try { sessionStorage.setItem('ledBy', k); } catch (e) { /* ignore */ } draw(); } }, l)),
      h('span', { style: { width: '10px' } }),
      select([['', 'All kinds'], ...[...new Set(led.map((r) => r.kind))].map((k) => [k, kindLabel(k)])], kind, { onchange: (e) => { kind = e.target.value; draw(); } }), search,
      by === 'cbs' ? h('button', { class: 'ws-link', onclick: () => { allIds().forEach((i) => open.add(i)); saveOpen(); draw(); } }, 'Open all') : null,
      by === 'cbs' ? h('button', { class: 'ws-link', onclick: () => { open.clear(); saveOpen(); draw(); } }, 'Close all') : null,
      focus.size ? h('button', { class: 'ws-link', onclick: () => { focus.clear(); go('risk', { tab: 'ledger' }); } }, 'Show the whole ledger') : null].filter(Boolean));
    const match = (r) => (!kind || r.kind === kind) && (!q || `${r.code} ${r.name} ${r.note || ''} ${r.ref || ''} ${(r.counter || []).map((c) => c.code + ' ' + c.name).join(' ')}`.toLowerCase().includes(q));
    const list = led.filter((r) => match(r) && (!focus.size || focusRows.has(r.id)));
    showC = list.some((r) => r.contingency); showR = list.some((r) => r.risk_cover);
    const head = ['Date', ...(by === 'date' ? ['CBS', 'Name'] : []), 'Movement', 'Funded by / to', 'Budget', 'Risk', ...(showC ? ['Contingency'] : []), ...(showR ? ['Risk cover'] : []), ...(by === 'cbs' ? ['Budget after'] : []), 'Ref', 'Note', 'By', ''];
    const thead = h('thead', {}, h('tr', {}, head.map((x) => h('th', { class: ['Budget', 'Risk', 'Contingency', 'Risk cover', 'Budget after'].includes(x) ? 'r' : '' }, x))));
    let tbody;
    if (by === 'date') tbody = h('tbody', {}, [...list].sort((a, b) => String(b.date || b.created_at).localeCompare(String(a.date || a.created_at)) || b.id - a.id).map((r) => rowOf(r)));
    else {
      const T = buildTree(list); const trs = [];
      const searching = !!q || !!kind;
      const visit = (n, depth) => {
        const isOpen = searching || open.has(n.id) || focus.has(n.id);
        const own = n.rows; const everything = T.all(n);
        const S = (k) => T.sum(n, k); const cls = depth === 0 ? 'gp' : depth === 1 ? 'par' : 'par2';
        const fb = fundedBy(everything);
        const fbText = fb.length ? 'Funded by ' + fb.slice(0, 2).map((x) => `${x.code} ${x.name} ${fmt.m(x.v)}`).join(', ') + (fb.length > 2 ? ` and ${fb.length - 2} more` : '') : '';
        const fbTitle = fb.map((x) => `${x.code} ${x.name}: ${fmt.money(x.v, 2)}`).join('\n');
        const hl = (n.rows.length && focus.has(n.id)) ? ' focus' : '';
        trs.push(h('tr', { class: cls + hl, 'data-node': String(n.id), style: { cursor: 'pointer' }, onclick: () => { if (open.has(n.id)) open.delete(n.id); else open.add(n.id); saveOpen(); draw(); } },
          h('td', { class: 'nowrap' }, h('span', { class: 'arr', style: { display: 'inline-block', width: '14px', transform: isOpen ? 'rotate(90deg)' : '' } }, '▸'), h('b', { class: 'mono' }, n.code)), h('td', {}, n.name),
          by === 'cbs' ? h('td', { class: 'small', title: fbTitle }, fbText) : null,
          h('td', { class: 'r num' }, fmt.money(S('budget'), 2)), h('td', { class: 'r num' }, fmt.money(S('risk'), 2)), showC ? h('td', { class: 'r num' }, S('contingency') ? fmt.money(S('contingency'), 2) : '') : null,
          showR ? h('td', { class: 'r num' }, S('risk_cover') ? fmt.money(S('risk_cover'), 2) : '') : null, h('td', { class: 'r num' }, fmt.money(S('budget'), 2)),
          h('td', { class: 'small muted', colspan: 4 }, `${T.count(n)} movement${T.count(n) === 1 ? '' : 's'}`)));
        if (!isOpen) return;
        let bal = 0; [...own].reverse().forEach((r) => { bal += r.budget || 0; trs.push(rowOf(r, bal, 'entry')); });
        n.kids.forEach((c) => visit(c, depth + 1));
      };
      T.roots.forEach((n) => visit(n, 0));
      tbody = h('tbody', {}, trs);
    }
    scroller.replaceChildren(list.length ? h('table', { class: 't' }, thead, tbody) : empty('No movements match', ''));
    if (pendingScroll) { pendingScroll = false; const el = scroller.querySelector('tr.focus'); if (el) el.scrollIntoView({ block: 'center' }); }
  }
  // opening from the Allowances workspace on selected lines: show just those lines (and the pots that funded them), opened
  const focusRows = new Set(); let pendingScroll = false;
  if (focus.size) {
    const isMine = (r) => focus.has(r.node_id);
    led.filter(isMine).forEach((r) => { focusRows.add(r.id); (r.counter || []).forEach(() => {}); });
    // the other sides of those moves (the pots that funded the lines) are shown too, so the funding is visible
    led.forEach((r) => { if (r.pair_id && led.some((o) => o.pair_id === r.pair_id && focus.has(o.node_id))) focusRows.add(r.id); });
    pendingScroll = true;
  }
  const allIds = () => { const s = new Set(); led.forEach((r) => { s.add(r.node_id); (r.anc || []).forEach((a) => s.add(a.id)); }); return s; };
  if (!open) { open = new Set(); led.forEach((r) => (r.anc || []).forEach((a, i) => { if (i < 2) open.add(a.id); })); }   // first visit: the top levels open, the lines folded
  if (focus.size) led.filter((r) => focus.has(r.node_id)).forEach((r) => (r.anc || []).forEach((a) => open.add(a.id)));
  draw();
}

// ---- register -----------------------------------------------------------------------------------
function registerTab(body, d) {
  const sm = d.summary;
  const kp = (l, v, sub, c = '') => h('div', { class: 'kpi ' + c }, h('div', { class: 'l' }, l), h('div', { class: 'v', style: { fontSize: '18px' } }, v), h('div', { class: 's' }, sub));
  const file = h('input', { type: 'file', accept: '.xlsx,.xlsm', class: 'hide' });
  file.onchange = async () => { if (!file.files[0]) return; try { const r = await api.upload(p('/risk/import'), file.files[0]); toast(`${r.created} risks created, ${r.updated} updated${r.skipped_without_description.length ? `; ${r.skipped_without_description.length} blank rows skipped` : ''}`); await render(); } catch (e) { toast(e.message, 'bad'); } };
  body.append(h('div', { class: 'grid g4', style: { marginBottom: '12px' } }, kp('Risk pot (estimate)', fmt.money(sm.pot), 'Sum of the CBS risk buckets'), kp('Reserved for events', fmt.money(sm.reserved), `${sm.n_risks - sm.n_ceased} live events, after treatment`, 't2'), kp('Unallocated risk (R-999)', fmt.money(sm.unallocated), 'Pot less what events reserve', sm.unallocated < 0 ? 't2' : 't3'), kp('Impact of materialised risks', fmt.money(sm.materialised_impact), `${sm.n_materialised} materialised`, 't4')));
  body.append(h('div', { class: 'grid g4', style: { marginBottom: '12px' } }, kp('Delay allowed for (days)', fmt.n(sm.delay_planned, 0), `Probability weighted; worst case ${fmt.n(sm.delay_worst, 0)} days`), kp('Delay occurred (days)', fmt.n(sm.delay_occurred, 0), 'From materialised risks', sm.delay_occurred > sm.delay_planned ? 't2' : 't3'), kp('Revenue exposure', fmt.money(sm.revenue_planned), `Probability weighted; worst case ${fmt.money(sm.revenue_worst)}`, 't2'), kp('Margin hit so far', fmt.money(sm.margin_hit), `Risk cost incl. forecast ${fmt.money(sm.materialised_impact)} plus revenue lost ${fmt.money(sm.revenue_occurred)}`, 't4')));
  body.append(h('div', { class: 'row', style: { marginBottom: '10px' } }, h('span', { class: 'muted small', style: { flex: 1 } }, 'Each event reserves its treated residual (estimate x likelihood x (1 - effectiveness)) out of the pot. Break the buckets down across events on the next tab; tag costs as they land.'), h('button', { class: 'btn ghost', onclick: () => file.click() }, 'Upload risk register (Excel)'), file, h('button', { class: 'btn', onclick: () => edit() }, '+ New risk')));
  const tone2 = { materialised: 'warn', ceased: '', open: 'navy' };
  body.append(d.risks.length ? table([{ label: 'Ref', f: (r) => h('b', {}, r.ref) }, { label: 'Type', f: (r) => r.kind === 'Opportunity' ? badge('Opportunity', 'good') : '' }, { label: 'Risk', cls: 'wrap', f: (r) => h('span', { style: { display: 'inline-block', minWidth: '220px' } }, r.title) }, { label: 'Area', f: (r) => r.area || r.category || '' },
    { label: 'Status', f: (r) => badge(r.status, tone2[r.status]) }, { label: 'Owner', f: (r) => r.owner || '' }, { label: 'Unmitigated', r: 1, f: (r) => fmt.money(r.estimate) }, { label: 'Likelihood', r: 1, f: (r) => fmt.pct(r.likelihood, 0) }, { label: 'Factored', r: 1, f: (r) => fmt.money(r.factored) }, { label: 'Treatment', f: (r) => r.treatment || '' }, { label: 'Effect', r: 1, f: (r) => r.effectiveness ? fmt.pct(r.effectiveness, 0) : '' },
    { label: 'Reserve (residual)', r: 1, f: (r) => h('b', {}, fmt.money(r.residual)) }, { label: 'Landed + accrued', r: 1, f: (r) => fmt.money(r.realised) }, { label: 'Forecast', r: 1, f: (r) => fmt.money(r.forecast) }, { label: 'Exposure left', r: 1, f: (r) => fmt.money(r.exposure) },
    { label: 'Delay est. (days)', r: 1, f: (r) => r.delay_days ? fmt.n(r.delay_days, 0) : '' }, { label: 'Delay occurred', r: 1, f: (r) => r.delay_actual ? fmt.n(r.delay_actual, 0) : '' }, { label: 'Revenue impact est.', r: 1, f: (r) => r.revenue_impact ? fmt.money(r.revenue_impact) : '' }, { label: 'Revenue impact occurred', r: 1, f: (r) => r.revenue_actual ? fmt.money(r.revenue_actual) : '' }],
    d.risks, { onRow: (r) => detail(r), foot: (c) => ({ Risk: 'Totals', Unmitigated: fmt.money(d.risks.reduce((a, r) => a + r.estimate, 0)), Factored: fmt.money(d.risks.reduce((a, r) => a + r.factored, 0)), 'Reserve (residual)': fmt.money(sm.reserved), 'Landed + accrued': fmt.money(d.risks.reduce((a, r) => a + r.realised, 0)) }[c.label]) })
    : empty('No risks yet', 'Add the risk events for the project, or upload the risk register workbook.', h('button', { class: 'btn', onclick: () => edit() }, '+ New risk')));
  if (d.risks.length) body.append(h('div', { class: 'note', style: { marginTop: '10px' } }, `R-999 Unallocated risk: ${fmt.money(sm.unallocated)}. This is the pot that no event reserves, and what the General Manager draws on for risks that were not foreseen.`));
  function edit(r = {}) {
    const f = { ref: h('input', { type: 'text', value: r.ref || '', placeholder: 'auto, e.g. R-023', disabled: !!r.id }), title: h('input', { type: 'text', value: r.title || '' }), kind: select(['Risk', 'Opportunity'], r.kind || 'Risk'), status: select(['open', 'materialised', 'ceased'], r.status || 'open'),
      category: h('input', { type: 'text', value: r.category || '', placeholder: 'e.g. Commercial' }), area: h('input', { type: 'text', value: r.area || '', placeholder: 'e.g. Delivery' }), owner: h('input', { type: 'text', value: r.owner || '' }),
      cons: h('textarea', { rows: 2, style: { width: '100%' } }, r.consequences || ''), cause: h('textarea', { rows: 2, style: { width: '100%' } }, r.cause || ''), est: h('input', { type: 'number', step: '0.01', value: r.estimate || '' }), lik: h('input', { type: 'number', step: '1', value: r.likelihood ? r.likelihood * 100 : '' }),
      basis: h('input', { type: 'text', value: r.basis || '' }), trig: h('input', { type: 'text', value: r.trigger_event || '' }), controls: h('textarea', { rows: 2, style: { width: '100%' } }, r.controls || ''), treat: select(['', 'Mitigate', 'Avoid', 'Accept', 'Preventative', 'Transfer'], r.treatment || ''),
      ccost: h('input', { type: 'number', step: '0.01', value: r.control_cost || '' }), eff: h('input', { type: 'number', step: '1', value: r.effectiveness ? r.effectiveness * 100 : '' }), rev: h('input', { type: 'date', value: r.last_reviewed || '' }), ret: h('input', { type: 'date', value: r.retire_date || '' }), comment: h('input', { type: 'text', value: r.comment || '' }),
      dd: h('input', { type: 'number', step: '1', value: r.delay_days || '' }), da: h('input', { type: 'number', step: '1', value: r.delay_actual || '' }), ri: h('input', { type: 'number', step: '0.01', value: r.revenue_impact || '' }), ra: h('input', { type: 'number', step: '0.01', value: r.revenue_actual || '' }) };
    const calc = h('div', { class: 'note' }); const upd = () => { const fc = num(f.est.value) * num(f.lik.value) / 100; calc.textContent = `Factored cost ${fmt.money(fc)}; reserve after treatment ${fmt.money(fc * (1 - num(f.eff.value) / 100))}`; };
    [f.est, f.lik, f.eff].forEach((i) => (i.oninput = upd)); upd();
    modal({ title: r.id ? `${r.ref}: ${r.title}` : 'New risk', size: 'wide', body: h('div', { class: 'grid' }, h('div', { class: 'grid g4' }, field('Reference', f.ref), field('Type', f.kind), field('Status', f.status), field('Owner', f.owner)), field('Description', f.title), h('div', { class: 'grid g2' }, field('Category', f.category), field('Area', f.area)),
      h('div', { class: 'grid g2' }, field('Consequences', f.cons), field('Root causes', f.cause)), h('div', { class: 'grid g4' }, field('Unmitigated cost ($)', f.est), field('Likelihood (%)', f.lik), field('Basis of estimate', f.basis), field('Triggering event', f.trig)), calc,
      field('Management controls and treatment actions', f.controls), h('div', { class: 'grid g4' }, field('Treatment method', f.treat), field('Cost of control ($)', f.ccost), field('Effectiveness of treatment (%)', f.eff), field('Comment', f.comment)), h('div', { class: 'grid g4' }, field('Date last reviewed', f.rev), field('Retirement date', f.ret), h('span'), h('span')),
      h('h3', { style: { margin: '6px 0 0' } }, 'Time and revenue impact'), h('div', { class: 'grid g4' }, field('Delay if it happens (days)', f.dd, 'Calendar days added to the project schedule'), field('Delay that occurred (days)', f.da), field('Revenue lost or deferred if it happens ($)', f.ri, 'Positive = a loss, e.g. liquidated damages payable or a milestone pushed out'), field('Revenue lost or deferred, occurred ($)', f.ra))),
      actions: [r.id ? { label: 'Delete', kind: 'danger', onClick: async () => { if (!(await confirmBox('Delete this risk? Its tags and bucket shares are removed.', 'Delete', true))) return false; await api.del(p(`/risk/${r.id}`)); await render(); } } : { label: 'Cancel', kind: 'ghost', onClick: () => {} },
        { label: 'Save', onClick: async () => { await api.post(p('/risk'), { id: r.id, ref: f.ref.value || undefined, title: f.title.value, kind: f.kind.value, status: f.status.value, owner: f.owner.value, category: f.category.value, area: f.area.value, consequences: f.cons.value, cause: f.cause.value, estimate: num(f.est.value), likelihood: num(f.lik.value) / 100, basis: f.basis.value, trigger_event: f.trig.value, controls: f.controls.value, treatment: f.treat.value, control_cost: num(f.ccost.value), effectiveness: num(f.eff.value) / 100, last_reviewed: f.rev.value || null, retire_date: f.ret.value || null, comment: f.comment.value, delay_days: num(f.dd.value), delay_actual: num(f.da.value), revenue_impact: num(f.ri.value), revenue_actual: num(f.ra.value) }); await render(); } }] });
  }
  async function detail(r) {
    const tg = await api.get(p(`/risk/tagged?risk_id=${r.id}`));
    const b = h('div'); drawer({ title: `${r.ref}: ${r.title}`, sub: [r.area, r.treatment].filter(Boolean).join(' \u00b7 '), body: b });
    b.append(h('div', { class: 'grid g4', style: { marginBottom: '12px' } }, kp('Reserve', fmt.money(r.residual), `${fmt.money(r.estimate)} x ${fmt.pct(r.likelihood, 0)}`), kp('Landed + accrued', fmt.money(r.realised), ''), kp('Forecast', fmt.money(r.forecast), '', 't3'), kp('Exposure left', fmt.money(r.exposure), '', 't4')),
      (r.delay_days || r.delay_actual || r.revenue_impact || r.revenue_actual) ? h('div', { class: 'grid g4', style: { marginBottom: '12px' } }, kp('Delay (days)', fmt.n(r.delay_actual, 0), `Estimated ${fmt.n(r.delay_days, 0)} if it happens`), kp('Revenue impact', fmt.money(r.revenue_actual), `Estimated ${fmt.money(r.revenue_impact)} if it happens`, 't2'), h('span'), h('span')) : null,
      h('div', { class: 'row', style: { marginBottom: '10px' } }, h('button', { class: 'btn ghost sm', onclick: () => edit(r) }, 'Edit risk'), h('button', { class: 'btn ghost sm', onclick: () => go('risk', { tab: 'tagging', risk: r.id }) }, 'Tag more costs')),
      tg.length ? table([{ label: 'Month', f: (x) => fmt.month(x.month) }, { label: 'Type', f: (x) => badge(x.kind, { actual: 'good', accrual: 'warn', forecast: '' }[x.kind]) }, { label: 'CBS', f: (x) => x.node }, { label: 'What', cls: 'wrap', f: (x) => x.text || '' }, { label: 'Amount', r: 1, f: (x) => fmt.money(x.amount) },
        { label: '', f: (x) => x.tag_id ? h('button', { class: 'btn danger sm', onclick: async () => { await api.del(p(`/risk/tag/${x.tag_id}`)); await render(); } }, 'Untag') : '' }], tg) : empty('Nothing tagged yet', 'Tag Pronto transactions, accruals or forecast items to this risk as costs land.'));
  }
}

// ---- buckets ------------------------------------------------------------------------------------
async function bucketsTab(body) {
  const b = await api.get(p('/risk/buckets'));
  if (!b.rows.length) { body.append(empty('No risk buckets', 'The estimate holds no risk yet. Enter risk against CBS items in the CBS editor (or apply the default risk % to the estimate).', h('button', { class: 'btn', onclick: () => go('cbs') }, 'Open the CBS editor'))); return; }
  if (!b.risks.length) { body.append(empty('No risks yet', 'Create the risk subjects first.', h('button', { class: 'btn', onclick: () => go('risk', { tab: 'register' }) }, 'Open the register'))); return; }
  body.append(h('div', { class: 'note', style: { marginBottom: '10px' } }, 'Break each CBS item\'s risk bucket down by risk subject. Whatever is not broken down stays unassigned (general risk). Type amounts; each cell saves as you leave it.'));
  const sums = b.risks.map(() => 0);
  const tbody = h('tbody');
  b.rows.forEach((r) => {
    const tr = h('tr', {}, h('td', { class: 'mono' }, r.code), h('td', {}, r.name), h('td', { class: 'r num' }, fmt.money(r.bucket)));
    const un = h('td', { class: 'r num' }); const al = h('td', { class: 'r num' });
    const upd = (vals) => { const a = vals.reduce((x, y) => x + y, 0); al.textContent = fmt.money(a); un.textContent = fmt.money(r.bucket - a); un.className = 'r num ' + (a > r.bucket + 0.5 ? 'bad' : ''); };
    const vals = b.risks.map((k) => r.alloc[String(k.id)] || 0);
    b.risks.forEach((k, i) => { const inp = h('input', { type: 'number', step: '0.01', value: vals[i] || '', style: { width: '104px' } }); inp.onchange = async () => { vals[i] = num(inp.value); await api.put(p('/risk/alloc'), { risk_id: k.id, node_id: r.node_id, amount: vals[i] }); upd(vals); }; tr.append(h('td', { class: 'in' }, inp)); });
    upd(vals); tr.append(al, un); tbody.append(tr);
  });
  const th = ['CBS', 'Name', 'Risk bucket', ...b.risks.map((k) => k.ref), 'Broken down', 'Unassigned'];
  body.append(h('div', { class: 'tw' }, h('table', { class: 't' }, h('thead', {}, h('tr', {}, th.map((x, i) => h('th', { class: i >= 2 ? 'r' : '', title: i >= 3 && i < 3 + b.risks.length ? b.risks[i - 3].title : '' }, x)))), tbody)));
}

// ---- tagging ------------------------------------------------------------------------------------
async function taggingTab(body, d) {
  const risks = d.risks.filter((r) => r.status !== 'ceased');
  if (!risks.length) { body.append(empty('No open risks', 'Create a risk first.', h('button', { class: 'btn', onclick: () => go('risk', { tab: 'register' }) }, 'Open the register'))); return; }
  const params = Object.fromEntries(new URLSearchParams(location.hash.split('?')[1] || ''));
  const riskSel = select(risks.map((r) => [r.id, `${r.ref} ${r.title}`]), params.risk || risks[0].id);
  const q = h('input', { type: 'search', placeholder: 'Search description, reference, supplier...', style: { width: '260px' } });
  const filt = select([['', 'All'], ['no', 'Not tagged'], ['yes', 'Tagged']], 'no');
  let node = null; const nodeBtn = h('button', { class: 'btn ghost sm', onclick: () => pickNode({ title: 'Limit to a CBS item', allowRoot: true, onPick: (r) => { node = r ? r.node_id : null; nodeBtn.textContent = r ? `${r.code} ${r.name}` : 'Any CBS item'; load(); } }) }, 'Any CBS item');
  const amt = h('input', { type: 'number', step: '0.01', placeholder: 'whole amount', style: { width: '130px' } });
  const out = h('div'); const checks = [];
  body.append(h('div', { class: 'note', style: { marginBottom: '10px' } }, 'Tick the Pronto transactions whose cost landed because of the risk, then tag them. Tags follow the transaction through later Pronto uploads. Accruals and forecast items are tagged in their own dialogs (Risk field).'),
    h('div', { class: 'row', style: { marginBottom: '10px' } }, field('Risk', riskSel), field('Show', filt), field('Search', q), field('CBS', nodeBtn), field('Part amount (optional)', amt, 'Leave blank for the whole transaction'), h('button', { class: 'btn', style: { marginTop: '18px' }, onclick: load }, 'Search'),
      h('button', { class: 'btn', style: { marginTop: '18px' }, onclick: tag }, 'Tag ticked to this risk')), out);
  async function load() {
    const rows = await api.get(p(`/risk/transactions?${new URLSearchParams({ ...(node ? { node } : {}), ...(q.value ? { q: q.value } : {}), ...(filt.value ? { tagged: filt.value } : {}) })}`));
    checks.length = 0;
    clear(out).append(rows.length ? h('div', { class: 'tw', style: { maxHeight: '60vh' } }, h('table', { class: 't' }, h('thead', {}, h('tr', {}, ['', 'Date', 'Doc', 'CBS', 'Supplier / account', 'Reference', 'Description', 'Cost', 'Tagged to'].map((x, i) => h('th', { class: i === 7 ? 'r' : '' }, x)))),
      h('tbody', {}, rows.map((r) => { const c = h('input', { type: 'checkbox', value: r.row_hash }); checks.push(c); return h('tr', {}, h('td', {}, c), h('td', {}, fmt.date(r.tx_date)), h('td', {}, r.doc_type), h('td', { class: 'mono' }, r.node_code || ''), h('td', {}, r.account_desc || ''), h('td', {}, r.reference || ''), h('td', { class: 'wrap' }, r.description || ''), h('td', { class: 'r num' }, fmt.money(r.cost, 2)),
        h('td', {}, r.tags.map((g) => h('span', { class: 'badge navy', style: { marginRight: '4px', cursor: 'pointer' }, title: 'Click to untag', onclick: async () => { await api.del(p(`/risk/tag/${g.id}`)); load(); } }, `${g.ref}${g.amount !== null ? ' ' + fmt.money(g.amount) : ''} ×`)))); }))))
      : empty('No transactions', 'Nothing matches. Try clearing the filters.'));
  }
  async function tag() {
    const hs = checks.filter((c) => c.checked).map((c) => c.value);
    if (!hs.length) return toast('Tick at least one transaction', 'bad');
    await api.post(p('/risk/tag'), { risk_id: +riskSel.value, row_hashes: hs, amount: amt.value === '' ? null : num(amt.value) });
    toast(`${hs.length} transaction${hs.length > 1 ? 's' : ''} tagged`); load();
  }
  load();
}

// ---- funding risk costs ----------------------------------------------------------------------------------
async function releaseTab(body, d) {
  const rel = await api.get(p('/risk/releases'));
  const rows = state.rows.rows; const co = isCompany();
  body.append(h('div', { class: 'note', style: { marginBottom: '10px' } }, 'Step 1, yours: put contingency aside as risk cover (from any CBS item that has contingency). Do it when a risk cost lands, or ahead of time to save for a risk you can see coming. Step 2, the company: once contingency is used up and the risk has materialised with its invoice landed in Pronto, it releases from the risk bucket. Step 3, the company: if the bucket is not enough, it adds new funds. Each lands as risk cover on the CBS line that carries the cost.'));
  const cols = [{ label: 'CBS', f: (x) => h('span', { class: 'mono' }, x.category) }, { label: 'Name', f: (x) => x.name }, { label: 'Contingency', r: 1, f: (x) => fmt.money(x.contingency) }, { label: 'Risk cost occurred', r: 1, f: (x) => h('b', {}, fmt.money(x.occurred)) },
    { label: 'Set aside from contingency', r: 1, f: (x) => fmt.money(x.from_contingency) }, { label: 'Released', r: 1, f: (x) => fmt.money(x.released) }, { label: 'Infused', r: 1, f: (x) => fmt.money(x.infused) }, { label: 'Saved ahead', r: 1, f: (x) => x.over_covered > 1 ? fmt.money(x.over_covered) : '' }, { label: 'Uncovered', r: 1, f: (x) => x.uncovered > 1 ? h('b', { class: 'bad' }, fmt.money(x.uncovered)) : fmt.money(0) },
    { label: 'Next step', cls: 'wrap', f: (x) => x.uncovered > 1 ? h('span', { class: 'small' }, [x.step_contingency > 1 ? `1. contingency ${fmt.money(x.step_contingency)}` : null, x.step_release > 1 ? `2. release ${fmt.money(x.step_release)}` : null, x.step_infuse > 1 ? `3. infuse ${fmt.money(x.step_infuse)}` : null, x.uncovered - x.uncovered_landed > 1 ? `(${fmt.money(x.uncovered - x.uncovered_landed)} awaiting invoice)` : null].filter(Boolean).join('  ')) : '' },
    ...(co ? [{ label: 'Bucket left', r: 1, f: (x) => fmt.money(x.bucket_remaining) }] : []),
    { label: 'Status', f: (x) => badge(x.status, STATUS_TONE[x.status]) }, { label: '', f: (x) => h('button', { class: 'btn sm', onclick: () => fundDialog(x) }, 'Fund...') }];
  body.append(d.positions.length ? table(cols, d.positions) : empty('Nothing to fund', 'Positions appear once costs are tagged to risks.'));
  body.append(h('div', { class: 'card', style: { marginTop: '14px' } }, h('h2', {}, 'Funding entries'), rel.length ? table([{ label: 'Date', f: (r) => fmt.date(r.date) }, { label: 'Step', f: (r) => badge({ contingency: '1 Contingency', release: '2 Release', infuse: '3 Infusion' }[r.kind] || r.kind, { contingency: 'navy', release: 'warn', infuse: 'bad' }[r.kind]) }, { label: 'Reference', f: (r) => r.ref || '' },
    { label: 'Funds', f: (r) => `${r.target_code} ${r.target_name}` }, { label: 'From', f: (r) => r.kind === 'infuse' ? 'new company funds' : (r.source_code ? `${r.source_code} ${r.source_name}` : '') }, { label: 'Amount', r: 1, f: (r) => fmt.money(r.amount) }, { label: 'Approved by', f: (r) => r.approved_by || '' }, { label: 'Exception', f: (r) => r.forced ? badge('approved as exception', 'warn') : '' }, { label: 'Note', f: (r) => r.note || '' },
    { label: '', f: (r) => h('button', { class: 'btn danger sm', onclick: async () => { if (await confirmBox('Reverse this entry?', 'Reverse', true)) { await api.del(p(`/risk/releases/${r.id}`)); await render(); } } }, 'Reverse') }], rel) : h('div', { class: 'muted' }, 'No funding entries yet.')));

  function fundDialog(x) {
    const leaves = rows.filter((r) => r.category === x.category && (r.kind === 'line' || r.kind === 'pot'));
    const best = [...leaves].sort((a, b) => (b.ctd + b.acc) - (a.ctd + a.acc))[0];
    let target = best ? best.node_id : null; let source = target;
    const tBtn = h('button', { class: 'btn ghost', onclick: () => pickNode({ title: 'Which CBS line carries the risk cost?', kinds: ['line', 'pot'], filter: (r) => r.category === x.category, onPick: (r) => { target = r.node_id; tBtn.textContent = `${r.code} ${r.name}`; if (kind.value !== 'contingency' || sBtn.dataset.set !== '1') { source = target; sBtn.textContent = 'Same item'; } } }) }, best ? `${best.code} ${best.name}` : 'Choose...');
    const sBtn = h('button', { class: 'btn ghost', onclick: () => pickNode({ title: 'Take the contingency from which CBS item?', kinds: ['line', 'pot'], onPick: (r) => { source = r.node_id; sBtn.dataset.set = '1'; sBtn.textContent = `${r.code} ${r.name} (${fmt.money(r.cont_earmark)} contingency)`; } }) }, 'Same item');
    const kind = select([['contingency', '1. Transfer contingency into risk (PM)'], ['release', '2. Release from the company risk bucket'], ['infuse', '3. Infuse new company funds']], x.step_contingency > 1 ? 'contingency' : x.step_release > 1 ? 'release' : x.step_infuse > 1 ? 'infuse' : 'contingency');
    const amount = h('input', { type: 'number', step: '0.01' }); const date = h('input', { type: 'date', value: todayISO() }); const by = h('input', { type: 'text' }); const ref = h('input', { type: 'text', placeholder: 'Approval reference' }); const note = h('input', { type: 'text' });
    const force = h('input', { type: 'checkbox' }); const hint = h('div', { class: 'note' }); const srcField = field('Contingency comes from', sBtn, 'Any CBS item that has contingency; its budget moves across with it');
    const sync = () => {
      const sug = { contingency: x.step_contingency, release: x.step_release, infuse: x.step_infuse }[kind.value];
      amount.value = sug > 0 ? sug.toFixed(2) : '';
      srcField.classList.toggle('hide', kind.value !== 'contingency');
      by.value = kind.value === 'contingency' ? (state.project.epec_pm || '') : 'General Manager';
      hint.textContent = { contingency: `Your own contingency, put aside as risk cover on the line that carries the cost, or saved ahead for a risk that may still happen. No invoice is needed. ${fmt.money(x.contingency)} of contingency is held on ${x.category}.`,
        release: `Company money, from the risk bucket${co ? ` (${fmt.money(x.bucket_remaining)} still held on ${x.category})` : ''} into this line's budget as risk cover. Only for risk whose invoice has landed in Pronto (${fmt.money(x.uncovered_landed)} here), and normally once contingency is used up.`,
        infuse: 'New company money, when more risk has occurred than the bucket allowed for. Normally only once contingency and the bucket are used up.' }[kind.value];
    };
    kind.onchange = sync; sync();
    modal({ title: `Fund risk cost: ${x.category} ${x.name}`, size: 'wide', body: h('div', { class: 'grid' },
      h('div', { class: 'grid g4' }, kp('Risk cost occurred', fmt.money(x.occurred)), kp('Already covered', fmt.money(x.cover)), kp('Uncovered', fmt.money(x.uncovered)), kp('Contingency held', fmt.money(x.contingency))),
      field('Funding step', kind), hint, field('Cover the risk cost on', tBtn), srcField, h('div', { class: 'grid g2' }, field('Amount', amount), field('Date', date)), h('div', { class: 'grid g2' }, field('Approved by', by), field('Reference', ref)), field('Note', note),
      h('label', { class: 'row small' }, force, 'Approve as an exception (company funds ahead of the invoice, or out of the usual order)')),
      actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} }, { label: 'Post funding', onClick: async () => {
        if (!target) throw new Error('Choose the line that carries the cost');
        await api.post(p('/risk/fund'), { kind: kind.value, target_node_id: target, source_node_id: kind.value === 'contingency' ? source : null, amount: num(amount.value), date: date.value, approved_by: by.value, ref: ref.value, note: note.value, force: force.checked });
        toast('Funding posted to the allowance'); await render(); } }] });
  }
  function kp(l, v) { return h('div', { class: 'kpi' }, h('div', { class: 'l' }, l), h('div', { class: 'v', style: { fontSize: '16px' } }, v)); }
}

// ---- close-out ----------------------------------------------------------------------------------------
export async function closeoutTab(body) {
  const c = await api.get(p('/risk/closeout'));
  const bx = c.by_risk;
  const refs = Object.keys(c.by_event);
  let view = sessionStorage.getItem('riskView') || 'cbs';
  const kpi = (l, v, s, cl = '') => h('div', { class: 'kpi ' + cl }, h('div', { class: 'l' }, l), h('div', { class: 'v', style: { fontSize: '19px' } }, v), h('div', { class: 's' }, s));
  body.append(h('div', { class: 'row', style: { marginBottom: '10px' } }, h('div', { class: 'note', style: { flex: 1 } }, 'For the estimator: how much risk really occurred, per CBS item and overall, how it was funded, and the risk percentage each item turned out to need. Use it to price risky items with more risk and safer items with less, and to challenge the blanket percentage on the next job. Each CBS item can also be read as the risk events behind it, or each event as the CBS items it hit.'),
    h('button', { class: 'btn', onclick: () => window.open(p('/risk/closeout.xlsx')) }, 'Download for the estimator (Excel)')));
  const t = c.totals;
  const over = t.overrun_vs_estimate;
  body.append(h('div', { class: 'grid g5', style: { marginBottom: '14px', gridTemplateColumns: 'repeat(5, minmax(0, 1fr))' } }, kpi('Risk the estimate allowed', fmt.money(t.orig_risk), `${fmt.pct(t.estimated_pct)} of budget, one blanket rate`), kpi('Risk that occurred', fmt.money(t.risk_needed), `${fmt.pct(t.actual_pct)} of budget`, 't2'),
    kpi(over > 0 ? 'More than allowed' : 'Less than allowed', fmt.money(Math.abs(over)), over > 0 ? 'Company funds were needed beyond the estimate' : 'Unused risk returns to margin', over > 0 ? 't2' : 't3'), kpi('How it was funded', `${fmt.m(t.from_contingency)} / ${fmt.m(t.released)} / ${fmt.m(t.infused)}`, 'Contingency / released / infused', 't4'),
    kpi('Suggested risk % next job', fmt.pct(t.suggested_overall_pct), 'Overall, from this project', 't5')));
  const sw = h('div'); const out = h('div'); body.append(sw, out);
  const draw = () => {
    clear(sw).append(tabs([['cbs', 'By CBS item: which events drove it'], ['event', 'By risk event: which CBS it hit'], ['matrix', 'Matrix: CBS by event'], ['impact', 'Time and revenue impact']], view, (k) => { view = k; sessionStorage.setItem('riskView', k); draw(); }));
    clear(out);
    if (view === 'cbs') return byCbs(); if (view === 'event') return byEvent(); if (view === 'impact') return impact(); return matrix();
  };
  function byCbs() {
    const tb = h('tbody');
    c.rows.forEach((r) => {
      tb.append(h('tr', { class: 'par' }, h('td', { class: 'mono' }, r.category), h('td', {}, r.name), h('td', { class: 'r num' }, fmt.money(r.orig_budget)), h('td', { class: 'r num' }, fmt.money(r.orig_risk)), h('td', { class: 'r num' }, fmt.pct(r.risk_pct_estimated)), h('td', { class: 'r num' }, fmt.money(r.risk_needed)),
        h('td', { class: 'r num' }, h('b', {}, fmt.pct(r.suggested_risk_pct))), h('td', { class: 'r num' }, fmt.money(r.from_contingency)), h('td', { class: 'r num' }, fmt.money(r.released)), h('td', { class: 'r num ' + (r.infused ? 'bad' : '') }, fmt.money(r.infused))));
      r.events.forEach((e) => tb.append(h('tr', {}, h('td'), h('td', { style: { paddingLeft: '28px' } }, h('span', { class: 'badge navy' }, e.ref), ' ', e.title), h('td'), h('td'), h('td'), h('td', { class: 'r num' }, fmt.money(e.risk_funded)), h('td', { class: 'r num' }, e.pct_of_budget === null ? '' : fmt.pct(e.pct_of_budget)), h('td', { colSpan: 3, class: 'muted small' }, fmt.pct(e.share, 0) + ' of this item\'s risk cost'))));
    });
    out.append(h('div', { class: 'tw' }, h('table', { class: 't' }, h('thead', {}, h('tr', {}, ['CBS', 'Name', 'Estimated budget', 'Estimated risk', 'Estimated %', 'Risk that occurred', 'Needed % of budget', 'From contingency', 'Released', 'Infused'].map((x, i) => h('th', { class: i >= 2 ? 'r' : '', title: x === 'Needed % of budget' ? 'The risk percentage this item turned out to need: a starting point for the next estimate' : '' }, x)))), tb)));
  }
  async function impact() {
    const rk = (await api.get(p('/risk'))).risks.filter((r) => (r.kind || 'Risk') === 'Risk' && (r.delay_days || r.delay_actual || r.revenue_impact || r.revenue_actual || r.realised));
    if (!rk.length) { out.append(empty('No time or revenue impacts recorded', 'Enter the delay in days and the revenue lost or deferred on each risk event in the register.')); return; }
    const sum = (k) => rk.reduce((a, r) => a + (r[k] || 0), 0);
    out.append(h('div', { class: 'note', style: { marginBottom: '10px' } }, 'The cost of each event is only part of its effect. Delay pushes out the project schedule and revenue lost or deferred comes straight off margin. Compare what the estimate assumed with what occurred, event by event.'),
      table([{ label: 'Ref', f: (r) => h('b', {}, r.ref) }, { label: 'Event', cls: 'wrap', f: (r) => r.title }, { label: 'Status', f: (r) => badge(r.status) },
        { label: 'Delay est. (days)', r: 1, f: (r) => fmt.n(r.delay_days, 0) }, { label: 'Delay occurred', r: 1, f: (r) => fmt.n(r.delay_actual, 0) },
        { label: 'Revenue impact est.', r: 1, f: (r) => fmt.money(r.revenue_impact) }, { label: 'Revenue impact occurred', r: 1, f: (r) => fmt.money(r.revenue_actual) },
        { label: 'Risk cost reserved', r: 1, f: (r) => fmt.money(r.residual) }, { label: 'Risk cost occurred', r: 1, f: (r) => fmt.money(r.realised) },
        { label: 'Total margin hit', r: 1, f: (r) => h('b', {}, fmt.money(r.realised + (r.revenue_actual || 0))) }], rk,
      { foot: (col) => ({ Ref: 'Total', 'Delay est. (days)': fmt.n(sum('delay_days'), 0), 'Delay occurred': fmt.n(sum('delay_actual'), 0), 'Revenue impact est.': fmt.money(sum('revenue_impact')), 'Revenue impact occurred': fmt.money(sum('revenue_actual')), 'Risk cost reserved': fmt.money(sum('residual')), 'Risk cost occurred': fmt.money(sum('realised')), 'Total margin hit': fmt.money(sum('realised') + sum('revenue_actual')) }[col.label]) }));
  }
  function byEvent() {
    if (!bx.events.length) { out.append(empty('No risk costs tagged', 'Tag costs to risk events to see which CBS items each one hit.')); return; }
    const tb = h('tbody');
    bx.events.forEach((x) => {
      tb.append(h('tr', { class: 'par' }, h('td', { class: 'mono' }, x.ref), h('td', {}, x.title), h('td', { class: 'r num' }, fmt.money(x.planned)), h('td', { class: 'r num' }, fmt.money(x.tagged)), h('td', { class: 'r num ' + (x.planned && x.tagged > x.planned ? 'bad' : '') }, x.planned ? fmt.pct(x.tagged / x.planned, 0) : ''), h('td', { class: 'r num' }, fmt.money(x.risk_funded)), h('td'), h('td', {}, badge(x.status || '', { materialised: 'warn', open: 'navy' }[x.status]))));
      x.categories.forEach((k) => tb.append(h('tr', {}, h('td'), h('td', { style: { paddingLeft: '28px' } }, h('span', { class: 'mono' }, k.category), ' ', k.name), h('td'), h('td', { class: 'r num' }, fmt.money(k.tagged)), h('td', { class: 'r num muted' }, k.pct_of_event === null ? '' : fmt.pct(k.pct_of_event, 0) + ' of event'), h('td', { class: 'r num' }, fmt.money(k.risk_funded)), h('td', { class: 'r num' }, k.pct_of_budget === null ? '' : fmt.pct(k.pct_of_budget) + ' of CBS budget'), h('td'))));
    });
    out.append(h('div', { class: 'tw' }, h('table', { class: 't' }, h('thead', {}, h('tr', {}, ['Risk', 'Event / CBS item', 'Planned reserve', 'Tagged cost', 'Against reserve', 'Risk funded', 'Of CBS budget', 'Status'].map((x, i) => h('th', { class: i >= 2 && i <= 6 ? 'r' : '' }, x)))), tb)));
  }
  function matrix() {
    if (!bx.refs.length) { out.append(empty('No risk costs tagged', 'Nothing to show yet.')); return; }
    const names = Object.fromEntries(c.rows.map((r) => [r.category, r.name]));
    const colTot = bx.refs.map((r) => Object.values(bx.matrix).reduce((a, v) => a + (v[r] || 0), 0));
    const tb = h('tbody', {}, Object.entries(bx.matrix).map(([cat, v]) => h('tr', {}, h('td', { class: 'mono' }, cat), h('td', {}, names[cat] || ''), ...bx.refs.map((r) => h('td', { class: 'r num' }, v[r] ? fmt.money(v[r]) : '')), h('td', { class: 'r num', style: { fontWeight: 700 } }, fmt.money(Object.values(v).reduce((a, x) => a + x, 0))))));
    out.append(h('div', { class: 'tw' }, h('table', { class: 't' }, h('thead', {}, h('tr', {}, ['CBS', 'Name', ...bx.events.map((e) => e.ref), 'Total'].map((x, i) => h('th', { class: i >= 2 ? 'r' : '', title: i >= 2 && bx.events[i - 2] ? bx.events[i - 2].title : '' }, x)))), tb, h('tfoot', {}, h('tr', {}, h('td'), h('td', {}, 'Total'), ...colTot.map((v) => h('td', { class: 'r num' }, fmt.money(v))), h('td', { class: 'r num' }, fmt.money(colTot.reduce((a, b) => a + b, 0))))))));
    const box = h('div', { class: 'chartbox' }); out.append(h('div', { class: 'card', style: { marginTop: '14px' } }, h('h2', {}, 'Tagged risk cost by CBS, split by event'), box));
    const cats = Object.keys(bx.matrix);
    chart(box, { type: 'bar', data: { labels: cats, datasets: bx.refs.map((r, i) => ({ label: r, data: cats.map((c2) => bx.matrix[c2][r] || 0), backgroundColor: PALETTE[i % PALETTE.length] })) }, options: { scales: { x: { stacked: true }, y: { stacked: true } } } });
  }
  draw();
}
