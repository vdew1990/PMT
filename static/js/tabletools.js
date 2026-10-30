// Table tools for every table in PMT: sort and filter any column, back to the original (CBS) order, and open the table
// in a window of its own (to move it to another screen). Attached automatically to every <table class="t"> that
// appears (see watchTables); no page has to do anything. A table opts out with class "notools"; tables whose body
// rows span several rows (rowspan) are not sorted, as moving their rows would break them.
// Sort and filter choices are kept per page and table, so they survive the page redrawing (e.g. changing level).

import { pref } from './api.js';

const memory = new Map();

const NUM = /^\(?-?\$?-?[\d,]*\.?\d+\s*([kKmM%h]|hrs?)?\)?$/;
const MONTHS = { jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6, jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12 };

function cellText(td) {
  if (!td) return '';
  const inp = td.querySelector('input:not([type=checkbox]), select, textarea');
  return (inp ? (inp.value ?? '') : td.textContent || '').trim();
}

// a sortable value: a number for amounts, %, hours, dates (dd/mm/yyyy) and months (Sep-26); else lower-case text
function sortValue(t) {
  if (!t || t === '–' || t === '-') return null;
  const s = t.replace(/\s+/g, ' ').trim();
  let m = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(s);
  if (m) return +m[3] * 10000 + +m[2] * 100 + +m[1];
  m = /^([A-Za-z]{3})-(\d{2})$/.exec(s);
  if (m && MONTHS[m[1].toLowerCase()]) return 200000 + +m[2] * 100 + MONTHS[m[1].toLowerCase()];
  if (NUM.test(s)) {
    const neg = s.startsWith('(') || s.includes('-');
    const n = parseFloat(s.replace(/[^\d.]/g, ''));
    if (!Number.isNaN(n)) {
      const mul = /m\)?$/i.test(s) ? 1e6 : /k\)?$/i.test(s) ? 1e3 : 1;
      return (neg ? -1 : 1) * n * mul;
    }
  }
  return s.toLowerCase();
}

// a filter: ">1000", "<=0", "=5" for numbers, otherwise "contains" (case-insensitive); "!text" excludes
function matches(t, f) {
  f = f.trim();
  if (!f) return true;
  const m = /^(>=|<=|>|<|=)\s*(.+)$/.exec(f);
  if (m) {
    const a = sortValue(t); const b = sortValue(m[2]);
    if (typeof a !== 'number' || typeof b !== 'number') return false;
    return { '>': a > b, '<': a < b, '>=': a >= b, '<=': a <= b, '=': Math.abs(a - b) < 0.005 }[m[1]];
  }
  if (f.startsWith('!')) return !t.toLowerCase().includes(f.slice(1).toLowerCase());
  return t.toLowerCase().includes(f.toLowerCase());
}

function keyOf(table) {
  if (table.dataset.ttkey) return table.dataset.ttkey;     // the key of the table as first drawn, whatever order its columns are in now
  const heads = [...(table.tHead?.rows[table.tHead.rows.length - 1]?.cells || [])].map((c) => c.textContent.trim()).join('|');
  return (location.hash.split('?')[0] || '#') + '::' + heads;
}

// ---- column order: drag a heading by its four-dot grip to put the column elsewhere; kept per page and table on this PC ----------
const ORDER = 'pmt.colorder';
const loadOrder = (key) => { try { return (JSON.parse(localStorage.getItem(ORDER) || '{}'))[key] || null; } catch (e) { return null; } };
const saveOrder = (key, perm) => { try { const all = JSON.parse(localStorage.getItem(ORDER) || '{}'); if (perm) all[key] = perm; else delete all[key]; localStorage.setItem(ORDER, JSON.stringify(all)); } catch (e) { /* storage may be blocked */ } };
const COLW_KEY = 'pmt.colw';
// can this table's columns be moved? Every row must have the same plain cells (no spans, one heading row, no frozen columns)
function reorderable(table, ncol) {
  if (table.classList.contains('freeze2') || table.classList.contains('noreorder') || table.closest('.dg, .lc') || table.tHead.rows.length !== 1) return false;
  return [...table.rows].every((r) => r.cells.length === ncol && [...r.cells].every((c) => (c.colSpan || 1) === 1 && (c.rowSpan || 1) === 1));
}
// order[newPosition] = position now
function permute(table, order) {
  [...table.rows].forEach((r) => { const cells = [...r.cells]; if (cells.length === order.length) order.forEach((from) => r.appendChild(cells[from])); });
}
function moveCol(table, from, to) {
  const order = [...Array(table.tHead.rows[0].cells.length).keys()];
  order.splice(to, 0, order.splice(from, 1)[0]);
  permute(table, order);
  return order;
}
// forget the tools added to a table and add them again (after its columns moved)
function reenhance(table) {
  [...table.tBodies[0].rows].sort((a, b) => +a.dataset.ord - +b.dataset.ord).forEach((r) => table.tBodies[0].appendChild(r));   // back to the original row order first
  table.querySelectorAll('.tt-sort, .tt-resize, .tt-grip').forEach((e) => e.remove());
  table.querySelector('tr.tt-filter')?.remove();
  table.querySelector('colgroup')?.remove(); table.classList.remove('tt-fixed'); table.style.width = '';
  delete table.dataset.tt;
  table.dataset.ttskiporder = '1';        // the columns are already in their saved order
  enhance(table);
}

