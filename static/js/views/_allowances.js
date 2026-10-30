import { h, clear, fmt, modal, toast, field, num, empty } from '../ui.js';
import { api, p, state } from '../api.js';
import { monthInput } from '../monthplan.js';

// ALLOWANCES > Allowance: the workspace for assigning money. Left, the estimate pots per CBS (grandparent, parent, child); right, the CBS lines
// in the same tree. Drag a pot across onto a line or a group to assign money; drag a line back onto a pot to return it. Drag a row up or
// down to reorder it among its siblings (same parent only). Tick several pots and lines to allocate in one go. Every move is a ledger transfer.
const SRC = { estimate: 'Estimate', variation: 'Variation', release: 'Risk released', infuse: 'Risk infused', adjust: 'Adjustment', contingency_set: 'Contingency set aside' };
const PAYLOAD = 'application/x-pmt-ws';   // what a drag carries, so it can be dropped in another window of the same browser
const cents = (x) => Math.round(x * 100) / 100;
const floor2 = (x) => Math.floor(x * 100) / 100;

export async function allowanceTab(body) {
  const [ov, cc] = await Promise.all([api.get(p('/allowance/overview')), api.get(p('/cost-control?months=0'))]);
  const rows = cc.rows; const WIN = () => cc.windows || {}; const byId = new Map(); const kidsOf = new Map(); const bk = new Map();
  const key = (v) => (v == null ? '' : String(v));
  function index() {
    byId.clear(); kidsOf.clear(); bk.clear();
    rows.forEach((r) => { if (r.kind === 'pot') return; byId.set(String(r.id), r); });
    rows.forEach((r) => { if (r.kind === 'pot' || r.active === 0) return; const k = key(r.parent_id); if (!kidsOf.has(k)) kidsOf.set(k, []); kidsOf.get(k).push(r); });
    ov.buckets.forEach((b) => bk.set(String(b.id), b));
  }
  index();
  const need = (l) => Math.max(0, (l.eac || 0) - (l.allowance || 0));
  const fundable = (l) => l.kind === 'line' && l.origin !== 'ctc' && l.origin !== 'wip';
  const descLines = (g) => (kidsOf.get(String(g.id)) || []).flatMap((c) => (c.kind === 'line' ? (fundable(c) ? [c] : []) : descLines(c)));
  const roots = () => kidsOf.get('') || [];

  const SK = `ws:${p('')}`; const load = (k, d) => { try { return JSON.parse(sessionStorage.getItem(SK + k) || 'null') ?? d; } catch (e) { return d; } };
  const save = (k, v) => { try { sessionStorage.setItem(SK + k, JSON.stringify(v)); } catch (e) { /* ignore */ } };
  const openL = new Set(load('L', roots().map((r) => String(r.id)))); const openR = new Set(load('R', roots().map((r) => String(r.id))));
  const selP = new Set(); const selL = new Set();
  // which of the optional columns of the lines pane are shown (kept on this PC); the other columns share the room
  const OPT = [['Start', 3], ['End', 4], ['Mths', 5], ['Short', 7]];
  const TRACKS = ['14px', 'minmax(100px,4fr)', 'minmax(42px,1.1fr)', 'minmax(42px,1.1fr)', 'minmax(22px,.55fr)', 'minmax(52px,1.5fr)', 'minmax(46px,1.4fr)', '16px'];
  let hidCols = new Set(); try { hidCols = new Set(JSON.parse(localStorage.getItem('wsCols') || '[]')); } catch (e) { /* storage may be blocked */ }
  const colsOn = (pos) => !hidCols.has(pos);
  // the two panes can sit in separate windows (or screens): the windows share what is selected and refresh each other
  const hashQ = new URLSearchParams(location.hash.split('?')[1] || ''); const pane = hashQ.get('solo') === '1' ? (hashQ.get('pane') || 'both') : 'both';
  let ch = null; try { ch = new BroadcastChannel(`pmt-ws:${state.pid}`); } catch (e) { /* no channel: each window works on its own */ }
  let lastSig = '';
  const extOf = (e) => { try { return JSON.parse(e.dataTransfer.getData(PAYLOAD) || 'null'); } catch (x) { return null; } };
  const extDrag = (e) => !drag && e.dataTransfer && [...(e.dataTransfer.types || [])].includes(PAYLOAD);
  let q = ''; let qp = ''; let showEmpty = false; let onlyShort = false; let drag = null;

  const wrap = h('div'); const left = h('div', { class: 'ws-list' }); const right = h('div', { class: 'ws-list' });
  const lead = h('div', { class: 'ws-lead' }); const act = h('div', { class: 'ws-act' });

  // ---- which rows show ----
  const potText = (b) => `${b.code} ${b.name} ${b.category || ''} ${(b.sources || []).map((x) => `${x.kind} ${x.ref || ''}`).join(' ')}`.toLowerCase();
  const potVisible = (b) => b && (showEmpty || b.available > 0.5 || b.risk > 0.5) && (!qp || potText(b).includes(qp));
  const leftShows = (g) => g.kind === 'group' && (potVisible(bk.get(String(g.id))) || (kidsOf.get(String(g.id)) || []).some(leftShows));
  const lineShows = (l) => (!q || `${l.code} ${l.name} ${l.resource_code || ''} ${l.resource_name || ''}`.toLowerCase().includes(q)) && (!onlyShort || need(l) > 0.5);
  const rightShows = (n) => (n.kind === 'line' ? lineShows(n) : (kidsOf.get(String(n.id)) || []).some(rightShows));

  // ---- drag: across assigns, up or down reorders ----
  const clearMarks = () => wrap.querySelectorAll('.ws-over,.ws-before,.ws-after').forEach((x) => x.classList.remove('ws-over', 'ws-before', 'ws-after'));
  const startDrag = (el, mk) => {
    el.addEventListener('dragstart', (e) => { e.stopPropagation(); drag = mk(); e.dataTransfer.effectAllowed = 'move'; try { e.dataTransfer.setData('text/plain', drag.node.code || ''); e.dataTransfer.setData(PAYLOAD, JSON.stringify({ from: drag.from, pots: (drag.pots || []).map((b) => b.id), node: drag.node.id })); } catch (x) { /* ignore */ } document.body.classList.add('ws-dragging'); });
    el.addEventListener('dragend', () => { drag = null; document.body.classList.remove('ws-dragging'); clearMarks(); });
  };
  const potsOf = (b) => (selP.has(String(b.id)) ? ov.buckets.filter((x) => selP.has(String(x.id))) : [b]);
  const sortTarget = (el, node, pane) => {
    const ok = () => drag && drag.from === pane && String(drag.node.id) !== String(node.id) && key(drag.node.parent_id) === key(node.parent_id) && drag.node.kind === node.kind;
    const after = (e) => { const r = el.getBoundingClientRect(); return e.clientY > r.top + r.height / 2; };
    el.addEventListener('dragover', (e) => { if (!ok()) return; e.preventDefault(); const a = after(e); el.classList.toggle('ws-after', a); el.classList.toggle('ws-before', !a); });
    el.addEventListener('dragleave', () => el.classList.remove('ws-before', 'ws-after'));
    el.addEventListener('drop', (e) => { if (!ok()) return; e.preventDefault(); e.stopPropagation(); const a = after(e); clearMarks(); reorderTo(drag.node, node, a); });
  };
  const reorderTo = async (dn, tn, after) => {
    const ids = (kidsOf.get(key(dn.parent_id)) || []).map((x) => x.id).filter((id) => String(id) !== String(dn.id));
    const at = ids.findIndex((id) => String(id) === String(tn.id)); if (at < 0) return;
    ids.splice(at + (after ? 1 : 0), 0, dn.id);
    try { await api.post(p('/reorder/cbs'), { ids }); await reload(); } catch (e) { toast(e.message, 'bad'); }
  };
  const fundTarget = (el, onDrop) => {
    el.addEventListener('dragover', (e) => { if ((drag && drag.pots) || extDrag(e)) { e.preventDefault(); el.classList.add('ws-over'); } });
    el.addEventListener('dragleave', () => el.classList.remove('ws-over'));
    el.addEventListener('drop', (e) => {
      const pots = drag && drag.pots ? drag.pots : (() => { const x = extOf(e); return x && x.pots && x.pots.length ? x.pots.map((id) => bk.get(String(id))).filter(Boolean) : null; })();
      if (!pots) return; e.preventDefault(); e.stopPropagation(); el.classList.remove('ws-over'); onDrop(pots);
    });
  };
  const returnTarget = (el, b) => {
    const ok = () => drag && drag.from === 'right' && drag.node.kind === 'line';
    el.addEventListener('dragover', (e) => { if (ok() || extDrag(e)) { e.preventDefault(); el.classList.add('ws-over'); } });
    el.addEventListener('dragleave', () => el.classList.remove('ws-over'));
    el.addEventListener('drop', (e) => {
      const line = ok() ? drag.node : (() => { const x = extOf(e); const n = x && x.from === 'right' ? byId.get(String(x.node)) : null; return n && n.kind === 'line' ? n : null; })();
      if (!line) return; e.preventDefault(); e.stopPropagation(); el.classList.remove('ws-over'); giveBack(line, b);
    });
  };

  // ---- the two trees ----
  const lvCls = (n, hasKids) => (!hasKids ? 'leaf' : n.level === 1 ? 'lv1' : n.level === 2 ? 'lv2' : 'lv3');
  const chev = (open, has) => h('span', { class: 'ws-chev' }, has ? (open ? '▾' : '▸') : '');
  const tick = (on, fn, title) => h('span', { class: 'ws-tick' + (on ? ' on' : ''), title, onclick: (e) => { e.stopPropagation(); fn(); } }, on ? '✓' : '');

  function leftNode(g, out) {
    if (!leftShows(g)) return;
    const b = bk.get(String(g.id)); const own = potVisible(b); const gk = (kidsOf.get(String(g.id)) || []).filter((c) => c.kind === 'group' && leftShows(c));
    const isOpen = qp || openL.has(String(g.id));
    const el = h('div', { class: `ws-n ${lvCls(g, gk.length > 0)}${own && selP.has(String(g.id)) ? ' sel' : ''}`, style: { paddingLeft: 10 + (g.level - 1) * 14 + 'px' }, draggable: 'true',
      title: own ? 'Click to select it (click again to deselect). Drag across onto a line to assign. Drag up or down to reorder' : 'Drag up or down to reorder within its parent' },
      chev(isOpen, gk.length > 0), own ? tick(selP.has(String(g.id)), () => { const k = String(g.id); if (selP.has(k)) selP.delete(k); else selP.add(k); draw(); }, 'Select this pot') : h('span', { class: 'ws-tick ghost' }),
      h('div', { class: 'ws-main' }, h('div', { class: 'ws-t' }, h('span', { class: 'mono ws-code' }, g.code), ' ', g.name),
        own ? h('div', { class: 'ws-sub' }, (b.sources.length ? b.sources.map((s) => `${SRC[s.kind] || s.kind}${s.ref && s.kind !== 'estimate' ? ' ' + s.ref : ''} ${fmt.m(s.budget + s.risk)}`).join(' · ') : 'No source recorded'), b.parked > 0.5 ? ` · ${fmt.m(b.parked)} cost already on it` : '') : null),
      own ? h('div', { class: 'r num ws-amt' }, h('b', {}, fmt.money(b.available)), b.risk > 0.5 ? h('div', { class: 'ws-sub' }, `+ ${fmt.money(b.risk)} risk`) : null) : null);
    const toggleSel = () => { const k = String(g.id); if (selP.has(k)) selP.delete(k); else selP.add(k); draw(); };
    const toggleOpen = () => { const k = String(g.id); if (openL.has(k)) openL.delete(k); else openL.add(k); save('L', [...openL]); draw(); };
    // a pot highlights on click and clears on a second click; the arrow opens or closes its children. A heading with no pot of its own opens or closes.
    el.addEventListener('click', (e) => { if (own && !(gk.length && e.target.closest('.ws-chev'))) toggleSel(); else if (gk.length) toggleOpen(); });
    startDrag(el, () => (own ? { from: 'left', pots: potsOf(b), node: g } : { from: 'left', node: g })); sortTarget(el, g, 'left'); if (own) returnTarget(el, b);
    out.push(el);
    if (isOpen) gk.forEach((c) => leftNode(c, out));
  }

  // ---- Start, End, Months on a line: the same window as Cost control (typed, from a duration, or following the project schedule) ----
  const mlast = (v) => { const [y, m] = v.split('-').map(Number); return `${v}-${String(new Date(y, m, 0).getDate()).padStart(2, '0')}`; };
  const mdiff = (a, b) => { const [y1, m1] = a.split('-').map(Number); const [y2, m2] = b.split('-').map(Number); return (y2 - y1) * 12 + m2 - m1 + 1; };
  function windowCells(r) {
    const w = WIN()[String(r.node_id)] || {}; const drv = (k) => (w[k] && !w[k].suspended ? w[k] : null);
    const eff = (k, own) => (own ? own.slice(0, 7) : String(r[k] || '').slice(0, 7));
    const sIn = monthInput(eff('start', r.start_own)); const eIn = monthInput(eff('end', r.end_own));
    const mIn = h('input', { type: 'number', min: 1, step: 1, value: sIn.ym && eIn.ym ? mdiff(sIn.ym, eIn.ym) : '' });
    const mark = (inp, k, own) => {
      inp.classList.add('ws-inl'); inp.addEventListener('click', (e) => e.stopPropagation()); inp.draggable = false; inp.addEventListener('dragstart', (e) => e.preventDefault());
      if (drv(k)) { inp.classList.add('drv'); inp.title = `Follows the project schedule: ${drv(k).task} (${drv(k).edge === 'start' ? 'start' : 'finish'}). Type to override it.`; }
      else if (w[k] && w[k].suspended) { inp.classList.add('ovr'); inp.title = `Typed over the schedule (${w[k].task}).`; }
      else if (!own) { inp.classList.add('inh'); inp.title = 'Inherited from the group above. Type to set this line\'s own window.'; }
    };
    mark(sIn, 'start', r.start_own); mark(eIn, 'stop', r.end_own); mIn.classList.add('ws-inl', 'mo'); mIn.title = 'Duration in months';
    const keep = (role, v, typed) => (drv(role) ? { mode: 'schedule', task_id: drv(role).task_id, edge: drv(role).edge } : typed(v));
    const tS = (v) => (v ? { mode: 'typed', date: v + '-01' } : { mode: 'typed' }); const tE = (v) => (v ? { mode: 'typed', date: mlast(v) } : { mode: 'typed' });
    async function commit(which) {
      const sv = sIn.ym; const ev = eIn.ym; const m = +mIn.value || 0; let a; let b; let months = null;
      if (which === 'start') { a = tS(sv); if (ev && (!sv || sv <= ev)) b = keep('stop', ev, tE); else if (m > 0) { b = { mode: 'duration' }; months = m; } else b = tE(''); }
      else if (which === 'stop') { b = tE(ev); if (sv && (!ev || sv <= ev)) a = keep('start', sv, tS); else if (m > 0) { a = { mode: 'duration' }; months = m; } else a = tS(''); }
      else { if (m < 1) return; if (sv) { a = keep('start', sv, tS); b = { mode: 'duration' }; months = m; } else if (ev) { b = keep('stop', ev, tE); a = { mode: 'duration' }; months = m; } else return toast('Fill in Start or End first, then the months', 'bad'); }
      try { await api.post(p(`/nodes/${r.node_id}/window`), { start: a, stop: b, months }); await reload(); } catch (err) { toast(err.message, 'bad'); }
    }
    sIn.addEventListener('change', () => commit('start')); eIn.addEventListener('change', () => commit('stop')); mIn.addEventListener('change', () => commit('months'));
    return [sIn, eIn, mIn];
  }

  function lineRow(l) {
    const n = need(l); const k = String(l.id);
    const el = h('div', { class: 'ws-line' + (n > 0.5 ? ' short' : '') + (selL.has(k) ? ' sel' : ''), style: { paddingLeft: 10 + (l.level - 1) * 14 + 'px' }, draggable: 'true', title: 'Drag up or down to reorder within its group. Drop a pot from the left onto it to assign money. Drag it onto a pot to return money' },
      tick(selL.has(k), () => { if (selL.has(k)) selL.delete(k); else selL.add(k); draw(); }, 'Select this line'),
      h('div', { class: 'ws-main' }, h('div', { class: 'ws-t' }, h('span', { class: 'mono ws-code' }, l.code), ' ', l.name, l.resource_code ? h('span', { class: 'ws-sub', style: { marginLeft: '6px' } }, l.resource_code) : null)),
      ...windowCells(l).filter((_, i) => colsOn(i + 3)),
      h('div', { class: 'r num ws-amt' }, h('b', {}, fmt.money(l.allowance))), colsOn(7) ? h('div', { class: 'r num ws-sub ' + (n > 0.5 ? 'bad' : '') }, n > 0.5 ? `short ${fmt.money(n)}` : 'covered') : null,
      h('button', { class: 'ws-back', title: 'Send money back to the pot it came from', onclick: (e) => { e.stopPropagation(); giveBack(l); } }, '↩'));
    el.addEventListener('click', () => { if (selL.has(k)) selL.delete(k); else selL.add(k); draw(); });   // clicking a line only selects it; the amount window opens from Allocate
    fundTarget(el, (pots) => (pots.length === 1 ? assign(pots[0], l) : allocate(pots, [l])));
    startDrag(el, () => ({ from: 'right', node: l })); sortTarget(el, l, 'right');
    return el;
  }
  function rightNode(n, out) {
    if (!rightShows(n)) return;
    if (n.kind === 'line') { out.push(lineRow(n)); return; }
    const ls = descLines(n).filter(lineShows); const gk = (kidsOf.get(String(n.id)) || []).filter(rightShows);
    const hasKids = gk.length > 0; const isOpen = q || onlyShort || openR.has(String(n.id)); const short = ls.reduce((a, l) => a + need(l), 0);
    const all = ls.length && ls.every((l) => selL.has(String(l.id)));
    const el = h('div', { class: `ws-n ${lvCls(n, true)}`, style: { paddingLeft: 10 + (n.level - 1) * 14 + 'px' }, draggable: 'true', title: 'Click to open or close. Tick to select all its lines. Drag up or down to reorder. Drop a pot here to spread it over its lines' },
      chev(isOpen, true), ls.length ? tick(all, () => { ls.forEach((l) => (all ? selL.delete(String(l.id)) : selL.add(String(l.id)))); draw(); }, 'Select every line in this group') : h('span', { class: 'ws-tick ghost' }),
      h('div', { class: 'ws-main' }, h('div', { class: 'ws-t' }, h('span', { class: 'mono ws-code' }, n.code), ' ', n.name, h('span', { class: 'ws-sub', style: { marginLeft: '8px' } }, `${ls.length} lines`), short > 0.5 ? h('span', { class: 'ws-sub bad', style: { marginLeft: '8px' } }, `short ${fmt.m(short)}`) : null)));
    el.addEventListener('click', () => { const k = String(n.id); if (openR.has(k)) openR.delete(k); else openR.add(k); save('R', [...openR]); draw(); });
    fundTarget(el, (pots) => allocate(pots, descLines(n))); startDrag(el, () => ({ from: 'right', node: n })); sortTarget(el, n, 'right');
    out.push(el);
    if (isOpen) gk.forEach((c) => rightNode(c, out));
  }

  function draw() {
    const sl = left.scrollTop; const sr = right.scrollTop;
    [...selP].forEach((k) => { const b = bk.get(k); if (!b) selP.delete(k); }); [...selL].forEach((k) => { if (!byId.has(k)) selL.delete(k); });
    const L = []; roots().forEach((g) => leftNode(g, L)); const R = []; roots().forEach((g) => rightNode(g, R));
    const headL = h('div', { class: 'ws-colhead ws-headL' }, h('span', { class: 'ws-title' }, 'Estimate pots'), h('span', { class: 'r' }, 'Available'));
    const headR = h('div', { class: 'ws-colhead' }, ...[h('span'), h('span', { class: 'ws-title' }, 'CBS resource and cost lines'), h('span', {}, 'Start'), h('span', {}, 'End'), h('span', { class: 'r' }, 'Mths'), h('span', { class: 'r' }, 'Allowance'), h('span', { class: 'r' }, 'Short'), h('span')].filter((_, i) => colsOn(i + 1)));
    right.classList.toggle('wsc', hidCols.size > 0); right.style.setProperty('--wsc', TRACKS.filter((_, i) => colsOn(i + 1)).join(' '));
    clear(left).append(headL, ...(L.length ? L : [empty('Nothing to assign', 'Every pot is spent or assigned. Approved variations and risk the company releases to this project show up here.')]));
    clear(right).append(headR, ...(R.length ? R : [empty('No lines match', 'Change the filter, or add lines on CBS and allowances.')]));
    left.scrollTop = sl; right.scrollTop = sr;
    const sig = JSON.stringify([[...selP].sort(), [...selL].sort()]); if (sig !== lastSig) { lastSig = sig; if (ch) ch.postMessage({ type: 'sel', pots: [...selP], lines: [...selL] }); }
    const pots = ov.buckets.filter((b) => selP.has(String(b.id))); const lns = [...selL].map((k) => byId.get(k)).filter(Boolean);
    const free = pots.reduce((a, b) => a + b.available, 0);
    clear(act);
    if (pots.length || lns.length) {
      act.append(...[h('span', { class: 'ws-sub' }, `${pots.length} pot${pots.length === 1 ? '' : 's'} (${fmt.money(free)} free) · ${lns.length} line${lns.length === 1 ? '' : 's'}`),
        pots.length && lns.length ? h('button', { class: 'ws-pill', onclick: () => (pots.length === 1 && lns.length === 1 ? assign(pots[0], lns[0]) : allocate(pots, lns)) }, 'Allocate') : null,
        h('button', { class: 'ws-link', onclick: () => { selP.clear(); selL.clear(); draw(); } }, 'Clear selection')].filter(Boolean));
    }
  }

  // ---- one pot to one line (budget and risk) ----
  function assign(pot, line) {
    const free = pot.available; const n = need(line); const bud0 = Math.min(free, n > 0.5 ? n : free);
    const b = h('input', { type: 'text', inputmode: 'decimal', value: String(floor2(bud0)), style: { width: '130px', textAlign: 'right' } });
    const r = h('input', { type: 'text', inputmode: 'decimal', value: String(floor2(Math.min(pot.risk, Math.max(0, n - bud0)))), style: { width: '130px', textAlign: 'right' } });
    const msg = h('div', { class: 'small', style: { marginTop: '6px' } });
    const chk = () => { const bb = num(b.value); const rr = num(r.value); const bad = bb > free + 1 || rr > pot.risk + 1; msg.className = 'small ' + (bad ? 'bad' : 'muted'); msg.textContent = bad ? `The pot has ${fmt.money(free)} budget${pot.risk > 0 ? ` and ${fmt.money(pot.risk)} risk` : ''} free.` : `${pot.code} keeps ${fmt.money(free - bb)}; ${line.code} goes to ${fmt.money((line.allowance || 0) + bb)}.`; };
    [b, r].forEach((x) => x.addEventListener('input', chk)); chk();
    modal({ title: `Assign from ${pot.code} to ${line.code} ${line.name}`, body: h('div', { class: 'grid' },
      h('div', { class: 'note' }, `${pot.code} ${pot.name} has ${fmt.money(free)} free. ${line.code} has ${fmt.money(line.allowance)} and is forecast at ${fmt.money(line.eac)}${n > 0.5 ? `, short by ${fmt.money(n)}` : ''}.`),
      h('div', { class: 'grid g2' }, field('Budget to assign', b), field('Risk to assign', r, `Risk held on the pot: ${fmt.money(pot.risk)}`)), msg),
      actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} }, { label: 'Assign', onClick: async () => {
        let bb = num(b.value); let rr = num(r.value);
        if (!(bb > 0 || rr > 0)) throw new Error('Enter an amount');
        if (bb > free + 1 || rr > pot.risk + 1) throw new Error(`The pot has ${fmt.money(free)} budget and ${fmt.money(pot.risk)} risk free`);
        bb = Math.min(bb, floor2(free)); rr = Math.min(rr, floor2(pot.risk));   // the screen shows whole dollars, so typing what it shows may be a few cents over
        await api.post(p('/ledger/transfer'), { from_id: pot.id, to_id: line.node_id, budget: bb, risk: rr, ref: 'ASSIGN', note: 'Assigned in the Allowances workspace' });
        toast(`Assigned ${fmt.money(bb + rr)} to ${line.code}. Every move is in the Ledger tile.`); await reload();
      } }] });
  }

  // ---- several pots, several lines: each line gets its amount, each pot gives in proportion to what it has free ----
  function allocate(pots, ls, mode0) {
    ls = ls.filter(fundable); if (!ls.length || !pots.length) { toast('Nothing to allocate to', 'bad'); return; }
    const free = pots.reduce((a, x) => a + x.available, 0); const sumNeed = ls.reduce((a, l) => a + need(l), 0); const remembered = (() => { try { return localStorage.getItem('wsMode'); } catch (e) { return null; } })();
    let mode = sumNeed <= 0.5 ? 'equal' : (['need', 'big', 'small', 'equal'].includes(mode0) ? mode0 : ['need', 'big', 'small', 'equal'].includes(remembered) ? remembered : 'need');   // the last method chosen is the default, and it can be changed in the window
    const amount = h('input', { type: 'text', inputmode: 'decimal', value: String(floor2(Math.min(free, mode === 'need' ? sumNeed : free))), style: { width: '120px', textAlign: 'right' } });
    const risk = ls.length === 1 ? h('input', { type: 'text', inputmode: 'decimal', value: '0', style: { width: '110px', textAlign: 'right' } }) : null;
    const riskFree = pots.reduce((a, x) => a + x.risk, 0);
    const ins = ls.map(() => h('input', { type: 'text', inputmode: 'decimal', style: { width: '110px', textAlign: 'right' } }));
    const msg = h('div', { class: 'small', style: { margin: '8px 0' } });
    const total = () => ins.reduce((a, x) => a + num(x.value), 0);
    const check = () => { const t = total(); const rr = risk ? num(risk.value) : 0; const bad = t > free + 1 || rr > riskFree + 1; msg.className = 'small ' + (bad ? 'bad' : 'muted'); msg.textContent = bad ? `The selected pots have ${fmt.money(free)} budget${risk ? ` and ${fmt.money(riskFree)} risk` : ''} free.` : `Assigning ${fmt.money(t)}${rr ? ` and ${fmt.money(rr)} risk` : ''} of ${fmt.money(free)} free across ${pots.length} pot${pots.length === 1 ? '' : 's'}; each gives in proportion to what it has free.`; };
    // how a short supply is shared: in proportion to each shortfall, biggest shortfall first, smallest first (covers the most lines in full), or equally but never above a line's shortfall
    const split = (a) => {
      const ns = ls.map(need); const out = ls.map(() => 0);
      if (mode === 'need') return ns.map((v) => cents(v * (a >= sumNeed ? 1 : a / (sumNeed || 1))));
      if (mode === 'big' || mode === 'small') { let left = a; ns.map((v, i) => [v, i]).sort((x, y) => (mode === 'big' ? y[0] - x[0] : x[0] - y[0])).forEach(([v, i]) => { const g = Math.min(v, left); out[i] = cents(g); left -= g; }); return out; }
      if (sumNeed <= 0.5) return ls.map(() => cents(a / ls.length));
      let left = a; let open = ls.map((_, i) => i).filter((i) => ns[i] > 0.004);
      while (left > 0.004 && open.length) { const each = left / open.length; const next = []; open.forEach((i) => { const g = Math.min(each, ns[i] - out[i]); out[i] += g; left -= g; if (ns[i] - out[i] > 0.004) next.push(i); }); if (next.length === open.length) break; open = next; }
      return out.map(cents);
    };
    const fill = () => { const parts = split(Math.max(0, num(amount.value))); ins.forEach((x, i) => { x.value = parts[i] ? String(parts[i]) : ''; }); check(); };
    const MODES = [['need', 'In proportion to shortfall'], ['big', 'Biggest shortfall first'], ['small', 'Smallest shortfall first'], ['equal', 'Equal, capped at shortfall'], ['typed', 'Typed']];
    const radios = MODES.map(([k, l]) => h('label', { class: 'row small', style: { gap: '4px' } }, h('input', { type: 'radio', name: 'wsmode', checked: mode === k, onchange: () => { mode = k; if (k !== 'typed') { try { localStorage.setItem('wsMode', k); } catch (e) { /* ignore */ } fill(); } } }), l));
    amount.addEventListener('input', () => { if (mode !== 'typed') fill(); }); ins.forEach((x) => x.addEventListener('input', () => { mode = 'typed'; radios[radios.length - 1].querySelector('input').checked = true; check(); }));
    if (risk) risk.addEventListener('input', check);
    modal({ title: ls.length === 1 ? `Fund ${ls[0].code} ${ls[0].name} from ${pots.length} pots` : `Allocate ${pots.length} pot${pots.length === 1 ? '' : 's'} over ${ls.length} lines`, size: 'wide', body: h('div', {},
      h('div', { class: 'row', style: { gap: '14px', flexWrap: 'wrap', marginBottom: '8px' } }, h('span', { class: 'small' }, 'Amount to allocate'), amount, risk ? h('span', { class: 'small' }, 'Risk to move') : null, risk),
      ls.length > 1 ? h('div', { class: 'ws-how' }, h('div', { class: 'ws-h' }, 'How to spread the funds'), h('div', { class: 'row', style: { gap: '14px', flexWrap: 'wrap' } }, ...radios), h('div', { class: 'ws-sub', style: { marginTop: '4px' } }, 'The method you choose becomes the default next time. Typing in any Gets box switches to Typed.')) : null,
      h('div', { class: 'small muted', style: { marginBottom: '6px' } }, pots.map((x) => `${x.code} ${fmt.m(x.available)}`).join(' · ')),
      h('div', { class: 'tw', style: { maxHeight: '38vh' } }, h('table', { class: 't' }, h('thead', {}, h('tr', {}, ['CBS', 'Line', 'Allowance', 'EAC', 'Short by', 'Gets'].map((x, i) => h('th', { class: i >= 2 ? 'r' : '' }, x)))),
        h('tbody', {}, ls.map((l, i) => h('tr', {}, h('td', { class: 'mono' }, l.code), h('td', {}, l.name), h('td', { class: 'r num' }, fmt.money(l.allowance)), h('td', { class: 'r num' }, fmt.money(l.eac)), h('td', { class: 'r num ' + (need(l) > 0.5 ? 'bad' : '') }, need(l) > 0.5 ? fmt.money(need(l)) : ''), h('td', { class: 'r' }, ins[i])))))), msg),
      actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} }, { label: 'Assign', onClick: async () => {
        const t = total(); const rr = risk ? num(risk.value) : 0;
        if (t > free + 1 || rr > riskFree + 1) throw new Error('The selected pots do not have that much free');
        const share = (get, amt) => { const tot = pots.reduce((a, x) => a + get(x), 0) || 1; const parts = pots.map((x) => cents(amt * get(x) / tot)); const diff = cents(amt - parts.reduce((a, v) => a + v, 0)); parts[0] = cents(parts[0] + diff); return parts; };
        let n = 0;
        for (let i = 0; i < ls.length; i++) {
          const v = Math.min(num(ins[i].value), free); const rv = ls.length === 1 ? Math.min(rr, riskFree) : 0;
          if (v <= 0.004 && rv <= 0.004) continue;
          const bs = share((x) => x.available, v); const rs = share((x) => x.risk, rv);
          for (let j = 0; j < pots.length; j++) { const bb = Math.min(bs[j], floor2(pots[j].available)); const r2 = Math.min(rs[j], floor2(pots[j].risk)); if (bb > 0.004 || r2 > 0.004) { await api.post(p('/ledger/transfer'), { from_id: pots[j].id, to_id: ls[i].node_id, budget: bb, risk: r2, ref: 'ASSIGN', note: 'Allocated in the Allowances workspace' }); n++; } }
        }
        toast(`Assigned ${fmt.money(t + rr)} to ${ls.length} line${ls.length === 1 ? '' : 's'} (${n} ledger moves)`); selP.clear(); selL.clear(); await reload();
      } }] });
    fill();
  }

  // ---- money back from a line to the pot it came from ----
  async function giveBack(line, prefer) {
    const led = await api.get(p('/ledger?all=1')); const pairs = new Map();
    led.forEach((r) => { if (r.pair_id) { if (!pairs.has(r.pair_id)) pairs.set(r.pair_id, []); pairs.get(r.pair_id).push(r); } });
    const src = new Map();
    led.filter((r) => r.node_id === line.node_id && r.pair_id && r.kind !== 'estimate').forEach((r) => (pairs.get(r.pair_id) || []).filter((o) => o.id !== r.id).forEach((o) => { const e = src.get(o.node_id) || { b: 0, r: 0 }; e.b += r.budget || 0; e.r += r.risk || 0; src.set(o.node_id, e); }));
    let cands = [...src.entries()].filter(([, e]) => e.b > 0.005 || e.r > 0.005).map(([id, e]) => ({ id, b: Math.min(e.b, line.allowance || 0), r: Math.max(0, e.r) }));
    if (!cands.length) { for (let n = byId.get(String(line.parent_id)); n; n = byId.get(String(n.parent_id))) if (bk.get(String(n.id))) cands.push({ id: n.id, b: Math.max(0, line.allowance || 0), r: 0 }); }
    if (prefer && !cands.some((c) => String(c.id) === String(prefer.id))) cands.unshift({ id: prefer.id, b: Math.max(0, line.allowance || 0), r: 0 });
    if (!cands.length) { toast('No pot found to send it back to', 'bad'); return; }
    const label = (id) => { const n = byId.get(String(id)); return n ? `${n.code} ${n.name}` : String(id); };
    const sel = h('select', {}, cands.map((c) => h('option', { value: c.id, selected: prefer ? String(c.id) === String(prefer.id) : false }, `${label(c.id)} (came from here: ${fmt.money(c.b)}${c.r > 0.5 ? ` + ${fmt.money(c.r)} risk` : ''})`)));
    const b = h('input', { type: 'text', inputmode: 'decimal', style: { width: '130px', textAlign: 'right' } }); const r = h('input', { type: 'text', inputmode: 'decimal', style: { width: '130px', textAlign: 'right' } });
    const msg = h('div', { class: 'small', style: { marginTop: '6px' } }); const cur = () => cands.find((c) => String(c.id) === String(sel.value)) || cands[0];
    const chk = () => { const left = (line.allowance || 0) - num(b.value); const used = (line.ctd || 0) + (line.acc || 0); msg.className = 'small ' + (left < used - 0.5 ? 'bad' : 'muted'); msg.textContent = `${line.code} keeps ${fmt.money(left)}; its cost to date and accruals are ${fmt.money(used)}${left < used - 0.5 ? ', so it would be over budget' : ''}.`; };
    const setDef = () => { const c = cur(); b.value = String(floor2(c.b)); r.value = String(floor2(c.r)); chk(); };
    sel.addEventListener('change', setDef); b.addEventListener('input', chk); setDef();
    modal({ title: `Send money back from ${line.code} ${line.name}`, body: h('div', { class: 'grid' }, h('div', { class: 'note' }, `${line.code} holds ${fmt.money(line.allowance)} and is forecast at ${fmt.money(line.eac)}. Choose the pot to return it to.`),
      field('Return to', sel), h('div', { class: 'grid g2' }, field('Budget to return', b), field('Risk to return', r)), msg),
      actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} }, { label: 'Send back', onClick: async () => {
        const bb = Math.min(num(b.value), floor2(Math.max(0, line.allowance || 0))); const rr = num(r.value);
        if (!(bb > 0 || rr > 0)) throw new Error('Enter an amount');
        await api.post(p('/ledger/transfer'), { from_id: line.node_id, to_id: +sel.value, budget: bb, risk: rr, ref: 'RETURN', note: 'Returned in the Allowances workspace' });
        toast(`Returned ${fmt.money(bb + rr)} to ${label(sel.value)}`); await reload();
      } }] });
  }

  async function reload(silent = false) {
    const [o, c] = await Promise.all([api.get(p('/allowance/overview')), api.get(p('/cost-control?months=0'))]);
    ov.buckets = o.buckets; cc.rows = c.rows; cc.windows = c.windows; rows.length = 0; rows.push(...c.rows); index(); draw(); leadDraw(); if (!silent && ch) ch.postMessage({ type: 'reload' });
  }
  if (ch) ch.onmessage = (m) => {
    const d = m.data || {};
    if (d.type === 'sel') { selP.clear(); selL.clear(); (d.pots || []).forEach((k) => selP.add(String(k))); (d.lines || []).forEach((k) => selL.add(String(k))); lastSig = JSON.stringify([[...selP].sort(), [...selL].sort()]); draw(); }
    else if (d.type === 'reload') reload(true);
  };
  const leadDraw = () => { clear(lead).append(h('b', {}, fmt.money(ov.buckets.reduce((a, b) => a + b.available, 0))), ' sits in pots, not yet assigned. Click pots on the left and lines on the right to select them (click again to deselect), then press Allocate. Or drag a pot across onto a line or group. Drag a line back onto a pot to return money. Drag a row up or down to reorder it within its parent.'); };

  const search = pane === 'left' ? null : h('input', { type: 'search', placeholder: 'Filter lines (name, resource)', style: { width: '210px' }, oninput: (e) => { q = e.target.value.trim().toLowerCase(); draw(); } });
  const searchP = pane === 'right' ? null : h('input', { type: 'search', placeholder: 'Filter pots (e.g. commissioning)', style: { width: '210px' }, oninput: (e) => { qp = e.target.value.trim().toLowerCase(); draw(); } });
  const chip = (label, get, set) => h('label', { class: 'row small', style: { gap: '4px' } }, h('input', { type: 'checkbox', checked: get(), onchange: (e) => { set(e.target.checked); draw(); } }), label);
  const allIds = () => rows.filter((r) => r.kind === 'group' && r.active !== 0).map((r) => String(r.id));
  body.append(lead, h('div', { class: 'row ws-bar', style: { gap: '10px', marginBottom: '6px' } }, ...[searchP, search].filter(Boolean), pane === 'left' ? null : chip('Only short lines', () => onlyShort, (v) => { onlyShort = v; }), pane === 'right' ? null : chip('Empty pots', () => showEmpty, (v) => { showEmpty = v; }),
    pane === 'left' ? null : h('span', { class: 'ws-colmenu' }, h('button', { class: 'ws-link', title: 'Choose which columns the lines pane shows', onclick: (e) => {
      const host = e.target.parentElement; const old = host.querySelector('.tt-pop'); if (old) { old.remove(); return; }
      const pop = h('div', { class: 'tt-pop' }, ...OPT.map(([l, pos]) => h('label', {}, h('input', { type: 'checkbox', checked: colsOn(pos), onchange: (ev) => { if (ev.target.checked) hidCols.delete(pos); else hidCols.add(pos); try { localStorage.setItem('wsCols', JSON.stringify([...hidCols])); } catch (x) { /* ignore */ } draw(); } }), ' ' + l)));
      host.append(pop); const away = (ev) => { if (!host.contains(ev.target)) { pop.remove(); document.removeEventListener('mousedown', away, true); } }; setTimeout(() => document.addEventListener('mousedown', away, true), 0);
    } }, '\u25A5 Columns')),
    h('button', { class: 'ws-link', onclick: () => { allIds().forEach((k) => { openL.add(k); openR.add(k); }); save('L', [...openL]); save('R', [...openR]); draw(); } }, 'Open all'),
    h('button', { class: 'ws-link', onclick: () => { openL.clear(); openR.clear(); save('L', []); save('R', []); draw(); } }, 'Close all'), h('span', { class: 'sp' }),
    document.body.classList.contains('popout') ? null : h('span', { class: 'row small', style: { gap: '4px' }, title: 'Open the panes in windows of their own, for a bigger or second screen. They stay live and share what you select, and a pot can be dragged from one window onto a line in the other.' }, 'New window:',
      ...[['both', 'Both'], ['left', 'Pots'], ['right', 'Lines']].map(([k, l]) => h('button', { class: 'ws-link', onclick: () => { const w = window.open(`${location.pathname}?popout=1#/risk?tab=allowance&solo=1&pane=${k}`, '_blank', `popup=yes,width=${k === 'both' ? 1700 : 950},height=950`); if (!w) toast('The browser blocked the new window. Allow pop-ups for PMT and try again.', 'bad'); } }, '⧉ ' + l))),
    h('button', { class: 'ws-link', title: 'Select a line or a pot first to see only its moves, with the pots that funded it. With nothing selected the whole Ledger opens.', onclick: () => { const ids = [...new Set([...[...selL].map((k) => (rows.find((r) => String(r.id) === k) || {}).node_id), ...[...selP].map((k) => +k)])].filter((k) => k > 0); location.hash = '#/risk?tab=ledger' + (ids.length ? '&node=' + ids.join(',') : ''); } }, 'See every move in the Ledger')), act, wrap);
  const grid = h('div', { class: 'ws' });
  const saved = (() => { try { return localStorage.getItem('wsLeft'); } catch (e) { return null; } })();
  if (saved) grid.style.setProperty('--wsl', saved + 'px');
  const split = h('div', { class: 'ws-split', title: 'Drag to change the widths of the two panes. Double-click to reset.' });
  split.addEventListener('pointerdown', (e) => {
    e.preventDefault(); split.setPointerCapture(e.pointerId); split.classList.add('on'); const box = grid.getBoundingClientRect();
    const move = (ev) => { const w = Math.round(Math.min(Math.max(ev.clientX - box.left, 260), box.width - 340)); grid.style.setProperty('--wsl', w + 'px'); try { localStorage.setItem('wsLeft', String(w)); } catch (x) { /* ignore */ } };
    const up = () => { split.classList.remove('on'); split.removeEventListener('pointermove', move); split.removeEventListener('pointerup', up); };
    split.addEventListener('pointermove', move); split.addEventListener('pointerup', up);
  });
  split.addEventListener('dblclick', () => { grid.style.removeProperty('--wsl'); try { localStorage.removeItem('wsLeft'); } catch (x) { /* ignore */ } });
  if (pane === 'left') { grid.style.gridTemplateColumns = '1fr'; grid.append(h('div', { class: 'ws-col' }, left)); }
  else if (pane === 'right') { grid.style.gridTemplateColumns = '1fr'; grid.append(h('div', { class: 'ws-col' }, right)); }
  else grid.append(h('div', { class: 'ws-col' }, left), split, h('div', { class: 'ws-col' }, right));
  wrap.append(grid);
  leadDraw(); draw();
}
