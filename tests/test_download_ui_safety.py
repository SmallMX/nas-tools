import copy
import json
import re
import shutil
import subprocess
import unittest
from html.parser import HTMLParser
from pathlib import Path

from flask import render_template

from scripts.preview_ui import create_preview_app, page_context


ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")


class Markup(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.elements = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))

    handle_startendtag = handle_starttag


class DownloadUISafetyTest(unittest.TestCase):
    def test_search_resource_metadata_survives_html_attributes_and_has_visible_summary_target(self):
        title = '资源 "修订版" & <img id="injected-resource" onerror="alert(1)">'
        site = '站点\' & "二"'
        size = '24.6 GB "原盘" <img id="injected-size">'
        codec = 'H265 "10bit"'
        effect = 'HDR <img id="injected-quality">'
        app = create_preview_app()
        with app.test_request_context("/search"):
            context = page_context("search")
            context["Results"] = copy.deepcopy(context["Results"])
            item = next(iter(context["Results"].values()))
            group = next(iter(item["torrent_dict"][0][1].values()))
            torrents = next(iter(group["group_torrents"].values()))["torrent_list"]
            torrents[0].update(torrent_name=title, site=site, size=size,
                               video_encode=codec, reseffect=effect)
            source = render_template("search.html", **context)
            shell = render_template("navigation.html", **page_context(""))

        markup = Markup(source)
        action = next(attrs for _, attrs in markup.elements
                      if attrs.get("data-nt-click") == "search-download"
                      and attrs.get("data-torrent-id") == torrents[0]["id"])
        self.assertEqual(f"【{site}】{title}", action["data-torrent-title"])
        self.assertEqual(site, action["data-torrent-site"])
        self.assertEqual(size, action["data-torrent-size"])
        self.assertEqual(f"{codec} / {effect}", action["data-torrent-quality"])
        self.assertFalse(any(attrs.get("id") in {"injected-resource", "injected-size", "injected-quality"}
                             for _, attrs in markup.elements))
        self.assertFalse(any(name.lower().startswith("on")
                             for _, attrs in markup.elements for name in attrs))

        shell_markup = Markup(shell)
        summary = [(tag, attrs) for tag, attrs in shell_markup.elements
                   if attrs.get("id") == "search_download_message"]
        self.assertEqual(1, len(summary), "下载身份摘要需要真实且唯一的渲染目标")
        self.assertNotEqual("input", summary[0][0])
        self.assertNotIn("hidden", summary[0][1])
        modal = next(attrs for _, attrs in shell_markup.elements
                     if attrs.get("id") == "modal-search-download")
        self.assertIn("search_download_message", modal.get("aria-describedby", "").split())

    def test_task_names_remain_data_in_delete_confirmation_arguments(self):
        # 名称会进入确认框与筛选数据；引号和 HTML 式内容不能打断属性边界。
        title = '片名 "特别版" & <img id="injected-title" src=x onerror="alert(1)">'
        filename = '原文件名\' </script><script id="injected-name">alert(1)</script>.mkv'
        app = create_preview_app()
        with app.test_request_context("/downloading"):
            context = page_context("downloading")
            torrent = copy.deepcopy(context["Torrents"][0])
            torrent.update(id="sample-task", title=title, name=filename)
            context.update(Torrents=[torrent], DownloadCount=1)
            source = render_template("download/downloading.html", **context)

        markup = Markup(source)
        controls = [attrs for _, attrs in markup.elements
                    if attrs.get("data-nt-click") == "remove-download"]
        self.assertEqual(1, len(controls))
        self.assertEqual(["sample-task", filename], json.loads(controls[0]["data-nt-args"]))
        rows = [attrs for _, attrs in markup.elements
                if attrs.get("data-download-id") == "sample-task"]
        self.assertEqual(1, len(rows))
        self.assertEqual(title, rows[0]["data-download-title"])
        self.assertEqual(filename, rows[0]["data-download-name"])
        self.assertFalse(any(attrs.get("id") in {"injected-title", "injected-name"}
                             for _, attrs in markup.elements))
        self.assertFalse(any(name.lower().startswith("on")
                             for _, attrs in markup.elements for name in attrs))

    @unittest.skipUnless(NODE, "下载反馈行为检查需要项目 CI 已使用的 Node.js")
    def test_download_feedback_preserves_selection_and_ignores_stale_responses(self):
        source = (ROOT / "web/templates/navigation.html").read_text()
        match = re.search(r"^  function download_link\([^\n]*\) \{.*?^  \}",
                          source, re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(match, "未找到资源下载处理函数")
        program = r'''
const assert = require("node:assert/strict");
const vm = require("node:vm");
let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", chunk => { input += chunk; });
process.stdin.on("end", async () => {
  const source = JSON.parse(input);
  const name = '【站点 "一"】资源 <img> & 特别版';
  for (const response of [
    {retcode: 0},
    {retcode: 1, retmsg: "下载器拒绝添加", msg: "不能覆盖具体错误"},
    {code: -99, msg: "网络暂时不可达"},
  ]) {
    for (const stale of [false, true]) {
      const values = {
        "#search_download_id": "0007",
        "#search_download_name": name,
        "#search_download_dir": '/downloads/中文 & "原盘"',
        "#search_download_setting": "site-preset-02",
      };
      const error = {text: "旧错误", hidden: false};
      const requests = [], successes = [], modalActions = [];
      let respond;
      const context = {
        downloadModalVersion: 7,
        show_download_success: value => successes.push(value),
        $: selector => ({
          val: () => {
            assert.ok(Object.hasOwn(values, selector), selector);
            return values[selector];
          },
          text(value) {
            assert.equal(selector, "#search_download_error");
            error.text = value;
            return this;
          },
          prop(key, value) {
            assert.equal(selector, "#search_download_error");
            assert.equal(key, "hidden");
            error.hidden = value;
            return this;
          },
          modal(action) { modalActions.push({selector, action}); return this; },
        }),
        NasToolsUI: {
          withButton: (target, busyText, action) => Promise.resolve().then(action),
          pageAction: (command, data, callback) => {
            requests.push({command, data: JSON.parse(JSON.stringify(data))});
            return new Promise(resolve => { respond = () => { callback(response); resolve(response); }; });
          },
        },
      };
      vm.createContext(context);
      vm.runInContext(source, context);
      const pending = context.download_link();
      await Promise.resolve();
      assert.deepEqual(requests, [{command: "download", data: {
        id: "0007", dir: values["#search_download_dir"], setting: "site-preset-02",
      }}], "请求应保留资源、目录与预设的原始值");
      assert.equal(error.hidden, true, "新请求清除上次错误状态");
      assert.equal(successes.length, 0);
      assert.deepEqual(modalActions, [], "等待结果时保留确认弹层");
      if (stale) {
        context.downloadModalVersion++;
        values["#search_download_name"] = "下一条资源";
        error.text = "新弹层自己的提示";
        error.hidden = false;
      }
      respond();
      await pending;
      assert.deepEqual(modalActions, [], "失败或旧响应不得关闭弹层；成功交由统一反馈处理");
      if (stale) {
        assert.deepEqual(successes, []);
        assert.deepEqual(error, {text: "新弹层自己的提示", hidden: false});
      } else if (response.retcode === 0) {
        assert.deepEqual(successes, [name], "成功反馈传递原始资源名称");
        assert.equal(error.hidden, true);
      } else {
        assert.deepEqual(successes, []);
        assert.equal(error.hidden, false);
        assert.ok(error.text.includes(response.retmsg || response.msg));
      }
    }
  }
  process.stdout.write("download-feedback: passed\n");
});
'''
        result = subprocess.run([NODE, "-e", program], input=json.dumps(match.group(0)),
                                text=True, capture_output=True, timeout=15)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("download-feedback: passed", result.stdout)

    @unittest.skipUnless(NODE, "删除确认行为检查需要项目 CI 已使用的 Node.js")
    def test_delete_request_waits_for_confirmation_and_removes_row_only_on_success(self):
        # 执行实际函数，只替换确认框、请求和反馈边界；不重写删除逻辑或模拟浏览器。
        source = (ROOT / "web/templates/download/downloading.html").read_text()
        match = re.search(r"^  function remove_pt_download\([^\n]*\) \{.*?^  \}",
                          source, re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(match, "未找到下载任务删除处理函数")
        program = r'''
const assert = require("node:assert/strict");
const vm = require("node:vm");
let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", chunk => { input += chunk; });
process.stdin.on("end", async () => {
  const source = JSON.parse(input);
  for (const response of [
    {retcode: 0, id: "sample-task"},
    {retcode: 1, id: "sample-task", retmsg: "下载器拒绝删除"},
  ]) {
    const calls = [], errors = [], confirmations = [];
    let removals = 0, filters = 0, confirmationClosed = 0;
    const count = {textContent: "1"};
    const tasks = new Map([["sample-task", {remove() { removals++; }}]]);
    const context = {
      pageVersion: 4,
      tasks,
      filter_downloads: () => { filters++; },
      show_confirm_modal: (message, callback, label) => confirmations.push({message, callback, label}),
      hide_confirm_modal: () => { confirmationClosed++; },
      show_fail_modal: message => errors.push(message),
      pageAction: async (command, data, callback) => {
        calls.push({command, data: JSON.parse(JSON.stringify(data))});
        callback(response);
        return response;
      },
      NasToolsUI: {pageVersion: 4, withButton: (target, busyText, action) => Promise.resolve().then(action)},
      document: {querySelector: () => count},
    };
    vm.createContext(context);
    vm.runInContext(source, context);
    context.remove_pt_download("sample-task", '原文件名 "特别版" <img>');
    await Promise.resolve();
    assert.equal(calls.length, 0, "打开确认框或取消时不能删除");
    assert.equal(removals, 0);
    assert.equal(confirmations.length, 1);
    assert.match(confirmations[0].message, /原文件名/);
    assert.match(confirmations[0].message, /文件/);
    assert.equal(confirmations[0].label, "删除任务及文件");
    await confirmations[0].callback();
    assert.deepEqual(calls, [{command: "pt_remove", data: {id: "sample-task"}}]);
    assert.equal(confirmationClosed, 1);
    assert.equal(removals, response.retcode === 0 ? 1 : 0);
    assert.equal(tasks.has("sample-task"), response.retcode !== 0);
    assert.equal(filters, response.retcode === 0 ? 1 : 0);
    if (response.retcode === 0) assert.equal(errors.length, 0);
    else assert.equal(errors.length, 1, "删除失败必须给出反馈，不能移除任务行");

    // 用户在确认前离开任务页，旧确认框不能删除另一个页面上下文中的任务。
    calls.length = 0;
    confirmations.length = 0;
    tasks.set("sample-task", {remove() { removals++; }});
    context.remove_pt_download("sample-task", "原文件名");
    context.NasToolsUI.pageVersion = 5;
    await confirmations[0].callback();
    assert.equal(calls.length, 0, "切页后旧确认不得发送删除请求");
  }
  process.stdout.write("confirmation-boundary: passed\n");
});
'''
        result = subprocess.run([NODE, "-e", program], input=json.dumps(match.group(0)),
                                text=True, capture_output=True, timeout=15)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("confirmation-boundary: passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
