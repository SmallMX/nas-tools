/* 运行：NODE_PATH=/path/to/node_modules node scripts/verify_ui_navigation.cjs
 * 依赖 Playwright 和 scripts/preview_ui.py；仅访问本地只读预览。
 */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const { chromium } = require("playwright");

const origin = new URL(process.env.UI_PREVIEW_URL || "http://127.0.0.1:5108").origin;
if (!["127.0.0.1", "localhost"].includes(new URL(origin).hostname)) {
  throw new Error("导航验证仅允许本地只读预览。");
}
const chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const pages = ["ranking", "tmdb_movie", "tmdb_tv", "tencent", "iqiyi", "mgtv", "bangumi", "search", "site", "statistics",
  "brushtask", "sitelist", "downloading", "downloaded", "torrent_remove", "tools", "service",
  "basic", "media_setting", "service_setting", "security_setting", "laboratory_setting",
  "notification", "downloader"];

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_PATH || (fs.existsSync(chrome) ? chrome : undefined) });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  await context.route("**/*", route => new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
  try {
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.goto(`${origin}/?next=`);
    await page.waitForSelector("#navbar-menu:not([hidden])");
    await page.waitForFunction(() => window.history.state?.page === "ranking");
    const visiblePages = await page.locator("#navbar-menu [data-lit-page]").evaluateAll(
      links => links.map(link => link.dataset.litPage)
    );
    assert.deepEqual(visiblePages, pages, "管理员应看到全部功能入口");
    assert.equal(await page.getByRole("button", { name: "打开消息中心" }).count(), 1);
    assert.equal(await page.getByRole("link", { name: "管理员菜单" }).count(), 1);
    assert.equal(await page.getByRole("button", { name: "实时日志", exact: true, includeHidden: true }).count(), 1);
    assert.equal((await page.request.get(`${origin}/users`)).status(), 404);
    console.log(`PASS 管理员导航：${visiblePages.length} 个入口；默认 ranking；用户管理页已移除`);

    // 显式入口和刷新后的历史页继续优先于默认页。
    await page.goto(`${origin}/?next=statistics`);
    await page.waitForFunction(() => window.history.state?.page === "statistics");
    await page.evaluate(() => history.replaceState(history.state, "", "/?next="));
    await page.reload();
    await page.waitForFunction(() => window.history.state?.page === "statistics");
    console.log("PASS 显式入口与刷新历史页保持 statistics");

    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByRole("button", { name: "打开主导航" }).click();
    await page.waitForSelector("#litLayoutNavbar.show");
    assert.deepEqual(await page.locator("#navbar-menu [data-lit-page]").evaluateAll(
      links => links.map(link => link.dataset.litPage)
    ), pages, "手机导航应包含全部管理员功能");
    assert.deepEqual(errors, [], "导航不应产生浏览器错误");
    console.log("PASS 手机导航完整；仅本地示例数据，未连接真实外部服务。");
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
