// Revenue against cost, three ways: value of work, invoices and bills, cash. Used on the dashboard.
import { h, clear, fmt, chart, PALETTE, tabs, badge, table, jumpTo, chartJump } from './ui.js';
import { api, p, pref } from './api.js';
import { monthForecastDialog } from './monthforecast.js';

const rgba = (hex, a) => { const n = parseInt(hex.slice(1), 16); return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a})`; };

export async function flowsCard(node) {
  const q = node ? `?node=${encodeURIComponent(node)}` : '';
  const d = await api.get(p('/flows' + q));
  const whole = d.scope === 'project';
  let tab = sessionStorage.getItem('flowTab') || pref('flow_tab');
  if (!whole && tab !== 'work') tab = 'work';
  const card = h('div', { class: 'card', style: { marginTop: '14px' } });
  const tb = h('div'); const body = h('div');
  const si = d.months.findIndex((m) => m >= d.status_month);
  const first = Math.max(0, d.months.findIndex((_, i) => (d.work.cost[i] || (d.work.revenue && d.work.revenue[i]) || (d.invoices.invoiced && d.invoices.invoiced[i]) || d.invoices.bills[i])));
  const sl = (x) => x.slice(first);
  const labels = sl(d.months).map(fmt.month);
  const shade = (hex) => (c) => (si >= 0 && c.dataIndex + first > si ? rgba(hex, .42) : (si >= 0 && c.dataIndex + first === si ? rgba(hex, .75) : hex));
  const tabItems = whole ? [['work', 'Value of work: claimed vs cost incurred'], ['invoices', 'Invoiced vs bills received'], ['cash', 'Cash: received vs paid']] : [['work', 'Cost incurred']];

  function draw() {
    clear(tb).append(tabs(tabItems, tab, (k) => { tab = k; sessionStorage.setItem('flowTab', k); draw(); }));
    clear(body);
    const box = h('div', { class: 'chartbox tall' });
    const kp = (l, v, s, cls = '', to = null) => jumpTo(h('div', { class: 'kpi ' + cls }, h('div', { class: 'l' }, l), h('div', { class: 'v', style: { fontSize: '18px' } }, v), s ? h('div', { class: 's' }, s) : null), to?.[0], to?.[1]);
    // where a tile or a bar leads: revenue to the claims, cost to the actuals (past) or the forecast (future), bills and payments to the Pronto data
    const nq = node ? `?node=${encodeURIComponent(node)}` : '';
    const TO = { claims: ['#/revenue?tab=claims', 'Open the progress claims'], ctd: ['#/actuals', 'Open the actuals (invoices by supplier)'], fc: ['#/forecast' + nq, 'Open the forecast lines'],
      margin: ['#/pmr', 'Open the PMR (board report)'], pronto: ['#/pronto', 'Open the Pronto data'], cash: ['#/eom', 'Open the EOM report (cashflow)'], terms: ['#/settings', 'Open the settings (payment terms)'] };
    let strip, note, rows;
    const lines = (cum1, cum2, l1, l2, extra = []) => [
      { type: 'line', label: l1, data: sl(cum1), borderColor: PALETTE[0], backgroundColor: PALETTE[0], borderDash: [5, 4], borderWidth: 2, pointRadius: 0, yAxisID: 'y1', tension: .2 },
      { type: 'line', label: l2, data: sl(cum2), borderColor: PALETTE[1], backgroundColor: PALETTE[1], borderDash: [5, 4], borderWidth: 2, pointRadius: 0, yAxisID: 'y1', tension: .2 }, ...extra];
    const opts = { interaction: { mode: 'index', intersect: false }, scales: { y1: { position: 'right', grid: { drawOnChartArea: false }, ticks: { callback: (v) => fmt.m(v) }, title: { display: true, text: 'Cumulative' } }, y: { title: { display: true, text: 'Per month' } } },
      plugins: { tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${fmt.money(c.parsed.y)}` } } } };

    if (tab === 'work') {
      const w = d.work;
      const sets = [];
      // incurred (Pronto actual + accrued) and forecast are separate bars stacked per month: forecast never reads as incurred
      if (w.revenue) sets.push({ type: 'bar', label: 'Revenue claimed', data: sl(w.revenue_actual), backgroundColor: PALETTE[0], stack: 'rev' },
        { type: 'bar', label: 'Revenue forecast', data: sl(w.revenue_planned), backgroundColor: rgba(PALETTE[0], .35), stack: 'rev' });
      sets.push({ type: 'bar', label: 'Cost incurred', data: sl(w.cost_incurred), backgroundColor: PALETTE[1], stack: 'cost' },
        { type: 'bar', label: 'Cost forecast', data: sl(w.cost_forecast), backgroundColor: rgba(PALETTE[1], .35), stack: 'cost' });
      const cum = w.revenue ? lines(w.cum_revenue, w.cum_cost, 'Revenue (cumulative)', 'Cost (cumulative)') : [{ type: 'line', label: 'Cost (cumulative)', data: sl(w.cum_cost), borderColor: PALETTE[1], borderDash: [5, 4], borderWidth: 2, pointRadius: 0, yAxisID: 'y1' }];
      strip = h('div', { class: 'grid g4' }, w.revenue ? kp('Claimed to date', fmt.m(w.revenue_to_date), `Source: ${w.source}`, '', TO.claims) : null, kp('Cost incurred to date', fmt.m(w.cost_to_date), 'Pronto actual plus accrued, no forecast', 't2', TO.ctd),
        w.revenue ? kp('Earned margin to date', fmt.pct(w.revenue_to_date ? (w.revenue_to_date - w.cost_to_date) / w.revenue_to_date : 0), fmt.m(w.revenue_to_date - w.cost_to_date), 't3', TO.margin) : null, w.revenue ? kp('At completion', fmt.m(w.cum_revenue[w.cum_revenue.length - 1] - w.cum_cost[w.cum_cost.length - 1]), 'Revenue less cost, whole job', 't4', TO.margin) : null);
      note = 'The view the PMR reports on: revenue counts in the month the work was claimed (certified where available), cost in the month the work was done (GL plus accruals). Lighter bars are forecast; the "to date" tiles leave forecast out.';
      rows = [['Month', ...(w.revenue ? ['Revenue claimed', 'Revenue forecast'] : []), 'Cost incurred', 'Cost forecast', ...(w.revenue ? ['Margin'] : [])], ...sl(d.months).map((m, i) => [fmt.month(m), ...(w.revenue ? [fmt.money(sl(w.revenue_actual)[i]), fmt.money(sl(w.revenue_planned)[i])] : []), fmt.money(sl(w.cost_incurred)[i]), fmt.money(sl(w.cost_forecast)[i]), ...(w.revenue ? [fmt.money(sl(w.revenue)[i] - sl(w.cost)[i])] : [])])];
      body.append(strip, h('div', { style: { height: '10px' } }), box, h('div', { class: 'small muted', style: { margin: '8px 0' } }, note));
      chart(box, { type: 'bar', data: { labels, datasets: [...sets, ...cum] }, options: { ...opts, scales: { ...opts.scales, x: { stacked: true }, y: { ...opts.scales.y, stacked: true } },
        // a cost bar from the status month on opens that month's forecast in a window, where it can also be adjusted
        ...chartJump(({ index, label }) => { const mo = d.months[index + first]; if (!label.startsWith('Revenue') && mo >= d.status_month && (mo > d.status_month || label.includes('forecast'))) return monthForecastDialog(mo, node); location.hash = (label.startsWith('Revenue') ? TO.claims : label.includes('forecast') || (label.includes('cumulative') && mo > d.status_month) ? TO.fc : TO.ctd)[0]; }) } });
    } else if (tab === 'invoices') {
      const v = d.invoices;
      strip = h('div', { class: 'grid g4' }, kp('Invoiced to date', fmt.m(v.invoiced_to_date), `Source: ${v.invoiced_source}`, '', TO.claims), kp('Bills received to date', fmt.m(v.bills_to_date), v.bills_include_labour ? 'Including labour' : 'Supplier and subcontractor bills, excluding labour', 't2', TO.pronto),
        kp('Invoiced less billed', fmt.m(v.invoiced_to_date - v.bills_to_date), 'Before labour', 't3', TO.cash), kp('Receivable from client', fmt.m(d.cash.receivable), 'Invoiced, not yet paid', 't4', TO.claims));
      body.append(strip, h('div', { style: { height: '10px' } }), box, h('div', { class: 'small muted', style: { margin: '8px 0' } }, 'By invoice date: client invoices sent against supplier bills received. Work done but not yet billed is expected as a bill the following month. Lighter bars are forecast; invoices still to raise follow the claim schedule.'));
      chart(box, { type: 'bar', data: { labels, datasets: [{ type: 'bar', label: 'Invoices sent', data: sl(v.invoiced), backgroundColor: shade(PALETTE[0]) }, { type: 'bar', label: 'Bills received', data: sl(v.bills), backgroundColor: shade(PALETTE[1]) }, ...lines(v.cum_invoiced, v.cum_bills, 'Invoiced (cumulative)', 'Billed (cumulative)')] }, options: { ...opts, ...chartJump(({ index, label }) => { location.hash = (label.startsWith('Invoice') ? TO.claims : d.months[index + first] > d.status_month ? TO.fc : TO.pronto)[0]; }) } });
    } else {
      const c = d.cash;
      strip = h('div', { class: 'grid g4' }, kp('Cash position now', fmt.m(c.position_now), 'Received less paid to date', c.position_now < 0 ? 't2' : 't3', TO.cash), kp('Lowest point', fmt.m(c.lowest.value), fmt.month(c.lowest.month), 't2', TO.cash), kp('Receivable', fmt.m(c.receivable), `Client terms ${c.client_terms_days} days`, 't4', TO.claims), kp('Payable after status month', fmt.m(c.payable_after_status), `Supplier terms ${c.supplier_terms_days} days`, 't5', TO.terms));
      body.append(strip, h('div', { style: { height: '10px' } }), box, h('div', { class: 'note', style: { margin: '8px 0' } }, c.note, ' Set the terms in Settings.'));
      chart(box, { type: 'bar', data: { labels, datasets: [{ type: 'bar', label: 'Money received', data: sl(c.received), backgroundColor: shade(PALETTE[0]) }, { type: 'bar', label: 'Money paid', data: sl(c.paid), backgroundColor: shade(PALETTE[1]) }, { type: 'line', label: 'Net cash position (cumulative)', data: sl(c.cum_net), borderColor: PALETTE[2], backgroundColor: PALETTE[2], borderWidth: 3, pointRadius: 0, yAxisID: 'y1', tension: .2 }] }, options: { ...opts, ...chartJump(({ index, label }) => { location.hash = (label.startsWith('Money received') ? TO.claims : label.startsWith('Money paid') ? (d.months[index + first] > d.status_month ? TO.fc : TO.pronto) : TO.cash)[0]; }) } });
    }
  }
  card.append(h('div', { class: 'ch' }, h('h2', {}, 'Revenue against cost'), h('span', { class: 'sp' }), h('span', { class: 'small muted' }, `Status month ${fmt.month(d.status_month)} \u00B7 click a tile or a bar to open its data`)), tb, body);
  draw();
  return card;
}
