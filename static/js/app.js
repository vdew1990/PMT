import { h, clear, modal, toast, field, select, fmt, badge, confirmBox , lookup } from './ui.js';
import { watchTables } from './tabletools.js';
import { watchTiles } from './tilelinks.js';
import { watchTileLayout } from './tilelayout.js';
import { mountHelp } from './help.js';
import { openSearch } from './search.js';
import { pickOpportunity, crmStatus } from './views/_crmpick.js';
import { api, state, p, loadProject, loadProjects, saveLocal, loadLocal, pref } from './api.js';

const NAV = [
  ['OVERVIEW', [['dashboard', 'Dashboard'], ['portfolio', 'Portfolio'], ['program', 'Program'], ['team', 'Team'], ['directory', 'Stakeholders']]],
  ['SETUP', [['setup?step=project', 'Project'], ['complexity', 'Project complexity'], ['projectteam', 'Project team'], ['setup?step=contract', 'Contract value'], ['setup?step=cbs', 'CBS and allowances'], ['setup?step=allowance', 'Allowance'], ['setup?step=programme', 'Project schedule'], ['setup?step=pronto', 'Pronto data'], ['setup?step=initialise', 'Initialise'], ['linked', 'Linked projects']]],
  ['PMO', [['pmolibrary', 'Project library'], ['lifecycle', 'Project lifecycle'], ['flow', 'Workflow'], ['ecf', 'Classification framework'], ['library', 'Archive']]],
  ['COMMUNICATION', [['projstakeholders', 'Stakeholders'], ['commatrix', 'Communication matrix'], ['meetings', 'Meetings'], ['orgchart', 'Project org chart']]],
  ['REVENUE', [['revenue', 'Contract and claims'], ['variations', 'Variations']]],
  ['COST', [['costcontrol', 'Cost control'], ['risk', 'Allowances'], ['pronto', 'Pronto data'], ['actuals', 'Actuals'], ['commitments', 'Commitments'], ['accruals', 'Accruals'], ['subcontracts', 'Subcontracts']]],
  ['FORECAST', [['programme', 'Project schedule'], ['forecast', 'Forecast lines'], ['groundup', 'Ground-Up register'], ['fhistory', 'Forecast history'], ['calendar', 'Labour calendar'], ['directory?tab=rates', 'Rates']]],
  ['MONTH-END', [['monthend', 'Month-end'], ['review', 'Review lines'], ['reports', 'Snapshots and history'], ['eom', 'EOM report (finance)']]],
  ['REPORTING', [['pmr', 'PMR (internal board)'], ['psr', 'PSR (client)']]],
  ['CLOSE-OUT', [['closeout', 'Close-out checklist']]],
  ['CONTROL', [['diagnostics', 'Diagnostics'], ['reconcile', 'Reconcile'], ['myprofile', 'My profile'], ['objects', 'Data objects'], ['activity', 'Activity and history'], ['settings', 'Settings'], ['shortcuts', 'Shortcuts']]]
];

let current = null;
const NO_PROJECT = ['myprofile', 'objects', 'ecf', 'portfolio', 'program', 'team', 'library', 'directory', 'commatrix', 'pmolibrary', 'lifecycle', 'meetings', 'flow', 'shortcuts'];
// Program and Team are for project directors: they show in the menu while the profile role says Project Director (a view, not a lock: PMT does not sign people in)
const DIRECTOR_ONLY = ['program', 'team'];
// Project Director and above (the same test as app/complexity.py DIRECTOR)
export const isDirector = () => /director|general manager|operations manager|head of|chief|\bcoo\b|executive|chair/i.test(state.me?.role || '');   // pages across projects: they work with no project open
// a parent project only reads its children's figures: these pages work on it, the rest are for its child projects
const PARENT_PAGES = ['dashboard', 'portfolio', 'program', 'team', 'library', 'directory', 'commatrix', 'pmolibrary', 'lifecycle', 'meetings', 'flow', 'shortcuts', 'linked', 'costcontrol', 'settings', 'forecast', 'revenue', 'eom', 'pmr', 'psr'];
// pages that show a parent project's figures (the sum of its child projects) but cannot change them
const PARENT_READ_ONLY = ['forecast', 'revenue', 'eom', 'pmr', 'psr'];
const isParent = () => !!state.project?.is_parent;

// open another project on a page (drilling from a parent, portfolio or program down to a child's line)
export async function openIn(pid, page, params) {
  state.pid = +pid; state.scope = { node: null, from: null, to: null }; saveLocal();
  await loadProjects();
  const hash = '#/' + page + (params ? '?' + new URLSearchParams(params) : '');
  if (location.hash === hash) await render();
  else location.hash = hash;   // the hash change renders the page (once: a second render would close the drawer it opens)
}