export function enhance(table) {
  if (!table || table.dataset.tt || table.classList.contains('notools') || table.closest('.dg, .notools') || !table.tHead || !table.tBodies[0]) return;
  table.dataset.tt = '1';
  table.dataset.ttkey = keyOf(table);
  const canMove = reorderable(table, table.tHead.rows[0].cells.length);
  const perm0 = loadOrder(table.dataset.ttkey);
  if (canMove && perm0 && perm0.length === table.tHead.rows[0].cells.length && !table.dataset.ttskiporder) permute(table, perm0.map((o) => o));
  delete table.dataset.ttskiporder;
  const body = table.tBodies[0];
  const rows = [...body.rows];
  rows.forEach((r, i) => { r.dataset.ord = i; });
  const spans = rows.some((r) => [...r.cells].some((c) => c.rowSpan > 1));
  const tree = rows.some((r) => r.classList.contains('gp') || r.classList.contains('par') || r.classList.contains('par2'));   // grouped rows (grandparent, parent, child): sorting would break the groups
  const head = table.tHead.rows[table.tHead.rows.length - 1];
  const labels = [...head.cells].map((th) => th.textContent.replace(/[⇅▲▼]/g, '').trim());
  const ncol = Math.max(...rows.map((r) => r.cells.length), head.cells.length);
  const key = keyOf(table);
  const st = memory.get(key) || { col: null, dir: 0, filters: {}, show: !!pref('table_filters') };
  memory.set(key, st);
  // column index as rendered (colspans in the heading row counted)
  const colOf = []; let ci = 0;
  [...head.cells].forEach((th) => { colOf.push(ci); ci += th.colSpan || 1; });

  const apply = () => {
    let list = [...body.rows];
    // filter
    const fs = Object.entries(st.filters).filter(([, v]) => v && v.trim());
    list.forEach((r) => { if (r.classList.contains('tt-grp')) return; r.style.display = fs.every(([c, v]) => matches(cellText(r.cells[+c]), v)) ? '' : 'none'; });
    // sort (or the original order); not while the rows are grouped under CBS headings
    if (!spans && !st.group) {
      const sorted = [...list].sort((a, b) => {
        if (st.col === null || !st.dir) return +a.dataset.ord - +b.dataset.ord;
        const x = sortValue(cellText(a.cells[st.col])); const y = sortValue(cellText(b.cells[st.col]));
        if (x === null && y === null) return +a.dataset.ord - +b.dataset.ord;
        if (x === null) return 1;
        if (y === null) return -1;
        const c = typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y), undefined, { numeric: true });
        return (c || (+a.dataset.ord - +b.dataset.ord)) * (c ? st.dir : 1);
      });
      sorted.forEach((r) => body.appendChild(r));
    }
    [...head.cells].forEach((th, i) => {
      const b = th.querySelector('.tt-sort'); if (!b) return;
      b.textContent = colOf[i] === st.col && st.dir ? (st.dir > 0 ? '▲' : '▼') : '⇅';
      b.classList.toggle('on', colOf[i] === st.col && !!st.dir);
    });
    reset.style.display = (st.dir || fs.length || (canMove && loadOrder(key))) ? '' : 'none';
    count.textContent = fs.length ? `${list.filter((r) => !r.classList.contains('tt-grp') && r.style.display !== 'none').length} of ${list.filter((r) => !r.classList.contains('tt-grp')).length}` : '';
  };

  // ---- group by CBS: a flat table whose rows carry CBS codes (PL04.002) is nested under grandparent (PL) and parent (PL04) headings ----
  const CBS_RE = /^P[LSME]\d{2}(\.\d{1,3})*/i;
  const CAT = { PL: 'Project Labour', PS: 'Project Subcontractors', PM: 'Materials & Equipment', PE: 'Expenses & Indirects' };
  const CATORD = ['PL', 'PS', 'PM', 'PE'];
  const cbsCol = (() => {
    if (spans || tree) return -1;
    for (let c = 0; c < ncol; c++) { const vals = rows.map((r) => (r.cells[c] ? cellText(r.cells[c]).trim() : '')).filter(Boolean); if (vals.length >= 3 && vals.filter((v) => CBS_RE.test(v)).length / vals.length >= 0.8) return c; }
    return -1;
  })();
  const numOf = (t) => { const x = parseFloat(String(t).replace(/[^0-9.\-]/g, '')); return Number.isFinite(x) ? x : 0; };
  const closed = new Set();
  const applyFold = () => {
    [...body.rows].forEach((r) => {
      if (r.classList.contains('tt-grp') && r.classList.contains('gp')) { r.classList.remove('tt-fold'); return; }
      const g1 = r.dataset.g1; const g2 = r.dataset.g2;
      r.classList.toggle('tt-fold', !!g1 && (closed.has(g1) || (!r.classList.contains('tt-grp') && closed.has(g2))));
    });
    body.querySelectorAll('tr.tt-grp .tt-arr').forEach((a) => { const r = a.closest('tr'); a.style.transform = closed.has(r.dataset.self) ? '' : 'rotate(90deg)'; });
  };
  const groupOff = () => {
    st.group = false; body.querySelectorAll('tr.tt-grp').forEach((r) => r.remove());
    [...body.rows].sort((a, b) => +a.dataset.ord - +b.dataset.ord).forEach((r) => { r.classList.remove('tt-fold'); body.appendChild(r); });
    saveGroup(key, false); apply();
  };
  const groupOn = () => {
    st.group = true; saveGroup(key, true);
    body.querySelectorAll('tr.tt-grp').forEach((r) => r.remove());
    const code = (r) => cellText(r.cells[cbsCol]).trim().toUpperCase();
    const ordered = [...rows].sort((a, b) => (CATORD.indexOf(code(a).slice(0, 2)) - CATORD.indexOf(code(b).slice(0, 2))) || code(a).localeCompare(code(b), undefined, { numeric: true }) || +a.dataset.ord - +b.dataset.ord);
    const numeric = [...head.cells].map((th, i) => i !== cbsCol && rows.some((r) => r.cells[i] && (r.cells[i].classList.contains('r') || r.cells[i].classList.contains('num'))));
    const sample = (i) => { const r = rows.find((x) => x.cells[i] && cellText(x.cells[i]).trim()); return r ? cellText(r.cells[i]) : ''; };
    const fmtLike = (i, v) => { const t = sample(i); const dec = /\.\d/.test(t); const s = Math.abs(v).toLocaleString('en-AU', { minimumFractionDigits: dec ? 2 : 0, maximumFractionDigits: dec ? 2 : 0 }); return (v < 0 ? '-' : '') + (t.includes('$') ? '$' : '') + s; };
    const header = (cls, label, g1, g2, self, members) => {
      const tr = document.createElement('tr'); tr.className = 'tt-grp ' + cls; tr.dataset.g1 = g1; tr.dataset.g2 = g2; tr.dataset.self = self; tr.style.cursor = 'pointer';
      for (let i = 0; i < ncol; i++) {
        const td = document.createElement('td');
        if (i === cbsCol || (i === 0 && cbsCol < 0)) { const a = document.createElement('span'); a.className = 'tt-arr'; a.textContent = '\u25B8'; a.style.cssText = 'display:inline-block;width:14px;transition:transform .12s'; td.append(a, label); }
        else if (numeric[i]) { td.className = 'r num'; td.textContent = fmtLike(i, members.reduce((a, r) => a + numOf(r.cells[i] ? cellText(r.cells[i]) : ''), 0)); }
        tr.appendChild(td);
      }
      tr.onclick = () => { if (closed.has(self)) closed.delete(self); else closed.add(self); applyFold(); };
      return tr;
    };
    const g1s = new Map();
    ordered.forEach((r) => { const c = code(r); const a = c.slice(0, 2); const b = c.slice(0, 4); if (!g1s.has(a)) g1s.set(a, new Map()); const m = g1s.get(a); if (!m.has(b)) m.set(b, []); m.get(b).push(r); });
    g1s.forEach((m, a) => {
      const all = [...m.values()].flat();
      body.appendChild(header('gp', `${a} ${CAT[a] || ''}`.trim(), a, a, a, all));
      m.forEach((members, b) => {
        body.appendChild(header('par', b, a, b, b, members));
        members.forEach((r) => { r.dataset.g1 = a; r.dataset.g2 = b; body.appendChild(r); });
      });
    });
    closed.clear(); applyFold(); reapplyHidden(); apply();
  };

  // sort buttons in the heading cells (a small arrow, so headings that do something on click keep doing it)
  if (!spans && !tree) {
    [...head.cells].forEach((th, i) => {
      if (!th.textContent.trim()) return;
      const b = document.createElement('span');
      b.className = 'tt-sort';
      b.title = 'Sort: ascending, descending, then back to the original order';
      b.onclick = (e) => { e.stopPropagation(); const c = colOf[i]; if (st.col !== c) { st.col = c; st.dir = 1; } else st.dir = st.dir === 1 ? -1 : (st.dir === -1 ? 0 : 1); apply(); };
      th.appendChild(b);
    });
  }
  // a four-dot grip at the left of each heading: drag it to move the column
  if (canMove) {
    [...head.cells].forEach((th, i) => {
      if (!th.textContent.trim()) return;
      const g = document.createElement('span');
      g.className = 'tt-grip grip4'; g.draggable = true; g.title = 'Drag to move this column';
      g.addEventListener('dragstart', (e) => { e.dataTransfer.setData('text/plain', 'column'); e.dataTransfer.effectAllowed = 'move'; table.dataset.ttdrag = String(th.cellIndex); try { e.dataTransfer.setDragImage(th, 12, 12); } catch (err) { /* optional */ } });
      g.addEventListener('dragend', () => { delete table.dataset.ttdrag; head.querySelectorAll('.tt-dropl, .tt-dropr').forEach((x) => x.classList.remove('tt-dropl', 'tt-dropr')); });
      th.insertBefore(g, th.firstChild);
      th.addEventListener('dragover', (e) => { if (table.dataset.ttdrag === undefined) return; e.preventDefault(); const r = th.getBoundingClientRect(); const left = e.clientX < r.left + r.width / 2; head.querySelectorAll('.tt-dropl, .tt-dropr').forEach((x) => x.classList.remove('tt-dropl', 'tt-dropr')); th.classList.add(left ? 'tt-dropl' : 'tt-dropr'); });
      th.addEventListener('drop', (e) => {
        if (table.dataset.ttdrag === undefined) return; e.preventDefault();
        const from = +table.dataset.ttdrag; const r = th.getBoundingClientRect(); const left = e.clientX < r.left + r.width / 2;
        let to = th.cellIndex + (left ? 0 : 1); if (from < to) to -= 1;
        delete table.dataset.ttdrag;
        if (to === from) return;
        const order = moveCol(table, from, to);                          // order[new] = position it came from
        const prev = loadOrder(key) || [...Array(order.length).keys()];     // prev[position] = original column
        saveOrder(key, order.map((p) => prev[p]));
        try { const w = JSON.parse(localStorage.getItem(COLW_KEY) || '{}'); if (w[key]) { const o = {}; order.forEach((p, n) => { if (w[key][p] !== undefined) o[n] = w[key][p]; }); w[key] = o; localStorage.setItem(COLW_KEY, JSON.stringify(w)); } } catch (err) { /* storage may be blocked */ }
        memory.set(key, { col: null, dir: 0, filters: {}, show: st.show });
        reenhance(table);
      });
    });
  }
  // filter row
  const frow = document.createElement('tr');
  frow.className = 'tt-filter';
  for (let c = 0; c < ncol; c++) {
    const th = document.createElement('th');
    const inp = document.createElement('input');
    inp.type = 'text'; inp.placeholder = 'filter'; inp.value = st.filters[c] || '';
    inp.title = 'Contains text; for numbers also >1000, <0, =0; !text to exclude';
    inp.oninput = () => { st.filters[c] = inp.value; apply(); };
    inp.onclick = (e) => e.stopPropagation();
    th.appendChild(inp); frow.appendChild(th);
  }
  if (st.show && !spans) table.tHead.appendChild(frow);

  // toolbar: filter, reset, open in a new window
  const bar = document.createElement('div');
  bar.className = 'tt-bar noprint';
  const btn = (label, title, fn) => { const b = document.createElement('button'); b.type = 'button'; b.className = 'tt-btn'; b.textContent = label; b.title = title; b.onclick = fn; bar.appendChild(b); return b; };
  const count = document.createElement('span'); count.className = 'tt-count';
  bar.appendChild(count);
  if (!spans) btn('⌕ Filter', 'Show or hide a filter box under each column', () => { st.show = !st.show; if (st.show) { table.tHead.appendChild(frow); reapplyHidden(); frow.querySelector('input')?.focus(); } else frow.remove(); });
  if (cbsCol >= 0) btn('☰ Group by CBS', 'Nest the rows under grandparent and parent CBS headings with subtotals; click a heading to fold it', () => { if (st.group) groupOff(); else groupOn(); });
  const reset = btn('↺ Original order', 'Back to the original (CBS) row order, the original column order, and no filters', () => { if (canMove && loadOrder(key)) { const cur = loadOrder(key); permute(table, [...cur.keys()].map((o) => cur.indexOf(o))); saveOrder(key, null); try { const w = JSON.parse(localStorage.getItem(COLW_KEY) || '{}'); delete w[key]; localStorage.setItem(COLW_KEY, JSON.stringify(w)); } catch (err) { /* storage may be blocked */ } memory.delete(key); reenhance(table); return; } st.col = null; st.dir = 0; st.filters = {}; frow.querySelectorAll('input').forEach((i) => { i.value = ''; }); apply(); });
  const reapplyHidden = () => { const h0 = new Set(loadHidden(key)); if (h0.size) applyHidden(table, head, new Set(labels.map((x, j) => (h0.has(x) ? j : -1)).filter((j) => j >= 0)), colOf); };
  const hideable = head.cells.length === ncol && labels.every((l, i) => l || true) && !table.classList.contains('nohide');
  if (hideable) {
    const cb = btn('▥ Columns', 'Choose which columns to show. Kept for this table on this PC', () => {
      const old = bar.querySelector('.tt-pop'); if (old) { old.remove(); return; }
      const pop = document.createElement('div'); pop.className = 'tt-pop';
      const saved = new Set(loadHidden(key));
      labels.forEach((l, i) => {
        if (!l) return;
        const lab = document.createElement('label'); const cbx = document.createElement('input'); cbx.type = 'checkbox'; cbx.checked = !saved.has(l);
        cbx.onchange = () => { if (cbx.checked) saved.delete(l); else saved.add(l); saveHidden(key, [...saved]); applyHidden(table, head, new Set(labels.map((x, j) => (saved.has(x) ? j : -1)).filter((j) => j >= 0)), colOf); table._ttTotal?.(); };
        lab.append(cbx, ' ' + l); pop.appendChild(lab);
      });
      const all = document.createElement('button'); all.type = 'button'; all.className = 'tt-btn'; all.textContent = 'Show all'; all.onclick = () => { saveHidden(key, []); applyHidden(table, head, new Set(), colOf); pop.remove(); table._ttTotal?.(); };
      pop.appendChild(all); bar.appendChild(pop);
      const away = (e) => { if (!pop.contains(e.target) && e.target !== cb) { pop.remove(); document.removeEventListener('mousedown', away, true); } };
      setTimeout(() => document.addEventListener('mousedown', away, true), 0);
    });
    const hid0 = new Set(loadHidden(key));
    if (hid0.size) applyHidden(table, head, new Set(labels.map((x, j) => (hid0.has(x) ? j : -1)).filter((j) => j >= 0)), colOf);
  }
  btn('↔ Fit to screen', 'Size the columns to their content and use the width of the screen', () => table._ttFit?.());
  btn('⧉ New window', 'Open this table in a window of its own, to move it to another screen (a copy as it is now; it can be sorted and filtered there)', () => popTable(table));
  const anchor = table.closest('.tw') || table;
  const prev = anchor.previousElementSibling;
  if (prev && prev.classList.contains('tt-bar')) prev.remove();  // a redraw of the same table: one toolbar only
  if (rows.length >= 3) anchor.parentNode?.insertBefore(bar, anchor);
  apply();
  if (cbsCol >= 0 && (st.group ?? loadGroup(key) ?? (rows.length >= 8 && !table.classList.contains('nogroup')))) groupOn();   // nested by default when the table is long enough to need it; the choice is remembered
  resizable(table, head, colOf, ncol, key);
}

