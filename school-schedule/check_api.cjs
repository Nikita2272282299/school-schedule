const fs=require('node:fs');
const vm=require('node:vm');
const ctx={self:{}};
vm.runInNewContext(fs.readFileSync(__dirname+'/config.js','utf8'),ctx);
const base=ctx.self.SCHEDULE_CONFIG.apiBase;
(async()=>{
 if(!base||!base.startsWith('https://'))throw Error('Configure a working HTTPS API in school-schedule/config.js before publishing.');
 const origin='https://nikita2272282299.github.io';
 const r=await fetch(base.replace(/\/$/,'')+'/api/schedule',{headers:{Origin:origin},signal:AbortSignal.timeout(20000)});
 if(!r.ok)throw Error('API HTTP '+r.status);
 if(r.headers.get('access-control-allow-origin')!==origin)throw Error('API CORS is not configured');
 const j=await r.json();
 if(!j.ok||!Array.isArray(j.days))throw Error('API cannot load the source schedule');
 console.log('Production API ready');
})().catch(e=>{console.error(e.message);process.exitCode=1});