export function route() {
  const hash = location.hash.replace(/^#\/?/, '') || 'dashboard';
  const [name, qs] = hash.split('?');
  return { name, params: Object.fromEntries(new URLSearchParams(qs || '')) };
}
// the menu layout lives in the person's profile (follows them between PCs), not in the browser
export function saveMenu() {
  api.put('/api/me/menu', { order: state.menu?.order || [], open: state.menu?.open ?? null }).catch(() => toast('The menu layout could not be saved to your profile', 'bad'));
}
// global search: the pages this person can see, plus projects, lines, documents, clients and people
export function searchPages() {
  return NAV.map(([grp, items]) => [grp, (isParent() ? items.filter(([k]) => PARENT_PAGES.includes(k)) : items).filter(([k]) => isDirector() || !DIRECTOR_ONLY.includes(k))])
    .flatMap(([grp, items]) => items.map(([k, label]) => [k, label, grp[0] + grp.slice(1).toLowerCase()]));
}
export function searchOpen() {
  openSearch({ pages: searchPages(), go, switchProject: async (id) => { state.pid = id; state.scope = { node: null, from: null, to: null }; saveLocal(); await boot(); } });
}
// keyboard shortcuts: the person's own set (Settings > Shortcuts), else these
export const DEFAULT_SHORTCUTS = [{ combo: 'Ctrl+K', action: 'search' }, { combo: '/', action: 'search' }];
export function comboOf(e) {
  const k = e.key;
  if (['Control', 'Shift', 'Alt', 'Meta'].includes(k)) return '';
  const name = k.length === 1 ? k.toUpperCase() : k === 'ArrowLeft' ? 'Left' : k === 'ArrowRight' ? 'Right' : k === 'ArrowUp' ? 'Up' : k === 'ArrowDown' ? 'Down' : k;
  return [(e.ctrlKey || e.metaKey) ? 'Ctrl' : '', e.altKey ? 'Alt' : '', e.shiftKey && !(k.length === 1 && !/[a-z0-9]/i.test(k)) ? 'Shift' : '', name].filter(Boolean).join('+');
}
export function runShortcut(action) {
  if (action === 'search') searchOpen();
  else if (action === 'back') history.back();
  else if (action === 'forward') history.forward();
  else if (action.startsWith('page:')) location.hash = '#/' + action.slice(5);
}
document.addEventListener('keydown', (e) => {
  const combo = comboOf(e);
  if (!combo || document.body.dataset.capturing) return;
  const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName || '') || document.activeElement?.isContentEditable;
  const hit = (state.shortcuts || DEFAULT_SHORTCUTS).find((x) => x.combo === combo);
  if (!hit) return;
  if (typing && !/^(Ctrl|Alt)\+|^F\d+$/.test(hit.combo)) return;   // a plain key never fires while typing
  e.preventDefault(); runShortcut(hit.action);
});

// back to the default menu: group order and which groups are open
export function resetMenu() {
  state.menu = { order: [], open: null };
  saveMenu();
  state.tiles = {}; api.put('/api/me/tiles', { reset: true }).catch(() => { /* nothing to reset */ });
  render();
}

// ---- Project setup drafts: a change on the Contract value, CBS or Project schedule step is kept only when the user saves it ----
// The first change takes a restore point; Save drops it (the changes stay), Don't save puts everything back.
export const draft = { rid: null, pid: null, step: null, hash: null };
const DRAFT_STEPS = ['contract', 'cbs', 'programme'];
const OWN_UNDO = ['/setup/', '/load-template', '/cmt/', '/restore-points', '/pronto/', '/initialise', '/programme/upload'];   // these confirm or undo themselves (a schedule file is already read when it is dropped: it says how many tasks it loaded)
api.beforeWrite = async (method, url) => {
  const r = route();
  const step = r.params.step || 'project';
  if (draft.rid || r.name !== 'setup' || !DRAFT_STEPS.includes(step) || !url.startsWith('/api/p/') || OWN_UNDO.some((x) => url.includes(x))) return;
  const out = await api.post(`/api/p/${state.pid}/setup/draft`, { step });
  Object.assign(draft, { rid: out.id, pid: state.pid, step, hash: location.hash });
};
export async function commitDraft() {
  if (!draft.rid) return false;
  await api.post(`/api/p/${draft.pid}/setup/draft/${draft.rid}/commit`, {});
  Object.assign(draft, { rid: null }); return true;
}
async function discardDraft() {
  await api.post(`/api/p/${draft.pid}/setup/draft/${draft.rid}/discard`, {});
  Object.assign(draft, { rid: null });
}
// 'save', 'discard' or 'stay'
function askDraft() {
  const label = { contract: 'Contract value', cbs: 'CBS and allowances', programme: 'Project schedule' }[draft.step] || 'this step';
  return new Promise((res) => modal({ title: 'Save your changes?', onClose: () => res('stay'),
    body: h('p', {}, `You changed ${label} but have not saved. Are you happy to save it? "Don't save" puts the step back as it was before you started.`),
    actions: [{ label: 'Stay on this step', kind: 'ghost', onClick: () => res('stay') }, { label: 'Don\'t save', kind: 'ghost', onClick: async () => { await discardDraft(); res('discard'); } },
      { label: 'Save', onClick: async () => { await commitDraft(); res('save'); } }] }));
}
window.addEventListener('beforeunload', (e) => { if (draft.rid) { e.preventDefault(); e.returnValue = ''; } });

export const go = (name, params) => { location.hash = '#/' + name + (params ? '?' + new URLSearchParams(params) : ''); };

