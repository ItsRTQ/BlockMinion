import test from 'node:test';
import assert from 'node:assert/strict';
import {startServer, loadPage} from './harness.mjs';

// Files in the chat: attach (button, drop, paste), see them waiting, send them with the message, see them in the conversation.
// Everything here talks to the real server except `dispatch` (no agent is started by a test).
let server, page;
const posts = (suffix) => page.calls.filter((c) => c.method === 'POST' && c.path.endsWith(suffix));
const chips = (sel = '#chat-files') => page.$$(`${sel} .chat-file`);
const PNG = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 0, 0, 0, 0, 0];
const file = (name, bytes, type = '') => `new File([new Uint8Array(${JSON.stringify(typeof bytes === 'string' ? [...Buffer.from(bytes)] : bytes)})], ${JSON.stringify(name)}, {type: ${JSON.stringify(type)}})`;

test.before(async () => {
  server = await startServer(); page = await loadPage(server); page.overrides['/api/project/infect/dispatch'] = {started: true};
  await page.eval('openProject("infect")'); await page.idle();
});
test.after(async () => { if (page) await page.close(); if (server) server.stop(); });

test('the compose box offers Attach, and says what can be attached', () => {
  assert.ok(page.$('#chat-attach')); assert.match(page.$('#chat-attach').title, /Pictures .* PDFs and text files/); assert.equal(page.$('#chat-file-input').multiple, true);
  assert.equal(chips().length, 0);
});

test('chosen files upload at once and wait as chips; the server decides what each one is', async () => {
  await page.eval(`chatAttach([${file('how it looks.txt', PNG, 'text/plain')}, ${file('crash.log', 'NullPointerException at Mod.java:12\n')}])`);
  assert.equal(posts('/chat-attach').length, 2, 'one request per file'); assert.equal(posts('/chat-attach')[0].body.name, 'how it looks.txt');
  assert.deepEqual(chips().map((c) => [c.dataset.id, c.classList.contains('image'), c.querySelector('.chat-file-name').textContent]), [['att-1', true, 'how it looks.txt'], ['att-2', false, 'crash.log']]);
  assert.match(chips()[0].querySelector('img').getAttribute('src'), /\/file\?path=attachments%2Fatt-1\.png&token=/, 'a picture by its bytes, whatever its name said');
  assert.equal(chips()[1].querySelector('a.chat-file-kind').textContent, 'TXT'); assert.equal(chips()[1].querySelector('a').getAttribute('download'), 'crash.log');
  assert.equal(chips()[0].querySelector('button').getAttribute('aria-label'), 'Remove how it looks.txt');
});

test('a file that cannot be attached is refused with the reason, and nothing waits for it', async () => {
  await page.eval(`chatAttach([${file('mod.jar', [0x50, 0x4b, 3, 4, 0, 0, 0, 0])}])`);
  assert.match(page.toasts(), /mod\.jar: That kind of file cannot be attached/); assert.equal(chips().length, 2);
});

test('dropping and pasting files attach them too; pasted text stays text', async () => {
  const drop = new page.w.Event('drop', {bubbles: true, cancelable: true}); drop.dataTransfer = {files: [page.eval(file('dropped.md', '# notes\n'))], types: ['Files']};
  page.$('#chat-drop').dispatchEvent(drop); assert.equal(drop.defaultPrevented, true, 'the browser must not open the file instead');
  await page.waitFor(() => chips().length === 3, 'the dropped file');
  const paste = new page.w.Event('paste', {bubbles: true, cancelable: true}); paste.clipboardData = {files: [page.eval(file('image.png', PNG, 'image/png'))]};
  page.$('#chat-text').dispatchEvent(paste); assert.equal(paste.defaultPrevented, true); await page.waitFor(() => chips().length === 4, 'the pasted screenshot');
  const text = new page.w.Event('paste', {bubbles: true, cancelable: true}); text.clipboardData = {files: []}; page.$('#chat-text').dispatchEvent(text); assert.equal(text.defaultPrevented, false);
  const over = new page.w.Event('dragover', {bubbles: true, cancelable: true}); over.dataTransfer = {types: ['Files']}; page.$('#chat-drop').dispatchEvent(over); assert.ok(page.$('#chat-drop').classList.contains('over'));
  const textDrag = new page.w.Event('dragover', {bubbles: true, cancelable: true}); textDrag.dataTransfer = {types: ['text/plain']}; page.$('#chat-drop').dispatchEvent(textDrag); assert.equal(textDrag.defaultPrevented, false, 'dragging text is left alone');
});

