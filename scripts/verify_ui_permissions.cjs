/* 运行：NODE_PATH=/path/to/node_modules node scripts/verify_ui_permissions.cjs
 * 依赖 Playwright 和 scripts/preview_ui.py；仅访问本地只读预览。
 */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const { chromium } = require("playwright");

const origin = new URL(process.env.UI_PREVIEW_URL || "http://127.0.0.1:5108").origin;
if (!["127.0.0.1", "localhost"].includes(new URL(origin).hostname)) {
  throw new Error("权限验证仅允许本地只读预览。");
}
const chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const settings = ["basic", "media_setting", "service_setting", "security_setting",
  "laboratory_setting", "users", "notification", "downloader"];
const cases = [
  { name: "仅站点管理", permissions: ["站点管理"], first: "site", pages: ["site", "statistics", "sitelist", "tools"] },
  { name: "仅服务", permissions: ["服务"], first: "service", pages: ["brushtask", "tools", "service"] },
  { name: "仅系统设置", permissions: ["系统设置"], first: "basic", pages: ["tools", "service", ...settings] },
  { name: "站点与服务", permissions: ["站点管理", "服务"], first: "site", pages: ["site", "statistics", "brushtask", "sitelist", "tools", "service"] },
  { name: "系统设置优先", permissions: ["系统设置", "服务"], first: "basic", pages: ["brushtask", "tools", "service", ...settings] },
  { name: "服务优先", permissions: ["服务", "系统设置"], first: "service", pages: ["brushtask", "tools", "service", ...settings] },
  { name: "空权限", permissions: [], first: "tools", pages: ["tools"] },
  { name: "仅资源搜索", permissions: ["资源搜索"], first: "search", pages: ["search", "tools"] },
  { name: "仅探索", permissions: ["探索"], first: "ranking", pages: ["ranking", "tmdb_movie", "tmdb_tv", "bangumi", "tools"] },
  { name: "仅下载管理", permissions: ["下载管理"], first: "downloading", pages: ["downloading", "downloaded", "torrent_remove", "tools"] },
];

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_PATH || (fs.existsSync(chrome) ? chrome : undefined) });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  await context.route("**/*", route => new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
  let checked = 0;
  try {
    for (const test of cases) {
      const page = await context.newPage();
      const errors = [];
      page.on("pageerror", error => errors.push(error.message));
      const query = new URLSearchParams({ next: "", permissions: test.permissions.join(",") });
      await page.goto(`${origin}/?${query}`);
      await page.waitForSelector("#navbar-menu:not([hidden])");
      await page.waitForFunction(expected => window.history.state?.page === expected, test.first);
      const state = await page.locator("#navbar-menu").evaluate(nav => ({
        pages: [...nav.querySelectorAll("[data-lit-page]")].map(link => link.dataset.litPage),
        emptyGroups: [...nav.querySelectorAll(".accordion-collapse")].filter(group => !group.querySelector("[data-lit-page]")).length,
        servicePermissions: nav.layout_page_permissions["/service"],
      }));
      assert.deepEqual(state.pages, test.pages, test.name);
      assert.equal(state.emptyGroups, 0, `${test.name} 不应出现空分组`);
      assert.deepEqual(state.servicePermissions, ["服务", "系统设置"], "模板须传递后端 OR 权限");
      assert.deepEqual(errors, [], `${test.name} 浏览器错误`);
      console.log(`PASS ${test.name}：${state.pages.length} 个入口；默认 ${test.first}`);
      checked++;
      await page.close();
    }

    // 显式入口和刷新后的历史页继续优先于默认页。
    const page = await context.newPage();
    await page.goto(`${origin}/?${new URLSearchParams({ next: "statistics", permissions: "站点管理" })}`);
    await page.waitForFunction(() => window.history.state?.page === "statistics");
    await page.evaluate(() => history.replaceState(history.state, "", `/?next=&permissions=${encodeURIComponent("站点管理")}`));
    await page.reload();
    await page.waitForFunction(() => window.history.state?.page === "statistics");
    checked += 2;
    console.log("PASS 显式入口与刷新历史页保持 statistics");

    // 缺少页面权限声明时隐藏入口，不能退回菜单名称推断权限。
    await page.locator("#navbar-menu").evaluate(async nav => {
      nav.layout_page_permissions = {};
      await nav.updateComplete;
    });
    assert.equal(await page.locator("#navbar-menu [data-lit-page]").count(), 0);
    checked++;
    console.log("PASS 缺少权限映射时不显示任何入口");
    await page.close();
    console.log(`导航权限验证通过：${checked} 项；仅本地示例数据，未连接真实外部服务。`);
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
