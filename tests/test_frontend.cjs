// Focused UI regression checks against the real application functions.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const elements = new Map();
const element = (key) => {
  if (!elements.has(key)) elements.set(key, {value:'',textContent:'',innerHTML:'',className:'',disabled:false});
  return elements.get(key);
};
const context = vm.createContext({
  document: {querySelector:element}, window:{addEventListener(){}},
  fetch:async () => ({ok:true,json:async () => []}),
  confirm:() => true, console
});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../static/app.js'), 'utf8'), context);

(async () => {
  // Let the startup fetch settle before exercising stateful functions.
  await new Promise((resolve) => setImmediate(resolve));
  context.fixture = {excerpt_parts:[{text:'<img onerror=alert(1)> ',highlight:false},
    {text:'VIBRACIÓN & <script>',highlight:true}]};
  const html = vm.runInContext('renderExcerpt(fixture)', context);
  assert.equal(html, '&lt;img onerror=alert(1)&gt; <mark class="search-highlight">VIBRACIÓN &amp; &lt;script&gt;</mark>');
  assert.equal(vm.runInContext('renderExcerpt({excerpt:"<script>old API</script>"})', context),
    '&lt;script&gt;old API&lt;/script&gt;');

  const notes = element('#notes'); notes.value = 'Cambios todavía sin guardar';
  element('#case-status').value = 'En investigación';
  element('#search-results').textContent = 'Old result';
  vm.runInContext('state.selected=7; state.current={documents:[{id:9,name:"temporary.txt"}]}; state.dirty=true;', context);
  const button = {dataset:{deleteDocument:'9'},disabled:false};
  context.event = {target:{closest:() => button}};
  let calls = [];
  context.fetch = async (url, options={}) => { calls.push([url,options.method]); return {ok:true,json:async () => []}; };
  context.confirm = () => false;
  await vm.runInContext('deleteDocument(event)', context);
  assert.equal(calls.length, 0, 'Cancelling must not send a DELETE');
  assert.equal(vm.runInContext('state.current.documents.length', context), 1);
  context.confirm = () => true;
  await vm.runInContext('deleteDocument(event)', context);
  assert.deepEqual(calls[0], ['/api/incidents/7/documents/9','DELETE']);
  assert.equal(vm.runInContext('state.current.documents.length', context), 0);
  assert.equal(element('#document-count').textContent, '0 adjunto(s)');
  assert.equal(element('#search-results').textContent, '');
  assert.equal(notes.value, 'Cambios todavía sin guardar');
  assert.equal(element('#case-status').value, 'En investigación');
  assert.equal(vm.runInContext('state.dirty', context), true);
  element('#case-status').value = 'Resuelta';
  vm.runInContext('syncClosureFields()', context);
  assert.equal(element('#closure-panel').open, true);
  assert.equal(element('#closure-verification').required, true);
  element('#case-status').value = 'En investigación';
  vm.runInContext('syncClosureFields()', context);
  assert.equal(element('#closure-verification').required, false);
  assert.match(vm.runInContext('closureForm({status:"Resuelta",conclusion:"<script>bad</script>"})', context), /&lt;script&gt;bad&lt;\/script&gt;/);
  console.log('Frontend OK: safe highlighting, cancellation, deletion, preserved unsaved review.');
})().catch((error) => { console.error(error); process.exitCode = 1; });
