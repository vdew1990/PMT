// Small UI toolkit: element builder, formatters, modal, toast, table and chart helpers. No framework, no build step.

export const h = (tag, attrs = {}, ...kids) => {
  const el = document.createElement(tag);
  // every number field is a calculator field: text, so the browser accepts 8*5 or =1200/3 (see calc below)
  const isCalc = tag === 'input' && attrs && (attrs.type === 'number' || attrs.inputmode === 'decimal');
  if (isCalc) attrs = { ...attrs, type: 'text', inputmode: 'decimal' };
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
    else if (k === 'dataset' && typeof v === 'object') Object.entries(v).forEach(([a, b]) => { if (b !== undefined && b !== null) el.dataset[a] = b; });
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === 'value') el.value = v;
    else if (k === 'checked' || k === 'disabled' || k === 'selected' || k === 'readOnly') el[k] = !!v;
    else if (k === 'html') el.innerHTML = v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  const add = (c) => {
    if (c === null || c === undefined || c === false) return;
    if (Array.isArray(c)) c.forEach(add);
    else el.append(c.nodeType ? c : document.createTextNode(String(c)));
  };
  kids.forEach(add);
  if (isCalc) el.classList.add('calc');
  return el;
};

export const $ = (sel, root = document) => root.querySelector(sel);
// Redrawing a block in place (an edit, a filter) puts its tables back where you were scrolled: the new tables get the old ones' scroll
// positions a moment later, unless you scroll yourself first. Only when the same number of tables comes back.
export const clear = (el) => {
  let keep = [];
  try { keep = [...el.querySelectorAll('.tw')].map((t) => [t.scrollLeft, t.scrollTop]).filter((x) => x[0] || x[1]); } catch (e) { /* ignore */ }
  while (el.firstChild) el.removeChild(el.firstChild);
  if (keep.length) {
    const all = keep.length;
    const put = () => { const now = [...el.querySelectorAll('.tw')]; if (now.length >= all) now.forEach((t, i) => { if (keep[i] && !t._moved) { t.scrollLeft = keep[i][0]; t.scrollTop = keep[i][1]; } }); };
    requestAnimationFrame(() => { put(); [...el.querySelectorAll('.tw')].forEach((t) => t.addEventListener('scroll', () => { t._moved = true; }, { once: true, passive: true })); setTimeout(put, 120); });
  }
  return el;
};

