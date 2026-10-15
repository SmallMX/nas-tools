/* 运行：UI_PREVIEW_URL=http://127.0.0.1:5118 NODE_PATH=/path/to/node_modules node scripts/verify_ui_site_actions.cjs
 * 使用隔离预览的真实模板与内存 fixture；写请求由 Playwright 拦截，不访问站点或下载器。
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {execFileSync} = require('node:child_process');
const {chromium} = require('playwright');
const root = path.resolve(__dirname, '..');
const origin = new URL(process.env.UI_PREVIEW_URL || 'http://127.0.0.1:5118').origin;
if (!['127.0.0.1', 'localhost'].includes(new URL(origin).hostname)) throw new Error('仅允许本地只读预览。');
const chrome = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const deferred = () => {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return {promise, resolve};
};

// 预览的默认资源列表只有一页。用相同渲染器生成分页和特殊字符边界，不手改 HTML 或执行真实业务模块。
const fixtures = JSON.parse(execFileSync(process.env.UI_PYTHON || path.join(root, '.venv/bin/python'), ['-c', String.raw`
import copy, json, sys
from flask import render_template
from scripts.preview_ui import create_preview_app, page_context
app = create_preview_app()
quoted = '''示例"'<img id="fixture-injected" src=x onerror="window.fixtureInjected=1"> &'''
result = {"quoted": quoted}
with app.test_request_context('/'):
    context = page_context('site')
    context['Sites'] = copy.deepcopy(context['Sites'])
    context['Sites'][0]['name'] = quoted
    result['site'] = render_template('site/site.html', **context)
    result['site_data'] = dict(context['Sites'][0], rssurl='https://site-1.example/rss',
                               cookie='fixture-cookie', ua='fixture-agent', uses='QT')
    for page in range(3):
        context = page_context('resources')
        context.update(CurrentPage=page, PageRange=[0, 1, 2], TotalPage=3, Title=quoted)
        context['Results'] = copy.deepcopy(context['Results'])
        context['Results'][0].update(title=quoted, enclosure='https://site-1.example/download?id=1',
                                     page_url='https://site-1.example/details?id=1')
        result['resources'+str(page)] = render_template('site/resources.html', **context)
    for selected in (False, True):
        context = page_context('tmdb_movie')
        context.update(Title=quoted, FilterConf={'with_genres': {'name': '类型', 'type': 'dropdown',
                       'options': [{'name': '全部', 'value': ''}, {'name': quoted, 'value': quoted}]}},
                       Params={'with_genres': quoted} if selected else {})
        result['recommend_selected' if selected else 'recommend'] = render_template('discovery/recommend.html', **context)
assert 'web.main' not in sys.modules and 'config' not in sys.modules and 'app' not in sys.modules
print(json.dumps(result))
`], {cwd: root, encoding: 'utf8'}));

(async () => {
  const browser = await chromium.launch({headless: true,
    executablePath: process.env.CHROME_PATH || (fs.existsSync(chrome) ? chrome : undefined)});
  const context = await browser.newContext({viewport: {width: 1440, height: 1000}});
  await context.route('**/*', route => new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
  const page = await context.newPage();
  page.setDefaultTimeout(7000);
  const calls = [], fragments = [], errors = [], responders = new Map();
  page.on('pageerror', error => errors.push(error.message));
  const count = cmd => calls.filter(call => call.cmd === cmd).length;
  const latest = cmd => calls.filter(call => call.cmd === cmd).at(-1);
  const waitFor = async (predicate, message = '等待界面请求超时') => {
    const deadline = Date.now() + 5000;
    while (!predicate()) { assert.ok(Date.now() < deadline, message); await pause(20); }
  };
  let checked = 0;
  const check = async (name, verify) => { await verify(); checked++; console.log(`PASS ${name}`); };
  const json = (route, data, status = 200) => route.fulfill({status, contentType: 'application/json', body: JSON.stringify(data)});
  const readonly = new Set(['refresh_message', 'get_site_favicon', 'get_download_setting', 'get_download_dirs',
    'get_site_history', 'get_site_user_statistics', 'refresh_process', 'get_sites', 'get_indexers',
    'get_site_activity', 'get_site_seeding_info', 'list_brushtask_torrents']);
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.origin !== origin) return route.abort();
    if (url.pathname === '/do') {
      const form = new URLSearchParams(route.request().postData() || '');
      const call = {cmd: form.get('cmd'), data: JSON.parse(form.get('data') || '{}')};
      calls.push(call);
      if (responders.has(call.cmd)) return json(route, await responders.get(call.cmd)(call.data));
      if (readonly.has(call.cmd)) return route.continue();
      return json(route, {code: -1, msg: '隔离交互验证：未模拟的动作已拦截'}, 403);
    }
    if (['/site', '/resources', '/tmdb_movie', '/recommend'].includes(url.pathname)) {
      fragments.push(url);
      let html;
      if (url.pathname === '/site') html = fixtures.site;
      else if (url.pathname === '/resources') html = fixtures['resources' + (url.searchParams.get('page') || 0)];
      else html = fixtures[url.searchParams.has('params') ? 'recommend_selected' : 'recommend'];
      assert.ok(html, `缺少隔离片段：${url.pathname}${url.search}`);
      return route.fulfill({status: 200, contentType: 'text/html; charset=utf-8', body: html});
    }
    return route.continue();
  });
  responders.set('get_site', () => ({code: 0, site: fixtures.site_data}));
  responders.set('get_recommend', () => ({code: 0, Items: []}));
  responders.set('get_brush_site_capabilities', data => ({code: 0, site_free: data.id === '1', site_hr: data.id === '1'}));
  const load = async name => {
    await page.goto(`${origin}/?next=${encodeURIComponent(name)}`);
    await page.waitForFunction(expected => window.history.state?.page === expected && !!window.NasToolsUI, name);
    await page.locator('#page_content h1').first().waitFor();
  };
  const navigate = async name => {
    await page.evaluate(target => navmenu(target), name);
    await page.waitForFunction(expected => window.history.state?.page === expected, name);
    await page.locator('#page_content h1').first().waitFor();
  };
  const closeModal = async id => {
    await page.locator(`${id} [data-bs-dismiss="modal"]`).first().click();
    await page.locator(id).waitFor({state: 'hidden'});
  };
  try {
    const preview = await context.request.get(`${origin}/preview`);
    assert.equal(preview.status(), 200);
    assert.match(await preview.text(), /只读预览/);

    await check('搜索桌面筛选与重置保留条目数量', async () => {
      await load('search');
      await page.locator('#search_results_filter_demo-media label').filter({has: page.locator('[name="filter_site"]')}).first().click();
      await page.waitForFunction(() => document.querySelectorAll('.search_results_torrent').length === 3 &&
        [...document.querySelectorAll('.search_results_torrent')].filter(el => el.offsetWidth > 0).length === 1);
      assert.equal(await page.locator('.search_results_group_total').first().textContent(), '1');
      await page.locator('#search_results_filter_demo-media [data-nt-click="search-reset"]').click();
      assert.equal(await page.locator('[name="filter_site"]:checked').count(), 0);
      assert.equal(await page.locator('.search_results_group_total').first().textContent(), '3');
    });

    await check('移动筛选弹层与重置通过change生效', async () => {
      await page.setViewportSize({width: 390, height: 844});
      await page.locator('[data-nt-click="search-filter-modal"]').click();
      const modal = page.locator('#search-filter-modal-demo-media');
      await modal.waitFor({state: 'visible'});
      await modal.locator('label').filter({has: page.locator('[name="filter_site"]')}).nth(1).click();
      assert.equal(await page.locator('.search_results_group_total').first().textContent(), '1');
      await modal.locator('[data-nt-click="search-reset"]').click();
      assert.equal(await page.locator('[name="filter_site"]:checked').count(), 0);
      assert.equal(await page.locator('.search_results_group_total').first().textContent(), '3');
      await closeModal('#search-filter-modal-demo-media');
      await page.setViewportSize({width: 1440, height: 1000});
    });

    await check('站点重复进入后编辑只发一次请求且引号名称保持文本', async () => {
      await navigate('site');
      await navigate('search');
      await navigate('site');
      const before = count('get_site');
      await page.locator('[data-nt-click="site-edit"]').first().click();
      await page.locator('#modal-site').waitFor({state: 'visible'});
      await waitFor(() => count('get_site') === before + 1);
      await pause(100);
      assert.equal(count('get_site'), before + 1);
      assert.deepEqual(latest('get_site').data, {id: '1'});
      assert.equal(await page.locator('#site_name').inputValue(), fixtures.quoted);
      assert.equal(await page.locator('#fixture-injected').count(), 0);
      assert.deepEqual(await page.locator('[name="site_uses"]:checked').evaluateAll(els => els.map(el => el.value)), ['Q', 'T']);
    });

    await check('站点保存保留checkbox与原始字段，双击只提交一次', async () => {
      await page.locator('label').filter({has: page.locator('[name="site_uses"][value="Q"]')}).click();
      await page.locator('label').filter({has: page.locator('[name="site_uses"][value="D"]')}).click();
      await page.locator('#site_parse').selectOption('N');
      await page.locator('#site_download_setting').selectOption('1');
      const response = deferred();
      responders.set('update_site', () => response.promise);
      const before = count('update_site');
      await page.locator('#add_or_edit_site_btn').dblclick();
      await waitFor(() => count('update_site') === before + 1);
      assert.deepEqual(latest('update_site').data, {
        site_id: '1', site_name: fixtures.quoted, site_pri: '1', site_rssurl: 'https://site-1.example/rss',
        site_signurl: 'https://site-1.example/', site_cookie: 'fixture-cookie', site_include: 'DT',
        site_note: {apikey: '', download_setting: '1', parse: 'N', ua: 'fixture-agent', chrome: 'N', proxy: 'N', message: 'Y'}
      });
      assert.equal(await page.locator('#add_or_edit_site_btn').isDisabled(), true);
      response.resolve({code: 0});
      await page.locator('#modal-site').waitFor({state: 'hidden'});
      await pause(100);
      assert.equal(count('update_site'), before + 1);
    });

    await check('刷流范围条件切换更新只读状态与隐藏操作值', async () => {
      await navigate('brushtask');
      await page.locator('[data-nt-click="brush-add"]').click();
      await page.locator('#brushtask_torrent_size_btn').click();
      await page.locator('#brushtask_torrent_size_do_bw').click();
      assert.equal(await page.locator('#brushtask_torrent_size_do').inputValue(), 'bw');
      assert.equal(await page.locator('#brushtask_torrent_size').isEditable(), true);
      await page.locator('#brushtask_torrent_size').fill('5,40');
      await page.locator('#brushtask_torrent_size_btn').click();
      await page.locator('#brushtask_torrent_size_do_').click();
      assert.equal(await page.locator('#brushtask_torrent_size_do').inputValue(), '');
      assert.equal(await page.locator('#brushtask_torrent_size').inputValue(), '');
      assert.equal(await page.locator('#brushtask_torrent_size').isEditable(), false);
    });

    await check('刷流站点change显示或移除促销与HR选项', async () => {
      await page.locator('#brushtask_site').selectOption('1');
      await page.locator('#brushtask_free option[value="FREE"]').waitFor({state: 'attached'});
      assert.equal(await page.locator('#brushtask_hr option[value="HR"]').count(), 1);
      await page.locator('#brushtask_site').selectOption('2');
      await page.locator('#brushtask_free option[value="FREE"]').waitFor({state: 'detached'});
      assert.equal(await page.locator('#brushtask_hr option[value="HR"]').count(), 0);
      assert.equal(latest('get_brush_site_capabilities').data.id, '2');
      await closeModal('#modal-brushtask');
    });

    await check('刷流执行保留字符串ID且重复进入后不叠加请求', async () => {
      await navigate('site');
      await navigate('brushtask');
      responders.set('run_brushtask', () => ({code: 0}));
      const before = count('run_brushtask');
      await page.locator('a[data-nt-click="brush-run"]').click();
      await waitFor(() => count('run_brushtask') === before + 1);
      assert.deepEqual(latest('run_brushtask').data, {id: '1'});
      await page.locator('#system-success-modal').waitFor({state: 'visible'});
      await pause(100);
      assert.equal(count('run_brushtask'), before + 1);
      await closeModal('#system-success-modal');
    });

    await check('资源全选和取消全选不反转checkbox默认行为', async () => {
      await navigate('resources?site=1&page=1');
      const all = page.locator('[data-nt-change="resources-select-all"]');
      await all.check();
      assert.equal(await page.locator('[name="resources_item"]:checked').count(), 4);
      await all.uncheck();
      assert.equal(await page.locator('[name="resources_item"]:checked').count(), 0);
    });

    await check('资源下载弹窗与提交保留特殊字符和请求参数', async () => {
      responders.set('download_link', () => ({code: 0}));
      const before = count('download_link');
      await page.locator('[data-nt-click="resources-download"]').first().click();
      await page.locator('#modal-search-download').waitFor({state: 'visible'});
      assert.equal(await page.locator('#search_download_name').inputValue(), fixtures.quoted);
      assert.equal(await page.locator('#fixture-injected').count(), 0);
      await page.locator('#search_download_dir option[value="/demo/downloads"]').waitFor({state: 'attached'});
      await page.locator('#search_download_dir').selectOption('/demo/downloads');
      await page.locator('#search_download_btn').click();
      await waitFor(() => count('download_link') === before + 1);
      const data = latest('download_link').data;
      assert.equal(data.title, fixtures.quoted);
      assert.equal(data.site, fixtures.quoted);
      assert.equal(data.enclosure, 'https://site-1.example/download?id=1');
      assert.equal(data.page_url, 'https://site-1.example/details?id=1');
      assert.equal(data.dl_dir, '/demo/downloads');
      assert.equal(data.dl_setting, ''); // 默认沿用站点下载设置。
      assert.equal(typeof data.size, 'string');
      await page.locator('#system-success-modal').waitFor({state: 'visible'});
      await closeModal('#system-success-modal');
    });

    await check('资源上一页随页码启用，页码点击传递数字页', async () => {
      const previous = page.locator('[data-nt-click="resources-previous"]');
      assert.equal(await previous.getAttribute('aria-disabled'), 'false');
      await previous.click();
      await page.waitForFunction(() => new URLSearchParams(window.history.state.page.split('?')[1]).get('page') === '0');
      assert.equal(await previous.getAttribute('aria-disabled'), 'true');
      const pageTwo = page.locator('[data-nt-click="resources-page"]').filter({hasText: /^3$/});
      await pageTwo.click();
      await page.waitForFunction(() => new URLSearchParams(window.history.state.page.split('?')[1]).get('page') === '2');
      assert.equal(await previous.getAttribute('aria-disabled'), 'false');
      assert.equal(fragments.at(-1).searchParams.get('title'), fixtures.quoted);
    });

    await check('统计7/30/365天切换各请求一次并更新当前按钮', async () => {
      await navigate('statistics');
      await waitFor(() => count('get_site_history') >= 2);
      for (const [id, days] of [['week', 7], ['month', 30], ['year', 365]]) {
        const before = count('get_site_history');
        await page.locator(`#btn-history-one-${id}`).click();
        await waitFor(() => count('get_site_history') === before + 1);
        assert.deepEqual(latest('get_site_history').data, {days});
        assert.match(await page.locator(`#btn-history-one-${id}`).getAttribute('class'), /active/);
      }
    });

    await check('推荐宏筛选安全传参并保留导航上下文', async () => {
      await navigate('tmdb_movie');
      const header = page.locator('.nt-discovery-header');
      await header.locator('.dropdown-toggle').click();
      await header.locator('[data-nt-click="recommend-filter"]').nth(1).click();
      await page.waitForFunction(() => window.history.state?.page?.startsWith('recommend?'));
      const url = fragments.at(-1);
      assert.equal(url.searchParams.get('type'), 'DISCOVER');
      assert.equal(url.searchParams.get('subtype'), 'MOV');
      assert.equal(url.searchParams.get('title'), fixtures.quoted);
      assert.equal(url.searchParams.get('filter'), 'tmdb_movie');
      assert.deepEqual(JSON.parse(url.searchParams.get('params')), {with_genres: fixtures.quoted});
      assert.equal(await page.locator('#fixture-injected').count(), 0);
      assert.equal(await page.evaluate(() => window.fixtureInjected), undefined);
    });

    assert.deepEqual(errors, [], '浏览器未捕获异常');
    console.log(`站点与搜索事件验证通过：${checked} 项；全部写请求均使用隔离 fixture，无真实服务调用。`);
  } finally {
    await context.close();
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
