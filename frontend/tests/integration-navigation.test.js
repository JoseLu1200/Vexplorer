import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
test('library retains navigation to the semantic explorer',()=>{
 const html=readFileSync(new URL('../index.html',import.meta.url),'utf8');
 assert.match(html, /data-panel-content="library"[\s\S]*?href="\.\/explorer\.html"/);
});
