import test from 'node:test';
import assert from 'node:assert/strict';
import { buildRefinement, clearProposal, refinementQuestions, parentRevisionUrl } from '../reconstruction-state.js';

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

test('parent navigation preserves embedded mode and the source run', () => {
  const params = new URLSearchParams('run=run-1&embedded=1&job=child');
  assert.equal(parentRevisionUrl(params, 'parent'), '?run=run-1&embedded=1&job=parent');
  assert.equal(params.get('job'), 'child');
});
