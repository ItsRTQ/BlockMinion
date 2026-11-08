// Starts the real `craftctl ui` server on a seeded home and loads the real page (index.html + kit.js + app.js) into jsdom.
import {spawn, execFileSync} from 'node:child_process';
import {mkdtempSync, readFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import net from 'node:net';
import path from 'node:path';
import {JSDOM} from 'jsdom';

const ROOT = path.resolve(import.meta.dirname, '../..');
const STATIC = path.join(ROOT, 'src/mod_orchestra/static');
const PY = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const freePort = () => new Promise((resolve, reject) => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const {port} = s.address(); s.close(() => resolve(port)); }); s.on('error', reject); });

export async function startServer() {
  const home = mkdtempSync(path.join(tmpdir(), 'orchestra-ui-'));
  const env = {...process.env, CRAFTCTL_HOME: home, BROWSER: 'true', PYTHONUNBUFFERED: '1'};
  execFileSync(PY, [path.join(ROOT, 'tests/ui/seed.py')], {env, cwd: ROOT, stdio: ['ignore', 'ignore', 'inherit']});
  const port = await freePort();
  const child = spawn(PY, ['-m', 'mod_orchestra.cli', 'ui', '--port', String(port)], {env, cwd: ROOT});
  let log = '';
  const url = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('the UI server did not start:\n' + log)), 30000);
    child.stdout.on('data', (d) => { log += d; const m = log.match(/Local app URL: (\S+)/); if (m) { clearTimeout(timer); resolve(m[1]); } });
    child.stderr.on('data', (d) => { log += d; });
    child.on('exit', (c) => { clearTimeout(timer); reject(new Error(`the UI server exited (${c}):\n${log}`)); });
  });
  return {base: `http://127.0.0.1:${port}`, token: url.split('#')[1], stop: () => child.kill()};
}

// Loads the page. `overrides` maps an API path to a JSON body (or a function returning one) and is read on every request, so a test can change it later;
// every other request goes to the real server. `calls` records what the page asked for. Native popups are recorded and must stay at zero.
export async function loadPage(server, {overrides = {}, settle = true} = {}) {
  const calls = [], popups = [];
  let html = readFileSync(path.join(STATIC, 'index.html'), 'utf8').replace(/<link[^>]*style\.css[^>]*>/, '').replace(/<script src="[^"]*"><\/script>/g, '');
  const dom = new JSDOM(html, {
    url: `${server.base}/#${server.token}`, runScripts: 'dangerously', pretendToBeVisual: true,
    beforeParse(w) {
      w.fetch = async (input, init = {}) => {
        const u = String(input), key = u.split('?')[0];
        calls.push({path: key, method: init.method || 'GET', body: init.body ? JSON.parse(init.body) : null});
        if (key in overrides) {
          const body = typeof overrides[key] === 'function' ? await overrides[key](init) : overrides[key];
          return new Response(JSON.stringify(body), {status: 200, headers: {'Content-Type': 'application/json'}});
        }
        // a browser adds the Origin header to a POST by itself; the server refuses a POST without it
        const headers = {...(init.headers || {})}; if (init.method && init.method !== 'GET') headers.Origin = server.base;
        return fetch(server.base + u, {...init, headers});
      };
      w.scrollTo = (x, y) => { w.__x = x; w.__y = y; };
      Object.defineProperty(w, 'scrollY', {get: () => w.__y || 0, configurable: true}); Object.defineProperty(w, 'scrollX', {get: () => w.__x || 0, configurable: true});
      w.Element.prototype.scrollIntoView = function () { w.__scrolledTo = this; };
      for (const name of ['confirm', 'prompt', 'alert']) w[name] = (...a) => { popups.push([name, a[0]]); return name === 'prompt' ? null : false; };
    },
  });
  const w = dom.window, doc = w.document;
  for (const file of ['kit.js', 'app.js']) { const s = doc.createElement('script'); s.textContent = readFileSync(path.join(STATIC, file), 'utf8'); doc.body.append(s); }
  const page = {
    dom, w, doc, calls, popups, overrides,
    $: (sel) => doc.querySelector(sel), $$: (sel) => [...doc.querySelectorAll(sel)],
    eval: (code) => w.eval(code),
    hidden: (sel) => doc.querySelector(sel).classList.contains('hidden'),
    click: (el) => el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true})),
    key: (el, key, extra = {}) => el.dispatchEvent(new w.KeyboardEvent('keydown', {key, bubbles: true, cancelable: true, ...extra})),
    waitFor: async (cond, what = 'the page', ms = 6000) => { const end = Date.now() + ms; for (;;) { const v = cond(); if (v) return v; if (Date.now() > end) throw new Error('timed out waiting for ' + what); await sleep(25); } },
    toasts: () => { const t = doc.getElementById('toast'); return t.classList.contains('hidden') ? '' : t.textContent; },
    close: () => w.close(),
  };
  if (settle) await page.waitFor(() => page.$('#p-name') && page.$('#p-name').textContent && !page.$('#project-list .dim'), 'the first project to render');
  return page;
}
