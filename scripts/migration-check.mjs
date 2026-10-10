import fs from 'node:fs';import path from 'node:path';import {pathToFileURL,fileURLToPath} from 'node:url';import {createRequire} from 'node:module';import{spawnSync}from'node:child_process';
const require=createRequire(import.meta.url),{chromium}=require('playwright'),{PDFDocument}=require('pdf-lib');
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..'),out=path.join(root,'work/qa-230/latest');fs.mkdirSync(out,{recursive:true});
const exe=[process.env.HTML_PDF_BROWSER,chromium.executablePath(),'C:/Program Files/Google/Chrome/Application/chrome.exe','/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'].filter(Boolean).find(p=>fs.existsSync(p));
const browser=await chromium.launch({headless:true,...(exe?{executablePath:exe}:{})}),page=await browser.newPage();const results=[];
await page.route(/^https?:/i,r=>r.abort());
try{for(let i=1;i<=14;i++){
const id='P'+String(i).padStart(2,'0'),folder=path.join(root,'examples',id),html=path.join(folder,'report-2.2.0.html'),pdf=path.join(out,id+'.pdf');
await page.setViewportSize({width:390,height:844});await page.goto(pathToFileURL(html).href);await page.evaluate(()=>document.fonts.ready);
const issues=await page.evaluate(()=>({overflow:document.documentElement.scrollWidth>innerWidth+1,missingImages:[...document.images].filter(x=>!x.complete||!x.naturalWidth).length}));
const status=spawnSync(process.execPath,[path.join(root,'scripts/render.mjs'),'--input',html,'--output',pdf],{encoding:'utf8'});
if(status.status!==0)throw Error(id+':PDF_FAILED');
const old=await PDFDocument.load(fs.readFileSync(path.join(folder,'report-2.2.0.pdf'))),fresh=await PDFDocument.load(fs.readFileSync(pdf));
results.push({id,mode:'historical_replay_2.2.0_source_preserved',...issues,old_pages:old.getPageCount(),new_pages:fresh.getPageCount(),page_count_unchanged:old.getPageCount()===fresh.getPageCount()});console.log(JSON.stringify(results.at(-1)));
}}finally{await browser.close()}
fs.writeFileSync(path.join(out,'results.json'),JSON.stringify(results,null,2));if(results.some(r=>r.overflow||r.missingImages||!r.page_count_unchanged))process.exit(2);

