import fs from 'node:fs';import path from 'node:path';import {fileURLToPath,pathToFileURL} from 'node:url';import {spawnSync} from 'node:child_process';import {createRequire} from 'node:module';
const require=createRequire(import.meta.url),{chromium}=require('playwright');
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const exe=[process.env.HTML_PDF_BROWSER,chromium.executablePath(),'C:/Program Files/Google/Chrome/Application/chrome.exe','/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'].filter(Boolean).find(p=>fs.existsSync(p));
const browser=await chromium.launch({headless:true,...(exe?{executablePath:exe}:{})});
const page=await browser.newPage({viewport:{width:1200,height:900}});let results=[];
await page.route(/^https?:/i,r=>r.abort());
const dest=process.env.EZIWORK_QA_DIR||path.join(root,'work','replay-qa');fs.mkdirSync(dest,{recursive:true});
try{
for(let i=1;i<=14;i++){
 const id='P'+String(i).padStart(2,'0'),html=path.join(root,'examples',id,'report.html');await page.setViewportSize({width:1200,height:900});await page.goto(pathToFileURL(html).href);await page.evaluate(()=>document.fonts.ready);
 const manifest=JSON.parse(fs.readFileSync(path.join(root,'examples',id,'content-manifest.json'),'utf8'));
 const copy=await page.evaluate(()=>({headings:[...document.querySelectorAll('h1,h2,h3')].map(x=>x.textContent.trim()),paragraphs:[...document.querySelectorAll('p')].filter(x=>!x.closest('svg')).map(x=>x.textContent.trim()).filter(Boolean)}));
 const exactCopy=JSON.stringify(copy.headings)===JSON.stringify(manifest.headings)&&JSON.stringify(copy.paragraphs)===JSON.stringify(manifest.paragraphs);
 const missing=await page.locator('img').evaluateAll(xs=>xs.filter(x=>!x.complete||!x.naturalWidth).length);
 const invalidWidths=await page.locator('[style]').evaluateAll(xs=>xs.filter(x=>/(?:^|;)\s*width\s*:\s*[1-9][0-9]*(?:\.[0-9]+)?\s*(?:;|$)/i.test(x.getAttribute('style'))).length);
 const ratioCheck=id!=='P12'||await page.locator('.price-bar').evaluateAll(xs=>Math.abs(xs[1].getBoundingClientRect().width/xs[0].getBoundingClientRect().width-75850/154790)<.001);
 await page.screenshot({path:path.join(dest,id+'-desktop.png'),fullPage:true});
 await page.setViewportSize({width:390,height:844});const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);
 await page.screenshot({path:path.join(dest,id+'-mobile.png'),fullPage:true});
 const pdf=path.join(dest,id+'.pdf');if(!fs.existsSync(pdf)){
  const r=spawnSync(process.execPath,[path.join(root,'scripts/render.mjs'),'--input',html,'--output',pdf],{encoding:'utf8'});
  if(r.status!==0)throw Error(id+' PDF failed: '+r.stderr);
 }
 results.push({id,mode:'historical_replay',exact_copy:exactCopy,missing_images:missing,invalid_css_widths:invalidWidths,price_ratio_check:ratioCheck,mobile_page_overflow:overflow,pdf_created:fs.existsSync(pdf),semantic_review:'SEE baseline-integrity and independent review',os:process.platform});
}
}finally{await browser.close()}
fs.writeFileSync(path.join(dest,'results.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results));
if(results.some(x=>!x.exact_copy||x.missing_images||x.invalid_css_widths||!x.price_ratio_check||x.mobile_page_overflow))process.exit(2);
