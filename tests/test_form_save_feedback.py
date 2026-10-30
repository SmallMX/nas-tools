import json
import re
import shutil
import subprocess
import unittest
from html.parser import HTMLParser
from pathlib import Path

from scripts.preview_ui import create_preview_app


ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")


class FormMarkup(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.tracked = []
        self.status_count = 0
        self.feed(source)

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if attrs.get("data-unsaved-label"):
            self.tracked.append(attrs)
        if "data-save-status" in attrs:
            self.status_count += 1
            assert attrs.get("role") == "status"
            assert attrs.get("aria-live") == "polite"


class FormSaveFeedbackTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = create_preview_app().test_client()

    def function(self, path, name):
        source = self.client.get(path).get_data(as_text=True)
        match = re.search(r"^  function " + re.escape(name) + r"\([^\n]*\)\s*\{.*?^  \}",
                          source, re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(match, name)
        return match.group(0)

    def run_node(self, program, payload):
        result = subprocess.run([NODE, "-e", program], input=json.dumps(payload),
                                text=True, capture_output=True, cwd=ROOT)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_long_forms_have_independent_unsaved_scope_and_status(self):
        expected = {
            "/basic": {"basic_system", "modal-user-script"},
            "/media_setting": {"basic_media", "modal-release-groups"},
            "/service_setting": {"basic_service", "cookiecloud_settings"},
            "/security_setting": {"security"},
            "/laboratory_setting": {"laboratory"},
            "/downloader": {"modal-qbittorrent", "modal-transmission", "modal-downloaddir"},
            "/tools/site-signin": {"site_signin_settings"},
        }
        for route, scopes in expected.items():
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertEqual(200, response.status_code)
                markup = FormMarkup(response.get_data(as_text=True))
                self.assertEqual(scopes, {attrs["id"] for attrs in markup.tracked})
                self.assertEqual(len(scopes), markup.status_count)
                for attrs in markup.tracked:
                    self.assertNotEqual("false", attrs.get("data-bs-keyboard"))

    @unittest.skipUnless(NODE, "表单反馈行为检查需要 Node.js")
    def test_basic_save_only_marks_the_submitted_snapshot_on_success(self):
        program = r'''
const assert = require('node:assert/strict'), vm = require('node:vm');
let input=''; process.stdin.on('data', d=>input+=d); process.stdin.on('end', async()=>{
 const source=JSON.parse(input);
 for (const response of [{code:0}, {code:1,msg:'保存被拒绝'}, {code:-99,msg:'网络中断'}]) {
  for (const edited of [false,true]) {
   let current='提交时的字段', saved='原配置', respond;
   const snapshots=[], statuses=[], requests=[];
   const tracker={capture:()=>current, markSaved:s=>{snapshots.push(s);saved=s;},setStatus:(...v)=>statuses.push(v)};
   const context={formTrackers:new Map([['basic_system',tracker]]),
    input_select_GetVal:()=>({'app.domain':'https://example.test/'}),
    document:{getElementById:id=>({id})},
    NasToolsUI:{withButton:(b,t,op)=>Promise.resolve().then(op)},
    pageAction:(command,data,callback)=>new Promise(resolve=>{
      requests.push({command,data});respond=()=>{callback(response);resolve(response);};
    })};
   vm.createContext(context); vm.runInContext(source,context);
   const pending=context.save_basic_config('basic_system'); await Promise.resolve();
   assert.equal(snapshots.length,0,'响应前不得清除dirty');
   if(edited) current='请求期间的新输入';
   respond(); await pending;
   assert.equal(requests[0].command,'update_config');
   assert.equal(requests[0].data['app.domain'],'https://example.test/');
   if(response.code===0){assert.deepEqual(snapshots,['提交时的字段']);assert.equal(saved,'提交时的字段');}
   else{assert.deepEqual(snapshots,[]);assert.equal(statuses.at(-1)[1],'error');assert.equal(statuses.at(-1)[0],response.msg);}
   assert.equal(current,edited?'请求期间的新输入':'提交时的字段','响应不得回写输入');
  }
 }
});'''
        self.run_node(program, self.function("/basic", "save_basic_config"))

    @unittest.skipUnless(NODE, "表单反馈行为检查需要 Node.js")
    def test_cookiecloud_response_does_not_clear_newer_input(self):
        program = r'''
const assert=require('node:assert/strict'),vm=require('node:vm');
let input='';process.stdin.on('data',d=>input+=d);process.stdin.on('end',async()=>{
 const source=JSON.parse(input);
 for(const edited of [false,true]) {
  const field=(value,defaultValue=value)=>({value,defaultValue,dataset:{configured:'true'},classList:{toggle(){}}});
  const fields={cookiecloud_server:field('https://cloud.example.test/','https://cloud.example.test'),
   cookiecloud_key:field('提交的 KEY',''),cookiecloud_password:field('提交的密码',''),cookiecloud_interval:field('90','180'),cookiecloud_schedule_status:{textContent:''}};
  const capture=()=>JSON.stringify(['cookiecloud_server','cookiecloud_key','cookiecloud_password','cookiecloud_interval'].map(k=>fields[k].value));
  const submitted=capture(),snapshots=[];let respond;
  const tracker={capture,markSaved:s=>snapshots.push(s),setStatus(){}};
  const context={URL,formTrackers:new Map([['cookiecloud_settings',tracker]]),document:{getElementById:id=>fields[id]},
   NasToolsUI:{withButton:(b,t,op)=>Promise.resolve().then(op)},
   pageAction:(command,data,callback)=>new Promise(resolve=>{respond=()=>{callback({code:0});resolve();};})};
  vm.createContext(context);vm.runInContext(source,context);
  const pending=context.save_cookiecloud_config();await Promise.resolve();
  if(edited){fields.cookiecloud_server.value='https://next.example.test';fields.cookiecloud_key.value='下一次 KEY';fields.cookiecloud_password.value='下一次密码';fields.cookiecloud_interval.value='120';}
  respond();await pending;
  if(edited){
   assert.equal(fields.cookiecloud_server.value,'https://next.example.test');assert.equal(fields.cookiecloud_key.value,'下一次 KEY');
   assert.equal(fields.cookiecloud_password.value,'下一次密码');assert.equal(fields.cookiecloud_interval.value,'120');
   assert.deepEqual(snapshots,[submitted]);assert.notEqual(snapshots[0],capture());
  }else{
   assert.equal(fields.cookiecloud_server.value,'https://cloud.example.test');assert.equal(fields.cookiecloud_key.value,'');assert.equal(fields.cookiecloud_password.value,'');
   assert.deepEqual(snapshots,[capture()]);
  }
  assert.equal(fields.cookiecloud_server.defaultValue,'https://cloud.example.test');assert.equal(fields.cookiecloud_interval.defaultValue,'90');
 }
});'''
        self.run_node(program, self.function("/service_setting", "save_cookiecloud_config"))

    @unittest.skipUnless(NODE, "表单反馈行为检查需要 Node.js")
    def test_connection_test_requires_saved_fields_and_never_marks_a_save(self):
        program = r'''
const assert=require('node:assert/strict'),vm=require('node:vm');
let input='';process.stdin.on('data',d=>input+=d);process.stdin.on('end',async()=>{
 const source=JSON.parse(input);
 for(const dirty of [false,true]) {
  const calls=[],messages=[];
  const tracker={isDirty:()=>dirty,setStatus:(...v)=>messages.push(v),markSaved:()=>assert.fail('测试不能记为保存')};
  const context={formTrackers:new Map([['modal-qbittorrent',tracker]]),document:{getElementById:id=>({id})},
   NasToolsUI:{withButton:(b,t,op)=>Promise.resolve().then(op)},
   pageAction:(cmd,data,callback)=>{calls.push({cmd,data});callback({code:0});return Promise.resolve({code:0});}};
  vm.createContext(context);vm.runInContext(source,context);
  await context.test_downloader_config('qbittorrent');
  if(dirty){assert.equal(calls.length,0);assert.match(messages.at(-1)[0],/先保存/);}
  else{assert.equal(calls.length,1);assert.equal(calls[0].cmd,'test_connection');assert.equal(calls[0].data.command,'qbittorrent');assert.match(messages.at(-1)[0],/已保存的连接测试成功/);}
 }
});'''
        self.run_node(program, self.function("/downloader", "test_downloader_config"))


if __name__ == "__main__":
    unittest.main()