test('a waiting file can be removed, and the ones left survive a reload of the page', async () => {
  page.click(chips()[2].querySelector('button')); await page.waitFor(() => chips().length === 3, 'removed'); assert.deepEqual({...posts('/chat-detach')[0].body}, {id: 'att-3'});
  const again = await loadPage(server);
  try { await again.eval('openProject("infect")'); await again.waitFor(() => again.$$('#chat-files .chat-file').length === 3, 'the waiting files again');
        assert.deepEqual(again.$$('#chat-files .chat-file').map((c) => c.dataset.id), ['att-1', 'att-2', 'att-4']); } finally { await again.close(); }
});

test('Send carries the files with the words; the message shows them and the compose box is empty again', async () => {
  page.$('#chat-text').value = 'make the runner look like the picture and see why it crashes';
  page.click(page.$('#chat-send')); await page.waitFor(() => posts('/chat').length === 1, 'the message');
  assert.deepEqual({...posts('/chat')[0].body}, {text: 'make the runner look like the picture and see why it crashes', attachments: ['att-1', 'att-2', 'att-4']});
  await page.waitFor(() => posts('/dispatch').length === 1 && chips('#chat-messages').length === 3, 'the turn dispatched and the message drawn');
  assert.equal(chips().length, 0); assert.equal(page.$('#chat-text').value, '');
  const mine = page.$('#chat-messages .chat-msg.user'); assert.match(mine.querySelector('.chat-text').textContent, /look like the picture/);
  assert.deepEqual([...mine.querySelectorAll('.chat-file-name')].map((n) => n.textContent), ['how it looks.txt', 'crash.log', 'image.png']);
  assert.equal(mine.querySelectorAll('.chat-file button').length, 0, 'a sent file is part of the conversation: it cannot be removed');
});

test('files alone are a message; nothing at all is not', async () => {
  page.click(page.$('#chat-send')); await page.waitFor(() => /Say something first/.test(page.toasts()), 'refused'); assert.equal(posts('/chat').length, 1);
  await page.eval(`chatAttach([${file('values.csv', 'damage,rate\n4,2\n')}])`); page.click(page.$('#chat-send'));
  await page.waitFor(() => posts('/chat').length === 2, 'sent'); assert.deepEqual({...posts('/chat')[1].body}, {text: '', attachments: ['att-5']});
  await page.waitFor(() => chips().length === 0, 'the box emptied once the server answered');   // the next test counts files from an empty box
});

test('at most six files per message, said before anything is uploaded', async () => {
  const n = posts('/chat-attach').length;
  await page.eval(`chatAttach([${Array.from({length: 8}, (_, i) => file(`n${i}.txt`, 'x')).join(', ')}])`);
  assert.equal(posts('/chat-attach').length - n, 6); assert.equal(chips().length, 6); assert.match(page.toasts(), /at most 6 files/);
});

test('the real server serves a picture inline and a text file only as a download', async () => {
  const get = async (rel) => { const r = await fetch(`${server.base}/api/project/infect/file?path=${encodeURIComponent(rel)}&token=${server.token}`); return [r.status, r.headers.get('content-type'), r.headers.get('content-disposition'), r.headers.get('x-content-type-options')]; };
  assert.deepEqual(await get('attachments/att-1.png'), [200, 'image/png', null, 'nosniff']);
  assert.deepEqual(await get('attachments/att-2.log'), [200, 'text/plain; charset=utf-8', 'attachment; filename="att-2.log"', 'nosniff']);
  assert.equal((await get('attachments/att-3.md'))[0], 404, 'a removed file is gone'); assert.equal((await get('attachments/../build.gradle'))[0], 404);
});

test('no native popup was used', () => assert.deepEqual(page.popups, []));
