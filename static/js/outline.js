// Outline for wide grids (months, days): groups of columns fold to nothing and a thin strip above the table gives them back.
//   - a bracket with a minus over each open group (quarter, month, week), named on the line
//   - a ring + where a whole group is folded, a small dot + where single columns are hidden inside an open group (names on hover)
//   - 1 2 (3) buttons: 1 is the narrowest view around the current column, the last number shows everything
//   - "Show all" while anything is hidden
// Folded and hidden columns take no width: the page draws only the columns `visible()` lets through. The strip is built from the real
// header cells (th[data-col]) once the table is on the page, so it lines up whatever the column widths are.
import { h } from './ui.js';
import { MONTH_LEVELS, DAY_LEVELS, defaultFolded, foldedSet, visible, levelFolds, currentLevel } from './outlinecore.js';
export { MONTH_LEVELS, DAY_LEVELS, defaultFolded, foldedSet, visible, levelFolds, currentLevel };

const LS = 'pmt.outline';
const load = (key) => { try { return (JSON.parse(localStorage.getItem(LS) || '{}'))[key] || null; } catch (e) { return null; } };
const store = (key, v) => { try { const all = JSON.parse(localStorage.getItem(LS) || '{}'); all[key] = v; localStorage.setItem(LS, JSON.stringify(all)); } catch (e) { /* storage may be blocked */ } };

// ---- state: which groups are folded, which single columns are hidden (kept per grid on this PC) --------------------------
// folded: ["0:2026-Q1", "1:2026-09-28"] (level index : group key); null means "the default": groups wholly before the current column.
export function outlineState(key, init = {}) {
  const st = Object.assign({ folded: null, hidden: [] }, init, load(key) || {});   // init: { folded: [] } for grids that should open with every group open
  st.save = () => store(key, { folded: st.folded, hidden: st.hidden });
  return st;
}