// the menu groups are keyed by their upper-case names (the saved order uses them); the menu shows them in sentence case
const niceName = (g) => (g === 'PMO' ? 'PMO' : g.charAt(0) + g.slice(1).toLowerCase());
function renderSide(active, health) {
  // a menu item may name a Project setup step (setup?step=contract): it is on when that step is open
  const cur = route();
  const isOn = (k) => (k.startsWith('directory?') ? active === 'directory' && ['rates', 'srates'].includes(cur.params.tab) : k === 'directory' ? active === 'directory' && !['rates', 'srates'].includes(cur.params.tab) : k.includes('?') ? (active === 'setup' && k === `setup?step=${cur.params.step || 'project'}`) || (active === 'cbs' && k === 'setup?step=cbs') : k === active || (k === 'lifecycle' && ['gates', 'phases'].includes(active)));
  const side = clear(document.getElementById('side'));
  side.append(h('div', { class: 'brand' }, h('img', { src: '/static/img/epec-icon.png', alt: 'EPEC', class: 'logo' }), h('div', {}, h('b', {}, 'Project Management Tool'), h('span', {}, 'Cost control for EPC delivery'))));
  const nav = h('nav');
  // each group folds: closed by default except the one holding the page you are on; what you open is remembered
  let opened = state.menu ? state.menu.open : null;
  const open = new Set(opened || []);
  // the groups (workspaces) can be dragged into the order the user wants; the order is remembered on this PC
  let order = state.menu?.order?.length ? state.menu.order : [];
  const names = NAV.map((g) => g[0]);
  // a group the saved order does not know yet (a new release) goes after the group before it in the standard menu, not at the end
  const ranked = order.filter((n) => names.includes(n));
  names.forEach((n, i) => { if (!ranked.includes(n)) { const at = i > 0 ? ranked.indexOf(names[i - 1]) : -1; ranked.splice(at + 1, 0, n); } });
  const moveGroup = (from, before) => {
    if (from === before) return;
    const next = ranked.filter((n) => n !== from); next.splice(next.indexOf(before), 0, from);
    state.menu = { ...(state.menu || {}), order: next }; saveMenu();
    renderSide(active, health);
  };
  [...NAV].sort((a, b) => ranked.indexOf(a[0]) - ranked.indexOf(b[0])).map(([grp, items]) => [grp, (isParent() ? items.filter(([k]) => PARENT_PAGES.includes(k)) : items).filter(([k]) => isDirector() || !DIRECTOR_ONLY.includes(k))]).filter(([, items]) => items.length).forEach(([grp, items]) => {
    const here = items.some(([k]) => isOn(k));
    const isOpen = here || open.has(grp);
    const flag = health && (health.error || health.warn) && items.some(([k]) => k === 'dashboard') ? h('span', { class: 'badge ' + (health.error ? 'bad' : 'warn') }, health.error || health.warn) : null;
    const box = h('div', { class: 'navitems', style: { display: isOpen ? '' : 'none' } });
    const head = h('div', { class: 'grp fold' + (isOpen ? ' open' : ''), title: isOpen ? 'Fold' : 'Unfold', onclick: () => {
      const now = box.style.display === 'none';
      box.style.display = now ? '' : 'none';
      head.classList.toggle('open', now);
      if (now) open.add(grp); else open.delete(grp);
      state.menu = { ...(state.menu || {}), open: [...open] }; saveMenu();
      if (flag) flag.style.display = now ? 'none' : '';
    } }, h('span', { class: 'arr' }, '\u25b8'), niceName(grp), flag);
    if (flag && isOpen) flag.style.display = 'none';
    items.forEach(([k, label]) => {
      const a = h('a', { class: 'nav' + (isOn(k) ? ' on' : ''), href: '#/' + k }, label);
      if (k === 'dashboard' && health && (health.error || health.warn)) {
        a.append(h('span', { class: 'badge ' + (health.error ? 'bad' : 'warn') }, health.error || health.warn));
      }
      box.append(a);
    });
    head.draggable = true; head.title = (isOpen ? 'Fold' : 'Unfold') + '. Drag to move this group up or down';
    head.addEventListener('dragstart', (e) => { e.dataTransfer.setData('text/plain', grp); e.dataTransfer.effectAllowed = 'move'; });
    const sec = h('div', { class: 'navgrp' }, head, box);
    sec.addEventListener('dragover', (e) => { e.preventDefault(); sec.classList.add('dropat'); });
    sec.addEventListener('dragleave', () => sec.classList.remove('dropat'));
    sec.addEventListener('drop', (e) => { e.preventDefault(); sec.classList.remove('dropat'); moveGroup(e.dataTransfer.getData('text/plain'), grp); });
    nav.append(sec);
  });
  side.append(nav, h('a', { class: 'resetmenu', title: 'Put the menu groups and the tiles back in their default layout', onclick: resetMenu }, 'Reset menu and tiles'), h('div', { class: 'foot' }, 'Commercial in Confidence', h('br'), 'AUD excl. GST', h('br'), h('span', { id: 'release' }, state.me?.release ? `Release ${state.me.release}` : '')));
}