const GRP = 'pmt.tt.group';
const loadGroup = (key) => { try { const v = (JSON.parse(localStorage.getItem(GRP) || '{}'))[key]; return v === undefined ? undefined : !!v; } catch (e) { return undefined; } };
const saveGroup = (key, on) => { try { const all = JSON.parse(localStorage.getItem(GRP) || '{}'); all[key] = on; localStorage.setItem(GRP, JSON.stringify(all)); } catch (e) { /* storage may be blocked */ } };

// ---- hidden columns: kept per table (by heading text, so a moved column stays hidden) -----------------------------
const HID = 'pmt.colhide';
const loadHidden = (key) => { try { return (JSON.parse(localStorage.getItem(HID) || '{}'))[key] || []; } catch (e) { return []; } };
const saveHidden = (key, list) => { try { const all = JSON.parse(localStorage.getItem(HID) || '{}'); if (list.length) all[key] = list; else delete all[key]; localStorage.setItem(HID, JSON.stringify(all)); } catch (e) { /* storage may be blocked */ } };
// hide the given column positions in every row; a cell spanning several columns keeps the span of its visible ones
function applyHidden(table, head, hidden, colOf) {
  [...table.rows].forEach((r) => {
    let at = 0;
    [...r.cells].forEach((c) => {
      const span = c.dataset.cs0 ? +c.dataset.cs0 : (c.colSpan || 1);
      if (span > 1 && !c.dataset.cs0) c.dataset.cs0 = String(span);
      let vis = 0; for (let k = at; k < at + span; k++) if (!hidden.has(k)) vis++;
      c.style.display = vis === 0 ? 'none' : '';
      if (span > 1) c.colSpan = Math.max(1, vis);
      at += span;
    });
  });
  table.dataset.tthidden = [...hidden].join(',');
}

