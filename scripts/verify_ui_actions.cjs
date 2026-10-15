/* 运行：UI_PREVIEW_URL=http://127.0.0.1:5108 NODE_PATH=/path/to/node_modules node scripts/verify_ui_actions.cjs
 * 只使用隔离 preview；写动作和乱序响应由 Playwright 拦截，不连接真实业务服务。
 * 结果默认写入临时目录，也可通过 UI_VERIFY_OUTPUT 指定目录。
 */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { chromium } = require("playwright");

const origin = new URL(process.env.UI_PREVIEW_URL || "http://127.0.0.1:5108").origin;
if (!["127.0.0.1", "localhost"].includes(new URL(origin).hostname)) {
  throw new Error("动作验证仅允许本地隔离预览。");
}
const chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const output = process.env.UI_VERIFY_OUTPUT || fs.mkdtempSync(path.join(os.tmpdir(), "nas-tools-ui-actions-"));
fs.mkdirSync(output, { recursive: true });

async function waitFor(predicate, message) {
  const end = Date.now() + 5000;
  while (!predicate()) {
    if (Date.now() > end) throw new Error(message);
    await new Promise(resolve => setTimeout(resolve, 10));
  }
}

(async () => {
  const browser = await chromium.launch({ headless: true,
    executablePath: process.env.CHROME_PATH || (fs.existsSync(chrome) ? chrome : undefined) });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  await context.route("**/*", route => new URL(route.request().url()).origin === origin
    ? route.continue() : route.abort());
  const page = await context.newPage();
  const errors = [], results = [], heldActions = new Map(), captured = [], fragments = [], nameTests = [];
  let backupMode = "forbidden", heldBackup;
  let directoryRequests = 0;
  page.on("pageerror", error => errors.push(error.message));
  async function check(name, verify) {
    await verify();
    results.push({ name, passed: true });
    console.log(`PASS ${name}`);
  }
  const json = (route, body, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  try {
    const preview = await context.request.get(`${origin}/preview`);
    assert.equal(preview.status(), 200, "必须启动 scripts/preview_ui.py");
    assert.match(await preview.text(), /只读预览/);
    await page.route("**/do?*", route => {
      const form = new URLSearchParams(route.request().postData());
      const command = form.get("cmd");
      const data = JSON.parse(form.get("data") || "{}");
      if (command === "verify_hold") {
        heldActions.set(data.key, route);
        return;
      }
      if (command === "verify_failure") return json(route, { msg: "模拟网络失败" }, 503);
      if (command === "name_test") {
        nameTests.push(data);
        return json(route, { code: 0, data: { name: data.name } });
      }
      if (command === "verify_capture") captured.push(data);
      if (command.startsWith("verify_")) return json(route, { code: 0, value: data.value ?? "ok" });
      return route.continue();
    });
    await page.route("**/__ui_verify_page?*", route => { fragments.push(route); });
    await page.route("**/backup", route => {
      if (backupMode === "network") return route.abort("failed");
      if (backupMode === "timeout") { heldBackup = route; return; }
      return json(route, { code: -1, msg: "模拟禁止备份" }, 403);
    });
    await page.route("**/dirlist", route => {
      directoryRequests++;
      return route.fulfill({ contentType: "text/html", body:
        '<ul class="jqueryFileTree"><li class="directory collapsed"><a rel="/demo/selected/">示例目录</a></li></ul>' });
    });
    await page.goto(`${origin}/?next=tools`);
    await page.waitForFunction(() => window.history.state?.page === "tools" && window.NasToolsUI);

    await check("请求回调一次，业务回调异常不伪装成网络失败", async () => {
      const result = await page.evaluate(async () => {
        let successCalls = 0, failureCalls = 0, thrownCalls = 0, error = "";
        const success = await ajax_post("verify_success", { value: 7 }, () => { successCalls++; }, true, false);
        const failure = await ajax_post("verify_failure", {}, () => { failureCalls++; }, true, false);
        try {
          await ajax_post("verify_success", {}, () => { thrownCalls++; throw new Error("callback-error"); }, true, false);
        } catch (caught) { error = caught.message; }
        return { successCalls, failureCalls, thrownCalls, error, success, failure };
      });
      assert.deepEqual([result.successCalls, result.failureCalls, result.thrownCalls], [1, 1, 1]);
      assert.equal(result.error, "callback-error");
      assert.equal(result.success.value, 7);
      assert.equal(result.failure.code, -99);
      assert.equal(result.failure.msg, "模拟网络失败");
    });

    await check("按钮防连点并在异常后恢复原内容和属性", async () => {
      const result = await page.evaluate(async () => {
        const button = document.createElement("button");
        button.innerHTML = "<span>保存</span>";
        button.setAttribute("aria-busy", "false");
        document.body.append(button);
        let calls = 0, reject;
        const pending = NasToolsUI.withButton(button, "保存中", () => {
          calls++;
          return new Promise((resolve, fail) => { reject = fail; });
        });
        const duplicate = NasToolsUI.withButton(button, "再次保存", () => { calls++; });
        await Promise.resolve();
        const busy = { disabled: button.disabled, text: button.textContent, aria: button.getAttribute("aria-busy") };
        reject(new Error("operation-error"));
        const outcome = await pending.then(() => "resolved", error => error.message);
        const restored = { html: button.innerHTML, disabled: button.hasAttribute("disabled"),
          aria: button.getAttribute("aria-busy"), ariaDisabled: button.getAttribute("aria-disabled") };
        await NasToolsUI.withButton(button, "测试中", () => NasToolsUI.pageAction("verify_failure", {}, undefined, true, false));
        const afterNetworkFailure = button.outerHTML;
        button.remove();
        return { same: pending === duplicate, calls, busy, outcome, restored, afterNetworkFailure };
      });
      assert.equal(result.same, true);
      assert.equal(result.calls, 1);
      assert.deepEqual(result.busy, { disabled: true, text: "保存中", aria: "true" });
      assert.equal(result.outcome, "operation-error");
      assert.deepEqual(result.restored, { html: "<span>保存</span>", disabled: false, aria: "false", ariaDisabled: null });
      assert.equal(result.afterNetworkFailure, '<button aria-busy="false"><span>保存</span></button>');
    });

    await check("备份 XHR 网络失败、403 和超时均收尾一次并恢复按钮", async () => {
      for (const mode of ["network", "forbidden", "timeout"]) {
        backupMode = mode;
        const result = await page.evaluate(async mode => {
          const NativeXHR = window.XMLHttpRequest, originalFailure = window.show_fail_modal;
          const button = document.createElement("button");
          button.textContent = "备份当前配置";
          document.body.append(button);
          let callbacks = 0, configuredTimeout;
          const failures = [];
          window.show_fail_modal = message => failures.push(message);
          if (mode === "timeout") {
            // 保留真实 XMLHttpRequest，只缩短等待，触发浏览器的真实 timeout 事件。
            window.XMLHttpRequest = class extends NativeXHR {
              send(...args) {
                configuredTimeout = this.timeout;
                this.timeout = 40;
                return super.send(...args);
              }
            };
          }
          try {
            await NasToolsUI.withButton(button, "备份中...", () => ajax_backup(() => { callbacks++; }));
            return { callbacks, failures, configuredTimeout, disabled: button.disabled,
              text: button.textContent, busy: button.getAttribute("aria-busy") };
          } finally {
            window.XMLHttpRequest = NativeXHR;
            window.show_fail_modal = originalFailure;
            button.remove();
          }
        }, mode);
        assert.equal(result.callbacks, 1, mode);
        assert.equal(result.failures.length, 1, mode);
        assert.equal(result.disabled, false, mode);
        assert.equal(result.text, "备份当前配置", mode);
        assert.equal(result.busy, null, mode);
        if (mode === "timeout") {
          assert.equal(result.configuredTimeout, 120000);
          await heldBackup.abort().catch(() => {});
        }
      }
    });

    await check("重复委托绑定只执行一次，引号参数保持数据语义", async () => {
      const dangerous = ['id\'";window.__uiExecuted=true;//', '<img src=x onerror="window.__uiExecuted=true">名字'];
      const result = await page.evaluate(async values => {
        window.__uiExecuted = false;
        const root = document.createElement("section");
        root.innerHTML = '<button data-nt-click="record"><span>执行</span></button><input type="checkbox" data-nt-click="toggle" data-nt-change="changed">';
        document.body.append(root);
        const button = root.querySelector("button"), checkbox = root.querySelector("input");
        button.dataset.ntArgs = JSON.stringify(values);
        let count = 0, toggles = 0, changes = 0, pending;
        for (let index = 0; index < 3; index++) {
          NasToolsUI.bindActions(root, { click: {
            record: element => { count++; pending = NasToolsUI.pageAction("verify_capture", { args: NasToolsUI.args(element) }, undefined, true, false); },
            toggle: () => { toggles++; },
          }, change: { changed: () => { changes++; } } });
        }
        button.querySelector("span").click();
        await pending;
        button.disabled = true;
        button.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
        checkbox.click();
        const result = { count, toggles, changes, checked: checkbox.checked, executed: window.__uiExecuted };
        root.remove();
        return result;
      }, dangerous);
      assert.deepEqual(result, { count: 1, toggles: 1, changes: 1, checked: true, executed: false });
      assert.deepEqual(captured, [{ args: dangerous }]);
    });

    await check("切页清除旧页面 timeout 和 interval", async () => {
      const result = await page.evaluate(async () => {
        let oldTimeout = 0, oldInterval = 0;
        const before = NasToolsUI.pageVersion;
        NasToolsUI.pageTimeout(() => { oldTimeout++; }, 20);
        NasToolsUI.pageInterval(() => { oldInterval++; }, 20);
        const version = NasToolsUI.beginPage();
        const fresh = await new Promise(resolve => NasToolsUI.pageTimeout(resolve, 60, "fresh"));
        return { oldTimeout, oldInterval, fresh, increased: version > before };
      });
      assert.deepEqual(result, { oldTimeout: 0, oldInterval: 0, fresh: "fresh", increased: true });
    });

    await check("目录选择委托重复初始化后仍支持动态输入且只请求一次", async () => {
      await page.evaluate(() => {
        for (let index = 0; index < 3; index++) init_filetree_element();
        const fixture = document.createElement("div");
        fixture.id = "verify-directory";
        const input = document.createElement("input");
        input.className = "filetree-folders-only";
        input.value = "/demo/";
        fixture.append(input);
        document.getElementById("page_content").append(fixture);
      });
      await page.locator("#verify-directory input").click();
      await page.locator("#verify-directory .fileTree a").waitFor();
      assert.equal(directoryRequests, 1);
      await page.locator("#verify-directory .fileTree a").first().click();
      assert.equal(await page.locator("#verify-directory input").inputValue(), "/demo/selected/");
      await page.locator("#verify-directory").evaluate(element => element.remove());
    });

    await check("真实人物页面保留带引号的 ID 和标题，不执行插入内容", async () => {
      const id = "id'\";window.__uiExecuted=true;//";
      const title = '<img src=x onerror="window.__uiExecuted=true">演员\'"';
      const target = "discovery_person?" + new URLSearchParams({ id, title, subtitle: title, type: "MOV" });
      await page.evaluate(value => { window.__uiExecuted = false; navmenu(value); }, target);
      await page.waitForFunction(value => history.state?.page === value && document.querySelector("page-person h1"), target);
      assert.equal(await page.locator("page-person").getAttribute("media-tmdbid"), id);
      assert.equal(await page.locator("page-person").getAttribute("page-title"), title);
      assert.equal(await page.locator("page-person h1 img").count(), 0);
      assert.equal(await page.evaluate(() => window.__uiExecuted), false);
      await page.getByRole("button", { name: "返回作品详情 →" }).click();
      await page.waitForFunction(() => history.state?.page?.startsWith("media_detail?"));
      const current = await page.evaluate(() => history.state.page);
      assert.equal(new URL(current, origin).searchParams.get("id"), id);
    });

    await check("真实服务页反复进入后识别一次，名称中的引号只作为数据传输", async () => {
      for (let index = 0; index < 3; index++) {
        const target = `service?verify_visit=${index}`;
        await page.evaluate(value => { navmenu(value); }, target);
        await page.waitForFunction(value => history.state?.page === value && document.getElementById("nametest_btn"), target);
      }
      await page.locator('[data-nt-click="service-open"][data-service-id="nametest"]').click();
      const name = '标题\'"<img src=x onerror="window.__uiExecuted=true">';
      await page.locator("#test_name").fill(name);
      await page.locator("#nametest_btn").click();
      await waitFor(() => nameTests.length > 0, "识别动作没有发出请求");
      await page.waitForFunction(() => !document.getElementById("nametest_btn").disabled);
      await page.waitForTimeout(100);
      assert.deepEqual(nameTests, [{ name }]);
      assert.equal(await page.locator("#test_result img").count(), 0);
      assert.equal(await page.evaluate(() => window.__uiExecuted), false);
      await page.locator("#modal-nametest [data-bs-dismiss=modal]").first().click();
      await page.waitForFunction(() => !document.querySelector("#modal-nametest.show"));
    });

    async function navigate(name) {
      const count = fragments.length;
      const target = `__ui_verify_page?name=${name}`;
      await page.evaluate(value => { navmenu(value); }, target);
      await waitFor(() => fragments.length > count, `没有收到页面请求 ${name}`);
      return { route: fragments[count], target };
    }
    async function render(fragment, marker) {
      // 迟到请求可能已被导航取消；无论取消还是丢弃，都不能写入页面或执行脚本。
      await fragment.route.fulfill({ contentType: "text/html", body:
        `<section id="verify-fragment" data-marker="${marker}"><button data-nt-click="count">记录</button></section>` +
        `<script>window.__fragmentRuns=(window.__fragmentRuns||[]).concat(${JSON.stringify(marker)});` +
        `NasToolsUI.bindActions(document.getElementById("verify-fragment"),{click:{count:()=>{window.__fragmentClicks=(window.__fragmentClicks||0)+1;}}});</script>`
      }).catch(error => {
        if (!/cancel|closed|abort|handled/i.test(error.message)) throw error;
      });
    }
    async function assertPage(fragment, marker) {
      await page.waitForFunction(({ target, marker }) => history.state?.page === target &&
        document.getElementById("verify-fragment")?.dataset.marker === marker, { target: fragment.target, marker });
    }
    await check("快速 A/B 导航拒绝迟到页面和脚本", async () => {
      await page.evaluate(() => { window.__fragmentRuns = []; });
      const a = await navigate("A"), b = await navigate("B");
      await render(b, "B-current");
      await assertPage(b, "B-current");
      await render(a, "A-stale");
      await page.waitForTimeout(100);
      await assertPage(b, "B-current");
      assert.deepEqual(await page.evaluate(() => window.__fragmentRuns), ["B-current"]);
    });

    await check("A/B/A 同地址再次进入也拒绝旧页面响应", async () => {
      await page.evaluate(() => { window.__fragmentRuns = []; });
      const oldA = await navigate("A"), b = await navigate("B");
      await render(b, "B-between");
      await assertPage(b, "B-between");
      const currentA = await navigate("A");
      await render(currentA, "A-current");
      await assertPage(currentA, "A-current");
      await render(oldA, "A-stale");
      await page.waitForTimeout(100);
      await assertPage(currentA, "A-current");
      assert.deepEqual(await page.evaluate(() => window.__fragmentRuns), ["B-between", "A-current"]);
    });

    await check("A/B/A 后业务 Promise 仍完成但旧回调不写入当前页面", async () => {
      await page.evaluate(() => {
        window.__oldCallbacks = 0;
        window.__oldAction = NasToolsUI.pageAction("verify_hold", { key: "old-A" }, () => {
          window.__oldCallbacks++;
          document.getElementById("verify-fragment").dataset.marker = "old-business-response";
        }, true, false);
      });
      await waitFor(() => heldActions.has("old-A"), "没有收到业务请求");
      const b = await navigate("B");
      await render(b, "B-business");
      await assertPage(b, "B-business");
      const a = await navigate("A");
      await render(a, "A-business");
      await assertPage(a, "A-business");
      await json(heldActions.get("old-A"), { code: 0, value: "completed" });
      const result = await page.evaluate(async () => ({ response: await window.__oldAction, callbacks: window.__oldCallbacks }));
      assert.deepEqual(result, { response: { code: 0, value: "completed" }, callbacks: 0 });
      await assertPage(a, "A-business");
    });

    await check("同页多次进入后一次点击只执行一个处理器", async () => {
      await page.evaluate(() => { window.__fragmentClicks = 0; });
      for (let index = 0; index < 3; index++) {
        const current = await navigate("repeat");
        await render(current, `repeat-${index}`);
        await assertPage(current, `repeat-${index}`);
      }
      await page.locator('#verify-fragment [data-nt-click="count"]').click();
      assert.equal(await page.evaluate(() => window.__fragmentClicks), 1);
    });
    assert.deepEqual(errors, [], "浏览器不应产生未处理异常");
    await page.screenshot({ path: path.join(output, "actions-final.png") });
    console.log(`动作验证通过：${results.length} 项；结果位于 ${output}`);
  } catch (error) {
    results.push({ name: "验证中断", passed: false, error: error.message });
    throw error;
  } finally {
    fs.writeFileSync(path.join(output, "actions-results.json"), JSON.stringify({ results, errors }, null, 2));
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
