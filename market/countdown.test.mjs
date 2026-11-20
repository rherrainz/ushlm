import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source = readFileSync(new URL('../static/market/countdown.js', import.meta.url), 'utf8');
function run(expires) {
  const button = {disabled:false, textContent:'Solicitar al prestador'};
  const timer = {dataset:{expires},textContent:''};
  const form = {dataset:{offerExpiry:expires}, querySelector:()=>button};
  vm.runInNewContext(source, {Date, document:{querySelectorAll:selector=>selector==='[data-expires]'?[timer]:[form]},setInterval:()=>{}});
  return {button,timer};
}
test('a real expired timestamp disables submission in the open form',()=>{
  const {button,timer}=run('2000-01-01T00:00:00Z');
  assert.equal(button.disabled,true);
  assert.equal(button.textContent,'Oferta vencida');
  assert.match(timer.textContent,/Vencida/);
});
test('a future persisted expiry keeps submission available',()=>{
  const {button,timer}=run(new Date(Date.now()+3600000).toISOString());
  assert.equal(button.disabled,false);
  assert.match(timer.textContent,/Vence en/);
});
