import json
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")


@unittest.skipUnless(NODE, "表单状态回归需要项目 CI 已使用的 Node.js")
class UIFormStateTest(unittest.TestCase):
    def run_behavior(self, behavior):
        # 执行完整生产模块，仅替换 DOM 事件、状态输出、离开确认和存储边界。
        program = r'''
const assert = require("node:assert/strict");
const vm = require("node:vm");
let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", chunk => { input += chunk; });
process.stdin.on("end", async () => {
  const {source, behavior} = JSON.parse(input);
  const windowEvents = new Map();
  const confirmations = [];
  let allowLeave = false;
  const window = {
    addEventListener(name, listener) { windowEvents.set(name, listener); },
    confirm() { throw new Error("应用内离开确认不能使用浏览器原生 confirm"); },
    show_unsaved_dialog(message, label) {
      confirmations.push({message, label});
      return Promise.resolve(allowLeave);
    },
    setTimeout, clearTimeout, setInterval, clearInterval,
  };
  const storage = new Proxy({}, {
    get() { throw new Error("表单值不得访问浏览器存储"); },
    set() { throw new Error("表单值不得写入浏览器存储"); },
  });
  window.localStorage = window.sessionStorage = storage;
  const context = {window, localStorage: storage, sessionStorage: storage};
  vm.createContext(context);
  vm.runInContext(source, context, {filename: "ui-actions.js"});
  const ui = window.NasToolsUI;

  function makeRoot() {
    const attributes = new Map();
    const listeners = new Map();
    return {
      dataset: {}, isConnected: true,
      getAttribute: key => attributes.get(key) ?? null,
      setAttribute: (key, value) => attributes.set(key, value),
      addEventListener(name, handler) {
        if (!listeners.has(name)) listeners.set(name, new Set());
        listeners.get(name).add(handler);
      },
      removeEventListener(name, handler) { listeners.get(name)?.delete(handler); },
      emit(name) { for (const handler of listeners.get(name) || []) handler({type: name}); },
      listenerCount(name) { return listeners.get(name)?.size || 0; },
      contains(other) { return this === other; },
    };
  }
  function makeStatus() {
    const classes = new Set();
    return {
      textContent: "", dataset: {},
      classList: {toggle(name, active) { active ? classes.add(name) : classes.delete(name); }},
      hasClass: name => classes.has(name),
    };
  }
  function beforeUnload() {
    const event = {prevented: false, preventDefault() { this.prevented = true; }};
    assert.ok(windowEvents.has("beforeunload"), "生产模块需要注册关闭页面的提醒");
    windowEvents.get("beforeunload")(event);
    return event;
  }
  const setAllowLeave = value => { allowLeave = value; };
  const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
  await new AsyncFunction("assert", "ui", "makeRoot", "makeStatus", "beforeUnload", "confirmations", "setAllowLeave", behavior)(
    assert, ui, makeRoot, makeStatus, beforeUnload, confirmations, setAllowLeave);
  process.stdout.write("form-state: passed\n");
});
'''
        result = subprocess.run(
            [NODE, "-e", program],
            input=json.dumps({
                "source": (ROOT / "web/static/js/ui-actions.js").read_text(),
                "behavior": behavior,
            }),
            text=True, capture_output=True, timeout=15,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("form-state: passed", result.stdout)

    def test_save_failure_preserves_dirty_values_and_success_clears_only_its_scope(self):
        self.run_behavior(r'''
const firstRoot = makeRoot(), secondRoot = makeRoot();
const firstStatus = makeStatus(), secondStatus = makeStatus();
const firstValues = {name: "基础配置", password: "仅保留内存中的输入"};
const secondValues = {enabled: false};
const first = ui.trackForm(firstRoot, {label: "基础设置", status: firstStatus, read: () => firstValues});
const second = ui.trackForm(secondRoot, {label: "通知设置", status: secondStatus, read: () => secondValues});
assert.equal(typeof first.capture(), "string");
assert.equal(first.isDirty(), false);
assert.equal(second.isDirty(), false);
assert.equal(firstRoot.dataset.unsaved, "false");
firstValues.name = '已修改 "中文" <img>';
firstRoot.emit("input");
assert.equal(first.isDirty(), true);
assert.equal(firstRoot.dataset.unsaved, "true");
assert.equal(firstStatus.dataset.saveState, "dirty");
first.setStatus("连接失败，请重试", "error");
assert.equal(first.isDirty(), true, "保存失败不能把当前值当成基准");
assert.equal(firstStatus.hasClass("text-danger"), true);
assert.equal(JSON.parse(first.capture()).name, firstValues.name);
secondValues.enabled = true;
secondRoot.emit("change");
first.markSaved(first.capture());
assert.equal(first.isDirty(), false);
assert.equal(firstRoot.dataset.unsaved, "false");
assert.equal(firstStatus.textContent, "已保存");
assert.equal(second.isDirty(), true, "保存一个分区不能清除另一个分区的更改");
assert.equal(ui.dirtyForms(firstRoot).length, 0);
assert.equal(ui.dirtyForms(secondRoot).length, 1);
assert.equal(await ui.confirmLeave(), false);
assert.match(confirmations.at(-1).message, /通知设置/);
assert.doesNotMatch(confirmations.at(-1).message, /基础设置/);
''')

    def test_response_marks_submitted_snapshot_without_discarding_new_edits(self):
        self.run_behavior(r'''
const root = makeRoot(), status = makeStatus();
const values = {directory: "/downloads/original", enabled: false};
const tracker = ui.trackForm(root, {label: "下载设置", status, read: () => values});
values.directory = "/downloads/submitted";
root.emit("input");
const submitted = tracker.capture();
values.directory = "/downloads/edited-while-saving";
values.enabled = true;
root.emit("change");
tracker.markSaved(submitted);
assert.equal(tracker.isDirty(), true, "响应到达时的新编辑仍需保存");
assert.equal(status.dataset.saveState, "dirty");
assert.match(status.textContent, /仍有未保存更改/);
assert.equal(JSON.parse(tracker.capture()).directory, "/downloads/edited-while-saving");
values.directory = "/downloads/submitted";
values.enabled = false;
root.emit("input");
assert.equal(tracker.isDirty(), false, "服务端已保存的提交快照才是新基准");
assert.equal(status.textContent, "已保存");
''')

    def test_leave_confirmation_and_beforeunload_follow_current_dirty_state(self):
        self.run_behavior(r'''
const root = makeRoot(), values = {query: "原值"};
const tracker = ui.trackForm(root, {label: "服务设置", read: () => values});
const cleanResult = ui.confirmLeave();
assert.equal(typeof cleanResult.then, "function", "干净页面也使用一致的异步确认契约");
assert.equal(await cleanResult, true);
assert.equal(confirmations.length, 0, "干净页面不应打断导航");
assert.equal(beforeUnload().prevented, false);
values.query = "修改后";
root.emit("input");
setAllowLeave(false);
const dirtyResult = ui.confirmLeave();
assert.equal(typeof dirtyResult.then, "function");
assert.equal(await dirtyResult, false);
assert.equal(tracker.isDirty(), true, "取消离开后保留更改");
assert.match(confirmations[0].message, /服务设置/);
assert.equal(confirmations[0].label, "放弃修改并离开");
const event = beforeUnload();
assert.equal(event.prevented, true);
assert.equal(event.returnValue, "");
setAllowLeave(true);
assert.equal(await ui.confirmLeave(), true);
assert.equal(tracker.isDirty(), true, "同意离开只是许可，尚未发生导航时不能清除输入");
tracker.markSaved(tracker.capture());
assert.equal(beforeUnload().prevented, false);
assert.equal(await ui.confirmLeave(), true);
assert.equal(confirmations.length, 2);
''')

    def test_retracking_and_page_change_release_previous_listeners_and_guards(self):
        self.run_behavior(r'''
const root = makeRoot(), status = makeStatus(), values = {text: "初始"};
ui.trackForm(root, {label: "旧分区", status, read: () => values});
values.text = "服务端重新载入后的值";
const current = ui.trackForm(root, {label: "当前分区", status, read: () => values});
assert.equal(root.listenerCount("input"), 1, "重新初始化同一根元素不能累积监听器");
assert.equal(root.listenerCount("change"), 1);
assert.equal(current.isDirty(), false);
values.text = "未保存";
root.emit("input");
assert.equal(ui.dirtyForms().length, 1);
assert.equal(beforeUnload().prevented, true);
const version = ui.pageVersion;
assert.equal(ui.beginPage(), version + 1);
assert.equal(root.listenerCount("input"), 0);
assert.equal(root.listenerCount("change"), 0);
assert.equal(ui.dirtyForms().length, 0);
assert.equal(beforeUnload().prevented, false);
assert.equal(await ui.confirmLeave(), true);
assert.equal(confirmations.length, 0);
const lastStatus = status.textContent;
values.text = "旧页迟到事件";
root.emit("input");
assert.equal(status.textContent, lastStatus);

const detached = makeRoot(), detachedValues = {text: "原值"};
ui.trackForm(detached, {read: () => detachedValues});
detachedValues.text = "旧值";
detached.isConnected = false;
assert.equal(beforeUnload().prevented, false, "已离开DOM的表单不能阻拦当前页面");
assert.equal(detached.listenerCount("input"), 0);
''')


if __name__ == "__main__":
    unittest.main()
