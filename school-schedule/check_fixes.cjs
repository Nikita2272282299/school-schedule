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
// Fixed regression fixture: merged lesson expanded for four classes, blank neighbours stay blank.
ctx.exportedRows=[['11 ноября'],['','','8А','8Б','8В','8Г'],['7','13:15-13:55',...Array(4).fill('химия (профиль) 205')],['8','14:00-14:40','история 313','','','']];
for(const cls of ['8А','8Б','8В','8Г']){
  ctx.testClass=cls;
  const lessons=vm.runInContext('parseSheetDays(exportedRows)[0].classes[testClass]',ctx);
  assert.equal(lessons[0].info.raw,'химия (профиль) 205');
  if(cls!=='8А')assert.equal(lessons.length,1);
}
// Announcement cells such as "с 8.50 в 405 кабинете" must go to notes, not lessons.
ctx.noteRows=[['20 ноября'],['','','11А','11Б','11Ф'],['1','8:00-8:40','алгебра 407','физика 310','химия 205'],['9','14:55-15:35','с  8.50 в 405 кабинете','','']];
assert.equal(vm.runInContext("parseSheetDays(noteRows)[0].classes['11А'].length",ctx),1);
assert.equal(vm.runInContext("parseSheetDays(noteRows)[0].notes['11А'][0]",ctx),'С 8:50 в 405 кабинете');
assert.equal(cell('Т Р Е Н И Н Г').title,'Тренинг');
assert.equal(cell('Т Р Е Н И Н Г').icon,'🎯');
assert.equal(cell('англ319').title,'Английский');
assert.equal(cell('англ319').icon,'🇬🇧');
assert.equal(JSON.stringify(cell('англ319').rooms),'["319"]');
