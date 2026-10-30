// The chat button (bottom right): ask how PMT works.
//   PMT guide: answers from PMT's own guide, on this PC, with a button to the page it is about.
//   Copilot:   Microsoft 365 Copilot Chat. With a Copilot Studio agent's web chat address (Settings > Your defaults)
//              it answers inside the panel; without one, "Open Copilot Chat" copies the question with what you are
//              looking at and opens Copilot Chat in the browser, ready to paste.
import { h, clear, toast } from './ui.js';
import { api, state, pref } from './api.js';
import { route } from './app.js';

let panel = null; let log = null; let input = null; let tab = 'guide'; let last = '';
const history = [];   // this session's conversation: [{who, el}]

export function mountHelp() {
  if (document.getElementById('helpbtn')) return;
  const btn = h('button', { id: 'helpbtn', class: 'helpbtn noprint', title: 'Ask how PMT works (guide or Microsoft Copilot)', onclick: () => toggle() }, h('span', { class: 'ic' }, '\u{1F4AC}'), h('span', {}, 'Ask'));
  document.body.append(btn);
  window.addEventListener('hashchange', () => { if (panel && !panel.hidden && tab === 'guide' && !history.length) greet(); });
}

function toggle(open) {
  if (!panel) build();
  panel.hidden = open === undefined ? !panel.hidden : !open;
  document.body.classList.toggle('help-open', !panel.hidden);
  if (!panel.hidden) { if (!history.length) greet(); setTimeout(() => input?.focus(), 50); }
}

function build() {
  log = h('div', { class: 'hp-log' });
  input = h('textarea', { rows: 2, placeholder: 'Ask how something works, e.g. "what does P 11 mean on the calendar?"', onkeydown: (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } } });
  const tabs = h('div', { class: 'hp-tabs' });
  const body = h('div', { class: 'hp-body' });
  const drawTabs = () => {
    clear(tabs).append(...[['guide', 'PMT guide'], ['copilot', 'Microsoft Copilot']].map(([k, l]) => h('button', { class: 'hp-tab' + (tab === k ? ' on' : ''), onclick: () => { tab = k; drawTabs(); drawBody(); } }, l)));
  };
  const drawBody = () => {
    clear(body);
    if (tab === 'guide') body.append(log, h('div', { class: 'hp-in' }, input, h('button', { class: 'btn', onclick: send }, 'Ask')));
    else body.append(copilotPane());
  };
  panel = h('aside', { class: 'helppanel noprint', hidden: true },
    h('div', { class: 'hp-head' }, h('b', {}, 'Help'), h('span', { class: 'sp' }), h('button', { class: 'btn ghost sm', title: 'Download the whole guide (also the knowledge for a Copilot Studio agent)', onclick: () => window.open('/api/help/guide.md') }, 'Guide ↓'), h('button', { class: 'hp-x', title: 'Close', onclick: () => toggle(false) }, '×')),
    tabs, body);
  document.body.append(panel);
  drawTabs(); drawBody();
}

const page = () => route().name || 'dashboard';

async function greet() {
  const r = await api.get(`/api/help/ask?page=${encodeURIComponent(page())}`).catch(() => null);
  if (!r) return;
  clear(log);
  bot(h('div', {}, h('div', {}, `Hi${state.me?.name ? ' ' + state.me.name.split(' ')[0] : ''}. Ask me how anything in PMT works. I answer from PMT's own guide; for anything else, the Microsoft Copilot tab is above.`),
    r.page_topic ? h('div', { class: 'hp-about' }, h('b', {}, `This page: ${r.page_name}`), h('div', {}, short(r.page_topic.text, 360))) : null,
    chips(r.suggestions.map((s) => [s, () => ask(s)]))));
}

function send() {
  const q = input.value.trim();
  if (!q) return;
  input.value = '';
  ask(q);
}

async function ask(q) {
  last = q;
  me(q);
  const r = await api.get(`/api/help/ask?q=${encodeURIComponent(q)}&page=${encodeURIComponent(page())}`).catch((e) => ({ error: e.message }));
  if (r.error) { bot(h('div', { class: 'bad' }, r.error)); return; }
  if (!r.answer) {
    bot(h('div', {}, h('div', {}, 'I could not find that in the PMT guide.'),
      r.related.length ? h('div', { class: 'small muted', style: { marginTop: '6px' } }, 'Closest topics:') : null, chips(r.related.map((t) => [t.title, () => showTopic(t.id)])),
      h('button', { class: 'btn ghost sm', style: { marginTop: '8px' }, onclick: () => toCopilot(q) }, 'Ask Microsoft Copilot instead')));
    return;
  }
  answerEl(r.answer, r.related);
}

