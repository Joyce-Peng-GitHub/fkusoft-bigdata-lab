/** Reproduce binary floating-point tails in real ECharts tooltips. */
const assert = require('node:assert/strict');
const { chromium } = require('playwright-core');
(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/usr/bin/chromium', args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  try {
    const page = await browser.newPage();
    await page.route('**/api/dashboard', async route => {
      const response = await route.fetch();
      const data = await response.json();
      // Deliberately retain raw precision: the display boundary must round it.
      for (const rows of Object.values(data.dimensions)) for (const row of rows) row.energy = 123.99999999999993;
      for (const row of data.battery) row.temperature = 32.99999999999993;
      await route.fulfill({ response, json: data });
    });
    await page.goto(process.env.BASE_URL || 'http://localhost:5173');
    await page.locator('.charts .chart').first().waitFor();
    for (let index = 0; index < 13; index++) {
      const chart = page.locator('.charts .chart').nth(index);
      await chart.scrollIntoViewIfNeeded();
      await chart.evaluate(async element => {
        const url = performance.getEntriesByType('resource').map(entry => entry.name).find(name => /\/echarts\.js\?/.test(name));
        const echarts = await import(url);
        echarts.getInstanceByDom(element).dispatchAction({ type: 'showTip', seriesIndex: 0, dataIndex: 0 });
      });
      await page.waitForTimeout(100);
      const text = await chart.innerText();
      assert.match(text, index === 12 ? /33/ : /124/, `Missing rounded value in chart ${index}: ${text}`);
      assert.doesNotMatch(text, /\.\d{3,}/, `Floating-point tail in chart ${index}: ${text}`);
    }
    console.log('Precision checks passed: all 13 real chart tooltips round floating-point tails');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
