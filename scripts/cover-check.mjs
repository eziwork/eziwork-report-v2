import fs from 'node:fs';import path from 'node:path';import{fileURLToPath,pathToFileURL}from'node:url';import{spawnSync}from'node:child_process';import{createRequire}from'node:module';
const require=createRequire(import.meta.url),{chromium}=require('playwright'),{PDFDocument}=require('pdf-lib');
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const exe=[process.env.HTML_PDF_BROWSER,chromium.executablePath(),'C:/Program Files/Google/Chrome/Application/chrome.exe','/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'].filter(Boolean).find(p=>fs.existsSync(p));
const browser=await chromium.launch({headless:true,...(exe?{executablePath:exe}:{})});const page=await browser.newPage({viewport:{width:1200,height:1200}});
const dest=process.env.EZIWORK_QA_DIR||path.join(root,'work/cover-qa');fs.mkdirSync(dest,{recursive:true});const results=[];
await page.route(/^https?:/i,r=>r.abort());
try{for(let i=1;i<=14;i++){
 const id='P'+String(i).padStart(2,'0'),dir=path.join(root,'examples',id),html=path.join(dir,'report-v.html'),pdf=process.argv.includes('--regenerate')?path.join(dest,id+'-regenerated.pdf'):path.join(dir,'report-v.pdf');
 await page.setViewportSize({width:1200,height:1200});await page.goto(pathToFileURL(html).href);await page.evaluate(()=>document.fonts.ready);
 const manifest=JSON.parse(fs.readFileSync(path.join(dir,'content-manifest.json'),'utf8'));
 const data=await page.evaluate(()=>({headings:[...document.querySelectorAll('h1,h2,h3')].map(x=>x.textContent.trim()),paragraphs:[...document.querySelectorAll('p')].filter(x=>!x.closest('svg')).map(x=>x.textContent.trim()).filter(Boolean),covers:document.querySelectorAll('[data-ezi-cover="V"]').length,missing:[...document.images].filter(x=>!x.complete||!x.naturalWidth).length}));
 if(i===1){await page.locator('[data-cover-side="front"]').screenshot({path:path.join(dest,'front.png')});await page.locator('[data-cover-side="back"]').screenshot({path:path.join(dest,'back.png')});}
 await page.setViewportSize({width:390,height:844});const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);
 if(i===1)await page.locator('[data-cover-side="front"]').screenshot({path:path.join(dest,'mobile.png')});
 if(!fs.existsSync(pdf)){const p=spawnSync(process.execPath,[path.join(root,'scripts/render.mjs'),'--input',html,'--output',pdf],{encoding:'utf8'});if(p.status!==0)throw Error(id+': '+p.stderr);}
 const before=await PDFDocument.load(fs.readFileSync(path.join(dir,'report.pdf'))),after=await PDFDocument.load(fs.readFileSync(pdf));
 const result={id,exact_body_copy:JSON.stringify(data.headings)===JSON.stringify(manifest.headings)&&JSON.stringify(data.paragraphs)===JSON.stringify(manifest.paragraphs),covers:data.covers,missing_images:data.missing,mobile_overflow:overflow,original_pages:before.getPageCount(),new_pages:after.getPageCount(),two_pages_added:after.getPageCount()===before.getPageCount()+2};results.push(result);console.log(JSON.stringify(result));
}}finally{await browser.close()}
fs.writeFileSync(path.join(dest,'results.json'),JSON.stringify({platform:process.platform,mode:'historical_replay_no_new_collection',results},null,2));
if(results.some(x=>!x.exact_body_copy||x.covers!==2||x.missing_images||x.mobile_overflow||!x.two_pages_added))process.exit(2);