// ---- formatting (AU English, metric, DD/MM/YYYY, AUD) ----------------------------------------
const nf0 = new Intl.NumberFormat('en-AU', { maximumFractionDigits: 0 });
const nf2 = new Intl.NumberFormat('en-AU', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const fmt = {
  n: (v, dp = 0) => (v === null || v === undefined || v === '' || Number.isNaN(+v)) ? '' : (dp === 2 ? nf2 : nf0).format(+v),
  money: (v, dp = 0) => {
    if (v === null || v === undefined || v === '' || Number.isNaN(+v)) return '';
    const x = +v;
    const s = (dp === 2 ? nf2 : nf0).format(Math.abs(x));
    return x < 0 ? `-$${s}` : `$${s}`;
  },
  m: (v) => { // compact $m / $k
    if (v === null || v === undefined || Number.isNaN(+v)) return '';
    const a = Math.abs(+v), s = +v < 0 ? '-' : '';
    if (a >= 1e6) return `${s}$${(a / 1e6).toFixed(2)}m`;
    if (a >= 1e3) return `${s}$${(a / 1e3).toFixed(0)}k`;
    return `${s}$${a.toFixed(0)}`;
  },
  pct: (v, dp = 1) => (v === null || v === undefined || Number.isNaN(+v)) ? '' : `${(+v * 100).toFixed(dp)}%`,
  date: (iso) => { if (!iso) return ''; const [y, m, d] = String(iso).slice(0, 10).split('-'); return d ? `${d}/${m}/${y}` : iso; },
  month: (ym) => { if (!ym) return ''; const [y, m] = ym.split('-'); return ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][+m - 1] + '-' + y.slice(2); },
};
// calc('=1,200/3') -> 400. Numbers with + - * / ( ), x or × for times, ÷ for divide; $ , % and spaces are ignored.
// A small parser rather than eval, so nothing typed into a cell can run as code. null when it is not a sum.
export function calc(v) {
  let t = String(v ?? '').trim().replace(/^=/, '').replace(/[$,%\s]/g, '').replace(/[x×X]/g, '*').replace(/÷/g, '/');
  if (!t || !/^[0-9.+\-*/()eE]+$/.test(t)) return null;
  let i = 0;
  const peek = () => t[i];
  const atom = () => {
    if (peek() === '-') { i++; return -atom(); }
    if (peek() === '+') { i++; return atom(); }
    if (peek() === '(') { i++; const x = sum(); if (peek() !== ')') throw 0; i++; return x; }
    const m = /^(\d+\.?\d*|\.\d+)(e[+-]?\d+)?/i.exec(t.slice(i)); if (!m) throw 0;
    i += m[0].length; return parseFloat(m[0]);
  };
  const prod = () => { let x = atom(); while (peek() === '*' || peek() === '/') { const o = t[i++]; const y = atom(); x = o === '*' ? x * y : x / y; } return x; };
  const sum = () => { let x = prod(); while (peek() === '+' || peek() === '-') { const o = t[i++]; const y = prod(); x = o === '+' ? x + y : x - y; } return x; };
  try { const x = sum(); return i === t.length && Number.isFinite(x) ? Math.round(x * 1e6) / 1e6 : null; } catch (e) { return null; }
}
export const num = (v) => { const c = calc(v); if (c !== null) return c; const x = parseFloat(String(v).replace(/[$,\s]/g, '')); return Number.isNaN(x) ? 0 : x; };
// Work out a sum typed into a calculator field before the page's own change / Enter handlers read it (capture phase).
const isSum = (v) => /[+*/x×÷()]|.-|^=/.test(String(v).trim().replace(/^-/, ''));
function settle(el) {
  if (!el || !el.classList || !el.classList.contains('calc')) return;
  const raw = el.value.trim();
  if (!raw || !isSum(raw)) { el.classList.remove('calc-bad'); return; }
  const x = calc(raw);
  el.classList.toggle('calc-bad', x === null);
  if (x === null) { el.title = `"${raw}" is not a sum this field can work out`; return; }
  el.value = String(x); el.title = `= ${raw.replace(/^=/, '')}`;
}
if (typeof document !== 'undefined') {
  document.addEventListener('change', (e) => settle(e.target), true);
  document.addEventListener('focusout', (e) => settle(e.target), true);
  document.addEventListener('keydown', (e) => { if (e.key === 'Enter') settle(e.target); }, true);
}
export const tone = (v, tol = 0.5) => (v === null || v === undefined) ? '' : (v < -tol ? 'bad' : v > tol ? 'good' : '');

// ---- toasts, modal, confirm ------------------------------------------------------------------
export function toast(msg, kind = '') {
  const t = h('div', { class: 'toast ' + kind }, msg);
  document.getElementById('toasts').append(t);
  setTimeout(() => t.remove(), kind === 'bad' ? 7000 : 3500);
}

export function modal({ title, body, actions = [], size = '' , onClose }) {
  const ov = h('div', { class: 'ov' });
  const close = () => { ov.remove(); onClose && onClose(); };
  const foot = h('div', { class: 'mf' });
  const box = h('div', { class: 'md ' + size },
    h('div', { class: 'mh' }, h('h2', {}, title), h('button', { onclick: close, 'aria-label': 'Close' }, '×')),
    h('div', { class: 'mb' }, body), foot);
  actions.forEach((a) => foot.append(h('button', {
    class: 'btn ' + (a.kind || ''), onclick: async (e) => {
      const btn = e.currentTarget;
      btn.disabled = true;
      try { const r = await a.onClick(close); if (r !== false && a.close !== false) close(); } catch (err) { toast(err.message || String(err), 'bad'); }
      btn.disabled = false;
    },
  }, a.label)));
  ov.append(box);
  ov.addEventListener('mousedown', (e) => { if (e.target === ov && !actions.length) close(); });
  document.body.append(ov);
  const first = box.querySelector('input,select,textarea');
  if (first) first.focus();
  return { close, el: box };
}

export const confirmBox = (message, okLabel = 'Confirm', danger = false) => new Promise((res) => {
  modal({
    title: 'Please confirm', body: h('p', {}, message),
    actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => res(false) }, { label: okLabel, kind: danger ? 'danger' : '', onClick: () => res(true) }],
    onClose: () => res(false),
  });
});

