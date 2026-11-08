import test from 'node:test';
import assert from 'node:assert/strict';
import {startServer, loadPage, sleep} from './harness.mjs';

let server, page;
test.before(async () => { server = await startServer(); page = await loadPage(server); });
test.after(async () => { if (page) await page.close(); if (server) server.stop(); });

const open = () => !page.hidden('#dlg');
const buttons = () => page.$$('#dlg-actions button');
const press = (label) => page.click(buttons().find((b) => b.textContent === label));

test('confirmBox answers true on OK and false on Cancel, Escape and a click outside', async () => {
  let p = page.eval('confirmBox("Run it?", {title: "Run", ok: "Go"})'); await page.waitFor(open);
  assert.equal(page.$('#dlg-title').textContent, 'Run'); assert.equal(page.$('#dlg-body').textContent, 'Run it?'); assert.deepEqual(buttons().map((b) => b.textContent), ['Cancel', 'Go']);
  press('Go'); assert.equal(await p, true); assert.ok(!open());
  p = page.eval('confirmBox("Again?")'); await page.waitFor(open); press('Cancel'); assert.equal(await p, false);
  p = page.eval('confirmBox("Again?")'); await page.waitFor(open); page.key(page.$('#dlg'), 'Escape'); assert.equal(await p, false);
  p = page.eval('confirmBox("Again?")'); await page.waitFor(open); page.$('#dlg').dispatchEvent(new page.w.MouseEvent('mousedown', {bubbles: true})); assert.equal(await p, false);
  p = page.eval('confirmBox("Again?")'); await page.waitFor(open); page.key(page.$('#dlg-actions .primary'), 'Enter'); assert.equal(await p, true);
});

test('a destructive confirmation is styled as such', async () => {
  const p = page.eval('confirmBox("Remove it?", {danger: true, ok: "Remove"})'); await page.waitFor(open);
  assert.ok(page.$('#dlg-actions .danger')); press('Cancel'); await p;
});

test('promptBox returns the typed text, null when cancelled, and keeps the dialog open on an empty required field', async () => {
  let p = page.eval('promptBox("Name?", "Old", {title: "Rename"})'); await page.waitFor(open);
  const input = page.$('#dlg-body input'); assert.equal(input.value, 'Old'); assert.equal(page.w.document.activeElement, input);
  input.value = 'New'; press('OK'); assert.equal(await p, 'New');
  p = page.eval('promptBox("Name?", "Old")'); await page.waitFor(open); press('Cancel'); assert.equal(await p, null);
  p = page.eval('promptBox("Why?", "", {required: true, multiline: true})'); await page.waitFor(open);
  press('OK'); assert.ok(open(), 'an empty required field does not close it'); assert.match(page.$('.dlg-error').textContent, /cannot be empty/);
  const ta = page.$('#dlg-body textarea'); ta.value = 'because'; press('OK'); assert.equal(await p, 'because');
});

test('in a text area Enter writes a new line and Ctrl+Enter sends', async () => {
  const p = page.eval('promptBox("Notes", "", {multiline: true})'); await page.waitFor(open);
  const ta = page.$('#dlg-body textarea'); ta.value = 'line one'; page.key(ta, 'Enter'); assert.ok(open());
  page.key(ta, 'Enter', {ctrlKey: true}); assert.equal(await p, 'line one');
});

test('formBox returns every field, or null when cancelled', async () => {
  let p = page.eval('formBox({title: "Art", fields: [{name: "concept", label: "Concept", value: "a"}, {name: "tags", label: "Tags", multiline: true, value: "b"}], ok: "Save"})'); await page.waitFor(open);
  assert.deepEqual(page.$$('.dlg-label').map((n) => n.textContent), ['Concept', 'Tags']);
  page.$('#dlg-f-0').value = 'new concept'; press('Save'); assert.deepEqual({...(await p)}, {concept: 'new concept', tags: 'b'});
  p = page.eval('formBox({fields: [{name: "x", value: ""}]})'); await page.waitFor(open); page.key(page.$('#dlg'), 'Escape'); assert.equal(await p, null);
});

test('noticeBox has one button and closes on OK or Escape', async () => {
  let p = page.eval('noticeBox("Saved.")'); await page.waitFor(open); assert.deepEqual(buttons().map((b) => b.textContent), ['OK']); press('OK'); await p;
  p = page.eval('noticeBox("Saved.")'); await page.waitFor(open); page.key(page.$('#dlg'), 'Escape'); await p; assert.ok(!open());
});

test('dialogs queue: the second opens only after the first closes, in order', async () => {
  const order = [];
  const a = page.eval('confirmBox("first")').then((v) => order.push('first:' + v)), b = page.eval('confirmBox("second")').then((v) => order.push('second:' + v));
  await page.waitFor(open); assert.equal(page.$('#dlg-body').textContent, 'first'); press('OK'); await a;
  await page.waitFor(() => open() && page.$('#dlg-body').textContent === 'second'); press('Cancel'); await b;
  assert.deepEqual(order, ['first:true', 'second:false']);
});

test('the message is text: markup in it is never interpreted', async () => {
  const p = page.eval('confirmBox("<img src=x onerror=alert(1)> <b>bold</b>")'); await page.waitFor(open);
  assert.equal(page.$$('#dlg-body img, #dlg-body b').length, 0); assert.match(page.$('#dlg-body').textContent, /<img src=x/); press('Cancel'); await p;
});

test('focus goes back to what had it, and Tab stays inside the dialog', async () => {
  const outside = page.$('#nav-env'); outside.focus();
  const p = page.eval('confirmBox("Focus?")'); await page.waitFor(open);
  const [cancel, ok] = buttons(); ok.focus(); const tab = new page.w.KeyboardEvent('keydown', {key: 'Tab', bubbles: true, cancelable: true}); ok.dispatchEvent(tab);
  assert.ok(tab.defaultPrevented); assert.equal(page.w.document.activeElement, cancel);
  press('Cancel'); await p; assert.equal(page.w.document.activeElement, outside);
});

test('while a dialog is open the refresh guard says the page is busy', async () => {
  assert.equal(page.eval('Guard.busy()'), false);
  const p = page.eval('confirmBox("busy?")'); await page.waitFor(open); assert.equal(page.eval('Guard.busy()'), true); press('Cancel'); await p;
  assert.equal(page.eval('Guard.busy()'), false);
});

test('the page never used a native popup', () => { assert.deepEqual(page.popups, []); });
