/* Isolated headless Chrome QA of our own local app; never attaches to user tabs. */
const fs=require('node:fs/promises'),os=require('node:os'),path=require('node:path'),{spawn}=require('node:child_process');
const root=path.resolve(__dirname,'..'),base=process.env.ECOKINEU_QA_URL||'http://127.0.0.1:8010';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function main(){
 const profile=await fs.mkdtemp(path.join(os.tmpdir(),'ecokineu-headless-'));
 const out=path.join(root,'outputs/pilot-browser-qa');await fs.mkdir(out,{recursive:true});
 const chrome=spawn('/usr/bin/google-chrome',['--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--remote-debugging-address=127.0.0.1','--user-data-dir='+profile,'about:blank'],{stdio:['ignore','ignore','pipe']});
 let stderr='',ws,seq=0;const pending=new Map(),errors=[];
 const deadline=Date.now()+20000;
 const endpoint=new Promise((resolve,reject)=>{chrome.stderr.on('data',b=>{stderr+=b;const m=stderr.match(/DevTools listening on (ws:\/\/[^\s]+)/);if(m)resolve(m[1])});chrome.on('exit',code=>reject(Error('Chrome exited '+code+': '+stderr.slice(-1200))));setTimeout(()=>reject(Error('Chrome startup timeout: '+stderr.slice(-1200))),20000).unref()});
 try{
 ws=new WebSocket(await endpoint);await new Promise((r,j)=>{ws.onopen=r;ws.onerror=j});
 ws.onmessage=event=>{const m=JSON.parse(event.data);if(m.id){const p=pending.get(m.id);if(p){pending.delete(m.id);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result)}}else if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.text+': '+(m.params.exceptionDetails.exception?.description||''))};
 const send=(method,params={},sessionId)=>new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params,...(sessionId?{sessionId}:{})}))});
 const {targetId}=await send('Target.createTarget',{url:'about:blank'});const {sessionId}=await send('Target.attachToTarget',{targetId,flatten:true});
 const c=(m,p={})=>send(m,p,sessionId);
 await c('Runtime.enable');await c('Page.enable');await c('Emulation.setDeviceMetricsOverride',{width:1440,height:1050,deviceScaleFactor:1,mobile:false});
 const value=async expression=>{const r=await c('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value};
 async function wait(expression,seconds=20){const until=Date.now()+seconds*1000;while(Date.now()<until){if(await value(expression))return;await sleep(100)}throw Error('UI wait timeout: '+expression)}
 async function shot(name){const r=await c('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await fs.writeFile(path.join(out,name+'.png'),Buffer.from(r.data,'base64'))}
 await c('Page.navigate',{url:base});await wait("document.getElementById('database')?.textContent.includes('MariaDB')");
 if(await value("!document.getElementById('notice').hidden"))throw Error('UI notice: '+await value("document.getElementById('notice').textContent"));
 if(!await value("document.getElementById('trash-availability').textContent.includes('временно недоступно')"))throw Error('Missing trash unavailable banner');
 await wait("fetch('/api/pilot/photos').then(r=>r.json()).then(x=>Number(document.getElementById('count-all').textContent)===x.photos.length)");await shot('01-overview');await value("document.querySelector('[data-tab=upload]').click()");await shot('02-upload');
 const mission=process.env.ECOKINEU_QA_MISSION||'browser-qa-real-photo';await value(`document.querySelector('[name=mission]').value=${JSON.stringify(mission)};document.querySelector('[name=metadata]').value='{"qa":true,"source":"UAVVaste public benchmark, not local drone"}'`);
 const {root:doc}=await c('DOM.getDocument');const {nodeId}=await c('DOM.querySelector',{nodeId:doc.nodeId,selector:'input[name=photos]'});
 const image=path.join(root,'datasets/uavvaste-pilot-v1/images/test/batch_03_img_1560.jpg');
 await c('DOM.setFileInputFiles',{nodeId,files:[image]});await value("document.getElementById('upload-form').requestSubmit()");
 await wait("!document.getElementById('upload-button').disabled && document.getElementById('upload-log').textContent.length>0");
 await wait(`fetch('/api/pilot/photos').then(r=>r.json()).then(x=>x.photos.some(p=>p.mission===${JSON.stringify(mission)}&&p.state==='done'))`,120);
 const count=await value(`fetch('/api/pilot/photos').then(r=>r.json()).then(x=>x.photos.filter(p=>p.mission===${JSON.stringify(mission)}).length)`);
 await value("document.getElementById('upload-form').requestSubmit()");await wait("document.getElementById('upload-log').textContent.includes('уже принят')");
 const second=await value(`fetch('/api/pilot/photos').then(r=>r.json()).then(x=>x.photos.filter(p=>p.mission===${JSON.stringify(mission)}).length)`);
 if(count!==1||second!==1)throw Error('Duplicate created an extra photo');
 await value("refresh()");await value("document.querySelector('[data-tab=overview]').click()");await value(`document.getElementById('overview-mission').value=${JSON.stringify(mission)};document.getElementById('overview-mission').dispatchEvent(new Event('change'))`);if(await value("document.getElementById('count-all').textContent")!=='1')throw Error('Mission counters mix other missions');await value("document.querySelector('[data-tab=journal]').click()");await wait("document.querySelectorAll('.card').length>0");if(!await value("document.querySelector('#journal-list .source-badge')?.textContent.includes('пример')"))throw Error('Missing visible example badge');if(!await value("document.querySelector('#journal-list .demo-notice')?.textContent.includes('Казахстане')"))throw Error('Missing demo notice');await shot('03-journal');
 await value("document.querySelector('#journal-list .card button').click()");await wait("document.getElementById('photo-dialog').open");if(!await value("document.getElementById('photo-model').textContent.includes('registry')"))throw Error('Missing saved model snapshot');await shot('04-evidence');await value("document.getElementById('close-dialog').click()");
 await value("document.querySelector('[data-tab=map]').click()");await wait("document.querySelector('.leaflet-control-zoom-in')");await shot('05-map');
 await c('Network.enable');await c('Network.setBlockedURLs',{urls:['https://tile.openstreetmap.org/*']});
 const fixtures=[{id:'map-qa-1',mission:'SYNTHETIC-MAP-ONLY',name:'QA camera A',state:'done',created:'2026-10-20T09:00:00Z',captured_at:'2026-10-20T08:00:00Z',location:{latitude:51.1,longitude:71.4,source:'synthetic_test_only'},metadata:{qa:true,synthetic_coordinates:true},result:{model:{},events:[{class_name:'fire',review_status:'unreviewed'}]}},{id:'map-qa-2',mission:'SYNTHETIC-MAP-ONLY',name:'QA camera B',state:'done',created:'2026-10-20T09:01:00Z',captured_at:'2026-10-20T08:01:00Z',location:{latitude:51.101,longitude:71.401,source:'synthetic_test_only'},metadata:{qa:true,synthetic_coordinates:true},result:{model:{},events:[{class_name:'smoke',review_status:'confirmed'}]}},{id:'map-qa-no-gps',mission:'NO-GPS-QA',name:'QA no GPS',state:'queued',created:'2026-10-20T09:02:00Z',metadata:{qa:true,synthetic_coordinates:true}}];
 await value(`EcoMap.update(${JSON.stringify(fixtures)},world,{openPhoto:()=>{},origin,versionLabel,names});document.getElementById('map-demo').checked=false;document.getElementById('map-demo').dispatchEvent(new Event('change'))`);
 if((await value('EcoMap.snapshot()')).shown!==0)throw Error('Synthetic/demo points visible by default');
 await value("document.getElementById('map-demo').click()");let mapState=await value('EcoMap.snapshot()');if(mapState.shown!==3||mapState.points!==2||mapState.routes!==1||mapState.findings!==2||mapState.online)throw Error('Map layers/GPS contract '+JSON.stringify(mapState));
 if(!await value("document.getElementById('map-list').textContent.includes('Без GPS — только в списке')"))throw Error('No-GPS photo lost');
 await value("document.getElementById('map-class').value='fire';document.getElementById('map-class').dispatchEvent(new Event('change'))");if((await value('EcoMap.snapshot()')).shown!==1)throw Error('Map class filter');
 await value("document.getElementById('map-class').value='';document.getElementById('map-review').value='confirmed';document.getElementById('map-review').dispatchEvent(new Event('change'))");if((await value('EcoMap.snapshot()')).shown!==1)throw Error('Map review filter');
 await value("document.getElementById('map-review').value='';document.getElementById('map-from').value='2026-10-21';document.getElementById('map-from').dispatchEvent(new Event('change'))");if((await value('EcoMap.snapshot()')).shown!==0)throw Error('Map date filter');
 await value("document.getElementById('map-from').value='';document.getElementById('map-mission').value='NO-GPS-QA';document.getElementById('map-mission').dispatchEvent(new Event('change'))");if((await value('EcoMap.snapshot()')).points!==0||(await value('EcoMap.snapshot()')).shown!==1)throw Error('Map mission/no GPS filter');
 await value("document.getElementById('map-online').click()");await wait("!document.getElementById('map-online').checked");if(!await value("document.getElementById('map-network').textContent.includes('недоступна')"))throw Error('No tile outage fallback');
 await value("document.getElementById('map-mission').value='';document.getElementById('map-demo').checked=false;refresh()");
await value("document.querySelector('[data-tab=training]').click()");await shot('06-training');
 await c('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});await value("document.querySelector('[data-tab=overview]').click()");await shot('07-mobile');
 const overflow=await value('document.documentElement.scrollWidth > window.innerWidth+1');
 if(errors.length)throw Error('Client exceptions: '+errors.join('\n'));
 const report={passed:true,map_checks:{interactive_layers:true,no_synthetic_coordinates_in_database:true,no_gps_list:true,demo_hidden_by_default:true,mission_class_review_date_filters:true,blocked_network_offline_fallback:true},browser:'isolated headless Google Chrome, normal sandbox',screenshots:7,real_photo_upload:true,duplicate_suppression:true,evidence_dialog:true,client_exceptions:errors,mobile_horizontal_overflow:overflow,mission_counter_filter:true,visible_demo_origin:true,per_result_model_snapshot:true,mission};
 await fs.writeFile(path.join(out,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));
 }finally{if(ws)ws.close();chrome.kill('SIGTERM');await new Promise(r=>{chrome.once('exit',r);setTimeout(r,5000).unref()});await fs.rm(profile,{recursive:true,force:true,maxRetries:10,retryDelay:500})}
}
main().catch(e=>{console.error(e);process.exitCode=1});
