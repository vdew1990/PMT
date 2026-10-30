import { h, clear, toast, field, select, confirmBox, lookup, badge, debounce } from '../ui.js';
import { api, state, p } from '../api.js';

// SETUP > Project org chart: who the owner, developer, builder, principal contractor, contractor and the network service provider (NSP) are,
// and the contract, reporting and communication lines between them. EPEC is always on it, as the Contractor or the Principal Contractor.
// Drag a box to move it, click it to edit it, Draw a line then click two boxes to join them, click a line to change it. Saved as you go.
const W = 176; const H = 66; const GRID = 10; const CW = 1100; const CH = 700;
const NS = 'http://www.w3.org/2000/svg';
const COL = { Owner: '#102361', Developer: '#2938c2', Builder: '#e56210', 'Principal Contractor': '#e56210', Contractor: '#ffb500', NSP: '#335062', Subcontractor: '#4195f2', Consultant: '#4195f2', Other: '#6b7a90' };
const LEVEL = { Owner: 0, Developer: 1, NSP: 1, Builder: 2, 'Principal Contractor': 2, Contractor: 3, Consultant: 3, Other: 3, Subcontractor: 4 };
const KIND_LABEL = { contract: 'Contract', reporting: 'Reporting line', communication: 'Communication' };
const KIND_STYLE = { contract: { colour: '#102361', width: 2.6, dash: '' }, reporting: { colour: '#e56210', width: 2.2, dash: '9 5' }, communication: { colour: '#335062', width: 2, dash: '2 5' } };
const lookupKind = (role) => (role === 'Owner' || role === 'Developer' ? 'client' : 'company');
const uid = () => Math.random().toString(16).slice(2, 10);
const sv = (tag, attrs = {}, ...kids) => { const e = document.createElementNS(NS, tag); Object.entries(attrs).forEach(([k, v]) => v != null && e.setAttribute(k, v)); kids.flat().forEach((k) => k != null && e.append(k)); return e; };

function tidy(parties) {
  const byLevel = {};
  parties.forEach((x) => { (byLevel[LEVEL[x.role] ?? 3] = byLevel[LEVEL[x.role] ?? 3] || []).push(x); });
  Object.entries(byLevel).forEach(([lv, list]) => {
    list.sort((a, b) => (a.role === 'NSP') - (b.role === 'NSP') || a.name.localeCompare(b.name));
    const gap = 40; const total = list.length * W + (list.length - 1) * gap; const x0 = Math.max(20, (CW - total) / 2);
    list.forEach((x, i) => { x.x = Math.round((x0 + i * (W + gap)) / GRID) * GRID; x.y = 30 + lv * 140; });
  });
}

const TEMPLATES = {
  'EPEC as Principal Contractor': (ch) => {
    const P = (role, name = '') => ({ id: uid(), role, name, note: '', x: 0, y: 0 });
    const owner = P('Owner'); const dev = P('Developer'); const nsp = P('NSP'); const sub = P('Subcontractor');
    ch.epec_role = 'Principal Contractor'; ch.parties = [owner, dev, nsp, ch.parties.find((x) => x.epec), sub];
    const e = ch.parties[3]; e.role = 'Principal Contractor';
    ch.links = [{ id: uid(), from: owner.id, to: dev.id, kind: 'communication', label: '' }, { id: uid(), from: dev.id, to: e.id, kind: 'contract', label: 'EPC contract' },
      { id: uid(), from: e.id, to: dev.id, kind: 'reporting', label: 'Reports to' }, { id: uid(), from: nsp.id, to: e.id, kind: 'communication', label: 'Connection' },
      { id: uid(), from: e.id, to: sub.id, kind: 'contract', label: 'Subcontract' }];
  },
  'EPEC as Contractor': (ch) => {
    const P = (role, name = '') => ({ id: uid(), role, name, note: '', x: 0, y: 0 });
    const owner = P('Owner'); const dev = P('Developer'); const pc = P('Principal Contractor'); const nsp = P('NSP');
    ch.epec_role = 'Contractor'; ch.parties = [owner, dev, pc, nsp, ch.parties.find((x) => x.epec)];
    const e = ch.parties[4]; e.role = 'Contractor';
    ch.links = [{ id: uid(), from: owner.id, to: dev.id, kind: 'communication', label: '' }, { id: uid(), from: dev.id, to: pc.id, kind: 'contract', label: 'EPC contract' },
      { id: uid(), from: pc.id, to: e.id, kind: 'contract', label: 'Subcontract' }, { id: uid(), from: e.id, to: pc.id, kind: 'reporting', label: 'Reports to' },
      { id: uid(), from: nsp.id, to: pc.id, kind: 'communication', label: 'Connection' }, { id: uid(), from: nsp.id, to: dev.id, kind: 'communication', label: '' }];
  },
};

