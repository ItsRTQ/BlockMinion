import test from 'node:test';
import assert from 'node:assert/strict';
import {startServer, loadPage} from './harness.mjs';

// Pointing at cards from the chat: type @ and pick, or press Send to chat on the map. Real server; only `dispatch` is scripted.
let server, page;
const posts = (suffix) => page.calls.filter((c) => c.method === 'POST' && c.path.endsWith(suffix));
const btnOf = (root, label) => [...root.querySelectorAll('button')].find((b) => b.textContent.trim() === label);
const ta = () => page.$('#chat-text');
const type = async (text) => { ta().value = text; ta().selectionStart = ta().selectionEnd = text.length; ta().dispatchEvent(new page.w.Event('input', {bubbles: true})); await page.idle(); };
const options = () => page.$$('#chat-mention .mention-row').map((r) => r.querySelector('.r-where').textContent.split(' · ')[0]);
const points = (sel = '#chat-points') => page.$$(`${sel} .card-chip`).map((c) => c.querySelector('span').textContent);
const key = (k, init = {}) => { const e = new page.w.KeyboardEvent('keydown', {key: k, bubbles: true, cancelable: true, ...init}); ta().dispatchEvent(e); return e; };

test.before(async () => {
  server = await startServer(); page = await loadPage(server); page.overrides['/api/project/infect/dispatch'] = {started: true};
  await page.eval('openProject("infect")'); await page.idle();
});
test.after(async () => { if (page) await page.close(); if (server) server.stop(); });

test('typing @ opens the list of cards, narrowed by what follows; vanilla resources come last', async () => {
  assert.ok(page.hidden('#chat-mention')); await type('make @');
  assert.ok(!page.hidden('#chat-mention')); assert.equal(options().length, 8); assert.ok(!options().slice(0, 5).some((o) => o.startsWith('@vanilla:')), 'the mod\'s own things first');
  await type('make @spit'); assert.deepEqual(options(), ['@spitter', '@spitter_acid_spit']);
  assert.equal(page.$('#chat-mention .mention-row.on .r-title').textContent, 'Spitter'); assert.equal(page.$('#chat-mention').getAttribute('role'), 'listbox');
  await type('make @zzz'); assert.ok(page.hidden('#chat-mention'), 'nothing matches: no list');
  await type('mail rtq@spit'); assert.ok(page.hidden('#chat-mention'), 'an @ inside a word is not a mention');
});

test('arrows move, Enter picks without sending or adding a line, Escape closes', async () => {
  await type('make @spit'); key('ArrowDown'); assert.equal(page.$('#chat-mention .mention-row.on .r-title').textContent, 'Spitter acid spit');
  key('ArrowUp'); const enter = key('Enter'); await page.idle();
  assert.equal(enter.defaultPrevented, true); assert.equal(ta().value, 'make @spitter '); assert.ok(page.hidden('#chat-mention')); assert.equal(posts('/chat').length, 0);
  assert.deepEqual(points(), ['Spitter'], 'the box says what the message points at');
  await type('make @spitter and @bru'); assert.equal(key('Escape').defaultPrevented, true); assert.ok(page.hidden('#chat-mention')); assert.equal(ta().value, 'make @spitter and @bru');
  await type('make @spitter and @bru'); page.click(page.$('#chat-mention .mention-row')); await page.idle(); assert.equal(ta().value, 'make @spitter and @brute ');
  assert.deepEqual(points(), ['Spitter', 'Brute']);
});

test('what is not a card is just text: no chip, nothing blocked', async () => {
  await type('@Override in my log, @everyone, and @Runner'); assert.deepEqual(points(), ['Runner'], 'found whatever the case');
  await type('no mentions here'); assert.deepEqual(points(), []);
});

test('Send carries the text; the server reads the mentions and the message shows them as chips that lead to the map', async () => {
  await type('make @spitter spit farther than @brute can reach, see @Override'); page.click(page.$('#chat-send'));
  await page.waitFor(() => posts('/chat').length === 1 && points('#chat-messages .chat-msg.user').length === 2, 'sent and drawn');
  assert.deepEqual({...posts('/chat')[0].body}, {text: 'make @spitter spit farther than @brute can reach, see @Override'}, 'the words are the message: nothing hidden rides along');
  assert.deepEqual(points('#chat-messages .chat-msg.user'), ['Spitter', 'Brute']); assert.equal(ta().value, ''); assert.deepEqual(points(), []);
  page.click(page.$('#chat-messages .card-chip')); await page.waitFor(() => page.$('.tab.active').dataset.tab === 'map' && !page.hidden('#map-inspector'), 'the map, on that card');
  assert.equal(page.$('#map-inspector h3').textContent, 'Spitter');
});

test('Send to chat on a map card puts it in the message being written and brings the chat forward; nothing is sent', async () => {
  const n = posts('/chat').length; page.click(btnOf(page.$('#map-inspector'), 'Send to chat')); await page.idle();
  assert.equal(page.$('.tab.active').dataset.tab, 'chat'); assert.equal(ta().value, '@spitter '); assert.deepEqual(points(), ['Spitter']);
  assert.match(page.toasts(), /Added to your message\. Say what you want from it\./); assert.equal(posts('/chat').length, n, 'pointing is not asking');
  ta().value = 'about @spitter'; page.eval('chatPoint(["spitter", "runner"])'); await page.idle();
  assert.equal(ta().value, 'about @spitter @runner ', 'a card already in the message is not added twice');
});

test('Select cards on the map can send the whole selection to the chat', async () => {
  ta().value = ''; page.click(page.$('.tab[data-tab="map"]')); page.click(page.$('#map-multi')); await page.idle();
  page.eval('MapView.reveal("brute", {instant: true}); MapView.frame()'); const tap = (id) => { const g = page.$(`#map-svg .layer-cards .node[data-id="${id}"]`); g.dispatchEvent(new page.w.Event('pointerdown', {bubbles: true})); g.dispatchEvent(new page.w.Event('pointerup', {bubbles: true})); };
  tap('brute'); page.eval('MapView.reveal("runner", {instant: true}); MapView.frame()'); tap('runner'); await page.idle();
  page.click(btnOf(page.$('#map-side'), 'Send to chat (2)')); await page.idle();
  assert.equal(page.$('.tab.active').dataset.tab, 'chat'); assert.equal(ta().value, '@brute @runner '); assert.match(page.toasts(), /2 cards added to your message/);
});

test('no native popup was used', () => assert.deepEqual(page.popups, []));
