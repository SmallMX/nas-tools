/* 运行：NODE_PATH=/path/to/node_modules node scripts/verify_ui_streaming.cjs
 * 依赖 Playwright 与 scripts/preview_ui.py；外部请求全部拦截。
 */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const { chromium } = require("playwright");
const origin = new URL(process.env.UI_PREVIEW_URL || "http://127.0.0.1:5108").origin;
if (!["127.0.0.1", "localhost"].includes(new URL(origin).hostname)) throw new Error("只允许本机隔离预览");
const chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_PATH || (fs.existsSync(chrome) ? chrome : undefined) });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  await context.route("**/*", route => new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
  try {
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    for (const [provider, title] of [["tencent", "腾讯视频"], ["iqiyi", "爱奇艺"], ["mgtv", "芒果视频"]]) {
      await page.goto(`${origin}/?next=${provider}`);
      await page.waitForSelector("#recommend_content normal-card .nt-media-card__link");
      assert.equal(await page.locator("#recommend_title").textContent(), title);
      assert.equal(await page.locator(`[data-lit-page="${provider}"]`).getAttribute("aria-current"), "page");
      const link = page.locator("#recommend_content .nt-media-card__link").first();
      assert.equal(await link.getAttribute("target"), "_blank");
      assert.equal(await link.getAttribute("rel"), "noopener noreferrer");
      assert.match(await link.getAttribute("href"), new RegExp(`^https://${provider}\\.example/preview/`));
      assert.equal(await page.locator("#recommend_load_more").isHidden(), true);
      await page.evaluate(() => { window.media_search = (...args) => { window.streamSearchArguments = args; }; });
      await page.locator("#recommend_content .nt-media-card__search").first().click();
      assert.deepEqual(await page.evaluate(() => window.streamSearchArguments), ["", "远山来信", "TV"]);
      await page.locator("#recommend_content normal-card").first().evaluate(card => card.setAttribute("card-detail-url", "javascript:alert(1)"));
      await page.waitForFunction(() => document.querySelector("#recommend_content .nt-media-card__link").getAttribute("href") === null);
    }
    console.log("PASS 三个平台入口、外部详情、资源搜索与不安全链接过滤");

    await page.goto(`${origin}/?next=tencent`);
    await page.getByRole("button", { name: "最热", exact: true }).click();
    await page.getByRole("link", { name: "高分", exact: true }).click();
    await page.getByRole("button", { name: "高分", exact: true }).waitFor();
    await page.getByRole("button", { name: "电视剧", exact: true }).click();
    await page.getByRole("link", { name: "少儿", exact: true }).click();
    await page.getByRole("button", { name: "少儿", exact: true }).waitFor();
    assert.equal(await page.getByRole("button", { name: "最热", exact: true }).count(), 1);
    assert.equal(await page.getByRole("link", { name: "高分", exact: true, includeHidden: true }).count(), 0);
    const selected = await page.evaluate(() => ({ page: window.history.state.page, active: document.querySelector('[data-lit-page="tencent"]').getAttribute("aria-current") }));
    assert.match(selected.page, /^tencent\?/);
    assert.deepEqual(JSON.parse(new URLSearchParams(selected.page.split("?")[1]).get("params")), { category: "children", sort: "hot" });
    assert.equal(selected.active, "page");
    console.log("PASS 分类筛选保留平台路径，重置排序并隐藏少儿不支持的高分选项");

    let firstAttempt = true;
    const requestedPages = [];
    const card = { id: "", source_id: "one", title: "分页示例", type: "TV", year: "2026", site: "腾讯视频", image: "/preview/art/0/poster.svg", detail_url: "https://tencent.example/preview/one" };
    await page.route(url => url.origin === origin && url.pathname === "/do", async route => {
      const form = new URLSearchParams(route.request().postData());
      const data = JSON.parse(form.get("data") || "{}");
      if (form.get("cmd") !== "get_recommend") return route.continue();
      const currentPage = Number(data.page);
      requestedPages.push(currentPage);
      let result;
      if (firstAttempt) { firstAttempt = false; result = { code: 1, msg: "示例来源暂不可用" }; }
      else if (currentPage === 1) result = { code: 0, Items: [card, card], has_more: true };
      else if (currentPage === 2) result = { code: 0, Items: [], has_more: true };
      else result = { code: 0, Items: [card, { ...card, source_id: "two", title: "另一部作品" }], has_more: false };
      await route.fulfill({ contentType: "application/json", body: JSON.stringify(result) });
    });
    await page.goto(`${origin}/?next=tencent`);
    await page.getByRole("button", { name: "重新加载", exact: true }).waitFor();
    assert.equal(await page.locator("#recommend_status").textContent(), "示例来源暂不可用");
    await page.evaluate(() => { window.hasScrollbar = () => true; });
    await page.getByRole("button", { name: "重新加载", exact: true }).click();
    await page.waitForFunction(() => document.querySelectorAll("#recommend_content normal-card").length === 1);
    await page.getByRole("button", { name: "加载更多", exact: true }).click();
    await page.waitForFunction(() => document.querySelector("#recommend_status").textContent === "已显示 1 部作品");
    await page.getByRole("button", { name: "加载更多", exact: true }).click();
    await page.waitForFunction(() => document.querySelectorAll("#recommend_content normal-card").length === 2);
    assert.equal(await page.locator("#recommend_load_more").isHidden(), true);
    assert.deepEqual(requestedPages, [1, 1, 2, 3]);
    console.log("PASS 失败重试、来源去重、空中间页继续加载与末页停止");

    await page.setViewportSize({ width: 390, height: 844 });
    await page.evaluate(() => document.body.classList.add("theme-dark"));
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
    assert.equal(await page.locator("#recommend_content .nt-media-card__search").first().isVisible(), true);
    assert.deepEqual(errors, []);
    if (process.env.UI_SCREENSHOT_PATH) await page.screenshot({ path: process.env.UI_SCREENSHOT_PATH, fullPage: true });
    console.log("PASS 390px 手机深色界面无横向溢出；仅隔离示例，未连接外部服务");
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
