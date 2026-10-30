// The outline's logic with no page in it: the two kinds of grid, which groups are folded, which columns show, and what the 1 2 (3) levels do.
// (outline.js draws the strip; this file has no imports so it can be tested on its own.)
export function fyQuarter(m) {
  const y = +m.slice(0, 4); const mo = +m.slice(5, 7); const fy = mo >= 7 ? y + 1 : y; const q = Math.floor(((mo + 5) % 12) / 3) + 1;
  return { key: `${fy}-Q${q}`, label: `Q${q} FY${String(fy).slice(2)}` };
}
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
// ---- the two kinds of grid the app has --------------------------------------------------------------------------------
// months: one level of group (the Australian financial year quarter). days: two (month, then week).
export const MONTH_LEVELS = [{ name: 'quarter', key: (c) => fyQuarter(c.id).key, label: (c) => fyQuarter(c.id).label }];
const mondayOf = (iso) => { const d = new Date(iso + 'T00:00:00Z'); const dow = (d.getUTCDay() + 6) % 7; d.setUTCDate(d.getUTCDate() - dow); return d.toISOString().slice(0, 10); };
export const DAY_LEVELS = [
  { name: 'month', key: (c) => c.id.slice(0, 7), label: (c) => `${MON[+c.id.slice(5, 7) - 1]}-${c.id.slice(2, 4)}` },
  { name: 'week', key: (c) => mondayOf(c.id), label: (c) => `Wk ${+mondayOf(c.id).slice(8, 10)} ${MON[+mondayOf(c.id).slice(5, 7) - 1]}` },
];

// columns: [{ id, ... }] in order; cur: index of the column that must always show (the status month, today); levels: MONTH_LEVELS or DAY_LEVELS
export function defaultFolded(cols, cur, levels) {
  if (cur < 0 || !cols.length) return [];
  const out = new Set();
  levels.forEach((lv, k) => { const ck = lv.key(cols[cur]); const keys = []; cols.forEach((c) => { const g = lv.key(c); if (!keys.includes(g)) keys.push(g); }); keys.filter((g) => keys.indexOf(g) < keys.indexOf(ck)).forEach((g) => out.add(`${k}:${g}`)); });
  return [...out];
}
export const foldedSet = (st, cols, cur, levels) => new Set(st.folded ?? defaultFolded(cols, cur, levels));

// the columns that show: every column except hidden ones and those inside a folded group; the current column always shows
export function visible(cols, cur, st, levels) {
  const folded = foldedSet(st, cols, cur, levels); const hid = new Set(st.hidden);
  return cols.map((c, i) => i === cur || (!hid.has(c.id) && !levels.some((lv, k) => folded.has(`${k}:${lv.key(c)}`))));
}

// the 1 2 (3) levels: the last shows everything; each step down folds one more level of group, except around the current column
export function levelFolds(cols, cur, levels, level) {
  const n = levels.length; const out = [];
  if (cur < 0) return out;
  levels.forEach((lv, k) => {
    if (k >= n + 1 - level) return;                       // this depth stays open at this level
    const mine = lv.key(cols[cur]); const seen = new Set();
    cols.forEach((c) => { const g = lv.key(c); if (seen.has(g)) return; seen.add(g); if (g !== mine) out.push(`${k}:${g}`); });
  });
  return out;
}
export function currentLevel(cols, cur, st, levels) {
  if (!st.hidden.length && foldedSet(st, cols, cur, levels).size === 0) return levels.length + 1;
  for (let L = 1; L <= levels.length; L++) {
    const want = new Set(levelFolds(cols, cur, levels, L)); const have = foldedSet(st, cols, cur, levels);
    if (!st.hidden.length && want.size === have.size && [...want].every((x) => have.has(x))) return L;
  }
  return 0;
}

