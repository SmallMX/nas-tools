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


class DownloadBulkUITest(unittest.TestCase):
    def test_bulk_selection_only_exposes_controllable_tasks_and_preserves_names(self):
        class Markup(HTMLParser):
            def __init__(self, source):
                super().__init__()
                self.elements = []
                self.feed(source)

            def handle_starttag(self, tag, attrs):
                self.elements.append((tag, dict(attrs)))

        name = '资源 "一" & <img id="injected-bulk-name" onerror="alert(1)">'
        app = create_preview_app()
        with app.test_request_context("/downloading"):
            context = page_context("downloading")
            torrents = copy.deepcopy(context["Torrents"][:2])
            torrents[0].update(id='task-"one', title=name, name=name)
            torrents[1]["nomenu"] = True
            context.update(Torrents=torrents, DownloadCount=2)
            markup = Markup(render_template("download/downloading.html", **context))

        checkboxes = [attrs for tag, attrs in markup.elements if tag == "input" and "data-download-select" in attrs]
        self.assertEqual(1, len(checkboxes), "没有控制能力的任务不能批量选择")
        self.assertEqual('task-"one', checkboxes[0]["data-download-select"])
        self.assertEqual(f"选择任务 {name}", checkboxes[0]["aria-label"])
        self.assertFalse(any(attrs.get("id") == "injected-bulk-name" for _, attrs in markup.elements))
        actions = {attrs.get("data-nt-click") for _, attrs in markup.elements}
        self.assertIn("pause-selected-downloads", actions)
        self.assertIn("start-selected-downloads", actions)
        self.assertNotIn("remove-selected-downloads", actions)

    @unittest.skipUnless(NODE, "批量控制行为检查需要项目 CI 已使用的 Node.js")
    def test_batch_runs_serially_reports_partial_results_and_retries_only_failures(self):
        self.run_node_case("partial-retry")

    @unittest.skipUnless(NODE, "批量控制行为检查需要项目 CI 已使用的 Node.js")
    def test_stopping_or_leaving_page_does_not_send_remaining_requests(self):
        self.run_node_case("stop-and-leave")

    @unittest.skipUnless(NODE, "批量控制行为检查需要项目 CI 已使用的 Node.js")
    def test_hidden_selections_are_removed_before_the_batch_scope_is_built(self):
        source = (ROOT / "web/templates/download/downloading.html").read_text()
        names = ["filter_downloads", "run_selected_downloads"]
        functions = []
        for name in names:
            match = re.search(r"^  function " + name + r"\([^\n]*\) \{.*?^  \}", source, re.M | re.S)
            self.assertIsNotNone(match, name)
            functions.append(match.group(0))
        program = r'''
const assert = require('node:assert/strict');
const vm = require('node:vm');
let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => { input += chunk; });
process.stdin.on('end', async () => {
  const source = JSON.parse(input);
  const tasks = new Map([
    ['a', {dataset:{downloadTitle:'电影 A', downloadName:'A.mkv', downloadState:'active'}, hidden:false}],
    ['b', {dataset:{downloadTitle:'电影 B', downloadName:'B.mkv', downloadState:'paused'}, hidden:false}],
  ]);
  const elements = new Map();
  const selection = new Set(['a', 'b', 'removed']);
  const calls = [];
  const context = {tasks, selectedDownloads:selection, selectionNotice:'',
    queryInput:{value:''}, stateInput:{value:'paused'},
    document:{getElementById:id => {
      if (!elements.has(id)) elements.set(id, {textContent:'', hidden:false});
      return elements.get(id);
    }},
    update_download_selection:() => {},
    run_download_batch:async (command, ids) => calls.push({command, ids:Array.from(ids)}),
  };
  vm.createContext(context);
  vm.runInContext(source, context);
  context.filter_downloads();
  assert.deepEqual([...selection], ['b'], '隐藏项和已移除项均应取消选择');
  assert.match(context.selectionNotice, /隐藏的 1 项已取消选择/);
  assert.equal(tasks.get('a').hidden, true);
  assert.equal(tasks.get('b').hidden, false);
  await context.run_selected_downloads('pt_start');
  assert.deepEqual(calls, [{command:'pt_start', ids:['b']}]);
  process.stdout.write('selection-boundary: passed\n');
});
'''
        self.assert_node(program, "\n".join(functions), "selection-boundary: passed")

    def run_node_case(self, case):
        # 运行真实队列函数，仅替换请求、页面生命周期和呈现边界；不模拟浏览器。
        source = (ROOT / "web/templates/download/downloading.html").read_text()
        names = ["is_current_download_page", "run_download_batch", "retry_failed_downloads"]
        functions = []
        for name in names:
            match = re.search(r"^  (?:async )?function " + name + r"\([^\n]*\) \{.*?^  \}", source, re.M | re.S)
            self.assertIsNotNone(match, name)
            functions.append(match.group(0))
        program = r'''
const assert = require('node:assert/strict');
const vm = require('node:vm');
let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => { input += chunk; });
process.stdin.on('end', async () => {
  const {source, testCase} = JSON.parse(input);
  function setup() {
    const requests = [], refreshes = [], updates = [], locks = [], responders = [];
    let concurrent = 0, maxConcurrent = 0;
    const tasks = new Map(['a','b','c'].map(id => [id, {dataset:{downloadName:`资源 ${id} <img>`, downloadState:'active'}}]));
    const context = {pageVersion:4, NasToolsUI:{pageVersion:4}, tasks, batchRunning:false,
      singleRequests:0, batchStopRequested:false, batchResults:[], batchCommand:'',
      set_download_batch_locked:locked => locks.push(locked),
      render_download_batch_results:() => updates.push('render'),
      update_download_batch_result:result => updates.push(`result:${result.id}:${result.state}`),
      update_download_batch_summary:() => updates.push('summary'),
      get_torrent_info:ids => refreshes.push(Array.from(ids)),
      pageAction:(command, data, callback, async, progress) => {
        assert.equal(async, true);
        assert.equal(progress, false, '逐项请求不反复弹全局进度');
        requests.push({command, data:JSON.parse(JSON.stringify(data))});
        concurrent++;
        maxConcurrent = Math.max(maxConcurrent, concurrent);
        return new Promise((resolve,reject) => responders.push({
          resolve:value => { concurrent--; resolve(value); },
          reject:error => { concurrent--; reject(error); },
        }));
      },
    };
    vm.createContext(context);
    vm.runInContext(source, context);
    return {context,requests,refreshes,updates,locks,responders, maxConcurrent:()=>maxConcurrent};
  }
  const tick = () => new Promise(resolve => setImmediate(resolve));
  if (testCase === 'partial-retry') {
    const run = setup(), c = run.context;
    const pending = c.run_download_batch('pt_stop',['a','b','a','c']);
    assert.deepEqual(run.requests.map(r=>r.data.id), ['a']);
    await c.run_download_batch('pt_start',['b']);
    assert.equal(run.requests.length,1,'运行中不允许冲突批量请求');
    run.responders.shift().resolve({retcode:0}); await tick();
    assert.deepEqual(run.requests.map(r=>r.data.id), ['a','b']);
    run.responders.shift().resolve({retcode:1,retmsg:'下载器拒绝暂停'}); await tick();
    run.responders.shift().resolve({retcode:null}); await pending;
    assert.equal(run.maxConcurrent(),1,'请求必须串行');
    assert.deepEqual(Array.from(c.batchResults,x=>x.state), ['success','failed','failed']);
    assert.equal(c.batchResults[1].message,'下载器拒绝暂停');
    assert.deepEqual(run.refreshes,[['a','b','c']]);
    assert.equal(c.tasks.get('a').dataset.downloadState,'active','请求成功不能伪造下载器实际状态');
    const retry = c.retry_failed_downloads();
    assert.deepEqual(run.requests.map(r=>r.data.id), ['a','b','c','b']);
    run.responders.shift().resolve({retcode:'0'}); await tick();
    run.responders.shift().resolve({retcode:0}); await retry;
    assert.deepEqual(run.requests.map(r=>r.data.id), ['a','b','c','b','c']);
    assert.deepEqual(Array.from(c.batchResults,x=>x.state), ['success','success','success']);
    assert.deepEqual(run.locks,[true,false,true,false]);
  } else {
    for (const leave of [false,true]) {
      const run = setup(), c = run.context;
      const pending = c.run_download_batch('pt_start',['a','b','c']);
      const updatesBefore = run.updates.length;
      if (leave) c.NasToolsUI.pageVersion++;
      else c.batchStopRequested = true;
      run.responders.shift().resolve({retcode:0});
      await pending;
      assert.deepEqual(run.requests.map(r=>r.data.id),['a'],'停止或切页后不能发后续请求');
      assert.deepEqual(Array.from(c.batchResults,x=>x.state),['success','skipped','skipped']);
      assert.equal(c.batchRunning,false);
      if (leave) {
        assert.equal(run.updates.length,updatesBefore,'旧响应不能更新新页面');
        assert.deepEqual(run.refreshes,[]);
        assert.deepEqual(run.locks,[true],'旧页面不恢复新页控件');
        await c.run_download_batch('pt_stop',['a']);
        assert.equal(run.requests.length,1,'旧页面不能重启队列');
      } else {
        assert.deepEqual(run.refreshes,[['a']]);
        assert.deepEqual(run.locks,[true,false]);
      }
    }
  }
  process.stdout.write(testCase+': passed\n');
});
'''
        self.assert_node(program, {"source": "\n".join(functions), "testCase": case}, case + ": passed")

    def assert_node(self, program, payload, expected):
        result = subprocess.run([NODE, "-e", program], input=json.dumps(payload),
                                text=True, capture_output=True, timeout=15)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn(expected, result.stdout)


if __name__ == "__main__":
    unittest.main()
