import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
const require=createRequire(import.meta.url);
const arg=(n)=>{let i=process.argv.indexOf(n);return i<0?null:process.argv[i+1]};
let chromium;
try {({chromium}=require('playwright'))} catch {console.log(JSON.stringify({status:'PLAYWRIGHT_REQUIRED'}));process.exit(2)}
const candidates=[process.env.HTML_PDF_BROWSER,chromium.executablePath(),'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome','/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',path.join(os.homedir(),'Applications/Google Chrome.app/Contents/MacOS/Google Chrome'), 'C:/Program Files/Google/Chrome/Application/chrome.exe','C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].filter(Boolean);
const executablePath=candidates.find(p=>fs.existsSync(p));
if(process.argv.includes('--doctor')){console.log(JSON.stringify({node:process.version,platform:process.platform,playwright:require('playwright/package.json').version,browser_found:!!executablePath}));process.exit(0)}
const input=path.resolve(arg('--input')||''),output=path.resolve(arg('--output')||'');
if(!arg('--input')||!arg('--output')||!fs.existsSync(input)||fs.existsSync(output))throw Error('INPUT_REQUIRED_OR_OUTPUT_EXISTS');
const browser=await chromium.launch({headless:true,...(executablePath?{executablePath}:{})});
try{
 const page=await browser.newPage({viewport:{width:1200,height:900}});let external=0;
 await page.route(/^https?:/i,r=>{external++;return r.abort()});
 await page.goto(pathToFileURL(input).href);await page.evaluate(()=>document.fonts.ready);
 const badImages=await page.locator('img').evaluateAll(xs=>xs.filter(x=>!x.complete||!x.naturalWidth).length);
 if(badImages||external)throw Error('EXTERNAL_OR_MISSING_ASSET');
 await page.emulateMedia({media:'print'});
 const coverCount=await page.locator('[data-ezi-cover="V"]').count();
 if(coverCount&& (coverCount!==2 || await page.locator('[data-cover-side="front"]').count()!==1 || await page.locator('[data-cover-side="back"]').count()!==1))throw Error('COVER_PAIR_REQUIRED');
 const sheetCount=await page.locator('.sheet').count();
 fs.mkdirSync(path.dirname(output),{recursive:true});
 if(sheetCount||coverCount){
  const {PDFDocument}=require('pdf-lib');const merged=await PDFDocument.create();
  const append=async bytes=>{const doc=await PDFDocument.load(bytes);for(const p of await merged.copyPages(doc,doc.getPageIndices()))merged.addPage(p);return doc.getPageCount()};
  const cover=async side=>{
   await page.goto(pathToFileURL(input).href);await page.emulateMedia({media:'print'});await page.evaluate(()=>document.fonts.ready);
   await page.evaluate(side=>{const el=document.querySelector(`[data-cover-side="${side}"]`).cloneNode(true);document.body.replaceChildren(el);document.body.style.cssText='margin:0;padding:0;display:block;background:white';el.style.cssText='width:210mm;height:296.9mm;margin:0;break-before:auto;break-after:auto;position:relative';},side);
   await page.addStyleTag({content:'@page{size:A4;margin:0}html{margin:0;padding:0}'});
   const bad=await page.evaluate(()=>{
    const overlap=(a,b)=>a.right>b.left+1&&a.left<b.right-1&&a.bottom>b.top+1&&a.top<b.bottom-1;
    const root=document.querySelector('.ezi-cover'),bounds=root.getBoundingClientRect();
    const xs=[...root.querySelectorAll('.ec-brand,.ec-kind,.ec-title,.ec-question,.ec-closing,.ec-body,.ec-contact,.ec-meta,.ec-footer')];
    return xs.some(x=>{const r=x.getBoundingClientRect();return x.scrollHeight>x.clientHeight+8||x.scrollWidth>x.clientWidth+2||r.bottom>bounds.bottom+2||r.right>bounds.right+2})||xs.some((a,i)=>xs.slice(i+1).some(b=>overlap(a.getBoundingClientRect(),b.getBoundingClientRect())));
   });
   if(bad)throw Error('COVER_TEXT_OVERLAP_OR_OVERFLOW_'+side);
   const bytes=await page.pdf({format:'A4',printBackground:true,preferCSSPageSize:true,margin:{top:'0',bottom:'0',left:'0',right:'0'}});
   const doc=await PDFDocument.load(bytes);if(doc.getPageCount()!==1)throw Error('COVER_OVERFLOW_'+side);
   await append(bytes);
  };
  if(coverCount)await cover('front');
  for(let i=0;i<sheetCount;i++){
   await page.goto(pathToFileURL(input).href);await page.emulateMedia({media:'print'});await page.evaluate(()=>document.fonts.ready);
   await page.evaluate(index=>{const el=document.querySelectorAll('.sheet')[index].cloneNode(true);document.body.replaceChildren(el);document.body.style.cssText='margin:0;background:white';el.style.cssText+=';margin:0;width:210mm;height:296mm;min-height:0;box-sizing:border-box;break-after:auto';},i);
   const clipped=await page.evaluate(()=>[...document.querySelectorAll('.sheet,.sheet *')].filter(el=>{
    const s=getComputedStyle(el);if(s.display==='none'||s.visibility==='hidden'||el instanceof SVGElement)return false;
    const vertical=['hidden','clip','auto','scroll'].includes(s.overflowY)&&el.scrollHeight>el.clientHeight+2;
    const horizontal=['hidden','clip','auto','scroll'].includes(s.overflowX)&&el.scrollWidth>el.clientWidth+2;
    return vertical||horizontal;
   }).length);
   const outside=await page.evaluate(()=>{const sheet=document.querySelector('.sheet'),box=sheet.getBoundingClientRect();return [...sheet.querySelectorAll('p,h1,h2,h3,table,figure,img,footer')].some(el=>{const b=el.getBoundingClientRect();return b.height&&b.bottom>box.bottom+2})});
   if(clipped||outside)throw Error('CONTENT_CLIPPED_'+i);
   const bytes=await page.pdf({format:'A4',printBackground:true,preferCSSPageSize:true,margin:{top:'0',bottom:'0',left:'0',right:'0'}});
   const doc=await PDFDocument.load(bytes);if(doc.getPageCount()!==1)throw Error('SHEET_OVERFLOW_'+i);
   for(const p of await merged.copyPages(doc,[0]))merged.addPage(p);
  }
  if(!sheetCount){
   await page.goto(pathToFileURL(input).href);await page.emulateMedia({media:'print'});await page.evaluate(()=>document.fonts.ready);
   await page.evaluate(()=>{document.querySelectorAll('[data-ezi-cover="V"]').forEach(x=>x.remove());});
   await append(await page.pdf({format:'A4',printBackground:true,preferCSSPageSize:true}));
  }
  if(coverCount)await cover('back');
  fs.writeFileSync(output,await merged.save());
 }else await page.pdf({path:output,format:'A4',printBackground:true,preferCSSPageSize:true});
 console.log(JSON.stringify({status:'PDF_CREATED',output,sheets:sheetCount,covers:coverCount,external_requests:external}));
}finally{await browser.close()}
