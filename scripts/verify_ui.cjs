/* Usage: NODE_PATH=/path/to/node_modules node scripts/verify_ui.cjs
 * Requires Playwright and a running scripts/preview_ui.py server.
 * Only visits the local read-only preview; never clicks write actions.
 */
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");

const origin = process.env.UI_PREVIEW_URL || "http://127.0.0.1:5108";
if (!["127.0.0.1", "localhost"].includes(new URL(origin).hostname)) {
  throw new Error("UI verification is restricted to a local preview server.");
}
const output = path.resolve(__dirname, "../docs/ui/verification");
const imageDirectory = path.join(output, "pages");
fs.mkdirSync(imageDirectory, { recursive: true });
const systemChrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const browserPath = process.env.CHROME_PATH || (fs.existsSync(systemChrome) ? systemChrome : undefined);

function screenshotName(route) {
  const url = new URL(route, origin);
  const main = url.searchParams.get("next");
  if (!main) return url.pathname.replace(/^\//, "").replaceAll("/", "-") || "shell";
  const target = new URL(main, origin);
  const variant = target.searchParams.get("subtype") || target.searchParams.get("type") || (target.search ? "detail" : "");
  return target.pathname.replace(/^\//, "").replaceAll("/", "-") + (variant ? `-${variant.toLowerCase()}` : "");
}

async function settlePage(page) {
  await page.evaluate(() => document.fonts.ready);
  // Trigger the real lazy-loading observers before taking a full-page image.
  for (let top = 0; top < await page.evaluate(() => document.documentElement.scrollHeight); top += 800) {
    await page.evaluate(y => window.scrollTo(0, y), top);
    await page.waitForTimeout(100);
  }
  await page.evaluate(async () => {
    const images = Array.from(document.images);
    images.forEach(image => { image.loading = "eager"; });
    await Promise.all(images.map(image => image.decode().catch(() => {})));
    window.scrollTo(0, 0);
  });
  await page.waitForTimeout(350);
}

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: browserPath });
  const results = [];
  try {
    const index = await browser.newPage();
    await index.goto(`${origin}/preview`);
    const routes = await index.locator("nav a").evaluateAll(links => links.map(link => ({ title: link.textContent, url: link.getAttribute("href") })));
    await index.close();
    for (const route of routes) {
      const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, colorScheme: "light" });
      const errors = [];
      page.on("pageerror", error => errors.push(error.message));
      const result = { route: route.url, title: route.title, errors, overflow: null, screenshot: `pages/${screenshotName(route.url)}.png` };
      try {
        const response = await page.goto(origin + route.url);
        result.status = response.status();
        if (route.url.startsWith("/?next=")) {
          await page.locator("#page_content:not([hidden]) h1").first().waitFor({ timeout: 10000 });
        } else if (route.url.startsWith("/api/")) {
          await page.locator(".swagger-ui .info .title").waitFor({ timeout: 10000 });
        }
        await settlePage(page);
        result.overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
        result.heading = await page.locator("h1, .swagger-ui .info .title").first().textContent().catch(() => "");
        await page.screenshot({ path: path.join(output, result.screenshot), fullPage: true });
      } catch (error) {
        errors.push(error.message);
        await page.screenshot({ path: path.join(output, result.screenshot), fullPage: true }).catch(() => {});
      }
      results.push(result);
      console.log(`${errors.length || result.overflow ? "CHECK" : "PASS"} ${route.title}`);
      await page.close();
    }
  } finally {
    await browser.close();
    const report = { preview: true, dataSource: "local fixtures; real templates and static assets", liveIntegrationsTested: false,
      viewport: { width: 1440, height: 1000 }, generatedAt: new Date().toISOString(), pages: results.length, results };
    fs.writeFileSync(path.join(output, "browser-results.json"), JSON.stringify(report, null, 2) + "\n");
  }
  const failed = results.filter(result => result.errors.length || result.overflow || result.status !== 200);
  console.log(JSON.stringify({ pages: results.length, failures: failed, report: path.join(output, "browser-results.json") }, null, 2));
  if (failed.length) process.exitCode = 1;
})().catch(error => { console.error(error); process.exitCode = 1; });
