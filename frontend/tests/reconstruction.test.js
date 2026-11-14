import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { buildRefinement, clearProposal, createActionKeyStore, refinementAvailable, refinementQuestions } from '../reconstruction-state.js';

const reconstructionApp=await readFile(new URL('../reconstruction.js',import.meta.url),'utf8');

test('refinement transmits only answered questions and explicit finite dimensions', () => {
  assert.deepEqual(buildRefinement({
    answers: [{question:'Uso', answer:' banco '}, {question:'Unión', answer:' '}],
    intendedUse:' ', envelope:{width:'1200', depth:'', height:''},
  }), {answers:[{question:'Uso',answer:'banco'}], envelope_mm:{width:1200}});
  for (const width of ['NaN','Infinity','0','-1','100001']) {
    assert.throws(() => buildRefinement({answers:[], envelope:{width}}));
  }
  assert.throws(() => buildRefinement({answers:[], envelope:{}}));
});

test('clearProposal removes previous geometry, downloads and assessment before new result', () => {
  const nodes = {};
  for (const id of ['assessment','parts','preview','exploded','selected','parts-body',
                    'downloads','viewer','refine-section','partial-download']) {
    nodes[id] = {hidden:false, checked:true, disabled:false, textContent:'old',
      removeAttribute(key) { delete this[key]; },
      replaceChildren(){this.textContent='';}, src:'old'};
  }
  let disposed = false;
  clearProposal(id => nodes[id], {dispose(){disposed=true;}});
  assert.equal(disposed, true);
  assert.equal(nodes.parts.hidden, true);
  assert.equal(nodes.preview.hidden, true);
  assert.equal(nodes.preview.src, undefined);
  assert.equal(nodes.downloads.textContent, '');
  assert.equal(nodes.viewer.textContent, '');
  assert.equal(nodes.exploded.checked, false);
  assert.equal(nodes.exploded.disabled, true);
});

test('previous declarations stay editable after the model stops asking', () => {
  assert.deepEqual(refinementQuestions({clarifications:[{question:'Uso',answer:'Mesa'}]},
    {missing_information:['Montaje','Uso']}), [
      {question:'Montaje',answer:''},{question:'Uso',answer:'Mesa'},
    ]);
});

test('the third reconstruction revision does not offer a refinement the server will reject', () => {
  assert.equal(refinementAvailable({refinement_supported:true,revision:2}),true);
  assert.equal(refinementAvailable({refinement_supported:true,revision:3}),false);
  assert.equal(refinementAvailable({refinement_supported:false,revision:1}),false);
  assert.match(reconstructionApp,/refinementAvailable\(state\)/);
});

test('reconstruction actions reuse one idempotency key only for a retry of the same body', () => {
  let sequence=0;
  const keys=createActionKeyStore(()=>`action-${++sequence}`);
  const first={intended_use:'Cajonera'};
  assert.equal(keys.keyFor('generate',first),'action-1');
  assert.equal(keys.keyFor('generate',{intended_use:'Cajonera'}),'action-1');
  assert.equal(keys.keyFor('generate',{intended_use:'Armario'}),'action-2');
  const refineKey=keys.keyFor('refine',{answers:[{question:'Uso',answer:'Taller'}]});
  assert.equal(refineKey,'action-3');
  keys.complete('refine',refineKey);
  assert.equal(keys.keyFor('refine',{answers:[{question:'Uso',answer:'Taller'}]}),'action-4');
  assert.equal((reconstructionApp.match(/'Idempotency-Key':actionKey/g)??[]).length,2);
});
