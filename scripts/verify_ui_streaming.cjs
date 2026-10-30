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
    const requests = [];
    let scenario = "normal";
    let failedOnce = false;
    let staleRelease;
    let staleStarted;
    const staleReady = new Promise(resolve => { staleStarted = resolve; });
    let pendingRelease;
    let pendingStarted;
    let pendingAttempts = 0;
    const pendingReady = new Promise(resolve => { pendingStarted = resolve; });
    const card = { id: "", source_id: "one", title: "分页示例", type: "TV", year: "2026", site: "腾讯视频", image: "/preview/art/0/poster.svg", detail_url: "https://tencent.example/preview/one" };
    page.on("pageerror", error => errors.push(error.message));
    await page.route(url => url.origin === origin && url.pathname === "/do", async route => {
      const form = new URLSearchParams(route.request().postData());
      const command = form.get("cmd");
      const data = JSON.parse(form.get("data") || "{}");
      requests.push({ command, data });
      if (scenario === "filter-error" && command === "get_streaming_filters" && !failedOnce) {
        failedOnce = true;
        return route.fulfill({ contentType: "application/json", body: JSON.stringify({ code: 1, msg: "示例筛选加载失败" }) });
      }
      if (scenario === "stale" && command === "get_streaming_filters" && data.source === "tencent") {
        staleStarted();
        await new Promise(resolve => { staleRelease = resolve; });
        return route.fulfill({ contentType: "application/json", body: JSON.stringify({ code: 0, Filters: [{ key: "old", name: "过期筛选", options: [{ value: "old", name: "过期选项" }] }] }) });
      }
      if (scenario === "history-failure" && command === "get_recommend" && data.subtype === "tencent") {
        const result = failedOnce ? { code: 0, Items: [card], has_more: false }
          : { code: 1, msg: "历史恢复失败示例" };
        failedOnce = true;
        return route.fulfill({ contentType: "application/json", body: JSON.stringify(result) });
      }
      if (scenario === "history-pending" && command === "get_recommend" && data.subtype === "tencent") {
        const attempt = ++pendingAttempts;
        if (attempt === 1) {
          pendingStarted();
          await new Promise(resolve => { pendingRelease = resolve; });
        }
        return route.fulfill({ contentType: "application/json", body: JSON.stringify({ code: 0,
          Items: [{ ...card, source_id: `pending-${attempt}`, title: attempt === 1 ? "过期列表" : "恢复请求" }], has_more: false }) });
      }
      if (scenario !== "pagination" || command !== "get_recommend") return route.continue();
      const currentPage = Number(data.page);
      let result;
      if (!failedOnce) { failedOnce = true; result = { code: 1, msg: "示例来源暂不可用" }; }
      else if (currentPage === 1) result = { code: 0, Items: [card, card], has_more: true };
      else if (currentPage === 2) result = { code: 0, Items: [], has_more: true };
      else result = { code: 0, Items: [card, { ...card, source_id: "two", title: "另一部作品" }], has_more: false };
      await route.fulfill({ contentType: "application/json", body: JSON.stringify(result) });
    });

    const filterRow = key => page.locator(`discovery-filters [data-filter-key="${key}"]`);
    const filterButton = (key, value) => filterRow(key).locator(`[data-filter-value="${value}"]`);
    const waitFilters = async () => page.waitForFunction(() => document.querySelectorAll("discovery-filters [data-filter-key]").length === 6);
    for (const provider of ["tencent", "iqiyi", "mgtv"]) {
      await page.goto(`${origin}/?next=${provider}`);
      await waitFilters();
      await page.waitForSelector("#recommend_content normal-card .nt-media-card__link");
      assert.equal(await page.locator('[data-lit-page="tmdb_movie"]').getAttribute("aria-current"), "page");
      assert.equal(await page.locator(`[data-discovery-source="${provider}"]`).getAttribute("aria-current"), "page");
      assert.equal(await page.locator(".nt-discovery-header").count(), 0);
      assert.deepEqual(await page.locator(".nt-explore-filter-label").allTextContents(), ["种类", "排序", "类型", "地区", "年份", "资费"]);
      assert.equal(await filterButton("category", "tv").getAttribute("aria-pressed"), "true");
      const typeKey = await page.locator(".nt-explore-filter-row").filter({ has: page.locator(".nt-explore-filter-label", { hasText: /^类型$/ }) }).getAttribute("data-filter-key");
      await filterButton(typeKey, "demo-tv-urban").click();
      await page.waitForFunction(({ provider, typeKey }) => {
        const state = window.history.state?.page || "";
        const params = JSON.parse(new URLSearchParams(state.split("?")[1]).get("params") || "{}");
        return state.startsWith(provider + "?") && params[typeKey] === "demo-tv-urban";
      }, { provider, typeKey });
      await waitFilters();
      assert.equal(await filterButton(typeKey, "demo-tv-urban").getAttribute("aria-pressed"), "true");
      await page.waitForFunction(() => document.querySelectorAll("#recommend_content normal-card").length > 0);
      assert.equal(requests.filter(item => item.command === "get_recommend").at(-1).data.params[typeKey], "demo-tv-urban");
      await filterButton("sort", "new").click();
      await waitFilters();
      await filterButton("category", "movie").click();
      await waitFilters();
      await page.waitForFunction(() => document.querySelector('[data-filter-key="category"] [aria-pressed="true"]')?.dataset.filterValue === "movie");
      const params = await page.evaluate(() => JSON.parse(new URLSearchParams(window.history.state.page.split("?")[1]).get("params")));
      assert.deepEqual(params, { category: "movie", sort: "hot" });
      assert.equal(await filterButton(typeKey, "demo-movie-comedy").count(), 1);
      assert.equal(await filterButton(typeKey, "demo-tv-urban").count(), 0);
      assert.equal(await filterButton("sort", "hot").getAttribute("aria-pressed"), "true");
      const link = page.locator("#recommend_content .nt-media-card__link").first();
      await link.waitFor();
      assert.equal(await link.getAttribute("target"), "_blank");
      assert.equal(await link.getAttribute("rel"), "noopener noreferrer");
      assert.match(await link.getAttribute("href"), new RegExp(`^https://${provider}\\.example/preview/`));
      await page.evaluate(() => { window.media_search = (...args) => { window.streamSearchArguments = args; }; });
      await page.locator("#recommend_content .nt-media-card__search").first().click();
      assert.deepEqual(await page.evaluate(() => window.streamSearchArguments), ["", "远山来信", "MOV"]);
    }
    console.log("PASS 三平台多行筛选常显，实际传递子筛选，切换种类清空依赖并重置排序");

    await page.locator('[data-discovery-source="tmdb"]').click();
    await filterButton("media_type", "MOV").waitFor();
    await filterButton("media_type", "TV").click();
    await page.waitForFunction(() => window.history.state?.page === "tmdb_tv");
    assert.equal(await filterButton("media_type", "TV").getAttribute("aria-pressed"), "true");
    await page.locator('[data-discovery-source="bangumi"]').click();
    await page.waitForFunction(() => window.history.state?.page === "bangumi");
    assert.equal(await page.locator('[data-discovery-source="bangumi"]').getAttribute("aria-current"), "page");
    assert.equal(await page.locator('[data-lit-page="tmdb_movie"]').getAttribute("aria-current"), "page");
    console.log("PASS 统一探索来源切换、TMDB电影电视剧切换与Bangumi兼容入口");

    scenario = "filter-error";
    failedOnce = false;
    await page.goto(`${origin}/?next=tencent`);
    await page.getByRole("button", { name: "重新加载筛选", exact: true }).waitFor();
    assert.equal(await filterButton("category", "movie").isVisible(), true);
    await page.getByRole("button", { name: "重新加载筛选", exact: true }).click();
    await waitFilters();
    assert.equal(await page.getByRole("button", { name: "重新加载筛选", exact: true }).count(), 0);
    console.log("PASS 筛选加载失败仍可选择种类，并可重试完整筛选");

    scenario = "stale";
    await page.goto(`${origin}/?next=tencent`);
    await staleReady;
    await page.locator('[data-discovery-source="iqiyi"]').click();
    await waitFilters();
    staleRelease();
    await page.waitForFunction(() => document.querySelector('[data-discovery-source="iqiyi"]')?.getAttribute("aria-current") === "page");
    assert.equal(await page.getByText("过期筛选", { exact: true }).count(), 0);
    console.log("PASS 切换来源后旧筛选响应不会覆盖新页面");

    scenario = "pagination";
    failedOnce = false;
    requests.length = 0;
    await page.goto(`${origin}/?next=tencent`);
    await page.getByRole("button", { name: "重新加载", exact: true }).waitFor();
    await page.evaluate(() => { window.hasScrollbar = () => true; });
    await page.getByRole("button", { name: "重新加载", exact: true }).click();
    await page.waitForFunction(() => document.querySelectorAll("#recommend_content normal-card").length === 1);
    await page.getByRole("button", { name: "加载更多", exact: true }).click();
    await page.waitForFunction(() => document.querySelector("#recommend_status").textContent === "已显示 1 部作品");
    await page.getByRole("button", { name: "加载更多", exact: true }).click();
    await page.waitForFunction(() => document.querySelectorAll("#recommend_content normal-card").length === 2);
    assert.equal(await page.locator("#recommend_load_more").isHidden(), true);
    assert.deepEqual(requests.filter(item => item.command === "get_recommend").map(item => Number(item.data.page)), [1, 1, 2, 3]);
    console.log("PASS 失败重试、来源去重、空中间页继续加载与末页停止");

    scenario = "normal";
    await page.locator('[data-discovery-source="iqiyi"]').click();
    await page.waitForFunction(() => window.history.state?.page === "iqiyi" && document.querySelector("#recommend_content")?.dataset.recommendFinished === "true");
    const completedRequests = requests.filter(item => item.command === "get_recommend").length;
    await page.goBack();
    await page.waitForFunction(() => window.history.state?.page === "tencent" && document.querySelectorAll("#recommend_content normal-card").length === 2);
    await page.evaluate(() => { window.getScrollRate = () => -1; window.dispatchEvent(new Event("scroll")); });
    await page.goForward();
    await page.waitForFunction(() => window.history.state?.page === "iqiyi" && document.querySelectorAll("#recommend_content normal-card").length === 8);
    await page.evaluate(() => window.dispatchEvent(new Event("scroll")));
    assert.equal(requests.filter(item => item.command === "get_recommend").length, completedRequests);
    console.log("PASS 后退和前进恢复末页状态，不再请求已结束列表的下一页");

    scenario = "history-failure";
    failedOnce = false;
    await page.goto(`${origin}/?next=tencent`);
    await page.getByRole("button", { name: "重新加载", exact: true }).waitFor();
    await page.locator('[data-discovery-source="iqiyi"]').click();
    await page.waitForFunction(() => window.history.state?.page === "iqiyi");
    const failedRequests = requests.filter(item => item.command === "get_recommend" && item.data.subtype === "tencent").length;
    await page.goBack();
    await page.waitForFunction(() => window.history.state?.page === "tencent" && document.querySelector("#recommend_content")?.dataset.recommendFailed === "true");
    await page.evaluate(() => { window.getScrollRate = () => -1; window.dispatchEvent(new Event("scroll")); });
    assert.equal(requests.filter(item => item.command === "get_recommend" && item.data.subtype === "tencent").length, failedRequests);
    await page.getByRole("button", { name: "重新加载", exact: true }).click();
    await page.waitForFunction(() => document.querySelector("#recommend_content")?.dataset.recommendFinished === "true");
    assert.equal(requests.filter(item => item.command === "get_recommend" && item.data.subtype === "tencent").at(-1).data.page, 1);
    console.log("PASS 历史恢复失败状态保留手动重试，不自动循环请求");

    scenario = "history-pending";
    await page.goto(`${origin}/?next=tencent`);
    await pendingReady;
    await page.locator('[data-discovery-source="iqiyi"]').click();
    await page.waitForFunction(() => window.history.state?.page === "iqiyi");
    await page.goBack();
    await page.waitForFunction(() => window.history.state?.page === "tencent" && document.querySelector("#recommend_content")?.dataset.recommendFinished === "true");
    pendingRelease();
    await page.waitForFunction(() => document.querySelector("#recommend_content normal-card")?.getAttribute("card-title") === "恢复请求");
    assert.equal(pendingAttempts, 2);
    assert.equal(requests.filter(item => item.command === "get_recommend" && item.data.subtype === "tencent").at(-1).data.page, 1);
    assert.equal(await page.locator("#recommend_content [data-loading-placeholder]").count(), 0);
    assert.equal(await page.locator("#recommend_content normal-card").count(), 1);
    console.log("PASS 历史恢复未完成请求时重取同一页、清除占位，旧响应不混入结果");

    scenario = "normal";
    await page.goto(`${origin}/?next=tencent`);
    await waitFilters();
    await page.waitForSelector("#recommend_content normal-card .nt-media-card__link");
    if (process.env.UI_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.UI_SCREENSHOT_DIR}/nastools-explore-desktop.png`, fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.evaluate(() => document.body.classList.add("theme-dark"));
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
    assert.equal(await filterRow("category").isVisible(), true);
    assert.equal(await page.locator(".nt-explore-sources").evaluate(element => getComputedStyle(element).overflowX), "auto");
    assert.equal(await page.locator(".nt-explore-filter-options").first().evaluate(element => element.scrollWidth > element.clientWidth), true);
    await page.locator('[data-discovery-source="mgtv"]').click();
    await waitFilters();
    await page.waitForFunction(() => document.querySelector('[data-discovery-source="mgtv"]')?.getAttribute("aria-current") === "page");
    if (process.env.UI_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.UI_SCREENSHOT_DIR}/nastools-explore-mobile-dark.png`, fullPage: true });
    assert.deepEqual(errors, []);
    console.log("PASS 桌面与390px手机深色界面，来源和筛选行可横滚，无整页横向溢出");
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
