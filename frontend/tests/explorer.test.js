import test from 'node:test';
import assert from 'node:assert/strict';
import { filterPoints, mapCoordinates, createRequestGate, overlap, counterpart } from '../core/explorer.js';

test('metadata filtering is case insensitive and preserves original point coordinates', () => {
  const point = {id:'a',label:'Mesa Álamo',category:'table',x:0.2,y:0.3};
  assert.deepEqual(filterPoints([point], 'álamo', 'table'), [point]);
  assert.deepEqual(filterPoints([point], '', 'chair'), []);
  assert.equal(filterPoints([point], '<img onerror=alert(1)>').length, 0);
});

test('degenerate map points stay coincident and fit stays finite', () => {
  const coords = mapCoordinates([{id:'a',x:0,y:0},{id:'b',x:0,y:0}]);
  assert.deepEqual(coords[0].position, coords[1].position);
  assert.deepEqual(coords[0].position, [400,260]);
  assert.deepEqual(mapCoordinates([]), []);
});

test('late search response cannot overwrite a changed selection', () => {
  const gate = createRequestGate();
  const old = gate.next(); const current = gate.next();
  assert.equal(gate.current(old), false);
  assert.equal(gate.current(current), true);
});

test('model comparison requires shared content rather than coinciding local ids', () => {
  assert.equal(counterpart({id:'same',content_hash:'abc'}, [{id:'same',content_hash:'different'}]), null);
  assert.equal(counterpart({id:'first',content_hash:'abc'}, [{id:'second',content_hash:'abc'}]).id, 'second');
  assert.equal(counterpart({id:'first'}, [{id:'first'}]), null);
  assert.deepEqual(overlap([{content_hash:'a'},{content_hash:'b'}], [{content_hash:'b'},{content_hash:'c'}]), {shared:1,total:3});
});
