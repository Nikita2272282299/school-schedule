const fs=require('node:fs');
const vm=require('node:vm');
const html=fs.readFileSync(__dirname+'/index.html','utf8');
let count=0;
for(const match of html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)){
 if(match[1].trim()){new vm.Script(match[1]);count++;}
}
console.log('Inline JavaScript syntax OK:',count,'scripts');
