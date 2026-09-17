/** Browser integration checks against the real Vite→Flask→MySQL service.
 * Install playwright-core and a compatible Chromium in a test environment.
 * Override BASE_URL / CHROMIUM_PATH when running outside the Compose frontend.
 */
const assert = require('node:assert/strict');
const { chromium } = require('playwright-core');

(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || '/usr/bin/chromium',
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  });
  try {
    const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(process.env.BASE_URL || 'http://localhost:5173');
    await page.getByRole('heading', { name: '电动汽车充电站监测' }).waitFor();
    await page.locator('.kpis').waitFor();
    assert.equal(await page.locator('.charts .chart').count(), 13);
    assert.equal(await page.locator('.charts .chart').evaluateAll(charts => charts.filter(chart => chart.querySelector('canvas')).length), 13);
    assert.match(await page.locator('.kpis').innerText(), /3,395/);
    await page.getByLabel('分析指标').selectOption('sessions');
    // The note text was removed with the copy cleanup; verify the switch through
    // the real chart instance instead of DOM text.
    await page.waitForFunction(async () => {
      const element = document.querySelector('.charts .chart');
      const url = performance.getEntriesByType('resource').map(entry => entry.name).find(name => /\/echarts\.js\?/.test(name));
      if (!element || !url) return false;
      const echarts = await import(url);
      return echarts.getInstanceByDom(element)?.getOption()?.yAxis?.[0]?.name === '单';
    });
    await page.screenshot({ path: '/tmp/charging-dashboard-desktop.png', fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    // ResizeObserver updates charts on the next animation frame.
    await page.waitForFunction(() => document.documentElement.scrollWidth <= window.innerWidth);
    await page.screenshot({ path: '/tmp/charging-dashboard-mobile.png', fullPage: true });
    await page.route('**/api/dashboard', route => route.fulfill({ status: 503, body: '{}' }));
    await page.getByRole('button', { name: '刷新数据' }).click();
    await page.locator('main > [role=alert]').waitFor();
    assert.match(await page.locator('main > [role=alert]').innerText(), /保留上次/);
    assert.equal(await page.locator('.charts .chart').count(), 13);
    assert.equal(await page.locator('.charts .chart').evaluateAll(charts => charts.filter(chart => chart.querySelector('canvas')).length), 13);
    await page.reload();
    await page.locator('main > [role=alert]').waitFor();
    assert.equal(await page.locator('.kpis').count(), 0);
    assert.deepEqual(errors, []);
    console.log('Browser checks passed: 13 charts, metric switch, mobile overflow, stale and empty errors');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
