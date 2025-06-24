// monitor.js

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

// ─── Configuration ────────────────────────────────────────────────────────────

// Comma-separated list of Popmart product URLs
const URLs = (process.env.POP_MART_URLS || '')
  .split(',')
  .map(u => u.trim())
  .filter(Boolean);

// Pushover credentials
const TOKEN = process.env.PUSHOVER_TOKEN;
const USER  = process.env.PUSHOVER_USER_KEY;

// Timeouts (ms)—defaults used in testing:
const NAV_TIMEOUT      = parseInt(process.env.NAV_TIMEOUT, 10)      || 30000; // 30 s
const SELECTOR_TIMEOUT = parseInt(process.env.SELECTOR_TIMEOUT, 10) || 15000; // 15 s
const RENDER_WAIT      = parseInt(process.env.RENDER_WAIT, 10)      || 2000;  // 2 s

// State file to track which URLs have already alerted
const STATE_FILE = path.resolve(__dirname, 'state.json');

// ─── Sanity checks ─────────────────────────────────────────────────────────────
if (!URLs.length) {
  console.error('❌ POP_MART_URLS must be set');
  process.exit(1);
}
if (!TOKEN || !USER) {
  console.error('❌ PUSHOVER_TOKEN and PUSHOVER_USER_KEY must be set');
  process.exit(1);
}

// ─── Load or initialize state ─────────────────────────────────────────────────
let state = {};
if (fs.existsSync(STATE_FILE)) {
  try {
    state = JSON.parse(fs.readFileSync(STATE_FILE, 'utf8'));
  } catch {
    console.warn('⚠ Could not parse state.json; starting fresh.');
  }
}
for (const url of URLs) {
  if (typeof state[url] !== 'boolean') {
    state[url] = false;
  }
}

// ─── Helper: simple retry wrapper ───────────────────────────────────────────────
async function withRetries(fn, retries = 3, delay = 500) {
  let attempt = 0;
  while (true) {
    try {
      return await fn();
    } catch (err) {
      attempt++;
      console.error(`   ❌ Attempt ${attempt} failed: ${err.message}`);
      if (attempt >= retries) throw err;
      console.log(`   ⏳ Retrying in ${delay}ms…`);
      await new Promise(r => setTimeout(r, delay));
    }
  }
}

// ─── Main ──────────────────────────────────────────────────────────────────────
(async () => {
  console.log('▶️  Starting monitor');

  // 1) Launch a single browser + context + page
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    userAgent:
      'Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) ' +
      'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Safari/605.1.15',
    viewport: { width: 1280, height: 800 },
  });
  const page = await context.newPage();

  // 2) Accept T&C modal once (on initial load)
  try {
    await page.goto(URLs[0], { waitUntil: 'domcontentloaded', timeout: NAV_TIMEOUT });
    const acceptBtn = page.locator('button', { hasText: /^accept$/i }).first();
    if (await acceptBtn.count()) {
      console.log('    ▶ Clicking initial Accept modal');
      await acceptBtn.click({ timeout: 5000 });
      await page.waitForTimeout(1000);
    }
  } catch (e) {
    console.warn('⚠ Initial T&C acceptance step failed:', e.message);
  }

  // 3) Loop through each URL
  for (const url of URLs) {
    const wasInStock = state[url];
    console.log(`\n🔗  Checking ${url}  (previously inStock: ${wasInStock})`);

    try {
      const nowInStock = await withRetries(async () => {
        // 3a) Navigate
        try {
          await page.goto(url, { waitUntil: 'domcontentloaded', timeout: NAV_TIMEOUT });
        } catch {
          console.warn('    ⚠ domcontentloaded timed out; using simple goto');
          await page.goto(url, { timeout: NAV_TIMEOUT });
        }

        // 3b) Wait for React to render dynamic button
        await page.waitForTimeout(RENDER_WAIT);

        // 3c) Wait for the stock-button container
        await page.waitForSelector(
          'div[class*="index_usBtn__"][class*="index_btnFull__"]',
          { timeout: SELECTOR_TIMEOUT }
        );

        // 3d) Detect “ADD TO BAG”
        const addCount = await page.locator(
          'div[class*="index_usBtn__"][class*="index_btnFull__"]:has-text("ADD TO BAG")'
        ).count();

        return addCount > 0;
      });

      console.log(`    ✓ nowInStock = ${nowInStock}`);

      // 4) Notify only on a fresh restock
      if (!wasInStock && nowInStock) {
        console.log('    ▶ New restock! Sending Pushover alert');
        const title = await page.title();
        await fetch('https://api.pushover.net/1/messages.json', {
          method: 'POST',
          body: new URLSearchParams({
            token: TOKEN,
            user: USER,
            message: `${title} is back in stock → ${url}`,
          }),
        });
        console.log('    ✓ Alert sent');
      } else {
        console.log('    • No alert (still out or already notified)');
      }

      // Update state for this URL
      state[url] = nowInStock;
    } catch (err) {
      console.error(`Error checking ${url}:`, err.message);
    }
  }

  // 5) Persist updated state
  try {
    fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2), 'utf8');
    console.log('\n✅ State saved to state.json');
  } catch (e) {
    console.error('❌ Failed to save state.json:', e.message);
  }

  // 6) Teardown
  await browser.close();
  console.log('\n🏁 All URLs processed');
})();
