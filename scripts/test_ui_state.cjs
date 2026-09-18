'use strict';
const {readFileSync}=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const context=vm.createContext({});
vm.runInContext(readFileSync('web/client.js','utf8'),context);
const evaluate=code=>JSON.parse(JSON.stringify(vm.runInContext(code,context)));
vm.runInContext(`const rows=[{detections:[{review:'weed'},{}]},{detections:[]},{detections:[{review:'unknown'},{review:'crop'},{review:'not_plant'}]}];`,context);
assert.deepEqual(evaluate('reviewMetrics(rows)'),{total:5,pending:2,reviewed:3,corrected:0,recognized:0,uncertain:0,confirmed:1,percent:60});
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

const automaticMetrics=evaluate("reviewMetrics([{mode:'automatic',detections:[{species:'Бодяк',kind:'weed',prediction_status:'recognized'},{species:'Бодяк',kind:'unknown',prediction_status:'uncertain',uncertainty_reasons:['unsupported_crop']},{species:'unknown',kind:'crop',prediction_status:'uncertain',review:'weed',review_status:'corrected',manual_correction:true}]}])");
assert.deepEqual(automaticMetrics,{total:3,pending:1,reviewed:1,corrected:1,recognized:1,uncertain:2,confirmed:1,percent:33});
console.log('PASS: automatic counters separate recognized, uncertain and manual corrections');

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

// Automatic results must not present model decisions as manual confirmations.
const autoElements=new Map();
const element=()=>({textContent:'',innerHTML:'',disabled:false,firstChild:{textContent:''},addEventListener(){},querySelector(selector){this.children??={};return this.children[selector]??=element();}});
const autoContext=vm.createContext({
 $:id=>{if(!autoElements.has(id))autoElements.set(id,element());return autoElements.get(id);},
 t:x=>x,number:String,escapeHTML:x=>String(x),
 metricElements:[element(),element(),element(),element()],pendingCard:element(),dashboardReview:element(),
 results:[{mode:'automatic',crop:'Пшеница',crop_supported:false,detections:[{kind:'unknown'}],learning_report:{accuracy:.98,balanced_accuracy:.97,count:110,coverage:.8}}]
});
vm.runInContext(app.slice(app.indexOf('function renderAutomaticResults()')),autoContext);
vm.runInContext('renderAutomaticResults()',autoContext);
assert.equal(autoElements.get('stat-species').textContent,'0');
assert.equal(autoElements.get('stat-pending').textContent,'1');
assert.equal(autoElements.get('stat-unknown').textContent,'0');
assert.match(autoContext.dashboardReview.innerHTML,/обучающих примеров/);
assert.match(autoContext.dashboardReview.innerHTML,/на поле: не измерена/);
assert.equal(autoElements.get('download-pseudo').disabled,true);
assert.match(autoElements.get('review-queue').innerHTML,/по желанию/);
console.log('PASS: automatic results, missing crop data, optional review, honest quality report');
