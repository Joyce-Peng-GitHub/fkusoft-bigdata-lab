/** Browser contract regression using deterministic API fixtures, without Hive/MySQL.
 * Run against Vite with NODE_PATH pointing to an installed playwright package.
 * BASE_URL and CHROMIUM_PATH may override the local defaults.
 */
const assert = require('node:assert/strict');
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({
    ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}),
    args: ['--no-sandbox'],
  });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    let failed = false;
    const forecast = {
      generated_at: '2026-09-16T00:00:00Z', history_end: '2015-10-31',
      history: [{ date: '2015-10-30', energy: 5, sessions: 1 }, { date: '2015-10-31', energy: 10, sessions: 2 }],
      forecast: [{ date: '2015-11-01', energy: 0, sessions: 1.2 }, { date: '2015-11-02', energy: 12.3, sessions: 2.4 }],
    };
    await page.route('**/api/ml/forecast', route => route.fulfill({
      status: failed ? 503 : 200, contentType: 'application/json', body: JSON.stringify(failed ? {} : forecast),
    }));
    await page.route('**/api/dashboard', route => route.fulfill({
      contentType: 'application/json', body: JSON.stringify({
        generated_at: forecast.generated_at,
        overview: { sessions: 3395, energy: 19723.69, fees: 401.52, stations: 105, avg_duration: 2.84 },
        dimensions: {}, battery: [],
        quality: { accepted_sessions: 3395, source_rows: {}, rejected_sessions: 0, duplicates_removed: 0, battery_accepted: 1594 },
      }),
    }));
    await page.goto(process.env.BASE_URL || 'http://127.0.0.1:5173');
    const panel = page.getByRole('region', { name: '历史与预测', exact: true });
    await panel.locator('canvas').first().waitFor();
    await panel.getByRole('heading', { name: '历史与预测', exact: true }).waitFor();
    assert.equal(await panel.locator('p').count(), 0);
    // Inspect the actual ECharts instance to verify values, units and the dashed bridge.
    async function chartOption() {
      return page.evaluate(async () => {
        const url = performance.getEntriesByType('resource').map(entry => entry.name).find(name => /\/echarts\.js\?/.test(name));
        const echarts = await import(url);
        return echarts.getInstanceByDom(document.querySelector('.forecast-panel .chart')).getOption();
      });
    }
    let option = await chartOption();
    assert.deepEqual(option.series[0].data, [5, 10, null, null]);
    assert.deepEqual(option.series[1].data, [null, 10, 0, 12.3]);
    assert.equal(option.series[1].lineStyle.type, 'dashed');
    await page.getByLabel('分析指标').selectOption('sessions');
    // Wait for the metric to reach the forecast chart itself; DOM text no longer changes.
    await page.waitForFunction(async () => {
      const element = document.querySelector('.forecast-panel .chart');
      const url = performance.getEntriesByType('resource').map(entry => entry.name).find(name => /\/echarts\.js\?/.test(name));
      if (!element || !url) return false;
      const echarts = await import(url);
      return echarts.getInstanceByDom(element)?.getOption()?.yAxis?.[0]?.name === '单';
    });
    option = await chartOption();
    assert.equal(option.yAxis[0].name, '单');
    assert.deepEqual(option.series[1].data, [null, 2, 1.2, 2.4]);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForFunction(() => document.documentElement.scrollWidth <= innerWidth);
    failed = true;
    await page.getByRole('button', { name: '刷新数据' }).click();
    await panel.getByRole('alert').waitFor();
    assert.match(await panel.innerText(), /保留上次/);
    assert.ok(await panel.locator('canvas').count());
    await page.reload();
    await panel.getByRole('alert').waitFor();
    assert.equal(await panel.locator('canvas').count(), 0);
    await page.locator('.kpis').waitFor();
    failed = false;
    await page.getByRole('button', { name: '刷新数据' }).click();
    await panel.locator('canvas').first().waitFor();
    assert.deepEqual(errors, []);
    console.log('Forecast browser checks passed: values, metric switch, mobile, stale, empty and recovery');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
