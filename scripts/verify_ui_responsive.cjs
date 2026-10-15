/* Run from the repository root with Playwright available in NODE_PATH.
 * Requires the isolated preview on 127.0.0.1:5108. Never connects live services. */
const {chromium}=require('playwright');
const fs=require('fs');
const path=require('path');
const origin=process.env.UI_PREVIEW_URL || 'http://127.0.0.1:5108';
if (!['127.0.0.1','localhost'].includes(new URL(origin).hostname)) throw new Error('UI verification requires a local preview.');
const output=path.resolve(process.env.UI_VERIFY_OUTPUT || 'docs/ui/verification');
fs.mkdirSync(output,{recursive:true});
(async()=>{
 const browser=await chromium.launch({headless:true, executablePath:process.env.CHROME_PATH || (fs.existsSync('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome') ? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' : undefined)});
 const context=await browser.newContext({viewport:{width:390,height:844}});
 await context.route('**/*',r=>new URL(r.request().url()).origin===new URL(origin).origin?r.continue():r.abort());
 const page=await context.newPage(), results=[];let errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 for(const width of [390,768,992,1440]){
  await page.setViewportSize({width,height:width<768?844:1000});
  for(const route of ['ranking','media_detail?id=1&type=MOV','search','statistics','basic','tools/site-signin','downloader','users','downloading']){
   errors=[];await page.goto(origin+'/?next='+encodeURIComponent(route));
   await page.waitForSelector('#page_content:not([hidden])');await page.waitForTimeout(350);
   const metrics=await page.evaluate(()=>({overflow:document.documentElement.scrollWidth-innerWidth,sidebar:document.querySelector('layout-navbar').getBoundingClientRect().width,header:document.querySelector('layout-searchbar').getBoundingClientRect().height}));
   results.push({width,route,...metrics,errors:[...errors]});
   if(width===390&&['basic','downloading','media_detail?id=1&type=MOV'].includes(route))await page.screenshot({path:output+'/mobile-'+route.split('?')[0]+'.png',fullPage:true});
  }
 }
 await page.setViewportSize({width:1440,height:1000});
 await page.goto(origin+'/?next=downloading&theme=dark');await page.waitForSelector('.nt-download-item');
 await page.screenshot({path:output+'/dark-downloads.png'});
 results.push({check:'dark',background:await page.evaluate(()=>getComputedStyle(document.body).backgroundColor)});
 await page.goto(origin+'/?next=ranking&theme=light');await page.waitForSelector('.home_search_bar');
 await page.locator('.home_search_bar').fill('星际');
 await page.locator('.home_search_bar').dispatchEvent('keydown',{key:'Enter',code:'Enter',isComposing:true});
 results.push({check:'ime-not-submitted',value:await page.locator('.home_search_bar').inputValue(),page:await page.evaluate(()=>CURRENT_PAGE_URI)});
 await page.locator('.home_search_bar').press('Enter');await page.waitForSelector('#recommend_title');
 results.push({check:'search-submit',title:await page.locator('#recommend_title').textContent()});
 await page.setViewportSize({width:390,height:844});
 await page.getByRole('button',{name:'打开主导航'}).click();await page.waitForSelector('#litLayoutNavbar.show');
 await page.screenshot({path:output+'/mobile-navigation.png'});
 results.push({check:'mobile-navigation',width:await page.locator('#litLayoutNavbar').evaluate(e=>e.getBoundingClientRect().width)});
 await page.goto(origin+'/preview/login');await page.locator('#login-password').fill('demo');await page.getByRole('button',{name:'显示密码'}).click();
 results.push({check:'password-toggle',type:await page.locator('#login-password').getAttribute('type')});
 fs.writeFileSync(output+'/responsive-results.json',JSON.stringify(results,null,2));
 const failures=results.filter(r => r.route ? (r.overflow !== 0 || r.errors.length || r.sidebar !== (r.width >= 992 ? 232 : 0) || r.header !== (r.width >= 992 ? 72 : 64))
  : r.check === 'dark' ? r.background !== 'rgb(16, 27, 23)'
  : r.check === 'ime-not-submitted' ? r.value !== '星际' || r.page !== 'ranking'
  : r.check === 'search-submit' ? r.title !== '搜索结果'
  : r.check === 'mobile-navigation' ? r.width !== 232
  : r.check === 'password-toggle' ? r.type !== 'text' : false);
 console.log(JSON.stringify({checks:results.length,failures}));await browser.close();
 if(failures.length) process.exitCode=1;
})().catch(e=>{console.error(e);process.exit(1)});