async function renderTop() {
  const top = clear(document.getElementById('top'));
  // archived projects stay off the list (except the one open now); they open and restore from "Archived projects..."
  const archived = state.projects.filter((x) => x.archived_at);
  const listed0 = state.projects.filter((x) => !x.archived_at || x.id === state.pid);
  // a parent with its children right under it
  const ids0 = new Set(listed0.map((x) => x.id));
  const listed = [];
  listed0.filter((x) => !x.parent_project_id || !ids0.has(x.parent_project_id)).forEach((x) => {
    listed.push(x);
    if (x.is_parent) listed0.filter((c) => c.parent_project_id === x.id).forEach((c) => listed.push(c));
  });
  const label = (x) => (x.parent_project_id && ids0.has(x.parent_project_id) ? '\u00a0\u00a0\u00a0\u21b3 ' : '') + (x.archived_at ? '[Archived] ' : x.is_template ? '[Template] ' : x.is_parent ? '\u25a3 ' : '') + x.name + (x.is_parent ? ' (parent)' : '');
  const sel = select([...listed.map((x) => [x.id, label(x)]),
    ...(archived.length ? [['archived', `Archive: ${archived.length} archived...`]] : [])], state.pid, {
    onchange: async (e) => {
      if (e.target.value === 'archived') { e.target.value = state.pid; go('library'); return; }
      state.pid = +e.target.value; state.scope = { node: null, from: null, to: null }; saveLocal(); await boot(); },
    style: { fontWeight: 700, color: 'var(--navy)', maxWidth: '320px' },
  });
  // a quiet top bar: back and forward as arrows on the left, the project and its state, then icon buttons on the right
  sel.className = 'tb-select';
  top.append(tbBtn('navback', 'chevL', 'Back to the previous page', () => history.back(), window.navigation ? !navigation.canGoBack : false),
    tbBtn('navfwd', 'chevR', 'Forward to the next page', () => history.forward(), window.navigation ? !navigation.canGoForward : false), sel);
  if (state.project?.archived_at) {
    top.append(h('span', { class: 'tb-pill warn', title: `Archived ${state.project.archived_at}${state.project.archived_by ? ' by ' + state.project.archived_by : ''}. It is off the project list; everything is kept.` }, 'Archived'),
      h('button', { class: 'tb-text', onclick: () => setArchived(state.pid, false) }, 'Restore'));
  }
  if (state.project) {
    if (isParent()) top.append(h('a', { class: 'tb-pill', href: '#/linked', title: 'A parent project: its child projects\' figures together. Read-only: changes are made in the child projects.' },
      `Parent · ${state.projects.filter((x) => x.parent_project_id === state.pid).length} linked`));
    else top.append(h('span', { class: 'tb-state', title: state.project.initialised ? 'Cost control is live' : 'Set-up in progress: initialise the project in Project setup' }, h('i', { class: state.project.initialised ? 'on' : 'off' }), state.project.initialised ? 'Live' : 'Setting up'));
    const par = state.projects.find((x) => x.id === state.project.parent_project_id);
    if (par) top.append(h('a', { class: 'tb-pill', title: 'This project is linked under a parent project: open the parent for the combined figures', onclick: () => openIn(par.id, 'dashboard') }, '\u2191 ' + par.name));
    // the status date can be changed right here (not on a parent project: it takes its children's)
    const shown = fmt.date(state.project.status_date) || 'No status date';
    if (isParent()) top.append(h('span', { class: 'tb-date', title: 'Status date: the latest of the child projects' }, shown));
    else top.append(h('button', { class: 'tb-date edit', title: 'Status date: the date cost control reports as at. Click to change it.', onclick: (e) => {
      const btn = e.currentTarget;
      const input = h('input', { type: 'date', value: (state.project.status_date || '').slice(0, 10), class: 'tb-dateinput' });
      btn.replaceWith(input); input.focus(); try { input.showPicker?.(); } catch (err) { /* the picker needs a user gesture in some browsers */ }
      let done = false;
      const finish = async (save) => {
        if (done) return; done = true;
        const v = input.value; const old = (state.project.status_date || '').slice(0, 10);
        if (!save || !v || v === old) { input.replaceWith(btn); return; }
        if (v.slice(0, 7) !== old.slice(0, 7) && !(await confirmBox(`Change the status date to ${fmt.date(v)}? Cost control, forecasts and reports then work as at ${fmt.month(v.slice(0, 7))}.`, 'Change status date'))) { input.replaceWith(btn); return; }
        try { await api.put(`/api/projects/${state.pid}`, { status_date: v }); toast('Status date changed'); await loadProjects(); await render(); } catch (err) { toast(err.message, 'bad'); input.replaceWith(btn); }
      };
      input.addEventListener('change', () => finish(true)); input.addEventListener('blur', () => setTimeout(() => finish(input.value !== ''), 150));
      input.addEventListener('keydown', (ev) => { if (ev.key === 'Escape') finish(false); });
    } }, shown));
  }
  if (state.scope.node) {
    top.append(h('span', { class: 'tb-pill on', title: 'Click to clear the scope', onclick: () => { state.scope.node = null; saveLocal(); render(); } }, 'Scope: ' + (state.scope.label || state.scope.node) + '  \u00d7'));
  }
  top.append(h('span', { class: 'sp' }));
  if (state.project && !isParent()) {
    const company = (state.project.settings?.allowance_view || 'pm') === 'company';
    top.append(select([['pm', 'Current allowance'], ['company', 'Total allowance']], company ? 'company' : 'pm', { class: 'tb-select quiet', title: 'Which allowance the pages show. Current allowance: the budget the project can spend, including risk the company has released to it. Total allowance: plus the risk the company still holds.',
      onchange: async (e) => { await api.put(`/api/projects/${state.pid}`, { settings: { allowance_view: e.target.value } }); await render(); } }));
  }
  if (state.project && !isParent()) { top.append(...undoRedoBtns()); refreshRevert(); }
  top.append(h('button', { class: 'tb-search', title: 'Search pages, projects, CBS lines, documents, clients and people (Ctrl+K, or / outside a text box)', onclick: searchOpen }, icon('search'), h('span', {}, 'Search'), h('kbd', {}, 'Ctrl K')));
  if (!document.body.classList.contains('popout')) top.append(tbBtn(null, 'window', 'Open this page in a window of its own (for example to move Cost control to another screen). It stays live.', () => {
    const w = window.open(location.pathname + '?popout=1' + location.hash, '_blank', 'popup=yes,width=1500,height=950');
    if (!w) toast('The browser blocked the new window. Allow pop-ups for PMT and try again.', 'bad');
  }));
  top.append(tbBtn(null, 'plus', 'New project', newProjectDialog));
  top.append(meChip());
  top.append(h('img', { src: '/static/img/epec-logo.png', alt: 'EPEC', class: 'toplogo' }));
}

// line icons for the top bar
const ICONS = {
  chevL: '<path d="M14.5 5.5 8 12l6.5 6.5"/>', chevR: '<path d="M9.5 5.5 16 12l-6.5 6.5"/>', search: '<circle cx="11" cy="11" r="6.2"/><path d="m16 16 4 4"/>',
  window: '<rect x="4" y="8" width="12" height="12" rx="2"/><path d="M8 8V6a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2"/>', plus: '<path d="M12 5v14M5 12h14"/>',
  undo: '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>', redo: '<path d="M15 14l5-5-5-5"/><path d="M20 9H9.5a5.5 5.5 0 0 0 0 11H13"/>',
};
function icon(name) {
  const e = document.createElement('span'); e.className = 'ico';
  e.innerHTML = `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${ICONS[name]}</svg>`;
  return e;
}
// ---- Undo and Redo: step back through the user's own changes on this project, and forward again (the change log, server side: revert.py) ----
let revertTimer = null;
function undoRedoBtns() {
  const mk = (id, name, title, fn) => { const b = tbBtn(id, name, title, fn, true); b.classList.add('tb-ur'); return b; };
  return [mk('undoBtn', 'undo', 'Undo', () => stepChange('revert', 'Undo')), mk('redoBtn', 'redo', 'Redo', () => stepChange('redo', 'Redo'))];
}
function refreshRevert() {
  clearTimeout(revertTimer);
  revertTimer = setTimeout(async () => {
    const u = document.getElementById('undoBtn'); const r = document.getElementById('redoBtn'); if (!u || !r || !state.pid) return;
    try {
      const x = await api.get(`/api/p/${state.pid}/revert`);
      u.disabled = !x.txn; u.dataset.summary = x.summary || ''; r.disabled = !x.redo; r.dataset.summary = x.redo?.summary || '';
    } catch (e) { u.disabled = true; r.disabled = true; }
  }, 250);
}
api.afterWrite = (method, url) => { if (url.startsWith('/api/p/') && !url.includes('/revert') && !url.includes('/redo')) refreshRevert(); };
async function stepChange(kind, label) {
  const b = document.getElementById(kind === 'redo' ? 'redoBtn' : 'undoBtn'); if (!b || b.disabled) return;
  try { const r = await api.post(`/api/p/${state.pid}/${kind}`, {}); toast(`${label}: ${r.summary}`); await loadProjects(); await render(); refreshRevert(); }
  catch (e) { toast(e.message, 'bad'); }
}
function tbBtn(id, name, title, onclick, disabled = false) {
  return h('button', { class: 'tb-btn', id: id || null, title, 'aria-label': title, onclick, disabled }, icon(name));
}

