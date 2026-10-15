// Offline browser acceptance against the real HTTP API and parser, in a temporary ledger.
// PLAYWRIGHT_MODULE=/path/to/playwright node scripts/tests/workbench_browser.cjs
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const {once} = require('node:events');
const {resolve} = require('node:path');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = resolve(__dirname, '../..');
const fixture = String.raw`
import sys, tempfile, threading, time, json
from pathlib import Path
sys.path.insert(0, 'scripts')
from http.server import ThreadingHTTPServer
from workbench_server import handler, Worker
from workbench_store import Store
from miit_paths import MIIT_FORMAL_DIR
import requests
requests.get = lambda *a, **k: (_ for _ in ()).throw(AssertionError('Live capture forbidden'))
with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    store = Store(root / 'db')
    archive = MIIT_FORMAL_DIR / 'batch_409'
    url = json.loads((archive / 'raw_metadata.json').read_text())['source_url']
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler(store, root / 'tasks'))
    worker = Worker(store, root / 'tasks', archive)
    def run():
        while True:
            time.sleep(1)
            worker.once()
    threading.Thread(target=run, daemon=True).start()
    print(json.dumps({'base': 'http://127.0.0.1:' + str(server.server_port), 'url': url}), flush=True)
    server.serve_forever()
`;
const server = spawn(resolve(root, '.venv/bin/python'), ['-u', '-c', fixture], {cwd:root, stdio:['ignore','pipe','pipe']});
let browser;
(async () => {
  try {
    const [chunk] = await Promise.race([once(server.stdout, 'data'), once(server, 'exit').then(([code])=>{throw Error('Offline fixture exited: ' + code);})]);
    const {base,url} = JSON.parse(chunk.toString().trim());
    browser = await chromium.launch({headless:true, ...(process.env.CHROME_PATH ? {executablePath:process.env.CHROME_PATH} : {})});
    const page = await browser.newPage({viewport:{width:1414,height:894}});
    const errors=[]; page.on('pageerror', e=>errors.push(e.message));
    await page.goto(base);
    await page.getByText('暂无采集任务，请在顶部输入正式公告链接。').waitFor();
    assert.equal(await page.locator('[data-task-id]').count(),0);
    await page.locator('#url').fill('https://example.com/invalid');
    await page.locator('#submit').click();
    await page.waitForFunction(()=>document.querySelector('#notice').textContent.includes('提交失败'));
    assert.equal(await page.locator('[data-task-id]').count(),0);
    await page.locator('[data-scope="reports"]').click();
    await page.locator('.file-tree').waitFor();
    assert.ok(Number(await page.locator('#reports-count').textContent()) > 0);
    let openedFolder = false;
    await page.route('**/api/miit/library/open-folder', async route => {
      assert.deepEqual(route.request().postDataJSON(), {path:'reports'});
      openedFolder = true; await route.fulfill({json:{ok:true}});
    });
    await page.locator('#open-folder').click();
    await page.waitForFunction(()=>document.querySelector('#notice').textContent.includes('已在 Finder'));
    assert.equal(openedFolder,true);
    await page.unroute('**/api/miit/library/open-folder');
    if (process.env.UI_SCREENSHOT) await page.screenshot({path:process.env.UI_SCREENSHOT,fullPage:true});
    await page.locator('#url').fill(url);
    await page.locator('#submit').click();
    await page.waitForSelector('[data-task-id][aria-pressed="true"]');
    assert.equal(await page.locator('[data-scope="tasks"]').getAttribute('aria-pressed'),'true');
    await page.getByRole('heading',{name:'第 409 批 · 候选结果',exact:true}).waitFor({timeout:15000});
    await page.getByText('1526 条来源记录', {exact:false}).waitFor();
    assert.match(await page.locator('#preview').innerText(), /归档离线回放/);
    await page.getByRole('button',{name:'预览原文'}).first().click();
    await page.waitForFunction(()=>[...document.querySelectorAll('.task-section pre')].some(e=>!e.hidden && e.textContent.includes('<html')));
    const candidate = await page.getByRole('link',{name:'下载候选快照 JSON'}).getAttribute('href');
    const snapshot = await (await page.request.get(base + candidate)).json();
    assert.equal(snapshot.payload.rows.length,1526);
    await page.reload();
    await page.getByRole('heading',{name:'第 409 批 · 候选结果',exact:true}).waitFor();
    await page.locator('[data-scope="reports"]').click();
    await page.locator('.file-tree').waitFor();
    await page.locator('[data-scope="tasks"]').click();
    await page.getByRole('heading',{name:'第 409 批 · 候选结果',exact:true}).waitFor();
    // Another execution is a distinct persisted task, automatically selected.
    const first = await page.locator('[data-task-id]').first().getAttribute('data-task-id');
    await page.locator('#url').fill(url);
    await page.locator('#submit').click();
    await page.waitForFunction(id=>document.querySelector('[data-task-id][aria-pressed="true"]')?.dataset.taskId!==id,first);
    await page.getByRole('heading',{name:'第 409 批 · 候选结果',exact:true}).waitFor();
    assert.equal(await page.locator('[data-task-id]').count(),2);
    assert.equal(await page.locator('#tasks-count').textContent(),'2');
    await page.locator(`[data-task-id="${first}"]`).click();
    await page.waitForFunction(id=>document.querySelector('#preview').textContent.includes(id),first);
    // Lose a successful POST response; resubmission must reuse the same idempotency key.
    await page.route('**/api/miit/tasks', async route => {
      if (route.request().method() !== 'POST') return route.continue();
      await route.fetch(); await route.abort('failed');
    });
    await page.locator('#submit').click();
    await page.waitForFunction(()=>document.querySelector('#notice').textContent.includes('提交失败'));
    await page.unroute('**/api/miit/tasks');
    await page.locator('#submit').click();
    await page.waitForFunction(()=>document.querySelectorAll('[data-task-id]').length===3);
    await page.getByRole('heading',{name:'第 409 批 · 候选结果',exact:true}).waitFor();
    // A valid URL without a matching replay archive fails visibly, and retry creates a linked task.
    await page.locator('#url').fill(url.replace('art_', 'art_dead'));
    await page.locator('#submit').click();
    await page.getByRole('heading',{name:'采集失败',exact:true}).waitFor({timeout:15000});
    await page.getByText('archive_url_mismatch', {exact:false}).waitFor();
    await page.getByRole('button',{name:'重新采集',exact:true}).click();
    await page.waitForFunction(()=>document.querySelectorAll('[data-task-id]').length===5);
    await page.getByRole('heading',{name:'采集失败',exact:true}).waitFor({timeout:15000});
    await page.getByText('重试自 ·', {exact:false}).waitFor();
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth),true);
    assert.deepEqual(errors,[]);
    console.log('Offline browser passed: empty ledger, invalid URL, Reports → submit → auto-select, completion polling, real candidate/evidence, reload, multiple tasks, response-loss idempotency, failure/retry, mobile.');
  } finally { if(browser) await browser.close(); server.kill('SIGTERM'); }
})().catch(error=>{console.error(error);process.exitCode=1;});