// ---- the strip --------------------------------------------------------------------------------------------------------
// opts: { cols, cur, levels, st, onChange, names: {1: 'this quarter', 2: 'every month'} }. Returns { el, mount(tw, table) }.
export function outlineStrip(opts) {
  const { cols, cur, levels, st, onChange } = opts;
  const n = levels.length;
  // summary: a folded group stays on the page as one summary column (th[data-sum]) with a ring over it, instead of vanishing (the Labour calendar);
  // there nothing is protected from folding, and `focus` is the column the 1 2 3 levels centre on
  const summary = !!opts.summary; const focus = opts.focus ?? cur; const prot = summary ? -1 : cur;
  const folded = foldedSet(st, cols, focus, levels);
  const vis = visible(cols, prot, st, levels);
  const change = (fn) => { fn(); st.save(); onChange(); };
  const explicit = () => { if (st.folded === null) st.folded = [...folded]; return new Set(st.folded); };
  const anything = vis.some((v) => !v);
  const el = h('div', { class: 'ol' + (n > 1 ? ' ol2' : '') });
  const lv = h('div', { class: 'ol-lv' }, ...Array.from({ length: n + 1 }, (_, i) => i + 1).map((L) => h('b', { class: currentLevel(cols, focus, st, levels) === L ? 'on' : '', 'data-tip': (opts.names && opts.names[L]) || (L === n + 1 ? 'Show everything' : `Level ${L}`),
    onclick: () => change(() => { st.hidden = []; st.folded = L === n + 1 ? [] : levelFolds(cols, focus, levels, L); }) }, String(L))));
  const clip = h('div', { class: 'ol-clip' }); const inner = h('div', { class: 'ol-in' }); clip.append(inner);
  const all = anything ? h('a', { class: 'ol-all', onclick: () => change(() => { st.hidden = []; st.folded = []; }) }, 'Show all') : null;
  el.append(lv, clip, ...(all ? [all] : []));

  function mount(tw, table) {
    let ro = null;
    const draw = () => {
      inner.replaceChildren();
      const seq = [...table.querySelectorAll('thead th[data-col]')]; const ths = seq.filter((th) => !th.dataset.sum); const sums = seq.filter((th) => th.dataset.sum);
      if (!seq.length) return;
      // the columns that stay in view while the months scroll (sticky ones): marks never draw over them
      let frozenW = 0; [...table.tHead.rows[0].cells].forEach((c) => { if (!c.dataset.col && !c.dataset.m) { const cs = getComputedStyle(c); if (cs.position === 'sticky' && cs.left !== 'auto') frozenW = Math.max(frozenW, c.offsetLeft + c.offsetWidth); } });
      clip.style.left = frozenW + 'px'; lv.style.width = Math.max(frozenW - 8, 40) + 'px';
      inner.style.width = table.offsetWidth + 'px';
      const sync = () => { inner.style.transform = `translateX(${-tw.scrollLeft}px)`; };
      sync(); tw.removeEventListener('scroll', tw._olSync || (() => {})); tw._olSync = sync; tw.addEventListener('scroll', sync, { passive: true });
      const at = (th, side) => (side === 'l' ? th.offsetLeft : th.offsetLeft + th.offsetWidth) - frozenW;
      const byId = new Map(); ths.forEach((th) => { const o = byId.get(th.dataset.col) || { l: th, r: th }; o.r = th; byId.set(th.dataset.col, o); });
      const idx = new Map(cols.map((c, i) => [c.id, i]));
      const seamList = [];
      // rings and dots: at every seam where columns are missing
      let i = 0;
      while (!summary && i < cols.length) {
        if (vis[i]) { i++; continue; }
        let j = i; while (j + 1 < cols.length && !vis[j + 1]) j++;
        const missing = cols.slice(i, j + 1);
        const prev = i > 0 ? byId.get(cols[i - 1].id) : null; const next = j < cols.length - 1 ? byId.get(cols[j + 1].id) : null;
        const x = prev ? at(prev.r, 'r') : next ? at(next.l, 'l') : 0;
        const marks = [];
        // the outermost folded group a column sits in gets a ring (once); columns hidden on their own, or inside a group that is still partly open, share a dot
        const rings = []; const dotCols = [];
        missing.forEach((c) => {
          let g = null;
          for (let k = 0; k < n; k++) { const gk = `${k}:${levels[k].key(c)}`; if (folded.has(gk)) { g = { k, gk, name: levels[k].label(c) }; break; } }
          const wholly = g && cols.filter((cc) => levels[g.k].key(cc) === levels[g.k].key(c)).every((cc) => !vis[idx.get(cc.id)]);
          if (g && wholly) { if (!rings.some((r) => r.gk === g.gk)) rings.push({ ...g, n: cols.filter((cc) => levels[g.k].key(cc) === levels[g.k].key(c)).length }); } else dotCols.push(c);
        });
        const tag = (el, row) => { el._row = row; return el; };
        if (rings.length > 2) {   // a long run of folded groups is one ring, not a row of them
          const k0 = rings[0].k; const gks = rings.map((r) => r.gk); const total = rings.reduce((a, r) => a + r.n, 0);
          marks.push(tag(h('i', { class: 'ol-ring', 'data-tip': `${rings[0].name} to ${rings[rings.length - 1].name} (${rings.length} groups, ${total} columns) \u00b7 click to show`, onclick: () => change(() => { const s2 = explicit(); gks.forEach((g) => s2.delete(g)); st.folded = [...s2]; const gone = new Set(cols.filter((cc) => gks.includes(`${k0}:${levels[k0].key(cc)}`)).map((cc) => cc.id)); st.hidden = st.hidden.filter((x) => !gone.has(x)); }) }, '+'), k0));
          rings.length = 0;
        }
        rings.forEach((r) => marks.push(tag(h('i', { class: 'ol-ring', 'data-tip': `${r.name} (${r.n} ${r.n === 1 ? 'column' : 'columns'}) · click to show`, onclick: () => change(() => { const s = explicit(); s.delete(r.gk); st.folded = [...s]; const gone = new Set(cols.filter((cc) => levels[r.k].key(cc) === r.gk.slice(r.gk.indexOf(':') + 1)).map((cc) => cc.id)); st.hidden = st.hidden.filter((x) => !gone.has(x)); }) }, '+'), r.k)));
        if (dotCols.length) marks.push(tag(h('i', { class: 'ol-dot', 'data-tip': `${dotCols.map((c) => levels[n - 1].label(c)).join(', ')} · click to show`, onclick: () => change(() => {
          const ids = new Set(dotCols.map((c) => c.id)); st.hidden = st.hidden.filter((x) => !ids.has(x));
          const s = explicit(); dotCols.forEach((c) => levels.forEach((l, k) => s.delete(`${k}:${l.key(c)}`))); st.folded = [...s]; }) }, '+'), n - 1));
        const rows = new Map(); marks.forEach((m) => { const r = m._row; if (!rows.has(r)) rows.set(r, []); rows.get(r).push(m); });
        seamList.push({ x, edge: !prev, rows, w: marks.reduce((a, m) => a + (m.classList.contains('ol-ring') ? 17 : 14), 0) });
        i = j + 1;
      }
      // brackets: one row per level; a bracket spans the visible columns of an open group that sit side by side
      levels.forEach((lvl, k) => {
        let run = null;
        const flush = () => {
          if (!run) return;
          const lx = at(run.first, 'l'); const pad = (seamList.find((q) => Math.abs(q.x - lx) < 4) || { w: 0 }).w; const a = lx + 2 + (pad ? pad + 4 : 0); const b = at(run.last, 'r') - 2; const gkey = run.g;
          const total = cols.filter((c) => lvl.key(c) === gkey).length; const shown = cols.filter((c, i) => lvl.key(c) === gkey && vis[i]).length;
          const name = lvl.label({ id: run.cid });
          const br = h('div', { class: 'ol-br l' + k, style: { left: a + 'px', width: Math.max(b - a, 14) + 'px', top: (n === 1 ? 24 : 24 + k * 18) + 'px' } },
            h('i', { class: 'ol-btn', 'data-tip': `Fold ${name}`, onclick: () => change(() => { const s = explicit(); s.add(`${k}:${gkey}`); st.folded = [...s]; }) }, '−'),
            h('span', {}, name, !summary && shown < total ? h('em', {}, ` · ${total - shown} hidden`) : null));
          inner.append(br); run = null;
        };
        // a summary column joins the bracket of the groups outside it (a folded week sits inside its month's bracket) but not its own level
        const mine = seq.filter((th) => !th.dataset.sum || k < +th.dataset.sum.split(':')[0]);
        mine.forEach((th, j) => {
          const i = idx.get(th.dataset.col); const g = lvl.key(cols[i]);
          if (run && (run.g !== g || th.offsetLeft - (run.last.offsetLeft + run.last.offsetWidth) > 1)) flush();
          if (!run) run = { g, first: th, last: th, cid: cols[i].id }; else run.last = th;
          if (j === mine.length - 1) flush();
        });
      });
      sums.forEach((th) => {
        const [k0, gk0] = [+th.dataset.sum.split(':')[0], th.dataset.sum];
        const x = (th.offsetLeft + th.offsetWidth / 2) - frozenW - 7.5;
        inner.append(h('div', { class: 'ol-seam', style: { left: x + 'px', top: (n === 1 ? 22 : 22 + k0 * 18) + 'px' } },
          h('i', { class: 'ol-ring', 'data-tip': th.dataset.tip || 'Open', onclick: () => change(() => { const s = explicit(); s.delete(gk0); st.folded = [...s]; }) }, '+')));
      });
      seamList.forEach((q) => q.rows.forEach((ms, r) => inner.append(h('div', { class: 'ol-seam', style: { left: (q.x - (q.edge ? -2 : 7)) + 'px', top: (n === 1 ? 22 : 22 + r * 18) + 'px' } }, ...ms))));
    };
    requestAnimationFrame(() => { draw(); setTimeout(draw, 160); setTimeout(draw, 700); });
    if (window.ResizeObserver) { ro = new ResizeObserver(() => draw()); ro.observe(table); }
    return () => { if (ro) ro.disconnect(); };
  }
  return { el, mount };
}