// ---- who am I, and is my copy in step with the others ------------------------------------------
const ROLES = ['Project Manager', 'Project Coordinator', 'Project Engineer', 'Cost Controller', 'Commercial Manager', 'Contract Administrator', 'Construction Manager', 'Site Supervisor', 'Project Director', 'Head of Project Management', 'Head of Project Engineering', 'Head of Delivery', 'General Manager Projects', 'Chief Operating Officer', 'Executive Director', 'Other'];
const initials = (n) => (n || '?').split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join('');
function meChip() {
  const me = state.me || {}; const s = me.sync || {};
  const dotCls = s.mode !== 'shared' ? '' : s.error ? 'err' : 'ok';
  const tip = s.mode === 'shared' ? (s.error ? 'Sharing problem: ' + s.error : `Sharing through ${s.folder}. Last sync ${s.last_import ? new Date(s.last_import).toLocaleTimeString() : 'not yet'}.`) : 'This copy is not shared with anyone.';
  const who = [me.name, me.role].filter(Boolean).join(', ');
  return h('span', { class: 'me', title: `${who ? who + '. ' : ''}${tip} Click to change your name, role or entity.`, onclick: profileDialog }, h('span', { class: 'av' }, initials(me.name)), h('span', { class: 'dot ' + dotCls }));
}
async function profileDialog() {
  const me = await api.get('/api/me'); state.me = me; const s = me.sync || {};
  const nameIn = h('input', { type: 'text', value: me.name || '' });
  const entity = select([['', '(choose)'], ...(me.entities || []).map((x) => [x, x])], me.org || '');
  const role = select([['', '(choose your role)'], ...ROLES.map((r) => [r, r])], ROLES.includes(me.role) ? me.role : (me.role ? 'Other' : ''));
  const other = h('input', { type: 'text', value: ROLES.includes(me.role) ? '' : (me.role || ''), placeholder: 'Your role' });
  const ago = (iso) => { if (!iso) return ''; const m = Math.round((Date.now() - new Date(iso)) / 60000); return m < 2 ? 'now' : m < 120 ? `${m} min ago` : `${Math.round(m / 60)} h ago`; };
  const shared = s.mode === 'shared'
    ? h('div', {}, h('div', { class: 'small' }, 'Sharing through ', h('span', { class: 'mono' }, s.folder)),
      h('div', { class: 'small muted', style: { margin: '4px 0 8px' } }, `Published ${fmt.n(s.exported)} changes, received ${fmt.n(s.imported)}. Last sync ${ago(s.last_import) || 'not yet'}.`),
      s.error ? h('div', { class: 'note bad' }, s.error) : null,
      h('h3', { style: { margin: '10px 0 6px' } }, 'People using this project'),
      ...(s.writers || []).map((w) => h('div', { class: 'row small', style: { gap: '8px' } }, h('span', { class: 'me', style: { cursor: 'default' } }, h('span', { class: 'av' }, initials(w.name)), h('b', {}, w.name), w.role ? h('span', { class: 'muted' }, w.role) : null), h('span', { class: 'muted' }, `${w.device} · seen ${ago(w.last_seen)}`))))
    : h('div', { class: 'note' }, 'This copy is not shared. To share a project, put the program folder in a SharePoint library that everyone syncs with OneDrive and create a folder called ', h('b', {}, 'shared'), ' next to PMT.exe. See the README.');
  modal({ title: 'You and sharing', body: h('div', { class: 'grid' },
    h('div', {}, h('div', { style: { fontSize: '16px', fontWeight: 700 } }, me.name), h('div', { class: 'mono' }, me.upn), me.org ? h('div', { class: 'small' }, me.org) : null, h('div', { class: 'small muted' }, 'Identified from ' + me.source + '. Every change you make is recorded under this name.')),
    h('div', { class: 'grid g2' }, field('Your name', nameIn, 'As colleagues see it in the history'), field('Entity', entity)),
    h('div', { class: 'grid g2' }, field('Your role on this project', role), field('If other', other)), shared),
  actions: [...(s.mode === 'shared' ? [{ label: 'Sync now', kind: 'ghost', close: false, onClick: async () => { await api.post('/api/sync/now'); toast('In step with the shared folder'); } }] : []),
    { label: 'Close', kind: 'ghost', onClick: () => {} }, { label: 'Save', onClick: async () => { state.me = { ...state.me, ...(await api.put('/api/me', { role: role.value === 'Other' || !role.value ? other.value : role.value, name: nameIn.value, entity: entity.value || null })) }; await render(); } }] });
}
let seenSeq = null;
async function pollSync() {
  try {
    const s = await api.get('/api/sync');
    if (state.me) state.me.sync = s;
    if (s.mode === 'shared' && seenSeq !== null && s.remote_seq !== seenSeq) {
      const r = (s.recent || [])[0];
      toast(r ? `Updated with ${r.changes} change${r.changes === 1 ? '' : 's'} from ${r.user}` : 'Updated with changes from a colleague');
      if (!document.querySelector('.ov, .drawer, input:focus, select:focus, textarea:focus')) await render();
    }
    seenSeq = s.remote_seq;
  } catch (e) { /* server restarting */ }
}
setInterval(pollSync, 20000);