// ---- column widths, as in Excel: drag the border on the right of a heading; double-click it to fit the content -----
// The first resize pins every column at its current width (a fixed layout, so a column can also be made narrower than
// its content); widths are kept per page and table on this PC.
const COLW = 'pmt.colw';
const loadW = (key) => { try { return (JSON.parse(localStorage.getItem(COLW) || '{}'))[key] || null; } catch (e) { return null; } };
const saveW = (key, w) => { try { const all = JSON.parse(localStorage.getItem(COLW) || '{}'); all[key] = w; localStorage.setItem(COLW, JSON.stringify(all)); } catch (e) { /* storage may be blocked */ } };
let measurer = null;

function resizable(table, head, colOf, ncol, key) {
  if (table.closest('.dg, .lc')) return;                  // day grids keep their own fixed columns
  let cols = null;
  const widths = {};
  const freeze = () => {
    if (cols) return;
    const ref = [...table.tBodies[0].rows].find((r) => r.cells.length === ncol && r.offsetParent !== null) || (head.cells.length === ncol ? head : null);
    if (!ref) return;
    const ws = [...ref.cells].map((c) => c.getBoundingClientRect().width);
    const cg = document.createElement('colgroup');
    cols = ws.map((w) => { const col = document.createElement('col'); col.style.width = `${Math.round(w)}px`; cg.appendChild(col); return col; });
    table.querySelector('colgroup')?.remove();
    table.insertBefore(cg, table.firstChild);
    table.classList.add('tt-fixed');
    total();
  };
  const hiddenNow = () => new Set((table.dataset.tthidden || '').split(',').filter(Boolean).map(Number));
  const total = () => { const hz = hiddenNow(); table.style.width = `${cols.reduce((a, c, i) => a + (hz.has(i) ? 0 : parseFloat(c.style.width)), 0)}px`; cols.forEach((c, i) => { c.style.visibility = hz.has(i) ? 'collapse' : ''; }); };
  table._ttTotal = () => { if (cols) total(); };
  const setW = (c, w) => { freeze(); if (!cols || !cols[c]) return; cols[c].style.width = `${Math.round(w)}px`; widths[c] = Math.round(w); total(); };
  const fit = (c) => {
    if (!measurer) { measurer = document.createElement('div'); Object.assign(measurer.style, { position: 'absolute', visibility: 'hidden', whiteSpace: 'nowrap', left: '-9999px', top: '0' }); document.body.appendChild(measurer); }
    let best = 40;
    [...table.rows].forEach((r) => {
      if (r.style.display === 'none' || r.classList.contains('tt-filter')) return;
      const cell = r.cells.length === ncol ? r.cells[c] : (r === head ? head.cells[colOf.indexOf(c)] : null);
      if (!cell || (cell.colSpan || 1) > 1) return;
      const cs = getComputedStyle(cell);
      measurer.style.font = cs.font; measurer.style.fontWeight = cs.fontWeight;
      measurer.replaceChildren(...[...cell.childNodes].filter((n) => !(n.classList && n.classList.contains('tt-resize'))).map((n) => n.cloneNode(true)));
      best = Math.max(best, measurer.scrollWidth + parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight) + 4);
    });
    setW(c, Math.min(best, 900));
  };
  [...head.cells].forEach((th, i) => {
    if ((th.colSpan || 1) > 1) return;
    const c = colOf[i];
    const g = document.createElement('span');
    g.className = 'tt-resize';
    g.title = 'Drag to change the width; double-click to fit the content';
    g.onclick = (e) => e.stopPropagation();
    g.onmousedown = (e) => {
      e.preventDefault(); e.stopPropagation();
      freeze(); if (!cols) return;
      const x0 = e.clientX; const w0 = parseFloat(cols[c].style.width);
      document.body.classList.add('tt-resizing');
      const move = (ev) => setW(c, Math.max(28, w0 + ev.clientX - x0));
      const up = () => { document.removeEventListener('mousemove', move); document.removeEventListener('mouseup', up); document.body.classList.remove('tt-resizing'); saveW(key, { ...(loadW(key) || {}), ...widths }); };
      document.addEventListener('mousemove', move); document.addEventListener('mouseup', up);
    };
    g.ondblclick = (e) => { e.preventDefault(); e.stopPropagation(); fit(c); saveW(key, { ...(loadW(key) || {}), ...widths }); };
    th.appendChild(g);
  });
  // fit to screen: every column to its content, then spread any spare width over them (never narrower than the content)
  const fitAll = () => {
    freeze(); if (!cols) return;
    const hz = hiddenNow();
    for (let c = 0; c < ncol; c++) if (!hz.has(c)) fit(c);
    const box = (table.closest('.tw') || table.parentElement); const avail = (box ? box.clientWidth : 0) - 4;
    const sum = cols.reduce((a, col, i) => a + (hz.has(i) ? 0 : parseFloat(col.style.width)), 0);
    if (avail > sum && sum > 0) { const k = avail / sum; for (let c = 0; c < ncol; c++) if (!hz.has(c)) setW(c, parseFloat(cols[c].style.width) * k); }
    saveW(key, { ...widths });
  };
  table._ttFit = fitAll;
  const saved = loadW(key);
  if (saved && Object.keys(saved).length) requestAnimationFrame(() => { const hz = hiddenNow(); Object.entries(saved).forEach(([c, w]) => { if (!hz.has(+c)) setW(+c, w); }); total(); });
  else if (window.innerWidth < 1500 && ncol <= 18 && !table.querySelector('.sticky1, .freeze') && !table.classList.contains('nofit')) {
    // a small screen and no widths chosen yet: if the table runs wider than its box, size it to its content so it fits as well as it can
    requestAnimationFrame(() => { const box = table.closest('.tw') || table.parentElement; if (box && table.scrollWidth > box.clientWidth + 8 && table.offsetParent) { fitAll(); try { const all = JSON.parse(localStorage.getItem(COLW) || '{}'); delete all[key]; localStorage.setItem(COLW, JSON.stringify(all)); } catch (e) { /* ignore */ } } });
  }
}

