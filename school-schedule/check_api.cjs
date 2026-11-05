const fs=require('node:fs');
const vm=require('node:vm');
const ctx={self:{}};
vm.runInNewContext(fs.readFileSync(__dirname+'/config.js','utf8'),ctx);
const base=ctx.self.SCHEDULE_CONFIG.apiBase;
/* Встроенный конфиг в HTML должен указывать туда же, куда config.js (им пользуется и SW). */
const html=fs.readFileSync(__dirname+'/index.html','utf8');
if(!html.includes("'"+base+"'"))throw Error('Embedded API base is out of sync with config.js');
(async()=>{
 if(!base||!base.startsWith('https://'))throw Error('Configure a working HTTPS API in school-schedule/config.js before publishing.');
 const origin='https://nikita2272282299.github.io';
 const r=await fetch(base.replace(/\/$/,'')+'/api/schedule',{headers:{Origin:origin},signal:AbortSignal.timeout(20000)});
 if(!r.ok)throw Error('API HTTP '+r.status);
 if(r.headers.get('access-control-allow-origin')!==origin)throw Error('API CORS is not configured');
 const j=await r.json();
 /* ok:false бывает сразу после рестарта WSGI, пока таблица не сверена заново.
    Для публикации важно, что API отдаёт расписание и нужный CORS. */
 if(!Array.isArray(j.days)||!j.days.length)throw Error('API has no schedule days');
 console.log('Production API ready'+(j.ok?'':' (данные из сохранённой копии, ok=false)'));
})().catch(e=>{console.error(e.message);process.exitCode=1});