let lastRender = '';
let renderSeq = 0;
const enhancers = [];   // the table, tile and tile-layout watchers: run on a page the moment it is swapped in, so nothing shifts afterwards
// where the keyboard focus is inside a page, as a path of child positions, so it can be put back after the page is redrawn
const focusPath = (root, el) => { const path = []; for (let n = el; n && n !== root; n = n.parentElement) path.unshift([...n.parentElement.children].indexOf(n)); return path; };
const atPath = (root, path) => path.reduce((n, i) => (n ? n.children[i] : null), root);
// Redraw the page you are on. The new page is built beside the old one, which stays on screen (no blank flash), and is swapped in
// in one step, with your scroll position and the field you were in put back, so you can update cell by cell.
export async function render() {
  const mine = ++renderSeq;
  document.body.classList.add('busy');
  const stale = [...document.querySelectorAll('.ov, .drawer')];   // dialogs never outlive the page they were opened on: these go when the new page is in
  document.body.classList.remove('ws-solo');   // set again by the Allowances page when it is opened alone in a window
  const { name, params } = route();
  try {
    if (draft.rid && (name !== 'setup' || (params.step || 'project') !== draft.step || state.pid !== draft.pid)) {
      if ((await askDraft()) === 'stay') {
        if (state.pid !== draft.pid) { state.pid = draft.pid; saveLocal(); await boot(); } else location.hash = draft.hash;
        return;
      }
      if (typeof loadProjects === 'function') await loadProjects();
    }
    const old = document.getElementById('view');
    const valid = [...NAV.flatMap((g) => g[1]).map((x) => x[0].split('?')[0]), 'gates', 'phases', 'cbs', 'resources'];   // gates and phases open from Project lifecycle; the CBS editor from Setup > CBS and allowances; rates from the forecast pages
    let key = valid.includes(name) ? name : 'dashboard';
    let health = null;
    if (state.pid) {
      try { await loadProject(); const d = await api.get(p('/health')); health = { error: d.filter((x) => x.level === 'error').length, warn: d.filter((x) => x.level === 'warn').length }; } catch (e) { /* project may have been deleted */ }
    }
    if (isParent() && !PARENT_PAGES.includes(key)) key = 'dashboard';
    // the page is built in a box beside the old one (same width, out of sight)
    const stage = h('main', { class: 'viewbox staging' });
    stage.style.width = old.getBoundingClientRect().width + 'px';
    old.after(stage);
    const here = location.hash; const same = here === lastRender;
    try {
      if (!state.pid && !NO_PROJECT.includes(key)) welcome(stage);
      else {
        if (isParent() && PARENT_READ_ONLY.includes(key)) stage.append(parentBanner(key));
        const mod = await import(`./views/${key}.js`);
        current = key;
        await mod.default(stage, params);
      }
    } catch (e) {
      console.error(e);
      stage.append(h('div', { class: 'note bad' }, 'Something went wrong loading this page: ' + e.message,
        e.message === 'Not Found' ? h('div', { style: { marginTop: '6px' } }, 'This usually means PMT was updated while it was running: the pages are new but the running program is old. Close PMT (its window, or end Python in Task Manager) and open PMT.exe again.') : null));
    }
    // a newer redraw has started, or the user is typing in a field that has not saved yet: leave the old page as it is
    const ae = document.activeElement;
    const typing = ae && old.contains(ae) && /^(INPUT|TEXTAREA)$/.test(ae.tagName) && ae.type !== 'checkbox' && ae.type !== 'radio' && ae.value !== ae.defaultValue;
    if (mine !== renderSeq || typing) { stage.remove(); return; }
    // swap: remember the place, replace the page, put the place back (all in one step, before the screen is painted)
    const keepY = same ? window.scrollY : 0; const keepTw = same ? [...old.querySelectorAll('.tw')].map((e) => [e.scrollTop, e.scrollLeft]) : [];
    const sideY = document.getElementById('side').scrollTop;
    const path = same && ae && old.contains(ae) && ae !== old ? focusPath(old, ae) : null;
    const sel = path && ae.selectionStart != null ? [ae.selectionStart, ae.selectionEnd] : null;
    lastRender = here;
    stage.querySelectorAll('.pagehead .sub').forEach((e) => { if ((e.textContent || '').length > 130) { e.classList.add('clamp'); if (!e.title) e.title = 'Hover to read the whole line'; } });   // one quiet line; the rest on hover
    stage.classList.remove('staging'); stage.style.width = ''; stage.id = 'view';
    old.replaceWith(stage);
    stale.forEach((e) => { if (e.isConnected) e.remove(); });
    renderSide(key, health); document.getElementById('side').scrollTop = sideY;
    await renderTop();
    enhancers.forEach((fn) => fn());
    if (same) {
      const back = () => { window.scrollTo(0, keepY); [...stage.querySelectorAll('.tw')].forEach((e, i) => { if (keepTw[i]) { e.scrollTop = keepTw[i][0]; e.scrollLeft = keepTw[i][1]; } }); };
      back();
      const target = path ? atPath(stage, path) : null;
      if (target && target.focus) { target.focus({ preventScroll: true }); if (sel && target.setSelectionRange) { try { target.setSelectionRange(sel[0], sel[1]); } catch (e) { /* not a text field */ } } else if (target.select && /^(text|number|search)$/.test(target.type || '')) target.select(); }
      setTimeout(back, 150);
      // big tables settle their column widths a moment later; keep putting you back until you scroll or click yourself
      let live = true; const stop = () => { live = false; ['wheel', 'touchstart', 'keydown', 'pointerdown'].forEach((ev) => window.removeEventListener(ev, stop, true)); };
      ['wheel', 'touchstart', 'keydown', 'pointerdown'].forEach((ev) => window.addEventListener(ev, stop, true));
      [450, 1000].forEach((ms) => setTimeout(() => { if (live) back(); if (ms === 1000) stop(); }, ms));
    }
  } finally {
    if (mine === renderSeq) document.body.classList.remove('busy');
  }
}

