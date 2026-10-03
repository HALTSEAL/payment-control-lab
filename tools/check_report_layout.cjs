// Development-only browser check. No browser dependency is used by the lab.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { chromium } = require('../.browser-check/node_modules/playwright');

async function main() {
  const out = 'out/browser-quality';
  fs.rmSync(out, { recursive: true, force: true });
  fs.mkdirSync(out, { recursive: true });
  const commands = [
    ['demo', ['demo'], 0],
    ['change', ['compare-policy', 'examples.route_retry_policy:decide', 'examples.fixture_policy:decide'], 0],
    ['regression', ['compare-policy', 'examples.fixture_policy:decide', 'examples.route_retry_policy:decide'], 2],
    ['workflow', ['review', 'examples/workflow.json'], 2],
    ['policy', ['check-policy', 'examples.fixture_policy:decide'], 0],
    ['advisory', ['check-policy', 'examples.route_retry_policy:decide', '--ci-mode', 'report'], 0],
    ['unbound', ['check-policy', 'examples.customer_adapter:decide', '--ci-mode', 'report'], 0],
    ['no-finding', ['review', 'payment_control_lab/data/traces/final-closure.json'], 0],
    ['unknown', ['review', 'payment_control_lab/data/traces/unobserved-portal.json'], 3],
  ];
  for (const [name, args, expected] of commands) {
    const result = spawnSync('python', ['lab.py', ...args, '--out', `${out}/${name}`], { encoding: 'utf8', timeout: 30000 });
    assert.equal(result.status, expected, result.stderr || result.error?.message);
  }
  const launch = { headless: true };
  // Optional local runtime. Hosted CI uses Playwright's installed Chromium.
  if (process.env.PAYMENT_LAB_CHROMIUM_EXECUTABLE) {
    launch.executablePath = process.env.PAYMENT_LAB_CHROMIUM_EXECUTABLE;
    launch.args = ['--no-sandbox', '--no-zygote', '--single-process', '--disable-gpu', '--disable-software-rasterizer'];
  }
  const browser = await chromium.launch(launch);
  const checks = [];
  try {
    const page = await browser.newPage();
    const errors = [];
    const externalRequests = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => {
      if (!request.url().startsWith('file:')) externalRequests.push(request.url());
    });
    for (const [name] of commands) {
      const result = JSON.parse(fs.readFileSync(`${out}/${name}/report.json`, 'utf8'));
      for (const file of ['report.html', 'owner-summary.html']) {
        for (const width of [1440, 720, 390, 320]) {
          errors.length = 0;
          externalRequests.length = 0;
          await page.setViewportSize({ width, height: 1000 });
          await page.emulateMedia({ media: 'screen' });
          await page.goto(`file://${path.resolve(out, name, file)}`);
          const state = await page.evaluate(() => ({
            overflow: document.documentElement.scrollWidth > innerWidth,
            scripts: document.scripts.length,
          }));
          assert.equal(state.overflow, false, `${name}/${file} overflow at ${width}`);
          assert.equal(state.scripts, 0);
          assert.deepEqual(errors, []);
          assert.deepEqual(externalRequests, []);
          assert.equal(await page.locator('h1').count(), 1);
          assert.equal(await page.locator('img,iframe,link').count(), 0);
          const text = await page.locator('body').innerText();
          assert.ok(text.includes('Continue with the free checks'));
          assert.ok(text.includes('Validate one actual workflow'));
          if (result.ci?.mode === 'report') assert.ok(text.includes('Advisory completion'));
          const disclosure = page.locator('details > summary').first();
          if (await disclosure.count()) {
            await disclosure.focus();
            await page.keyboard.press('Enter');
            assert.equal(await disclosure.evaluate(element => element.parentElement.open), true);
            assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
          }
          const region = page.locator('.table-wrap').first();
          if (await region.count()) {
            await region.focus();
            assert.equal(await region.evaluate(element => document.activeElement === element), true);
            if (await region.evaluate(element => element.scrollWidth > element.clientWidth)) {
              await region.evaluate(element => { element.scrollLeft = 0; });
              await region.press('ArrowRight');
              await page.waitForFunction(element => element.scrollLeft > 0, await region.elementHandle(), { timeout: 3000 });
              assert.ok(await region.evaluate(element => element.scrollLeft > 0), `${name}/${file} keyboard horizontal scrolling at ${width}`);
            }
          }
          if (width === 1440 || width === 390) {
            await page.screenshot({ path: `${out}/${name}-${file}-${width}.png`, fullPage: true });
          }
          await page.emulateMedia({ media: 'print' });
          assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
          if (file === 'owner-summary.html' && width === 1440) {
            const pdf = await page.pdf({ path: `${out}/${name}-owner-summary.pdf`, preferCSSPageSize: true, printBackground: true });
            const pages = (pdf.toString('latin1').match(/\/Type\s*\/Page\b/g) || []).length;
            assert.equal(pages, 1, `${name} owner summary should fit one A4 page`);
          }
          checks.push({ name, file, width, screen: 'PASS', print: 'PASS', scripts: 0, externalRequests: 0 });
        }
      }
    }
    const record = { browser: browser.version(), layoutChecks: checks.length, ownerSummaryPdfCount: commands.length, checks };
    fs.writeFileSync(`${out}/verification.json`, JSON.stringify(record, null, 2) + '\n');
    console.log(`PASS ${checks.length} screen/print layouts, keyboard disclosures and comparison regions, no scripts or external asset requests, and ${commands.length} one-page A4 owner summaries.`);
  } finally {
    await browser.close();
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
