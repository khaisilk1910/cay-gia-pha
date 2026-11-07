/** Basic no-browser smoke test for Lovelace custom card registration and contract. */
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const registered = new Map();
globalThis.window = { customCards: [] };
globalThis.HTMLElement = class {
  attachShadow() {
    this.shadowRoot = {
      addEventListener() {},
      querySelector() { return null; },
      childElementCount: 0,
    };
  }
};
globalThis.ResizeObserver = class {
  observe() {}
  disconnect() {}
};
globalThis.customElements = {
  get(name) { return registered.get(name); },
  define(name, klass) {
    assert.equal(registered.has(name), false, `Duplicate registration: ${name}`);
    registered.set(name, klass);
  },
};

const source = await readFile(new URL('../custom_components/cay_gia_pha/frontend/cay-gia-pha-card.js', import.meta.url), 'utf8');
// Data URL guarantees that the source runs as an ES module, independent of package.json.
const url = `data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`;
await import(url);
assert.ok(registered.has('cay-gia-pha-card'));
assert.ok(registered.has('cay-gia-pha-card-editor'));
assert.equal(window.customCards.filter((card) => card.type === 'cay-gia-pha-card').length, 1);
const card = new (registered.get('cay-gia-pha-card'))();
const grid = card.getGridOptions();
assert.ok(grid.columns >= grid.min_columns);
assert.ok(grid.rows >= grid.min_rows);
assert.ok(card.getCardSize() > 0);
card._render = () => {};
card._maybeLoadTree = () => {};
card.setConfig({ title: 'Gia phả kiểm thử' });
assert.equal(card._config.title, 'Gia phả kiểm thử');
assert.throws(() => card.setConfig([]), /không hợp lệ/);
assert.ok(source.includes('config-changed'));
assert.ok(!source.includes('ha-selector-file.prototype'), 'Global HA UI prototype mutation is forbidden');
console.log('Lovelace custom card API smoke checks passed');
