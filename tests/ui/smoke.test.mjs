import test from 'node:test';
import assert from 'node:assert/strict';
import {startServer, loadPage} from './harness.mjs';

let server, page;
test.before(async () => { server = await startServer(); page = await loadPage(server); await page.eval('openProject("infect")'); });
test.after(async () => { if (page) await page.close(); if (server) server.stop(); });
const tab = (name) => page.click(page.$(`.tab[data-tab="${name}"]`));
const sub = (name) => page.click(page.$(`.subtab[data-sub="${name}"]`));
const dlgOpen = () => !page.hidden('#dlg');
const post = (path) => page.calls.filter((c) => c.method === 'POST' && c.path.endsWith(path));
const buttonOf = (root, label) => [...root.querySelectorAll('button')].find((b) => b.textContent.trim() === label);

test('the page boots against the real server with no error toast', () => { assert.ok(!page.toasts().includes('failed to render'), page.toasts()); assert.equal(page.$('#p-name').textContent, 'Infectious Zombies'); });

test('the Spec tab lists the behaviors, and the capability shows who carries it as toggles', async () => {
  tab('spec'); const box = page.$('#spec-body'); assert.match(box.textContent, /Behaviors the coder builds after generation \(5\)/);
  const infection = [...box.querySelectorAll('.behavior')].find((b) => b.textContent.includes('Infection') && b.textContent.includes('capability'));
  assert.ok(infection, 'the Infection capability is shown'); assert.deepEqual([...infection.querySelectorAll('.carriers button')].map((b) => b.textContent), ['✓ Runner', '✓ Spitter', '✓ Brute']);
});

test('the Mobs tab shows each mob with its body plan, its art direction and a working Art button', async () => {
  tab('features'); sub('mobs'); await page.waitFor(() => page.$$('[data-focus^="mob:"]').length === 3, 'three mob cards');
  const brute = page.$('[data-focus="mob:brute"]'); assert.match(brute.querySelector('h4').textContent, /Brute\s*·\s*hostile\s*·\s*primate/);
  assert.match(brute.querySelector('.art-concept').textContent, /chimpanzee/); assert.ok(buttonOf(brute, 'Art'));
  assert.match(page.$('[data-focus="mob:runner"] h4').textContent, /biped/);
});

test('Art opens one form in the page style; Cancel changes nothing and Save writes it', async () => {
  const brute = page.$('[data-focus="mob:brute"]'); const before = post('/set-art').length;
  page.click(buttonOf(brute, 'Art')); await page.waitFor(dlgOpen, 'the art form');
  assert.match(page.$('#dlg-title').textContent, /Art direction: Brute/); assert.equal(page.$$('#dlg-body .dlg-field').length, 2);
  page.click(buttonOf(page.$('#dlg'), 'Cancel')); await page.waitFor(() => !dlgOpen()); assert.equal(post('/set-art').length, before);
  page.click(buttonOf(brute, 'Art')); await page.waitFor(dlgOpen);
  page.$('#dlg-f-0').value = 'A hulking chimpanzee zombie with a cracked tusk'; page.$('#dlg-f-1').value = 'knuckle-walking, cracked tusk, scarred hide';
  page.click(buttonOf(page.$('#dlg'), 'Save art direction')); await page.waitFor(() => post('/set-art').length === before + 1, 'the save');
  const sent = post('/set-art').at(-1).body; assert.deepEqual([sent.kind, sent.identifier, sent.tags], ['mob', 'brute', ['knuckle-walking', 'cracked tusk', 'scarred hide']]);
  await page.waitFor(() => /cracked tusk/.test(page.$('[data-focus="mob:brute"] .art-tags')?.textContent || ''), 'the card to show the new art');
  assert.match(page.$('[data-focus="mob:brute"] .art-source').textContent, /written/);
});

test('running an agent asks in the page style, names the runtime in use, and Cancel starts nothing', async () => {
  tab('activity'); const run = await page.waitFor(() => buttonOf(page.$('#now'), 'Run agent') || buttonOf(page.$('#now'), 'Run'), 'a Run button in Now');
  const before = post('/dispatch').length; page.click(run); await page.waitFor(dlgOpen, 'the confirmation');
  assert.match(page.$('#dlg-title').textContent, /Run an agent/); assert.match(page.$('#dlg-body').textContent, /Start ONE Claude Code worker for/);
  page.click(buttonOf(page.$('#dlg'), 'Cancel')); await page.waitFor(() => !dlgOpen()); assert.equal(post('/dispatch').length, before);
});

test('the runtime named in that question follows the runtime selector', async () => {
  page.eval('runtimeId = "antigravity-cli"'); tab('activity'); await page.eval('refreshProject("infect")');
  const run = buttonOf(page.$('#now'), 'Run agent') || buttonOf(page.$('#now'), 'Run'); page.click(run); await page.waitFor(dlgOpen);
  assert.match(page.$('#dlg-body').textContent, /Start ONE Antigravity CLI worker/); assert.match(page.$('#dlg-body').textContent, /Uses your installed Antigravity CLI/);
  page.click(buttonOf(page.$('#dlg'), 'Cancel')); await page.waitFor(() => !dlgOpen());
});

test('removing an item asks first, and the question looks dangerous', async () => {
  page.click(page.$('#project-list .proj[data-pid="draft"]')); await page.waitFor(() => page.$('#p-name').textContent === 'Draft Opal');
  tab('features'); sub('items'); const remove = await page.waitFor(() => buttonOf(page.$('#sub-items'), 'Remove'), 'a Remove button');
  const before = post('/remove-feature').length; page.click(remove); await page.waitFor(dlgOpen);
  assert.ok(page.$('#dlg-actions .danger')); assert.match(page.$('#dlg-body').textContent, /Remove (opal|jade) from the spec/);
  page.click(buttonOf(page.$('#dlg'), 'Cancel')); await page.waitFor(() => !dlgOpen()); assert.equal(post('/remove-feature').length, before);
});

test('every item row has Art and Redesign buttons and its art direction line', async () => {
  page.click(page.$('#project-list .proj[data-pid="quiet"]')); await page.waitFor(() => page.$('#p-name').textContent === 'Quiet Gems'); tab('features'); sub('items');
  await page.waitFor(() => page.$$('#sub-items .feature').length >= 2, 'the item rows'); const rows = page.$$('#sub-items .feature');
  for (const r of rows) { assert.ok(buttonOf(r, 'Art'), 'Art'); assert.ok(buttonOf(r, 'Redesign'), 'Redesign'); assert.ok(r.querySelector('.art-concept').textContent.length > 10, 'the art line'); }
});

test('the Environment view still draws, with the runtime selector', async () => {
  page.click(page.$('#nav-env')); await page.waitFor(() => page.$('#env-provider') && page.$('#env-provider').options.length >= 3, 'the runtime options');
  assert.ok([...page.$('#env-provider').options].some((o) => /Antigravity/.test(o.textContent)));
});

test('across the whole tour the page used no native popup and raised no render error', () => { assert.deepEqual(page.popups, []); assert.ok(!/failed to render/.test(page.toasts()), page.toasts()); });
