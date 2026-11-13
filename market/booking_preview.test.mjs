import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

const source = readFileSync(new URL('../static/market/booking-preview.js', import.meta.url), 'utf8');
function preview(value, currency = 'ARS') {
  let onInput;
  const input = { value, addEventListener: (_, listener) => { onInput = listener; } };
  const output = { textContent: '' };
  const form = { dataset: {unitCents: '1999', currency},
    querySelector: selector => selector === '[name="quantity"]' ? input : output };
  runInNewContext(source, {document: {querySelectorAll: () => [form]}});
  return { input, output, change: value => { input.value = value; onInput(); } };
}

test('19.99 × 3 is exactly 59.97 and updates when quantity changes', () => {
  const result = preview('3');
  assert.equal(result.output.textContent, 'ARS 59,97');
  result.change('2');
  assert.equal(result.output.textContent, 'ARS 39,98');
});

test('currency comes from the offer and large totals keep their cents', () => {
  assert.equal(preview('1', 'USD').output.textContent, 'USD 19,99');
  assert.equal(preview('2147483647').output.textContent, 'ARS 42928198103,53');
});

test('invalid quantities do not display a misleading total', () => {
  for (const quantity of ['', '0', '-1', '1.5', 'abc', '2147483648']) {
    assert.equal(preview(quantity).output.textContent, 'Ingresá una cantidad entera positiva');
  }
});
