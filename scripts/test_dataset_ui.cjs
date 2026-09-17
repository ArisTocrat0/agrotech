const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('web/app.js','utf8');
const events=[];
const context=vm.createContext({
 t:s=>s,translateMessage:s=>s,renderResults(){},notice:s=>events.push(['notice',s]),
 showError:s=>events.push(['error',s]),tab:s=>events.push(['tab',s]),
 trainingPanel:{parentElement:{open:false}},fullTraining:{focus:()=>events.push(['focus'])},
 refreshTraining:async()=>events.push(['refresh']),
 api:async(url,options)=>{events.push(['api',url,options.method]);return {train_images:2,val_images:1};}
});
vm.runInContext("let datasetPreparing=false,selected='abc';"+source.slice(source.indexOf('async function prepareDataset()')),context);
(async()=>{
 await vm.runInContext('Promise.all([prepareDataset(),prepareDataset()])',context);
 assert.equal(events.filter(e=>e[0]==='api').length,1);
 assert.deepEqual(events.find(e=>e[0]==='api'),['api','/api/jobs/abc/dataset','POST']);
 assert.deepEqual(events.find(e=>e[0]==='tab'),['tab','setup']);
 assert.equal(context.trainingPanel.parentElement.open,true);
 assert.equal(vm.runInContext('datasetPreparing',context),false);
 events.length=0;
 context.api=async()=>{throw Error('not enough images');};
 await vm.runInContext('prepareDataset()',context);
 assert.deepEqual(events.find(e=>e[0]==='error'),['error','not enough images']);
 assert.equal(events.some(e=>e[0]==='tab'),false);
 assert.equal(vm.runInContext('datasetPreparing',context),false);
 console.log('PASS: dataset CTA, duplicate-submit guard, training refresh, error recovery');
})().catch(error=>{console.error(error);process.exitCode=1;});
