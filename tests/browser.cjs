// Optional real-browser regression: NODE_PATH=<playwright install>/node_modules
// node tests/browser.cjs dashboard.html .scratch/browser
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

(async () => {
  const source = path.resolve(process.argv[2] || 'dashboard.html');
  const output = path.resolve(process.argv[3] || '.scratch/browser');
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const cache = new Map();
  const results = [];
  async function imageResponse(route) {
    const url = route.request().url();
    if (!cache.has(url)) cache.set(url, (async () => {
      const response = await route.fetch();
      assert.equal(response.status(), 200, url);
      return await response.body();
    })());
    await route.fulfill({ status: 200, contentType: 'image/png', body: await cache.get(url) });
  }
  try {
    for (const colorScheme of ['light', 'dark']) {
      for (const width of [390, 768, 820, 1024, 1440]) {
        const page = await browser.newPage({ viewport: { width, height: 1000 }, colorScheme });
        const errors = [];
        const imageRequests = [];
        page.on('pageerror', e => errors.push(String(e)));
        page.on('request', r => { if (r.url().endsWith('.png')) imageRequests.push(r.url()); });
        await page.route('https://raw.githubusercontent.com/**/*.png', imageResponse);
        await page.addInitScript(() => {
          window.copied = [];
          Object.defineProperty(navigator, 'clipboard', { value: {
            writeText: async value => { window.copied.push(value); }
          }});
        });
        await page.goto(pathToFileURL(source).href);
        assert.equal(await page.locator('.dataset[open]').count(), 0);
        assert.equal(imageRequests.length, 0, 'no figure fetch before a selection');
        const libraryLink = page.locator('nav a[href="#lens"]').first();
        await libraryLink.focus();
        await page.keyboard.press('Enter');
        const library = page.locator('#lens').locator('xpath=ancestor::details[1]');
        const dataset = library.locator('.dataset').first();
        await dataset.locator('summary').waitFor({ state: 'visible' });
        await dataset.locator('summary').focus();
        await page.keyboard.press('Enter');
        const select = dataset.locator('select');
        const choices = await select.locator('option').evaluateAll(nodes => nodes.slice(1).map(n => ({
          value: n.value, review: n.dataset.review, suggest: n.dataset.suggest, label: n.textContent
        })));
        assert(choices.length > 1);
        await select.selectOption(choices[0].value);
        const image = dataset.locator('.figure-image img');
        await image.waitFor({ state: 'visible' });
        await page.waitForFunction(() => document.querySelector('.figure-image:not([hidden]) img')?.naturalWidth > 0);
        assert.equal(await image.getAttribute('src'), choices[0].value);
        assert.equal(await dataset.locator('.suggest').getAttribute('href'), choices[0].suggest);
        await dataset.locator('[data-copy]').click();
        assert.equal(await page.evaluate(() => window.copied.at(-1)), choices[0].review);
        const initialURL = page.url();
        await dataset.locator('.figure-image').click();
        assert(await page.locator('dialog').evaluate(d => d.open));
        assert.equal(page.url(), initialURL);
        await page.keyboard.press('Escape');
        assert.equal(await page.locator('dialog').evaluate(d => d.open), false);
        assert(await dataset.locator('.figure-image').evaluate(b => b === document.activeElement));
        await dataset.locator('.figure-image').click();
        await page.getByRole('button', { name: 'Close', exact: true }).click();
        assert.equal(await page.locator('dialog').evaluate(d => d.open), false);
        await select.selectOption(choices[1].value);
        await page.waitForFunction(url => document.querySelector('.figure-image:not([hidden]) img')?.src === url, choices[1].value);
        await dataset.locator('[data-copy]').click();
        assert.equal(await page.evaluate(() => window.copied.at(-1)), choices[1].review);
        assert.equal(await dataset.locator('.suggest').getAttribute('href'), choices[1].suggest);
        assert.equal(await page.locator('.figure-image:visible').count(), 1);
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
        assert(overflow <= 1, `overflow ${overflow} at ${width}/${colorScheme}`);
        if (width === 390 || width === 1440) {
          await page.screenshot({ path: path.join(output, `${width}-${colorScheme}.png`), fullPage: true });
        }
        // Switching datasets closes the previous viewer and does not fetch its images.
        const other = library.locator('.dataset').nth(1);
        await other.locator('summary').click();
        await page.waitForFunction(() => document.querySelectorAll('.dataset[open]').length === 1);
        assert.equal(await dataset.getAttribute('open'), null);
        // Failed requests offer a retry, which restores the selected image.
        let fail = true;
        const faultURL = choices[0].value + "?browser-failure-check=1";
        await select.locator('option').nth(1).evaluate((option, url) => option.value = url, faultURL);
        await page.route(faultURL, async route => {
          if (fail) await route.abort(); else await imageResponse(route);
        });
        await dataset.locator('summary').click();
        await select.selectOption(faultURL);
        await dataset.getByRole('button', { name: 'Retry loading' }).waitFor({ state: 'visible' });
        fail = false;
        await dataset.getByRole('button', { name: 'Retry loading' }).click();
        await image.waitFor({ state: 'visible' });
        await select.locator('option').nth(1).evaluate((option, url) => option.value = url, choices[0].value);
        // A delayed previous selection cannot overwrite the latest selection/actions.
        await page.route(choices[0].value, async route => {
          await new Promise(resolve => setTimeout(resolve, 150));
          await imageResponse(route);
        });
        await select.selectOption('');
        await select.selectOption(choices[0].value);
        await select.selectOption(choices[1].value);
        await page.waitForFunction(url => document.querySelector('.figure-image:not([hidden]) img')?.src === url, choices[1].value);
        await page.waitForTimeout(250);
        assert.equal(await image.getAttribute('src'), choices[1].value);
        assert.equal(await dataset.locator('.suggest').getAttribute('href'), choices[1].suggest);
        assert.deepEqual(errors, []);
        results.push({ width, colorScheme, passed: true });
        console.log(`Passed ${width}/${colorScheme}`);
        await page.close();
      }
    }
    for (const width of [390, 1440]) {
      const host = await browser.newPage({ viewport: { width, height: 1000 } });
      await host.route('https://raw.githubusercontent.com/**/*.png', imageResponse);
      await host.goto(pathToFileURL(source).href);
      await host.evaluate(() => {
        const frame = document.createElement('iframe');
        frame.src = location.href;
        frame.style = 'width:100%;height:900px;border:0';
        document.body.replaceChildren(frame);
      });
      const frame = host.frameLocator('iframe');
      await frame.locator('nav a[href="#galaxy"]').click();
      const section = frame.locator('#galaxy').locator('xpath=ancestor::details[1]');
      const dataset = section.locator('.dataset').first();
      await dataset.locator('summary').click();
      await dataset.locator('select').selectOption({ index: 1 });
      await dataset.locator('.figure-image').waitFor({ state: 'visible' });
      await dataset.locator('.figure-image').click();
      assert(await frame.locator('dialog').evaluate(d => d.open));
      await host.keyboard.press('Tab');
      assert(await frame.locator('dialog').evaluate(d => d.contains(document.activeElement)));
      await host.keyboard.press('Shift+Tab');
      assert(await frame.locator('dialog').evaluate(d => d.contains(document.activeElement)));
      await host.keyboard.press('Escape');
      assert(await dataset.locator('.figure-image').evaluate(b => b === document.activeElement));
      assert(await frame.locator('html').evaluate(el => el.scrollWidth <= innerWidth + 1));
      results.push({ width, embedded: true, passed: true });
      await host.close();
    }
    const noJS = await browser.newPage({ javaScriptEnabled: false });
    await noJS.goto(pathToFileURL(source).href);
    assert(await noJS.locator('noscript a').count() > 0);
    await noJS.close();
    fs.writeFileSync(path.join(output, 'results.json'), JSON.stringify({ cases: results, realImages: cache.size }, null, 2));
    console.log(`${results.length} responsive interaction cases passed; ${cache.size} real PNGs loaded; no-JS fallback present.`);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
