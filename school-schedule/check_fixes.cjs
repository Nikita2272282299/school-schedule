const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync(__dirname+'/index.html','utf8');
const sub=html.match(/const SUBJECTS=(.*);/)[1];
const code=html.slice(html.indexOf('function parseCSV('),html.indexOf('/* ---------- storage ---------- */'));
const ctx={Date,Set,URLSearchParams,console};
vm.createContext(ctx);
vm.runInContext("const SUBJECTS="+sub+";const MONTHS=['января','февраля','марта','апреля','мая','июня','июля','августа','сентября','октября','ноября','декабря'];const norm=c=>(c||'').replace(/\\s+/g,'').toUpperCase();const CLASS_RE=/^\\d{1,2}[А-ЯЁ]$/;const now=()=>new Date('2026-11-10T12:00:00');const pad=n=>String(n).padStart(2,'0');"+code,ctx);
const cell=t=>vm.runInContext('parseCell('+JSON.stringify(t)+')',ctx);
assert.equal(cell('англ319/308(1)').title,'Английский');
assert.equal(JSON.stringify(cell('англ319/308(1)').rooms),'["319","308(1)"]');
for(const raw of ['Алг (305)','Англ210а','Физика (305(2),407)'])assert(cell(raw).rooms.length,raw);
assert.equal(cell('Химия (пр)').rooms.length,0);
const rows=[['10 ноября'],['','','8А','8Б','8Г'],['1','8:00-8:40','','','Алг 407'],[],['6','12:25-13:05','','','Хим пр 205'],['','','8А','8Б','8Г'],['7','13:15-13:55','','','РоВ 323']];
ctx.rows=rows;assert.equal(vm.runInContext("parseSheetDays(rows)[0].classes['8Г'].length",ctx),3);
assert(!html.includes('<b>NEW</b>'));
// Test the real worker's push and click handlers without a push server.
const handlers={},shown=[];const scope='https://example.com/school-schedule/';
const worker={URL,Response,self:{registration:{scope,showNotification:async(t,o)=>shown.push({t,o})},addEventListener:(k,fn)=>handlers[k]=fn,clients:{matchAll:async()=>[],openWindow:async u=>u}}};vm.createContext(worker);vm.runInContext(fs.readFileSync(__dirname+'/sw.js','utf8'),worker);
(async()=>{let done;handlers.push({data:{json:()=>({title:'Расписание',body:'Тест',url:'/'})},waitUntil:p=>done=p});await done;assert.equal(shown[0].o.data.url,scope);handlers.push({data:{json:()=>({url:'https://evil.example/'})},waitUntil:p=>done=p});await done;assert.equal(shown[1].o.data.url,scope);console.log('Parser and push-handler regressions OK');})().catch(e=>{console.error(e);process.exitCode=1});
