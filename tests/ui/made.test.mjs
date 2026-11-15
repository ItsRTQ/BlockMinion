import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdirSync, writeFileSync} from 'node:fs';
import path from 'node:path';
import {startServer, loadPage} from './harness.mjs';

// Other content: what is in the mod's code beyond the spec. Found by reading the source, adopted by the user, then a card like any other.
let server, page;
const posts = (suffix) => page.calls.filter((c) => c.method === 'POST' && c.path.endsWith(suffix));
const btnOf = (root, label) => [...root.querySelectorAll('button')].find((b) => b.textContent.trim() === label);
const rows = (sel) => page.$$(`${sel} .made-row`).map((r) => r.dataset.id);

test.before(async () => {
  server = await startServer();
  const dir = path.join(server.home, 'projects/infect/src/main/java/com/example/infect/entity'); mkdirSync(dir, {recursive: true});   // what a coder left behind without declaring it
  writeFileSync(path.join(dir, 'Leftovers.java'), `class Leftovers {
  static final Object GLOB = Registry.register(BuiltInRegistries.ENTITY_TYPE, ResourceLocation.fromNamespaceAndPath("infect", "acid_glob"), null);
  static final Object HISS = Registry.register(BuiltInRegistries.SOUND_EVENT, ResourceLocation.fromNamespaceAndPath("infect", "spitter_hiss"), null);
  // Registry.register(BuiltInRegistries.ITEM, ResourceLocation.fromNamespaceAndPath("infect", "commented_out"), null);
}\n`);
  page = await loadPage(server); await page.eval('openProject("infect")'); await page.idle();
  page.click(page.$('.tab[data-tab="features"]')); page.click(page.$('.subtab[data-sub="made"]')); await page.idle();
});
test.after(async () => { if (page) await page.close(); if (server) server.stop(); });

test('Features has an Other content section listing what coders declared, even from before this list existed', () => {
  assert.ok(!page.$('#sub-made').classList.contains('hidden')); assert.deepEqual(rows('#made-list'), ['bile_glob'], 'the seeded project\'s coder declared a glob long ago: it is here');
  const row = page.$('#made-list .made-row[data-id="bile_glob"]'); assert.match(row.textContent, /bile glob\s*projectile/); assert.match(row.textContent, /declared by the coder · made by /);
  assert.equal(row.querySelector('.fname').draggable, true, 'it can be dragged to the chat'); assert.equal(page.$('#made-scan').disabled, false);
});

test('looking in the code lists what is registered and tracked by nothing, with where it is', async () => {
  page.click(page.$('#made-scan')); await page.waitFor(() => rows('#made-found').length === 2, 'the two leftovers');
  assert.deepEqual(rows('#made-found'), ['acid_glob', 'spitter_hiss']); assert.match(page.$('#made-found').textContent, /2 are tracked by nothing/);
  const glob = page.$('#made-found .made-row[data-id="acid_glob"]');
  assert.match(glob.textContent, /entity type · src\/main\/java\/com\/example\/infect\/entity\/Leftovers\.java:2/); assert.equal(glob.querySelector('select[aria-label="What it is"]').value, 'entity');
  assert.ok(!/commented_out/.test(page.$('#made-found').textContent), 'commented-out code is not content');
  assert.ok([...glob.querySelector('select[aria-label="The feature it belongs to"]').options].some((o) => o.value === 'spitter_acid_spit'), 'the mod\'s features are offered as its owner');
});

test('Adopt makes it tracked content with the kind and the feature the user chose; Ignore puts the other away', async () => {
  const glob = page.$('#made-found .made-row[data-id="acid_glob"]'); glob.querySelector('select[aria-label="What it is"]').value = 'projectile'; glob.querySelector('select[aria-label="The feature it belongs to"]').value = 'spitter_acid_spit';
  page.click(btnOf(glob, 'Adopt')); await page.waitFor(() => rows('#made-list').includes('acid_glob'), 'adopted');
  assert.deepEqual({...posts('/made-adopt')[0].body}, {id: 'acid_glob', kind: 'projectile', card: 'spitter_acid_spit'});
  const row = page.$('#made-list .made-row[data-id="acid_glob"]'); assert.match(row.textContent, /acid glob\s*projectile/); assert.match(row.textContent, /found in the code, adopted by you · made by spitter_acid_spit/);
  page.click(btnOf(page.$('#made-found .made-row[data-id="spitter_hiss"]'), 'Ignore')); await page.waitFor(() => /Ignored when looking in the code: spitter_hiss/.test(page.$('#made-list').textContent), 'ignored');
  page.click(page.$('#made-scan')); await page.waitFor(() => /0 are tracked by nothing/.test(page.$('#made-found').textContent), 'nothing left'); assert.deepEqual(rows('#made-found'), []);
});

test('the adopted thing is a card of the map, made by its feature, and can be pointed at from the chat', async () => {
  page.click(btnOf(page.$('#made-list .made-row[data-id="acid_glob"]'), 'Show on the map'));
  await page.waitFor(() => page.$('.tab.active').dataset.tab === 'map' && !page.hidden('#map-inspector') && page.$('#map-inspector h3').textContent === 'Acid glob', 'its card');
  const note = page.$('#map-inspector'); assert.match(note.querySelector('.eyebrow').textContent, /^projectile/);
  assert.match(note.textContent, /Made by\s*Spitter acid spit/); assert.match(note.textContent, /found in the code and adopted \(entity type registry\)/);
  assert.match(note.textContent, /← makes\s*Spitter acid spit/); assert.equal(page.eval('MapCore.KIND_PLURAL.projectile'), 'Projectiles');
  page.click(btnOf(note, 'Send to chat')); await page.idle(); assert.equal(page.$('#chat-text').value, '@acid_glob '); assert.equal(page.$$('#chat-points .card-chip').length, 1);
});

test('no native popup was used', () => assert.deepEqual(page.popups, []));
