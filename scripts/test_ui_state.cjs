'use strict';
const {readFileSync}=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const context=vm.createContext({});
vm.runInContext(readFileSync('web/client.js','utf8'),context);
const evaluate=code=>JSON.parse(JSON.stringify(vm.runInContext(code,context)));
vm.runInContext(`const rows=[{detections:[{review:'weed'},{}]},{detections:[]},{detections:[{review:'unknown'},{review:'crop'},{review:'not_plant'}]}];`,context);
assert.deepEqual(evaluate('reviewMetrics(rows)'),{total:5,pending:2,reviewed:3,confirmed:1,percent:60});
assert.deepEqual(evaluate('pendingTarget(rows)'),{image:0,detection:1});
assert.deepEqual(evaluate('pendingTarget(rows,0,1)'),{image:2,detection:0});
assert.deepEqual(evaluate('pendingTarget(rows,2,0)'),{image:0,detection:1});
assert.equal(evaluate("pendingTarget([{detections:[{review:'weed'}]}])"),null);
assert.equal(evaluate('pendingTarget([])'),null);
assert.equal(evaluate('reviewMetrics([{detections:[]}]).percent'),100);
// Ensure every literal translation key used by the views exists in both languages.
const i18n=readFileSync('web/i18n.js','utf8').split("let language = 'ru';")[0];
vm.runInContext(i18n,context);
for(const file of ['app.js','review.js','settings.js','client.js']){
 const source=readFileSync('web/'+file,'utf8');
 for(const match of source.matchAll(/\bt\((['"])(.*?)\1\)/g)){
   const key=match[2];
   assert.equal(vm.runInContext(`Boolean(translations[${JSON.stringify(key)}]?.en && translations[${JSON.stringify(key)}]?.kk)`,context),true,`${file}: missing ${key}`);
 }
}
console.log('PASS: KPI, unresolved decisions, cross-image traversal, empty results, RU/EN/KZ keys');

// Execute the actual upload-state renderer with lightweight element doubles.
const elements=new Map();
context.$=id=>{if(!elements.has(id))elements.set(id,{});return elements.get(id);};
context.document={querySelectorAll:()=>[]};context.t=x=>x;context.locale=()=> 'en-US';
const app=readFileSync('web/app.js','utf8');
vm.runInContext("let files=[{size:1024}],busy=false,uploading=false;"+app.slice(app.indexOf('function updateFiles('),app.indexOf('function addFiles(')),context);
vm.runInContext('updateFiles(false)',context);assert.equal(elements.get('start-analysis').disabled,false);
vm.runInContext('uploading=true;updateFiles(false)',context);assert.equal(elements.get('start-analysis').disabled,true);assert.equal(elements.get('file-input').disabled,true);
vm.runInContext('uploading=false;busy=true;updateFiles(false)',context);assert.equal(elements.get('start-analysis').disabled,true);
vm.runInContext('busy=false;files=[];updateFiles(false)',context);assert.equal(elements.get('start-analysis').disabled,true);
console.log('PASS: upload and running states prevent repeat analysis');

// Execute decision saving: inspect the API payload and ensure double clicks do not POST twice.
const review=readFileSync('web/review.js','utf8');
const calls=[];
const saveContext=vm.createContext({
 $:()=>({textContent:''}),t:x=>x,translateMessage:x=>x,
 renderReview(){},renderResults(){},
 api:async(url,options)=>{calls.push({url,...JSON.parse(options.body)});return [{detections:[{id:17,review:'weed'}]}];}
});
vm.runInContext("let reviewSaving=false,selected='job',reviewJob='job',reviewImage=0,reviewDetection=0,results=[{detections:[{id:17}]}];"+review.slice(review.indexOf('async function decide('),review.indexOf("document.querySelectorAll('[data-decision]').forEach(button=>button.addEventListener")),saveContext);
(async()=>{
 await vm.runInContext("Promise.all([decide('weed'),decide('crop')])",saveContext);
 assert.deepEqual(calls,[{url:'/api/jobs/job/review',image:0,detection:17,decision:'weed'}]);
 assert.equal(vm.runInContext('reviewSaving',saveContext),false);
 assert.equal(vm.runInContext("results[0].detections[0].review",saveContext),'weed');
 console.log('PASS: review save payload, response and duplicate-submit guard');
})().catch(error=>{console.error(error);process.exitCode=1;});