// shown on pages that read a parent project: the figures are its children's, so they are changed in the child project
function parentBanner(page) {
  const kids = state.projects.filter((x) => x.parent_project_id === state.pid && !x.archived_at);
  return h('div', { class: 'note', style: { marginBottom: '12px' } }, h('b', {}, 'This is a parent project. '),
    'These figures are the sum of its child projects and cannot be changed here. Open the child project to change the numbers: ',
    ...kids.flatMap((k, i) => [i ? ', ' : '', h('a', { onclick: () => openIn(k.id, page) }, k.name)]), kids.length ? '.' : 'it has no child projects yet (Linked projects).');
}

function welcome(view) {
  view.append(h('div', { class: 'card', style: { maxWidth: '760px', margin: '40px auto' } },
    h('h1', {}, 'Welcome'),
    h('p', {}, 'Create a contract to set up its CBS, load the proposal allowances and initialise cost control. Pronto exports then feed actuals, commitments and claims.'),
    h('div', { class: 'row' },
      h('button', { class: 'btn', onclick: newProjectDialog }, 'Create a project'),
      h('button', { class: 'btn ghost', onclick: loadDemo }, 'Load the demonstration project'),
      h('button', { class: 'btn ghost', onclick: async () => { toast('Building the demo team (about half a minute)...'); try { const r = await api.post('/api/demo/team'); state.pid = r.parent; saveLocal(); await boot(); go('portfolio'); } catch (e) { toast(e.message, 'bad'); } } }, 'Load the demo team (8 projects)')),
    h('p', { class: 'muted small' }, 'The demonstration project is entirely fictional. It exists so every screen can be explored before real data is loaded.'),
    state.me?.sync?.mode === 'shared' ? h('div', { class: 'note', style: { marginTop: '14px' } }, h('b', {}, 'Shared folder. '),
      'If your team already used PMT on one PC, publish that database once so everyone starts from it (usually data\\pmt.db in the old PMT folder). Only do this in an empty shared folder.',
      h('div', { style: { marginTop: '8px' } }, h('input', { type: 'file', accept: '.db', onchange: async (e) => { const f = e.target.files[0]; if (!f) return; toast('Publishing...'); try { const r = await api.upload('/api/sync/publish', f); toast(`Published ${r.rows} records`); await boot(); } catch (err) { toast(err.message, 'bad'); } } }))) : null));
}

async function loadDemo() {
  toast('Building the demonstration project...');
  try {
    const r = await api.post('/api/demo');
    state.pid = r.id; saveLocal(); await boot(); toast('Demonstration project loaded');
  } catch (e) { toast(e.message, 'bad'); }
}

// Archive / restore. Archiving only takes a finished project off the list: nothing is deleted, colleagues see the same.
export async function setArchived(pid, value) {
  await api.post(`/api/projects/${pid}/archive`, { value });
  const p = state.projects.find((x) => x.id === pid);
  toast(value ? `${p?.name || 'Project'} archived: it has moved to the Archive (PMO > Archive).` : `${p?.name || 'Project'} is back with the running projects`);
  if (value && pid === state.pid) state.pid = (state.projects.find((x) => !x.archived_at && x.id !== pid) || {}).id || pid;
  saveLocal(); await boot();
}
export async function newProjectDialog() {
  const projects = state.projects;
  const name = h('input', { type: 'text', placeholder: 'e.g. Wandoan South BESS' });
  const code = h('input', { type: 'text' }); const number = h('input', { type: 'text' });
  // names from the company database (or typed new and added): see ui.lookup
  const client = lookup('client', '', { placeholder: 'Pick a client or type a new one' }); const pm = lookup('pm', '', { placeholder: 'Pick or type a name' });
  const director = lookup('director', '', { placeholder: 'Pick or type a name' });
  const from = select([['', 'Blank project (standard CBS only)'], ...projects.map((x) => [x.id, (x.archived_at ? '[Archived] ' : '') + x.name])], '');
  const inc = {};
  const incBox = h('div', { class: 'row', style: { gap: '14px', marginTop: '6px' } });
  [['lines', 'CBS lines and groups'], ['allowances', 'Original allowances'], ['resources', 'Resources'], ['rate_card', 'Rate card'], ['milestones', 'Project schedule (names only)'], ['contract_items', 'Payment Milestones']]
    .forEach(([k, l]) => { const c = h('input', { type: 'checkbox', checked: k === 'rate_card' }); inc[k] = c; incBox.append(h('label', { class: 'row small', style: { gap: '4px' } }, c, l)); });
  const incWrap = h('div', { class: 'hide' }, h('div', { class: 'small muted' }, 'Copy from the source project. Pronto data, claims, accruals and history are never copied.'), incBox);
  from.onchange = () => incWrap.classList.toggle('hide', !from.value);
  // optional: start from a CRM opportunity (read-only copy of its client, place, dates and asset data; see app/crm_link.py)
  let crm = null; let crmDup = null;
  const crmBox = h('div', { class: 'small' });
  const showCrm = () => {
    crmBox.replaceChildren();
    if (!crm) return;
    const rows = Object.entries(crm.fields).map(([k, v]) => h('div', {}, h('span', { class: 'muted' }, (crm.labels[k] || k) + ': '), String(v), crm.inferred.includes(k) ? h('span', { class: 'muted' }, ' (suggested: check)') : null));
    crmDup = crm.existing ? h('input', { type: 'checkbox' }) : null;
    crmBox.append(h('div', {}, h('b', {}, `CRM opportunity ${crm.crm.opportunity_id}`), ' ', h('a', { href: '#', onclick: (e) => { e.preventDefault(); crm = null; showCrm(); } }, 'remove')),
      ...rows, ...(crm.existing ? [h('label', { class: 'row small', style: { gap: '4px', color: '#b00020' } }, crmDup, `Already used by "${crm.existing}": tick to start another project from it`)] : []));
  };
  const crmBtn = h('button', { class: 'btn ghost', onclick: () => pickOpportunity((d) => {
    crm = d; name.value = d.fields.name || name.value; client.value = d.fields.client_name || client.value; showCrm();
  }) }, 'Start from a CRM opportunity...');
  crmStatus().then((s) => { if (!s.ok) { crmBtn.disabled = true; crmBtn.title = s.message || 'The CRM link is not set up'; } });
  modal({
    title: 'New project',
    body: h('div', { class: 'grid' }, h('div', {}, crmBtn), crmBox, field('Project name', name), h('div', { class: 'grid g2' }, field('EPEC project code', code), field('EPEC project number', number)),
      field('Client', client), h('div', { class: 'grid g2' }, field('EPEC project manager', pm), field('EPEC project director', director)), field('Start from', from), incWrap),
    actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} }, {
      label: 'Create project', onClick: async () => {
        if (!name.value.trim()) throw new Error('Enter a project name');
        const r = await api.post('/api/projects', { name: name.value.trim(), code: code.value, number: number.value, client_name: client.value, epec_pm: pm.value, project_director: director.value,
          ...(crm ? { ...crm.fields, notes: crm.notes, crm_opportunity_id: crm.crm.opportunity_id, crm_allow_duplicate: !!(crmDup && crmDup.checked) } : {}),
          name: name.value.trim(), client_name: client.value, from_template_id: from.value ? +from.value : null, include: Object.fromEntries(Object.entries(inc).map(([k, c]) => [k, c.checked])) });
        state.pid = r.id; saveLocal(); await boot(); go('setup');
      } }],
  });
}

