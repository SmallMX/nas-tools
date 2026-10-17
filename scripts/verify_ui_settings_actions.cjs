/* 运行：NODE_PATH=/path/to/node_modules node scripts/verify_ui_settings_actions.cjs
 * 使用本地只读 preview_ui.py 的真实模板；所有写请求在浏览器侧拦截。
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {chromium} = require('playwright');
const origin = new URL(process.env.UI_PREVIEW_URL || 'http://127.0.0.1:5108').origin;
if (!['127.0.0.1', 'localhost'].includes(new URL(origin).hostname)) {
  throw new Error('仅允许本地只读预览。');
}
const chrome = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const deferred = () => {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return {promise, resolve};
};

(async () => {
  const browser = await chromium.launch({headless: true, executablePath: process.env.CHROME_PATH || (fs.existsSync(chrome) ? chrome : undefined)});
  const context = await browser.newContext({viewport: {width: 1440, height: 1000}});
  const calls = [];
  const responders = new Map();
  const errors = [];
  let checked = 0;
  const record = name => { checked++; console.log(`PASS ${name}`); };
  const waitFor = async predicate => {
    const deadline = Date.now() + 5000;
    while (!predicate()) {
      assert.ok(Date.now() < deadline, '等待请求超时');
      await pause(20);
    }
  };
  await context.route('**/*', async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.origin !== origin) return route.abort();
    if (url.pathname !== '/do') return route.continue();
    const fields = new URLSearchParams(request.postData() || '');
    const call = {cmd: fields.get('cmd'), data: JSON.parse(fields.get('data') || '{}')};
    calls.push(call);
    const responder = responders.get(call.cmd);
    if (!responder) return route.continue(); // preview 本身会拒绝一切未模拟的写操作。
    const result = await responder(call.data);
    if (result === null) return route.abort('failed');
    return route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify(result)});
  });
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  const count = cmd => calls.filter(call => call.cmd === cmd).length;
  const load = async name => {
    await page.goto(`${origin}/?next=${name}`);
    await page.waitForFunction(expected => window.history.state?.page === expected && !!window.NasToolsUI, name);
    await page.locator('#page_content h1').first().waitFor();
  };
  const click = selector => page.locator(selector).evaluate(element => element.click());
  const navigate = async (name, selector) => {
    await page.evaluate(target => navmenu(target), name);
    await page.locator(selector).waitFor({state: 'attached'});
    await page.waitForFunction(expected => window.history.state?.page === expected, name);
  };
  try {
    const preview = await context.request.get(`${origin}/preview`);
    assert.match(await preview.text(), /只读/);
    for (const name of ['basic', 'media_setting', 'service_setting', 'security_setting', 'laboratory_setting', 'notification', 'downloader', 'download_setting', 'userdownloader', 'downloading', 'torrent_remove']) {
      await load(name);
      const inline = await page.locator('#page_content [onclick], #page_content [onchange], #page_content [oninput], #page_content a[href^="javascript:"]').count();
      assert.equal(inline, 0, `${name} 不应保留内联动作`);
      record(`${name} 真实模板载入与事件迁移`);
    }

    await load('notification');
    await click('[data-nt-click="show-custom-message"]');
    const send = page.locator('#send_custom_message_btn');
    const original = await send.innerHTML();
    await click('#send_custom_message_btn');
    assert.equal(count('send_custom_message'), 0);
    assert.equal(await send.isDisabled(), false);
    assert.equal(await send.innerHTML(), original);
    assert.equal(await page.locator('#custom_message_title.is-invalid').count(), 1);
    record('自定义消息先校验标题，不遗留禁用按钮');

    await page.locator('#custom_message_title').fill('测试标题');
    let response = deferred();
    responders.set('send_custom_message', () => response.promise);
    await page.locator('#send_custom_message_btn').evaluate(element => { element.click(); element.click(); });
    await waitFor(() => count('send_custom_message') === 1);
    assert.equal(await send.isDisabled(), true);
    response.resolve({code: -1, msg: '模拟失败'});
    await page.waitForFunction(() => !document.getElementById('send_custom_message_btn').disabled);
    assert.equal(await send.innerHTML(), original);
    responders.set('send_custom_message', () => null);
    await click('#send_custom_message_btn');
    await waitFor(() => count('send_custom_message') === 2);
    await page.waitForFunction(() => !document.getElementById('send_custom_message_btn').disabled);
    assert.equal(await send.innerHTML(), original);
    record('通知提交防重复，业务及网络失败均恢复按钮');

    responders.set('check_message_client', () => ({code: -1}));
    const toggle = page.locator('[data-nt-change="check-client"]').first();
    await toggle.evaluate(element => { element.checked = false; element.dispatchEvent(new Event('change', {bubbles: true})); });
    await waitFor(() => count('check_message_client') === 1);
    assert.equal(calls.find(call => call.cmd === 'check_message_client').data.checked, false);
    record('消息开关沿用布尔参数');

    await load('downloader');
    const saves = new Map([['qbittorrent', deferred()], ['transmission', deferred()]]);
    responders.set('update_config', data => saves.get(data['pt.pt_client']).promise);
    responders.set('test_connection', data => ({code: data.command === 'qbittorrent' ? 0 : -1}));
    await page.evaluate(() => {
      document.getElementById('qbittorrent_test_btn').click();
      document.getElementById('qbittorrent_test_btn').click();
      document.getElementById('transmission_test_btn').click();
    });
    await waitFor(() => calls.filter(call => call.cmd === 'update_config' && call.data.test === true).length === 2);
    saves.get('transmission').resolve({code: 0});
    await waitFor(() => count('test_connection') === 1);
    saves.get('qbittorrent').resolve({code: 0});
    await waitFor(() => count('test_connection') === 2);
    await page.waitForFunction(() => document.getElementById('qbittorrent_test_btn').textContent === '测试成功' && document.getElementById('transmission_test_btn').textContent === '测试失败！');
    assert.deepEqual(calls.filter(call => call.cmd === 'test_connection').map(call => call.data.command), ['transmission', 'qbittorrent']);
    record('两个下载器交错测试各自回写，重复点击只保存一次');

    responders.set('get_categories', data => ({code: 0, id: data.id, value: '', category: ['剧情']}));
    await click('[data-nt-click="show-directories"]');
    await click('[data-nt-click="add-directory"]');
    const row = page.locator('#dirdiv_1');
    assert.equal(await row.count(), 1);
    await row.locator('[name="dir_type"]').selectOption('电视剧');
    await waitFor(() => calls.some(call => call.cmd === 'get_categories' && call.data.id === '1' && call.data.type === '电视剧'));
    await row.locator('[name="dir_subtype"] option[value="剧情"]').waitFor({state: 'attached'});
    await click('#dirdiv_1 [data-nt-click="delete-directory"]');
    assert.equal(await row.count(), 0);
    record('新增目录行的change与删除通过同一委托处理器');

    await load('basic');
    const settingsBefore = count('update_config');
    responders.set('update_config', () => ({code: 0}));
    await page.locator('[id="app.login_user"]').fill('admin-review');
    await page.locator('[id="app.login_password"]').fill('demo-only-password');
    await click('#basic_system_btn');
    await waitFor(() => count('update_config') === settingsBefore + 1);
    const adminSettings = calls.filter(call => call.cmd === 'update_config').at(-1).data;
    assert.equal(adminSettings['app.login_user'], 'admin-review');
    assert.equal(adminSettings['app.login_password'], 'demo-only-password');
    record('基础设置保留唯一管理员账号与密码保存入口');

    await load('userdownloader');
    await click('[data-nt-click="add-downloader"]');
    await page.locator('#dl_name').fill('测试下载器');
    await page.locator('#dl_host').fill('localhost');
    await page.locator('#dl_port').fill('8080');
    await page.locator('#dl_save_dir').fill('/demo');
    const oldTest = deferred();
    responders.set('add_downloader', () => oldTest.promise);
    await click('#dl_test_btn');
    await waitFor(() => count('add_downloader') === 1);
    await navigate('basic', '#basic_system_btn');
    await navigate('userdownloader', '#dl_test_btn');
    oldTest.resolve({code: 0});
    await pause(100);
    assert.equal((await page.locator('#dl_test_btn').textContent()).trim(), '测试');
    record('A→B→A 后旧测试结果不覆盖新页面同ID按钮');

    await load('downloading');
    const infoBeforeStart = count('pt_info');
    const start = deferred();
    responders.set('pt_start', data => start.promise.then(() => ({retcode: '0', id: data.id})));
    await page.locator('#start_btn_4').evaluate(element => { element.click(); element.click(); });
    await waitFor(() => count('pt_start') === 1);
    assert.equal(calls.find(call => call.cmd === 'pt_start').data.id, '4');
    start.resolve();
    await waitFor(() => count('pt_info') > infoBeforeStart);
    await navigate('basic', '#basic_system_btn');
    const pollingCount = count('pt_info');
    await pause(2200);
    assert.equal(count('pt_info'), pollingCount);
    record('下载图标操作防连点且保留字符串ID，切页停止轮询');

    assert.deepEqual(errors, [], '浏览器未捕获异常');
    console.log(`下载与设置事件验证通过：${checked} 项；仅本地示例数据，无真实服务写入。`);
  } finally {
    await context.close();
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