export function drawer({ title, sub, body, onClose }) {
  const bg = h('div', { class: 'ov', style: { background: 'rgba(16,35,97,.25)', zIndex: 80 } });
  const dr = h('div', { class: 'drawer' });
  const close = () => { bg.remove(); dr.remove(); onClose && onClose(); };
  bg.addEventListener('mousedown', (e) => { if (e.target === bg) close(); });
  const head = h('div', { class: 'dh' }, h('div', {}, h('h2', {}, title), sub ? h('div', { class: 'sub' }, sub) : null), h('button', { class: 'x', onclick: close }, '×'));
  const b = h('div', { class: 'db' }, body);
  dr.append(head, b);
  document.body.append(bg, dr);
  return { close, body: b, head };
}

// ---- form helpers ----------------------------------------------------------------------------
export const field = (label, input, hint) => h('label', { class: 'f' }, label, input, hint ? h('span', { class: 'muted small', style: { fontWeight: 400 } }, hint) : null);
export const select = (opts, value, attrs = {}) => {
  const s = h('select', attrs);
  opts.forEach((o) => { const [v, l] = Array.isArray(o) ? o : [o, o]; s.append(h('option', { value: v, selected: String(v) === String(value) }, l)); });
  return s;
};
export const tabs = (items, active, onChange) => {
  const wrap = h('div', { class: 'tabs' });
  items.forEach(([k, label]) => wrap.append(h('button', { class: k === active ? 'on' : '', onclick: () => onChange(k) }, label)));
  return wrap;
};

// ---- tables ----------------------------------------------------------------------------------
// columns: [{key, label, r:true, f:(row)=>string|Node, cls}]
export function table(columns, rows, opts = {}) {
  const thead = h('thead', {}, h('tr', {}, columns.map((c) => h('th', { class: c.r ? 'r' : '', title: c.title || '' }, c.label))));
  const tbody = h('tbody');
  const trs = [];
  rows.forEach((row, i) => {
    const tr = h('tr', { class: [opts.onRow ? 'click' : '', opts.rowClass ? opts.rowClass(row) : ''].join(' ').trim(), onclick: opts.onRow ? () => opts.onRow(row) : null });
    columns.forEach((c) => {
      const v = c.f ? c.f(row, i) : row[c.key];
      tr.append(h('td', { class: [c.r ? 'r num' : '', c.cls || ''].join(' ').trim() }, v));
    });
    tbody.append(tr);
    trs.push(tr);
  });
  if (opts.reorder) sortableRows(trs, rows, opts.reorder);
  const t = h('table', { class: 't' + (opts.cls ? ' ' + opts.cls : '') }, thead, tbody);
  if (opts.foot) {
    t.append(h('tfoot', {}, h('tr', {}, columns.map((c) => h('td', { class: c.r ? 'r num' : '' }, opts.foot(c) ?? '')))));
  }
  return h('div', { class: 'tw', style: opts.maxHeight ? { maxHeight: opts.maxHeight } : {} }, t);
}

export const empty = (title, text, action) => h('div', { class: 'empty' }, h('b', {}, title), text, action ? h('div', { style: { marginTop: '12px' } }, action) : null);

export const badge = (text, kind = '') => h('span', { class: 'badge ' + kind }, text);
export const statusPill = (s) => s ? h('span', { class: 'status ' + s }, s) : '';

