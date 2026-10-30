import { h } from '../ui.js';
import { go } from '../app.js';
import { historyPage } from './_history.js';

// FORECAST > Forecast history: what was forecast, month by month, at every month-end close.
export default async function forecastHistory(root, params) {
  await historyPage(root, params, 'f', {
    title: 'Forecast history',
    sub: 'What you forecast, month by month, at every month-end close: for example what was forecast for Sep-25 back in Jul-25. Pick a close or play them; per line you see the method used and how the value moved.',
    actions: [h('button', { class: 'btn ghost', onclick: () => go('forecast') }, 'Forecast lines')],
  });
}