// a copy of the table in a new window with the app's styles; sorting and filtering work there too
// A table that names its own page (data-popout="#/page?part=...") opens that page, live, in the new window: it looks
// and works exactly as it does here (frozen columns, toggles, editing).
export function popTable(table) {
  if (table.dataset.popout) {
    const w = window.open(location.pathname + '?popout=1' + table.dataset.popout, '_blank', 'popup=yes,width=1500,height=950');
    if (!w) alert('The browser blocked the new window. Allow pop-ups for PMT and try again.');
    return;
  }
  const w = window.open('', '_blank', 'popup=yes,width=1400,height=900');
  if (!w) { alert('The browser blocked the new window. Allow pop-ups for PMT and try again.'); return; }
  const clone = table.cloneNode(true);
  clone.removeAttribute('data-tt');
  // frozen (sticky) columns need the page's own layout; in a copy they would overlap, so they scroll normally
  clone.querySelectorAll('.sticky1, .freeze, [style*="sticky"]').forEach((e) => { e.classList.remove('sticky1', 'freeze'); e.style.position = ''; e.style.left = ''; });
  clone.querySelectorAll('.tt-sort, tr.tt-filter').forEach((e) => e.remove());
  clone.querySelectorAll('tbody tr').forEach((r) => { r.style.display = ''; r.removeAttribute('data-ord'); });
  // inputs become their values (the copy is for reading)
  const src = table.querySelectorAll('input, select, textarea'); const dst = clone.querySelectorAll('input, select, textarea');
  dst.forEach((e, i) => { const v = src[i]?.type === 'checkbox' ? (src[i].checked ? '✓' : '') : (src[i]?.value ?? ''); e.replaceWith(w.document.createTextNode(src[i]?.tagName === 'SELECT' ? (src[i].selectedOptions[0]?.textContent || v) : v)); });
  const title = (document.querySelector('.pagehead h1')?.textContent || 'PMT') + ' – ' + ((table.closest('.card')?.querySelector('h2')?.textContent) || 'table');
  const when = new Date().toLocaleString();
  w.document.write(`<!doctype html><html lang="en-AU"><head><meta charset="utf-8"><title>${title}</title><link rel="stylesheet" href="${location.origin}/static/css/app.css"></head>
<body class="popout"><div style="padding:14px 18px"><div class="row" style="margin-bottom:8px"><b style="color:var(--navy);font-size:16px">${title}</b><span class="muted small" style="margin-left:10px">Copy as at ${when}</span></div>
<div class="tw" style="max-height:calc(100vh - 90px)">${clone.outerHTML}</div></div>
<script type="module">import { enhance } from '${location.origin}/static/js/tabletools.js'; document.querySelectorAll('table.t').forEach(enhance);</script></body></html>`);
  w.document.close();
}