async function showTopic(id) {
  const t = await api.get(`/api/help/topic/${encodeURIComponent(id)}`).catch(() => null);
  if (t) { me(t.title); answerEl(t, []); }
}

function answerEl(t, related) {
  bot(h('div', {}, h('b', {}, t.title), h('div', { class: 'hp-text' }, ...paras(t.text)),
    t.page && t.page !== page() ? h('button', { class: 'btn sm', style: { marginTop: '8px' }, onclick: () => { location.hash = '#/' + t.page; } }, 'Open this page →') : null,
    related.length ? h('div', { class: 'small muted', style: { marginTop: '8px' } }, 'Related:') : null,
    chips(related.map((x) => [x.title, () => showTopic(x.id)]))));
}

function me(text) { const el = h('div', { class: 'hp-msg me' }, text); history.push({ who: 'me', el }); log.append(el); log.scrollTop = log.scrollHeight; }
function bot(content) { const el = h('div', { class: 'hp-msg bot' }, content); history.push({ who: 'bot', el }); log.append(el); log.scrollTop = log.scrollHeight; }
const chips = (list) => (list.length ? h('div', { class: 'hp-chips' }, list.map(([l, fn]) => h('button', { class: 'chip', onclick: fn }, l))) : null);
const short = (s, n) => (s.length > n ? s.slice(0, n).replace(/\s+\S*$/, '') + '...' : s);
const paras = (s) => s.split(/\n\n+/).map((p) => h('p', {}, p.replace(/\n/g, ' ')));

// ---- Microsoft Copilot -------------------------------------------------------------------------------------------
function copilotPane() {
  const embed = (pref('copilot_embed') || '').trim();
  if (/^https:\/\//i.test(embed)) {
    return h('div', { class: 'hp-cop' }, h('iframe', { src: embed, title: 'Copilot', class: 'hp-frame', allow: 'clipboard-write' }),
      h('div', { class: 'small muted' }, 'Your organisation\'s Copilot Studio agent. Change it in Settings > Your defaults.'));
  }
  const q = h('textarea', { rows: 3, placeholder: 'Your question for Copilot', value: last || '' });
  return h('div', { class: 'hp-cop' },
    h('p', {}, 'Microsoft 365 Copilot Chat opens in your browser, signed in with your EPEC account. Your question is copied with what you are looking at in PMT: paste it there (Ctrl+V).'),
    q, h('button', { class: 'btn', style: { marginTop: '8px' }, onclick: () => toCopilot(q.value) }, 'Open Copilot Chat ↗'),
    h('div', { class: 'note', style: { marginTop: '14px' } }, h('b', {}, 'A Copilot that knows PMT, inside this panel'),
      h('p', { class: 'small' }, 'IT (or anyone with Copilot Studio) can make an agent with the PMT guide as its knowledge: download the guide (button above), add it as the agent\'s knowledge, publish the agent to a website and put its web chat address in Settings > Your defaults. It then answers here.')),
    h('div', { class: 'small muted', style: { marginTop: '8px' } }, 'Copilot does not see your PMT data unless you paste it. Mind what you share: Commercial in Confidence.'));
}

async function toCopilot(question) {
  const { name } = route();
  const ctx = `I am using PMT (EPEC's Project Management Tool for project cost control: CBS, Pronto data, accruals, forecasts, `
    + `subcontracts, claims, variations, risk). I am on the "${document.querySelector('.pagehead h1')?.textContent || name}" page`
    + `${state.project?.name ? ` of project ${state.project.name}` : ''}. ${question ? 'My question: ' + question : ''}`;
  try { await navigator.clipboard.writeText(ctx); toast('Question copied: paste it in Copilot Chat (Ctrl+V)'); } catch (e) { toast('Copy the question from the box, then paste it in Copilot Chat'); }
  const url = (pref('copilot_url') || 'https://m365.cloud.microsoft/chat').trim();
  window.open(/^https:\/\//i.test(url) ? url : 'https://m365.cloud.microsoft/chat', '_blank', 'noopener');
}