export async function boot() {
  await loadProjects();
  if (!state.projects.find((x) => x.id === state.pid)) state.pid = (state.projects.find((x) => !x.archived_at) || state.projects[0] || {}).id ?? null;
  saveLocal();
  await render();
}

window.addEventListener('hashchange', render);
// grey out Back and Forward when there is nowhere to go (browsers with the Navigation API)
if (window.navigation) navigation.addEventListener('currententrychange', () => {
  const b = document.getElementById('navback'); const f = document.getElementById('navfwd');
  if (b) b.disabled = !navigation.canGoBack;
  if (f) f.disabled = !navigation.canGoForward;
});
// how many PMT pages deep this tab is, so Esc never steps back out of PMT
let depth = history.state?.pmt ?? 0;
if (history.state?.pmt == null) history.replaceState({ ...(history.state || {}), pmt: 0 }, '');
window.addEventListener('hashchange', () => {
  if (history.state?.pmt == null) history.replaceState({ ...(history.state || {}), pmt: ++depth }, '');
  else depth = history.state.pmt;
});
// Esc: close the top dialog / drawer / help panel; else leave the field being edited; else go back a page
document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape' || e.defaultPrevented || e.isComposing) return;
  const x = [...document.querySelectorAll('.ov .md .mh button, .drawer .dh .x')].pop();
  if (x) { e.preventDefault(); x.click(); return; }
  const help = document.querySelector('.helppanel:not([hidden])');
  if (help) { e.preventDefault(); help.hidden = true; document.body.classList.remove('help-open'); return; }
  const a = document.activeElement;
  if (a && a !== document.body && a.matches('input,select,textarea,[contenteditable]')) { a.blur(); return; }
  if ((history.state?.pmt || 0) > 0) { e.preventDefault(); history.back(); }
});
(async () => {
  const saved = loadLocal();
  state.pid = saved.pid || null; state.scope = saved.scope || state.scope;
  // a page opened in its own window (to move to another screen): no side menu
  if (new URLSearchParams(location.search).get('popout') === '1') document.body.classList.add('popout');
  enhancers.push(watchTables(document.body));  // sort / filter / open-in-a-window on every table
  enhancers.push(watchTiles(document.body));   // every tile opens the data behind it
  enhancers.push(watchTileLayout(document.body));   // and can be moved around its grid
  mountHelp();                 // the Ask button: PMT guide and Microsoft Copilot
  state.tax = await api.get('/api/taxonomy');
  state.me = await api.get('/api/me').catch(() => null);
  state.menu = await api.get('/api/me/menu').catch(() => null);
  state.shortcuts = (await api.get('/api/me/shortcuts').catch(() => null))?.shortcuts || null;
  state.tiles = (await api.get('/api/me/tiles').catch(() => null))?.tiles || {};
  seenSeq = state.me?.sync?.remote_seq ?? null;
  if (!location.hash && pref('start_page') !== 'dashboard') history.replaceState(null, '', location.pathname + location.search + '#/' + pref('start_page'));  // Settings > Your defaults
  await boot();
  checkBuild(state.me);
  setInterval(async () => checkBuild(await api.get('/api/me').catch(() => null)), 60000);
})();

// The running program and the files on disk must be the same release. A release copied over the folder while PMT runs
// leaves an old server behind new pages (errors such as "Not Found"): say so until PMT is restarted.
function checkBuild(me) {
  if (!me) return;
  const rel = document.getElementById('release');
  if (rel) rel.textContent = me.release ? `Release ${me.release}` : 'Release: an older program is running';
  const stale = !me.build ? 'The running PMT program is older than these pages.' : (me.build_now && me.build_now !== me.build ? 'PMT was updated while it was running.' : '');
  let bar = document.getElementById('build-banner');
  if (!stale) { if (bar) bar.remove(); return; }
  if (!bar) { bar = h('div', { id: 'build-banner', class: 'build-banner' }); document.body.prepend(bar); }
  bar.replaceChildren(h('b', {}, stale), ' Close PMT (the PMT window, or end Python in Task Manager) and open PMT.exe again to use the new version.');
}