// watch the page: every table that appears gets the tools (debounced, so a redraw of many rows is handled once)
// a long table repeats its total row under the heading (the total also stays at the bottom)
function topTotal(tb) {
  if (tb.dataset.tot || tb.classList.contains('fgrid') || !tb.tFoot || tb.tFoot.rows.length !== 1 || !tb.tBodies[0] || tb.tBodies[0].rows.length < 10 || !tb.tHead || !tb.tHead.rows.length) return;
  tb.dataset.tot = '1';
  const tr = tb.tFoot.rows[0].cloneNode(true); tr.classList.add('tot-top');
  const hh = tb.tHead.rows[0].offsetHeight || 34;
  [...tr.cells].forEach((c) => { c.style.top = hh + 'px'; });
  tb.tHead.append(tr);
}



// ---- copy by dragging, as in Excel: put the mouse in the bottom-right corner of a cell you can type in (a crosshair shows);
// drag it up, down, left or right over cells with the same kind of control, and they get this value. Moving a value is
// different: pages that allow it show a four-dot grip at the left of the cell. ------------------------------------------------
const EDITABLE = 'input:not([type=checkbox]):not([type=radio]):not([type=file]):not([type=button]), select, textarea';
function editableOf(td) {
  if (!td || td.closest('.fillcell, .md .tw table.sgrid')) return null;
  const els = td.querySelectorAll(EDITABLE);
  const el = els.length === 1 ? els[0] : null;
  if (!el || el.disabled || el.readOnly || el.dataset.field || el.classList.contains('lk-input') || el.closest('.lk-list')) return null;   // data-field cells have their own fill (ui.fillHandle)
  return el;
}
function installFill() {
  if (window.__pmtFill) return; window.__pmtFill = true;
  const knob = document.createElement('div');
  knob.className = 'tt-fill'; knob.title = 'Drag to copy this value to the neighbouring cells'; knob.style.display = 'none';
  document.body.appendChild(knob);
  let host = null; let busy = false;
  const place = (td) => {
    const r = td.getBoundingClientRect();
    knob.style.left = `${Math.round(r.right - 8)}px`; knob.style.top = `${Math.round(r.bottom - 8)}px`; knob.style.display = 'block'; host = td;
  };
  const hide = () => { if (!busy) { knob.style.display = 'none'; host = null; } };
  document.addEventListener('mouseover', (e) => {
    if (busy) return;
    const td = e.target.closest?.('table.t[data-tt] td');
    if (td && editableOf(td)) place(td); else if (!e.target.closest?.('.tt-fill')) hide();
  });
  window.addEventListener('scroll', hide, true);
  const cellOf = (x, y) => document.elementFromPoint(x, y)?.closest('td');
  knob.addEventListener('mousedown', (e) => {
    if (!host) return;
    e.preventDefault(); e.stopPropagation();
    const srcTd = host; const src = editableOf(srcTd); const table = srcTd.closest('table'); if (!src) return;
    const key = table.dataset.ttkey; const rIdx = srcTd.parentElement.rowIndex; const cIdx = srcTd.cellIndex;
    const value = src.value; const same = (el) => el && el.tagName === src.tagName && el.type === src.type && !el.disabled && !el.readOnly && (el.tagName !== 'SELECT' || [...el.options].some((o) => o.value === value));
    let marked = [];
    busy = true; document.body.classList.add('tt-filling');
    const mark = (x, y) => {
      marked.forEach((t) => t.classList.remove('fill-sel')); marked = [];
      const td = cellOf(x, y); if (!td || td.closest('table') !== table) return;
      const dr = td.parentElement.rowIndex - rIdx; const dc = td.cellIndex - cIdx;
      if (!dr && !dc) return;
      const vertical = Math.abs(dr) >= Math.abs(dc);
      const n = vertical ? Math.abs(dr) : Math.abs(dc); const step = vertical ? Math.sign(dr) : Math.sign(dc);
      for (let k = 1; k <= n; k++) {
        const row = table.rows[vertical ? rIdx + step * k : rIdx]; const cell = row?.cells[vertical ? cIdx : cIdx + step * k];
        if (cell && row.style.display !== 'none' && same(editableOf(cell))) { cell.classList.add('fill-sel'); marked.push(cell); }
      }
    };
    const move = (ev) => mark(ev.clientX, ev.clientY);
    const up = async () => {
      document.removeEventListener('mousemove', move); document.removeEventListener('mouseup', up);
      document.body.classList.remove('tt-filling');
      const coords = marked.map((t) => [t.parentElement.rowIndex, t.cellIndex]);
      marked.forEach((t) => t.classList.remove('fill-sel')); marked = [];
      busy = false; knob.style.display = 'none';
      let t = table;
      for (const [r, c] of coords) {
        if (!t.isConnected) {            // a change redrew the page: find the table again
          for (let w = 0; w < 25 && !t?.isConnected; w++) { await new Promise((ok) => setTimeout(ok, 100)); t = [...document.querySelectorAll('table.t[data-tt]')].find((x) => x.dataset.ttkey === key) || t; }
          if (!t.isConnected) return;
        }
        const el = editableOf(t.rows[r]?.cells[c]);
        if (!same(el)) continue;
        el.value = value;
        el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true }));
        await new Promise((ok) => setTimeout(ok, 120));
      }
    };
    document.addEventListener('mousemove', move); document.addEventListener('mouseup', up);
  });
}

export function watchTables(root = document.body) {
  installFill();
  let t = null;
  const run = () => { t = null; root.querySelectorAll('table.t:not([data-tt])').forEach((tb) => { try { enhance(tb); topTotal(tb); } catch (e) { console.error(e); } }); };
  new MutationObserver(() => { if (!t) t = setTimeout(run, 60); }).observe(root, { childList: true, subtree: true });
  run();
  return run;
}
