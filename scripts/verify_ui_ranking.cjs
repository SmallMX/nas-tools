/* 运行：NODE_PATH=/path/to/node_modules node scripts/verify_ui_ranking.cjs
 * 依赖 Playwright 和 scripts/preview_ui.py；所有外部请求均被拦截。
 */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const { chromium } = require("playwright");
const origin = new URL(process.env.UI_PREVIEW_URL || "http://127.0.0.1:5108").origin;
if (!["127.0.0.1", "localhost"].includes(new URL(origin).hostname)) throw new Error("只允许本机隔离预览");
const chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_PATH || (fs.existsSync(chrome) ? chrome : undefined) });
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    await context.route("**/*", route => new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
    const page = await context.newPage();
    const errors = [];
    const calls = [];
    const attempts = new Map();
    let active = 0;
    let maximum = 0;
    let scenario = "normal";
    let releaseStale;
    let beginStale;
    const staleStarted = new Promise(resolve => { beginStale = resolve; });
    const items = Array.from({ length: 8 }, (_, index) => ({ id: `DB:${123 + index}`, type: "MOV", title: `榜单示例影片 ${index + 1}`, year: "2026", image: `/preview/art/${index}/poster.svg`, vote: 8.1 }));
    page.on("pageerror", error => errors.push(error.message));
    await page.route(url => url.origin === origin && url.pathname === "/do", async route => {
      const form = new URLSearchParams(route.request().postData());
      if (form.get("cmd") !== "get_recommend") return route.continue();
      const data = JSON.parse(form.get("data") || "{}");
      const key = `${data.type}:${data.subtype}:${data.week || ""}`;
      calls.push(data);
      const attempt = (attempts.get(key) || 0) + 1;
      attempts.set(key, attempt);
      active++;
      maximum = Math.max(maximum, active);
      try {
        if (scenario === "stale" && data.subtype === "tmdb") {
          beginStale();
          await new Promise(resolve => { releaseStale = resolve; });
        } else await new Promise(resolve => setTimeout(resolve, 100));
        let payload = { code: 0, Items: items.map(item => ({ ...item, type: data.type === "TV" ? "TV" : "MOV" })) };
        if (data.subtype === "dbhm" && attempt === 1) payload = { code: 1, msg: "示例豆瓣服务暂不可用", Items: [] };
        if (data.subtype === "dbht" && attempt === 1) payload = { code: 0, Items: [] };
        await route.fulfill({ contentType: "application/json", body: JSON.stringify(payload) });
      } finally { active--; }
    });
    const slide = key => page.locator(`custom-slide[data-discovery-key="${key}"]`);
    const loadAll = async () => {
      for (const element of await page.locator("page-discovery custom-slide").all()) {
        await element.scrollIntoViewIfNeeded();
        await element.locator('.nt-slide__viewport[aria-busy="false"]').waitFor({ state: "attached" });
      }
    };

    await page.goto(`${origin}/?next=ranking`);
    await page.locator('page-discovery custom-slide[slide-status="ready"]').first().waitFor();
    assert.deepEqual(await page.locator("[data-ranking-category]").allTextContents(), ["全部", "电影", "电视剧", "动漫", "榜单"]);
    assert.equal(await page.locator("page-discovery .nt-discovery-banner").count(), 0);
    assert.equal(await page.locator("page-discovery custom-slide").count(), 13);
    assert.ok(calls.length < 13, "离屏榜单应等接近视口再请求");
    await page.setViewportSize({ width: 1440, height: 12000 });
    await loadAll();
    assert.equal(new Set(calls.map(data => `${data.type}:${data.subtype}`)).size, 13);
    assert.ok(maximum <= 3, `榜单请求并发应不超过3，实际${maximum}`);
    assert.equal(calls.filter(data => data.subtype === "dbnm").length, 0, "最新电影不能仍使用即将上映接口");
    assert.equal(calls.filter(data => data.subtype === "dbnewmovie").length, 1);
    assert.equal(calls.filter(data => data.subtype === "dbnewtv").length, 1);
    assert.equal(await slide("MOV:dbhm:").getAttribute("slide-status"), "error");
    assert.equal(await slide("TV:dbht:").getAttribute("slide-status"), "ready");
    assert.equal(await slide("TV:dbht:").locator("normal-card").count(), 0);
    const cachedKeys = await page.evaluate(() => Object.keys(window.history.state.extra || {}));
    assert.equal(cachedKeys.includes("discovery:v2:RANKING:MOV:dbhm:"), false);
    assert.equal(cachedKeys.includes("discovery:v2:RANKING:TV:dbht:"), false);
    await slide("MOV:dbhm:").getByRole("button", { name: "重新加载", exact: true }).click();
    await slide("MOV:dbhm:").locator("normal-card").first().waitFor();
    assert.equal(attempts.get("MOV:dbhm:"), 2);
    console.log("PASS 13个真实来源契约、视口懒加载、最多3并发、错误重试且失败/空结果不缓存");

    const beforeReturn = new Map(attempts);
    await page.evaluate(() => navmenu("tmdb_movie"));
    await page.waitForFunction(() => window.history.state?.page === "tmdb_movie");
    await page.goBack();
    await page.waitForFunction(() => window.history.state?.page === "ranking");
    await loadAll();
    assert.equal(attempts.get("TV:dbht:"), beforeReturn.get("TV:dbht:") + 1, "返回榜单须重新获取上次空结果");
    assert.equal(attempts.get("MOV:dbhm:"), beforeReturn.get("MOV:dbhm:"), "有效非空成功结果应复用短时缓存");
    const key = "discovery:v2:RANKING:MOV:dbnewmovie:";
    await page.evaluate(key => { window.history.state.extra[key].savedAt = 0; window_history(false, window.history.state.extra); navmenu("tmdb_movie"); }, key);
    await page.waitForFunction(() => window.history.state?.page === "tmdb_movie");
    const beforeExpiry = attempts.get("MOV:dbnewmovie:");
    await page.goBack();
    await page.waitForFunction(() => window.history.state?.page === "ranking");
    await loadAll();
    assert.equal(attempts.get("MOV:dbnewmovie:"), beforeExpiry + 1, "过期榜单缓存须重新加载");
    console.log("PASS 历史返回只复用有效非空缓存，空结果与过期缓存重新加载");

    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.locator('[data-ranking-category="movie"]').click();
    assert.equal(await page.locator("page-discovery custom-slide").count(), 5);
    await page.locator('[data-ranking-category="tv"]').click();
    assert.equal(await page.locator("page-discovery custom-slide").count(), 5);
    await page.locator('[data-ranking-category="anime"]').click();
    assert.equal(await page.locator("page-discovery custom-slide").count(), 2);
    await page.locator('[data-ranking-category="rank"]').click();
    assert.equal(await page.locator("page-discovery custom-slide").count(), 4);
    await slide("MOV:dbtop:").getByRole("button", { name: "查看全部", exact: false }).click();
    await page.waitForFunction(() => (window.history.state?.page || "").startsWith("recommend?"));
    const more = await page.evaluate(() => Object.fromEntries(new URLSearchParams(window.history.state.page.split("?")[1])));
    assert.equal(more.type, "MOV");
    assert.equal(more.subtype, "dbtop");
    assert.equal(more.title, "豆瓣电影 TOP250");
    console.log("PASS 分类切换和查看全部保持准确媒体类型、榜单ID与标题");

    scenario = "stale";
    await page.goto(`${origin}/?next=ranking`);
    await staleStarted;
    await page.evaluate(() => navmenu("tmdb_movie"));
    await page.waitForFunction(() => window.history.state?.page === "tmdb_movie");
    releaseStale();
    await page.waitForFunction(() => document.querySelector("discovery-filters") !== null);
    assert.equal(await page.locator("page-discovery").count(), 0);
    assert.equal(await page.evaluate(() => Object.keys(window.history.state.extra || {}).some(key => key.startsWith("discovery:v2:"))), false);
    console.log("PASS 离开榜单后旧响应不会写入新页面或污染新页面缓存");

    scenario = "normal";
    await page.goto(`${origin}/?next=ranking`);
    await page.locator('page-discovery custom-slide[slide-status="ready"]').first().waitFor();
    await page.locator("page-discovery custom-slide").nth(2).locator('.nt-slide__viewport[aria-busy="false"]').waitFor({ state: "attached" });
    if (process.env.UI_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.UI_SCREENSHOT_DIR}/nastools-ranking-desktop.png`, fullPage: false });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.evaluate(() => document.body.classList.add("theme-dark"));
    await page.locator('[data-ranking-category="anime"]').click();
    await page.locator('page-discovery custom-slide[slide-status="ready"]').first().waitFor();
    await loadAll();
    await page.evaluate(() => window.scrollTo(0, 0));
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    assert.deepEqual(errors, []);
    if (process.env.UI_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.UI_SCREENSHOT_DIR}/nastools-ranking-mobile-dark.png`, fullPage: false });
    console.log("PASS 桌面和390px深色榜单无页面横向溢出；仅本地示例，未连接外部服务");
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