// ---- charts (Chart.js, brand palette) ---------------------------------------------------------
export const PALETTE = ['#102361', '#e56210', '#ffb500', '#4195f2', '#2938c2', '#335062'];
const GRID = '#e0e6e8';
export function chart(canvasParent, config) {
  const cv = h('canvas');
  clear(canvasParent).append(cv);
  Chart.defaults.font.family = '"Mulish","Century Gothic","Calibri",sans-serif';
  Chart.defaults.color = '#335062';
  const base = {
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, boxHeight: 12, usePointStyle: false } },
      tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${fmt.money(c.parsed.y ?? c.parsed.x ?? c.parsed)}` } } },
    scales: config.type === 'doughnut' || config.type === 'radar' ? {} : {
      x: { grid: { color: GRID }, ticks: { maxRotation: 0, autoSkip: true } },
      y: { grid: { color: GRID }, ticks: { callback: (v) => fmt.m(v) } },
    },
  };
  const merged = deepMerge(base, config.options || {});
  return new Chart(cv, { type: config.type, data: config.data, options: merged });
}
function deepMerge(a, b) {
  const o = { ...a };
  for (const k of Object.keys(b)) o[k] = (b[k] && typeof b[k] === 'object' && !Array.isArray(b[k]) && a[k] && typeof a[k] === 'object') ? deepMerge(a[k], b[k]) : b[k];
  return o;
}

// ---- misc ------------------------------------------------------------------------------------
export const debounce = (fn, ms = 250) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
export function download(blobOrUrl, name) { const a = h('a', { href: blobOrUrl, download: name || '' }); document.body.append(a); a.click(); a.remove(); }
export const todayISO = () => new Date().toISOString().slice(0, 10);

// Click-through from a summary (dashboard tile, chart) to the page holding the data behind it.
// jumpTo(el, '#/accruals', 'Open the accruals') makes a tile clickable; chartJump(fn) is chart options that call fn
// with the clicked point ({ index, datasetIndex, label }) and show a hand over the points that lead somewhere.
// `to` is a page ('#/accruals?tab=history'), or a function (e.g. toCard('Manual accruals') to scroll to the table on
// the same page that holds the figures).
export function jumpTo(el, to, title = '') {
  if (!el || !to) return el;
  const go = () => { if (typeof to === 'function') to(); else location.hash = to; };
  el.classList.add('jump');
  el.title = title ? title + ' →' : 'Open the data behind this';
  el.tabIndex = 0;
  el.onclick = (e) => { if (e.target.closest('a, button, input, select')) return; go(); };
  el.onkeydown = (e) => { if (e.key === 'Enter') go(); };
  return el;
}
// scroll to the card on this page whose heading starts with `title` (or the next title given, when the page has no
// such card, e.g. no schedule loaded yet), and flash it
export const toCard = (...titles) => () => {
  const cards = [...document.querySelectorAll('#view .card')];
  const c = titles.map((t) => cards.find((e) => (e.querySelector('h2')?.textContent || '').startsWith(t))).find(Boolean);
  if (!c) return;
  c.scrollIntoView({ behavior: 'smooth', block: 'start' });
  c.classList.remove('flash'); void c.offsetWidth; c.classList.add('flash');
};
export function chartJump(fn) {
  const hit = (e, chart) => chart.getElementsAtEventForMode(e.native || e, 'nearest', { intersect: false }, true)[0];
  return {
    onClick: (e, _els, chart) => { const el = hit(e, chart); if (el) fn({ index: el.index, datasetIndex: el.datasetIndex, label: chart.data.datasets[el.datasetIndex]?.label || '' }); },
    onHover: (e, _els, chart) => { (e.native?.target || chart.canvas).style.cursor = hit(e, chart) ? 'pointer' : 'default'; },
  };
}

// ---- drag rows to reorder -----------------------------------------------------------------------------------------
// trs and rows line up one to one. A row moves among the rows of its own group (same group(row) key), before or after
// the row it is dropped on; save(ids) gets that group's ids in the new order. canDrag(row) keeps some rows fixed.
export function sortableRows(trs, rows, { group = (r) => r.parent_id ?? null, save, canDrag = () => true }) {
  let from = null;
  const clearMarks = () => trs.forEach((t) => t.classList.remove('drop-before', 'drop-after'));
  trs.forEach((tr, i) => {
    const row = rows[i];
    if (!canDrag(row)) return;
    tr.draggable = true;
    tr.classList.add('draggable');
    tr.addEventListener('dragstart', (e) => {
      if (['INPUT', 'SELECT', 'TEXTAREA', 'BUTTON'].includes(e.target.tagName)) { e.preventDefault(); return; }
      from = i; tr.classList.add('dragging'); e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', String(i));
    });
    tr.addEventListener('dragend', () => { from = null; tr.classList.remove('dragging'); clearMarks(); });
    tr.addEventListener('dragover', (e) => {
      if (from === null || from === i || group(rows[from]) !== group(row)) return;
      e.preventDefault();
      const after = e.offsetY > tr.offsetHeight / 2;
      clearMarks(); tr.classList.add(after ? 'drop-after' : 'drop-before');
    });
    tr.addEventListener('dragleave', () => tr.classList.remove('drop-before', 'drop-after'));
    tr.addEventListener('drop', async (e) => {
      if (from === null || group(rows[from]) !== group(row)) return;
      e.preventDefault();
      const after = tr.classList.contains('drop-after');
      clearMarks();
      const sib = rows.filter((r) => group(r) === group(row) && canDrag(r));
      const moving = rows[from];
      const ids = sib.filter((r) => r !== moving).map((r) => r.id);
      let at = ids.indexOf(row.id); if (after) at += 1;
      ids.splice(at, 0, moving.id);
      from = null;
      try { await save(ids); } catch (err) { toast(err.message || String(err), 'bad'); }
    });
  });
}

// ---- fill handle (as Excel): focus a grid cell (an input or select with data-id and data-field), drag the square at
// its bottom-right corner up or down over other rows; onFill(field, value, ids) gets the rows to give that value ------
export function fillHandle(container, onFill) {
  const knob = h('div', { class: 'fill-knob', title: 'Drag over other rows to give them this value' });
  let src = null;
  const place = (el) => {
    const td = el.closest('td'); if (!td) return;
    src = el; td.classList.add('fill-host'); td.appendChild(knob);
  };
  container.addEventListener('focusin', (e) => { const el = e.target.closest('[data-field]'); if (el && el.dataset.id) place(el); });
  knob.addEventListener('mousedown', (e) => {
    if (!src) return;
    e.preventDefault(); e.stopPropagation();
    const field = src.dataset.field; const value = src.value;
    const tbody = src.closest('tbody'); const ci = src.closest('td').cellIndex;
    const rows = [...tbody.rows].filter((r) => r.style.display !== 'none');
    const from = rows.indexOf(src.closest('tr'));
    let marked = [];
    const mark = (to) => {
      marked.forEach((td) => td.classList.remove('fill-sel')); marked = [];
      const [a, b] = from <= to ? [from, to] : [to, from];
      for (let k = a; k <= b; k++) {
        if (k === from) continue;
        const td = rows[k].cells[ci]; const el = td?.querySelector(`[data-field="${field}"]`);
        if (el) { td.classList.add('fill-sel'); marked.push(td); }
      }
    };
    const move = (ev) => { const tr = document.elementFromPoint(ev.clientX, ev.clientY)?.closest('tr'); const k = rows.indexOf(tr); if (k >= 0) mark(k); };
    const up = async () => {
      document.removeEventListener('mousemove', move); document.removeEventListener('mouseup', up); document.body.classList.remove('filling');
      const ids = marked.map((td) => td.querySelector(`[data-field="${field}"]`).dataset.id);
      marked.forEach((td) => td.classList.remove('fill-sel'));
      if (ids.length) await onFill(field, value, ids);
    };
    document.body.classList.add('filling');
    document.addEventListener('mousemove', move); document.addEventListener('mouseup', up);
  });
}

// ---- name lookup: free text, or pick from the company database, or add what you typed --------------------------------
// lookup(kind, value, {placeholder, onPick}) -> an <input> (read .value as usual) with a dropdown that filters the
// database as you type. kind: client | pm | director | employee | supplier | subcontractor | consultant | company | resource
// (see app/directory.py). The last option adds the typed name to the database; Esc closes the list, free text is kept.
const LOOKUP_DB = { client: 'clients', pm: 'employees', director: 'employees', employee: 'employees', supplier: 'suppliers',
  subcontractor: 'subcontractors', consultant: 'consultants', company: 'companies', resource: 'resources' };
export function lookup(kind, value = '', opts = {}) {
  const inp = h('input', { type: 'text', value: value ?? '', placeholder: opts.placeholder || 'Type to search, or a new name', autocomplete: 'off', class: 'lk-input', ...(opts.attrs || {}) });
  const list = h('div', { class: 'lk-list', hidden: true });
  const wrap = h('span', { class: 'lk' }, inp, list);
  let items = null; let hi = -1; let shown = []; let typed = false;   // on click: the whole list; once typing: filtered
  const load = async () => { if (!items) items = await fetch(`/api/directory/names?kind=${kind}`).then((r) => r.json()).catch(() => []); return items; };
  const close = () => { list.hidden = true; hi = -1; };
  const pick = (name) => { inp.value = name; close(); inp.dispatchEvent(new Event('change', { bubbles: true })); opts.onPick && opts.onPick(name); };
  async function draw() {
    await load();
    const q = typed ? inp.value.trim().toLowerCase() : '';
    shown = items.filter((x) => !q || x.name.toLowerCase().includes(q) || (x.sub || '').toLowerCase().includes(q)).slice(0, 60);
    const exact = items.some((x) => x.name.trim().toLowerCase() === q);
    list.replaceChildren(...shown.map((x, i) => h('div', { class: 'lk-opt' + (i === hi ? ' on' : ''), onmousedown: (e) => { e.preventDefault(); pick(x.name); } },
      h('b', {}, x.name), x.sub ? h('span', {}, x.sub) : null)));
    if (!typed) { const cur = shown.findIndex((x) => x.name === inp.value); if (cur >= 0) list.children[cur]?.classList.add('on'); }
    if (q && !exact) {   // what was typed is not in the database: offer to add it
      list.append(h('div', { class: 'lk-opt lk-add' + (hi === shown.length ? ' on' : ''), onmousedown: async (e) => {
        e.preventDefault();
        try {
          const r = await fetch('/api/directory/add', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ kind, name: inp.value.trim() }) }).then((x) => x.json());
          items = null; toast(`${r.name} added to ${LOOKUP_DB[kind] || 'the database'}`); pick(r.name || inp.value.trim());
        } catch (err) { toast('Could not add: ' + err.message, 'bad'); }
      } }, `+ Add "${inp.value.trim()}" to ${LOOKUP_DB[kind] || 'the database'}`));
    }
    if (!shown.length && !q) list.append(h('div', { class: 'lk-opt muted' }, 'Nothing in the database yet: type a name to add it'));
    list.hidden = false;
  }
  inp.addEventListener('focus', () => { typed = false; draw(); });
  inp.addEventListener('input', () => { typed = true; hi = -1; draw(); });
  inp.addEventListener('blur', () => setTimeout(close, 120));
  inp.addEventListener('keydown', (e) => {
    if (list.hidden) return;
    const n = list.querySelectorAll('.lk-opt:not(.muted)').length;
    if (e.key === 'ArrowDown') { e.preventDefault(); hi = Math.min(n - 1, hi + 1); draw(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); hi = Math.max(-1, hi - 1); draw(); }
    else if (e.key === 'Enter' && hi >= 0) { e.preventDefault(); list.querySelectorAll('.lk-opt:not(.muted)')[hi]?.dispatchEvent(new MouseEvent('mousedown')); }
    else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close(); }   // Esc closes the list only (not the page)
  });
  // the input stands in for the field: callers read inp.value, set inp.onchange; the wrapper goes in the form
  inp.wrap = wrap;
  wrap.input = inp;
  Object.defineProperty(wrap, 'value', { get: () => inp.value, set: (v) => { inp.value = v; } });
  return opts.wrapped === false ? inp : wrap;
}


// Ask for the file name first, then download a PDF from `url` (the name is passed as ?name=)
export function pdfNameDialog({ title = 'Download as a PDF', suggest = '', url, hint = '' }) {
  const name = h('input', { type: 'text', value: suggest.replace(/[\\/:*?"<>|]+/g, ' ').replace(/\s+/g, ' ').trim(), style: { width: '100%' } });
  modal({ title, body: h('div', {}, field('File name', name, 'Without .pdf; it is added for you'), hint ? h('div', { class: 'small muted' }, hint) : null),
    actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} }, { label: 'Download', onClick: () => { window.open(`${url}${url.includes('?') ? '&' : '?'}name=${encodeURIComponent(name.value.replace(/\.pdf$/i, ''))}`); } }] });
  setTimeout(() => { name.focus(); name.select(); }, 50);
}


// A quiet filter bar: a button with a count of what is on, and the rest of the filters in a small panel under it. `items` are elements (chips or
// labelled checkboxes); `redraw` rebuilds the bar when one is clicked, so the panel's open state is kept in `fm.open` per label.
export const fm = { open: {} };
export function filterMenu(label, items, count = 0) {
  const pop = h('div', { class: 'pop' }, ...items);
  const wrap = h('span', { class: 'fmenu' });
  const btn = h('button', { class: 'btn ghost sm', onclick: (e) => { e.stopPropagation(); fm.open[label] = !fm.open[label]; pop.style.display = fm.open[label] ? '' : 'none'; } }, label, count ? h('span', { class: 'n' }, String(count)) : null);
  pop.style.display = fm.open[label] ? '' : 'none';
  wrap.append(btn, pop);
  if (!fm.bound) { fm.bound = true; document.addEventListener('mousedown', (e) => { if (!e.target.closest('.fmenu')) { Object.keys(fm.open).forEach((k) => { fm.open[k] = false; }); document.querySelectorAll('.fmenu .pop').forEach((p) => { p.style.display = 'none'; }); } }, true); }
  return wrap;
}