export default async function orgchart(root) {
  const data = await api.get(p('/orgchart'));
  const ch = { epec_role: data.epec_role, parties: data.parties, links: data.links };
  const ui = { sel: null, draw: false, kind: 'contract', from: null };
  const status = h('span', { class: 'small muted' }, data.saved ? 'Saved' : 'Not saved yet');
  const save = debounce(async () => { try { await api.put(p('/orgchart'), ch); status.textContent = 'Saved'; } catch (e) { status.textContent = 'Not saved: ' + e.message; } }, 500);
  const changed = () => { status.textContent = 'Saving...'; save(); };

  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, 'Project org chart'),
    h('div', { class: 'sub' }, 'Who the owner, developer, builder, contractors and the network service provider are, and how contracts, reporting and communication run between them.'))));
  const bar = h('div', { class: 'card row', style: { padding: '10px 14px', marginBottom: '10px', gap: '10px', flexWrap: 'wrap' } });
  const stage = h('div', { class: 'card', style: { padding: 0, overflow: 'auto' } });
  // the edit panel sits right under the toolbar, above the chart, so it is always in view (not below the fold)
  const panel = h('div', { class: 'card', style: { margin: '10px 0' } });
  root.append(bar, panel, stage);
  const svg = sv('svg', { viewBox: `0 0 ${CW} ${CH}`, width: '100%', style: 'min-width:900px;display:block;background:#f7f8fa;touch-action:none' });
  stage.append(svg);

  const party = (id) => ch.parties.find((x) => x.id === id);
  const epec = () => ch.parties.find((x) => x.epec);
  const drawBar = () => {
    const roleSel = select(data.roles.filter((r) => !['Principal Contractor', 'Contractor'].includes(r) || true).map((r) => [r, r]), 'Developer');
    const kindSel = select(data.kinds.map((k) => [k, KIND_LABEL[k]]), ui.kind); kindSel.onchange = () => { ui.kind = kindSel.value; };
    const epecSel = select([['Principal Contractor', 'Principal Contractor'], ['Contractor', 'Contractor']], ch.epec_role);
    epecSel.onchange = () => { ch.epec_role = epecSel.value; epec().role = epecSel.value; changed(); draw(); };
    clear(bar).append(h('span', { class: 'small' }, 'EPEC is the'), epecSel, h('span', { style: { width: '10px' } }),
      roleSel, h('button', { class: 'btn sm', onclick: () => { const x = { id: uid(), role: roleSel.value, name: '', note: '', x: 0, y: 0 }; const spot = free(); x.x = spot.x; x.y = spot.y; ch.parties.push(x); ui.sel = { type: 'party', id: x.id }; changed(); draw(); } }, '+ Add party'),
      h('span', { style: { width: '10px' } }), kindSel,
      h('button', { class: 'btn sm' + (ui.draw ? '' : ' ghost'), onclick: () => { ui.draw = !ui.draw; ui.from = null; drawBar(); draw(); } }, ui.draw ? 'Click two boxes... (cancel)' : 'Draw a line'),
      h('button', { class: 'btn sm ghost', title: 'Lay the boxes out by role again', onclick: () => { tidy(ch.parties); changed(); draw(); } }, 'Tidy layout'),
      ...(ch.parties.length <= 1 ? Object.keys(TEMPLATES).map((t) => h('button', { class: 'btn sm ghost', onclick: () => { TEMPLATES[t](ch); tidy(ch.parties); ui.sel = null; changed(); drawBar(); draw(); } }, 'Start: ' + t)) : []),
      h('span', { class: 'sp', style: { flex: 1 } }), status, h('button', { class: 'btn sm ghost', onclick: download }, 'Download image'));
  };
  const free = () => { let y = 30; for (;;) { for (let x = 30; x < CW - W; x += W + 30) if (!ch.parties.some((q) => Math.abs(q.x - x) < W && Math.abs(q.y - y) < H + 10)) return { x, y }; y += H + 30; } };

  // where a line leaves a box: along the line between the two centres, at the box edge
  const edgePt = (a, b, off = 0) => {
    const ax = a.x + W / 2; const ay = a.y + H / 2; const bx = b.x + W / 2; const by = b.y + H / 2;
    const dx = bx - ax; const dy = by - ay; const len = Math.hypot(dx, dy) || 1; const nx = -dy / len; const ny = dx / len;
    const t = Math.min((W / 2) / Math.abs(dx || 1e-9), (H / 2) / Math.abs(dy || 1e-9));
    return { x: ax + dx * t + nx * off, y: ay + dy * t + ny * off };
  };

  function drawChart() {
    clear(svg);
    const defs = sv('defs');
    Object.entries(KIND_STYLE).forEach(([k, st]) => {
      defs.append(sv('marker', { id: 'ar-' + k, viewBox: '0 0 10 10', refX: 9, refY: 5, markerWidth: 8, markerHeight: 8, orient: 'auto-start-reverse' }, sv('path', { d: 'M0 0 10 5 0 10z', fill: st.colour })));
    });
    svg.append(defs);
    // lines first, so the boxes sit on top
    const pairs = {};
    ch.links.forEach((l) => { const k = [l.from, l.to].sort().join('|'); (pairs[k] = pairs[k] || []).push(l); });
    ch.links.forEach((l) => {
      const a = party(l.from); const b = party(l.to); if (!a || !b) return;
      const group = pairs[[l.from, l.to].sort().join('|')]; const idx = group.indexOf(l);
      const off = (idx - (group.length - 1) / 2) * 30 * (l.from < l.to ? 1 : -1);
      const p1 = edgePt(a, b, off); const p2 = edgePt(b, a, -off); const st = KIND_STYLE[l.kind];
      const sel = ui.sel?.type === 'link' && ui.sel.id === l.id;
      const g = sv('g', { style: 'cursor:pointer' });
      g.append(sv('line', { x1: p1.x, y1: p1.y, x2: p2.x, y2: p2.y, stroke: 'transparent', 'stroke-width': 16 }));
      g.append(sv('line', { x1: p1.x, y1: p1.y, x2: p2.x, y2: p2.y, stroke: sel ? '#ffb500' : st.colour, 'stroke-width': sel ? st.width + 2 : st.width, 'stroke-dasharray': st.dash, 'marker-end': `url(#ar-${l.kind})`, ...(l.kind === 'communication' ? { 'marker-start': `url(#ar-${l.kind})` } : {}) }));
      if (l.label) {
        const mx = (p1.x + p2.x) / 2; const my = (p1.y + p2.y) / 2;
        const pair = group.length > 1; const right = mx >= (a.x + b.x + W) / 2; g.append(sv('text', { x: pair ? mx + (right ? 8 : -8) : mx, y: pair ? my + 4 : my - 5, 'text-anchor': pair ? (right ? 'start' : 'end') : 'middle', 'font-size': 11.5, 'font-weight': 700, fill: st.colour, stroke: '#f7f8fa', 'stroke-width': 4, 'paint-order': 'stroke' }, l.label));
      }
      g.addEventListener('pointerdown', (e) => { e.stopPropagation(); if (ui.draw) return; ui.sel = { type: 'link', id: l.id }; draw(); });
      svg.append(g);
    });
    ch.parties.forEach((x) => {
      const sel = ui.sel?.type === 'party' && ui.sel.id === x.id; const pick = ui.draw && ui.from === x.id;
      const g = sv('g', { transform: `translate(${x.x} ${x.y})`, style: `cursor:${ui.draw ? 'crosshair' : 'grab'}` });
      g.append(sv('rect', { width: W, height: H, rx: 10, fill: '#fff', stroke: sel || pick ? '#ffb500' : x.epec ? '#102361' : '#c9d1d6', 'stroke-width': sel || pick ? 3.5 : x.epec ? 3 : 1.5 }));
      g.append(sv('rect', { width: 9, height: H, rx: 4, fill: COL[x.role] || COL.Other }));
      g.append(sv('text', { x: 20, y: 22, 'font-size': 10.5, 'font-weight': 800, fill: COL[x.role] === '#ffb500' ? '#8a6100' : COL[x.role] || COL.Other, 'letter-spacing': '.6' }, x.role.toUpperCase() + (x.epec ? '  ·  EPEC' : '')));
      const name = x.name || (x.epec ? 'EPEC' : 'Click to add a name');
      g.append(sv('text', { x: 20, y: 44, 'font-size': 14.5, 'font-weight': 800, fill: x.name || x.epec ? '#102361' : '#9aa6b4' }, name.length > 20 ? name.slice(0, 19) + '…' : name));
      if (x.note) g.append(sv('text', { x: 20, y: 58, 'font-size': 10.5, fill: '#335062' }, x.note.length > 28 ? x.note.slice(0, 27) + '…' : x.note));
      g.addEventListener('pointerdown', (e) => {
        e.stopPropagation();
        if (ui.draw) {
          if (!ui.from) { ui.from = x.id; draw(); return; }
          if (ui.from !== x.id) {
            const l = { id: uid(), from: ui.from, to: x.id, kind: ui.kind, label: '' };
            if (!ch.links.some((q) => q.from === l.from && q.to === l.to && q.kind === l.kind)) { ch.links.push(l); ui.sel = { type: 'link', id: l.id }; changed(); }
            ui.from = null; ui.draw = false; drawBar(); draw();
          }
          return;
        }
        const pt = svgPoint(e); const ox = pt.x - x.x; const oy = pt.y - x.y; let moved = false;
        const mv = (ev) => { const q = svgPoint(ev); const nx = Math.round((q.x - ox) / GRID) * GRID; const ny = Math.round((q.y - oy) / GRID) * GRID;
          if (nx !== x.x || ny !== x.y) { moved = true; x.x = Math.max(0, Math.min(CW - W, nx)); x.y = Math.max(0, Math.min(CH - H, ny)); draw(); } };
        const up = () => { window.removeEventListener('pointermove', mv); window.removeEventListener('pointerup', up); if (moved) changed(); else { ui.sel = { type: 'party', id: x.id }; draw(); } };
        window.addEventListener('pointermove', mv); window.addEventListener('pointerup', up);
      });
      svg.append(g);
    });
  }
  let shownSel = null;
  function draw() {
    drawChart(); drawPanel();
    // a newly selected party: put the cursor in the name box
    const key = ui.sel ? `${ui.sel.type}:${ui.sel.id}` : null;
    if (key && key !== shownSel && ui.sel.type === 'party') {
      const box = panel.querySelector('input[type=text]:not([disabled])'); if (box && !box.value) box.focus({ preventScroll: true });
    }
    shownSel = key;
  }
  const svgPoint = (e) => { const pt = svg.createSVGPoint(); pt.x = e.clientX; pt.y = e.clientY; return pt.matrixTransform(svg.getScreenCTM().inverse()); };
  svg.addEventListener('pointerdown', () => { if (ui.draw) return; if (ui.sel) { ui.sel = null; draw(); } });

  function drawPanel() {
    clear(panel);
    const s = ui.sel;
    if (ui.draw) { panel.append(h('div', { class: 'small' }, `Drawing a ${KIND_LABEL[ui.kind].toLowerCase()}: ${ui.from ? 'now click the party it goes to.' : 'click the party it starts from.'} The arrow points to the second party (for a reporting line: to who is reported to; for a contract: to the party doing the work).`)); return; }
    if (!s) { panel.append(h('div', { class: 'small muted' }, 'Click a box or a line in the chart below to edit its name or delete it. Drag a box to move it. ', h('b', {}, 'Lines: '), 'solid arrow = contract, dashed orange = reporting line (arrow to who is reported to), dotted = communication (both ways).')); return; }
    if (s.type === 'party') {
      const x = party(s.id); if (!x) return;
      const role = select(data.roles.map((r) => [r, r]), x.role); role.disabled = x.epec;
      role.onchange = () => { x.role = role.value; changed(); draw(); };
      const nameBox = x.role === 'NSP' ? h('div', {}, h('input', { type: 'text', value: x.name, list: 'nsps', placeholder: 'e.g. Transgrid, Powerlink' }), h('datalist', { id: 'nsps' }, data.nsps.map((n) => h('option', { value: n }))))
        : lookup(lookupKind(x.role), x.name, { placeholder: 'Pick or type a name' });
      const nameInput = nameBox.matches?.('input') ? nameBox : nameBox.querySelector('input');
      nameInput.disabled = x.epec;
      const setName = () => { x.name = nameInput.value.trim(); changed(); drawNodesOnly(); };
      nameInput.addEventListener('change', setName); nameInput.addEventListener('input', debounce(setName, 400));
      const note = h('input', { type: 'text', value: x.note || '', placeholder: 'e.g. 275 kV connection, PM Jane Smith' });
      note.addEventListener('input', debounce(() => { x.note = note.value; changed(); drawNodesOnly(); }, 400));
      panel.append(h('div', { class: 'grid g3' }, field('Role', role, x.epec ? 'EPEC: change it with the selector above' : ''), field('Name', nameBox), field('Note', note)),
        x.epec ? null : h('div', { style: { marginTop: '8px' } }, h('button', { class: 'btn danger sm', onclick: async () => { if (await confirmBox(`Delete ${x.name || x.role} and its lines from the chart?`, 'Delete', true)) { ch.parties = ch.parties.filter((q) => q.id !== x.id); ch.links = ch.links.filter((l) => l.from !== x.id && l.to !== x.id); ui.sel = null; changed(); draw(); } } }, 'Delete party')));
      panel.prepend(h('div', { class: 'small', style: { marginBottom: '6px' } }, h('b', {}, x.name || x.role), ' selected. Edit the name here, or ', h('b', {}, 'Delete party'), x.epec ? ' (not available for EPEC).' : ' (or press the Delete key).'));
    } else {
      const l = ch.links.find((q) => q.id === s.id); if (!l) return;
      const a = party(l.from); const b = party(l.to);
      const kind = select(data.kinds.map((k) => [k, KIND_LABEL[k]]), l.kind); kind.onchange = () => { l.kind = kind.value; changed(); draw(); };
      const label = h('input', { type: 'text', value: l.label || '', placeholder: 'e.g. EPC contract, weekly report, design queries' });
      label.addEventListener('input', debounce(() => { l.label = label.value; changed(); draw(); }, 300));
      panel.append(h('div', { class: 'small', style: { marginBottom: '6px' } }, `${a?.name || a?.role} → ${b?.name || b?.role}`),
        h('div', { class: 'grid g3' }, field('Kind', kind), field('Label', label), h('div', { style: { alignSelf: 'end' } }, h('button', { class: 'btn ghost sm', onclick: () => { [l.from, l.to] = [l.to, l.from]; changed(); draw(); } }, 'Swap direction'), ' ',
          h('button', { class: 'btn danger sm', onclick: () => { ch.links = ch.links.filter((q) => q.id !== l.id); ui.sel = null; changed(); draw(); } }, 'Delete line'))));
    }
  }
  // typing a name must not rebuild the panel (it would lose focus): redraw the chart only
  const drawNodesOnly = drawChart;

  function download() {
    const copy = svg.cloneNode(true); copy.setAttribute('xmlns', NS); copy.setAttribute('width', CW); copy.setAttribute('height', CH);
    const xs = ch.parties.map((q) => q.x); const ys = ch.parties.map((q) => q.y);
    copy.setAttribute('viewBox', `${Math.max(0, Math.min(...xs) - 20)} ${Math.max(0, Math.min(...ys) - 20)} ${Math.max(...xs) - Math.min(...xs) + W + 40} ${Math.max(...ys) - Math.min(...ys) + H + 40}`);
    const blob = new Blob([copy.outerHTML], { type: 'image/svg+xml' }); const a = h('a', { href: URL.createObjectURL(blob), download: `${(state.project?.code || 'project')}_org_chart.svg` }); document.body.append(a); a.click(); a.remove();
  }

  if (ch.parties.length <= 1 && !data.saved) { epec().x = 460; epec().y = 260; }
  // Delete key removes the selected party or line (not while typing in a box)
  const onKey = (e) => {
    if (!root.isConnected) { window.removeEventListener('keydown', onKey); return; }
    if (e.key !== 'Delete' || !ui.sel || /INPUT|SELECT|TEXTAREA/.test(document.activeElement?.tagName || '')) return;
    if (ui.sel.type === 'party') { const x = party(ui.sel.id); if (!x || x.epec) return; ch.parties = ch.parties.filter((q) => q.id !== x.id); ch.links = ch.links.filter((l) => l.from !== x.id && l.to !== x.id); }
    else ch.links = ch.links.filter((q) => q.id !== ui.sel.id);
    ui.sel = null; changed(); draw();
  };
  window.addEventListener('keydown', onKey);
  drawBar(); draw();
}
