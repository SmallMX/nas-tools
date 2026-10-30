import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")


@unittest.skipUnless(NODE, "异步导航回归需要项目 CI 已使用的 Node.js")
class UINavigationGuardTest(unittest.TestCase):
    def source_function(self, name, asynchronous=False):
        source = (ROOT / "web/templates/navigation.html").read_text()
        prefix = "async " if asynchronous else ""
        match = re.search(
            rf"^  {prefix}function {name}\([^\n]*\)\s*\{{.*?^  \}}",
            source, re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(match, f"未找到实际导航函数 {name}")
        return match.group(0)

    def run_behavior(self, source, behavior):
        # 直接执行实际函数；历史记录、确认 Promise 和片段加载是测试边界。
        program = r'''
const assert = require("node:assert/strict");
const vm = require("node:vm");
let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", chunk => { input += chunk; });
process.stdin.on("end", async () => {
  const {source, behavior} = JSON.parse(input);
  const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
  await new AsyncFunction("assert", "vm", "source", behavior)(assert, vm, source);
  process.stdout.write("navigation-guard: passed\n");
});
'''
        result = subprocess.run(
            [NODE, "-e", program], input=json.dumps({"source": source, "behavior": behavior}),
            text=True, capture_output=True, timeout=15,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("navigation-guard: passed", result.stdout)

    def test_form_history_never_reads_or_stores_form_html(self):
        self.run_behavior(self.source_function("window_history"), r'''
let hasForm = true, reads = 0;
let pageHTML = '<input type="password" value="do-not-store-this-draft">';
const historyCalls = [];
const history = {
  state: {extra: {filter: "active"}},
  pushState(state) { this.state = state; historyCalls.push({method: "push", state: JSON.parse(JSON.stringify(state))}); },
  replaceState(state) { this.state = state; historyCalls.push({method: "replace", state: JSON.parse(JSON.stringify(state))}); },
};
const context = {
  CURRENT_PAGE_URI: "basic", CURRENT_HISTORY_INDEX: 7, CURRENT_HISTORY_STATE: history.state,
  window: {history, scrollY: 120}, sessionStorage: {CurrentPage: "2"},
  document: {title: "基础设置", querySelector(selector) {
    assert.equal(selector, "#page_content [data-unsaved-label]");
    return hasForm ? {} : null;
  }},
  $: selector => {
    assert.equal(selector, "#page_content");
    return {html() { reads++; return pageHTML; }};
  },
};
vm.createContext(context);
vm.runInContext(source, context);
context.window_history();
context.window_history(true, {section: "general"});
assert.equal(reads, 0, "表单历史不应读取可能含凭据和草稿的HTML");
assert.deepEqual(historyCalls.map(call => call.method), ["replace", "push"]);
for (const {state} of historyCalls) {
  assert.equal(state.reloadForm, true);
  assert.equal(state.html, "");
  assert.equal(state.page, "basic");
  assert.equal(state.scroll, 120);
  assert.equal(state.CurrentPage, "2");
  assert.ok(!JSON.stringify(state).includes("do-not-store-this-draft"));
}
assert.equal(historyCalls[0].state.ntIndex, 7);
assert.deepEqual(historyCalls[0].state.extra, {filter: "active"});
assert.equal(historyCalls[1].state.ntIndex, 8);
assert.deepEqual(historyCalls[1].state.extra, {section: "general"});

hasForm = false;
pageHTML = '<main>公开的任务列表</main>';
context.CURRENT_PAGE_URI = "downloading";
context.window_history();
assert.equal(reads, 1, "非表单页面保留原有历史缓存能力");
assert.equal(historyCalls.at(-1).state.reloadForm, false);
assert.equal(historyCalls.at(-1).state.html, pageHTML);
''')

    def test_navigation_waits_for_confirmation_and_only_latest_intent_loads(self):
        self.run_behavior(self.source_function("navmenu", asynchronous=True), r'''
const decisions = [], loads = [];
const context = {
  page_navigation_intent: 0,
  NasToolsUI: {confirmLeave: () => new Promise(resolve => { decisions.push(resolve); })},
  load_page_fragment: (page, newflag) => { loads.push({page, newflag}); return "loaded:" + page; },
};
vm.createContext(context);
vm.runInContext(source, context);
const cancelled = context.navmenu("service_setting");
assert.equal(loads.length, 0, "等待确认时不能加载或替换当前页面");
decisions.shift()(false);
await cancelled;
assert.equal(loads.length, 0, "取消离开保留当前页面");

const older = context.navmenu("site?site_name=中文&site_id=7");
const latest = context.navmenu("downloading", true);
assert.equal(loads.length, 0);
const resolveOlder = decisions.shift(), resolveLatest = decisions.shift();
resolveLatest(true);
assert.equal(await latest, "loaded:downloading");
resolveOlder(true);
await older;
assert.deepEqual(loads, [{page: "downloading", newflag: true}], "旧确认晚到不能覆盖较新的导航意图");

loads.length = 0;
const first = context.navmenu("basic");
const second = context.navmenu("media_setting");
decisions.shift()(true);
await first;
assert.equal(loads.length, 0, "较新的确认尚未决定时，也不能先执行旧导航");
decisions.shift()(false);
await second;
assert.equal(loads.length, 0);
''')

    def test_history_form_return_reloads_saved_data_and_cancel_restores_position(self):
        source = (ROOT / "web/templates/navigation.html").read_text()
        match = re.search(
            r"window\.addEventListener\('popstate', (async function\(e\) \{.*?^    \})\);",
            source, re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(match, "未找到实际 popstate 处理函数")
        self.run_behavior("historyHandler = " + match.group(1), r'''
const loads = [], historyMoves = [];
let allowed = true, confirmationCount = 0;
const context = {
  restoring_history_position: false, page_navigation_intent: 0,
  CURRENT_HISTORY_INDEX: 6, CURRENT_HISTORY_STATE: {page: "basic", ntIndex: 6}, CURRENT_PAGE_URI: "basic",
  NasToolsUI: {confirmLeave: async () => { confirmationCount++; return allowed; }},
  load_page_fragment: (...args) => loads.push(args),
  document: {title: "当前设置"},
  window: {history: {
    go: offset => historyMoves.push(offset),
    pushState() { throw new Error("有索引的历史应恢复位置，而非新增历史"); },
  }},
  begin_page_navigation() { throw new Error("表单恢复必须交给片段加载器，不得恢复缓存HTML"); },
  $() { throw new Error("表单历史不能调用html恢复草稿"); },
};
vm.createContext(context);
vm.runInContext(source, context);
const formState = {page: "service_setting", title: "服务设置", ntIndex: 4, scroll: 360,
                   reloadForm: true, html: '<input value="stale-private-draft">'};
await context.historyHandler({state: formState});
assert.deepEqual(loads, [["service_setting", true, 360]]);
assert.equal(context.document.title, "服务设置");
assert.equal(context.CURRENT_HISTORY_INDEX, 4);

loads.length = 0;
allowed = false;
await context.historyHandler({state: {...formState, ntIndex: 3}});
assert.equal(loads.length, 0);
assert.deepEqual(historyMoves, [1]);
assert.equal(context.restoring_history_position, true);
const previousConfirmations = confirmationCount;
await context.historyHandler({state: formState});
assert.equal(confirmationCount, previousConfirmations, "还原历史位置不应再次弹出离开确认");
assert.equal(context.restoring_history_position, false);
''')


if __name__ == "__main__":
    unittest.main()
