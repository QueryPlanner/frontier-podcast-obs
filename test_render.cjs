const {test,before,after}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const {execFileSync}=require('node:child_process');
const {chromium}=require('playwright');
const {PNG}=require('pngjs');
let browser,page;
const errors=[];
const assets=path.join(__dirname,'assets');
const render=path.join(__dirname,'render');
before(async()=>{
  const candidates=[process.env.CHROME,'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome','/Applications/Brave Browser.app/Contents/MacOS/Brave Browser'].filter(Boolean);
  const executablePath=candidates.find(p=>fs.existsSync(p));
  browser=await chromium.launch({executablePath,headless:true,args:['--disable-gpu']});
  page=await browser.newPage({viewport:{width:1920,height:1080}});
  page.on('pageerror',e=>errors.push(e.message));
  await page.route(/^https?:/,route=>route.abort());
  fs.mkdirSync(render,{recursive:true});
  execFileSync('python3',['preview_studio.py'],{cwd:__dirname});
});
after(async()=>{await browser?.close()});
async function open(file,w=1920,h=1080,query=''){
  await page.setViewportSize({width:w,height:h});
  await page.goto(pathToFileURL(path.join(assets,file)).href+query);
  await page.evaluate(()=>window.WTF_FONTS_READY||document.fonts.ready);
  await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
}
test('font variants keep the local default and load configured trials',async()=>{
  await open('lower_stack.html',1920,196);
  assert.equal(await page.locator('html').getAttribute('data-font-variant'),'current');
  assert.match(await page.locator('html').evaluate(e=>e.style.getPropertyValue('--brand')),/Anybody/);
  assert.equal(await page.locator('link[data-font-variant]').count(),0);
  await open('lower_stack.html',1920,196,'?font=cormorant-garamond');
  assert.equal(await page.locator('html').getAttribute('data-font-variant'),'cormorant-garamond');
  assert.match(await page.locator('html').evaluate(e=>e.style.getPropertyValue('--brand')),/Cormorant Garamond/);
  assert.match(await page.locator('link[data-font-variant]').getAttribute('href'),/fonts\.googleapis\.com/);
  await open('lower_stack.html',1920,196,'?font=not-configured');
  assert.equal(await page.locator('html').getAttribute('data-font-variant'),'current');
  assert.equal(await page.locator('link[data-font-variant]').count(),0);
});
for(const [file,w,h] of [['topbar.html',1920,96],['lower_stack.html',1920,196],['title_card.html',1920,1080],['outro_card.html',1920,1080],['starfield_bg.html',1920,1080],['participant_label.html',488,64]]){
  test(file+' fits its native canvas offline',async()=>{
    await open(file,w,h);
    const layout=await page.evaluate(()=>({width:document.documentElement.scrollWidth,height:document.documentElement.scrollHeight,images:[...document.images].every(i=>i.complete&&i.naturalWidth>0),text:document.body.innerText,fonts:[...document.fonts].filter(f=>f.status==='loaded').map(f=>f.family)}));
    assert.equal(layout.width,w);assert.equal(layout.height,h);assert.ok(layout.images);
    assert.ok(!layout.text.includes('\u2014'));assert.ok(!layout.text.includes('/'));
    if(file!=='starfield_bg.html')assert.ok(layout.fonts.length>0);
    await page.screenshot({path:path.join(render,file.replace('.html','.png')),omitBackground:true});
  });
}
test('transparent overlays leave the canvas corners clear',async()=>{
  for(const [file,h] of [['topbar.html',96],['lower_stack.html',196]]){
    await open(file,1920,h);
    const im=PNG.sync.read(await page.screenshot({omitBackground:true}));
    for(const [x,y] of [[0,0],[1919,0],[0,h-1],[1919,h-1]])assert.equal(im.data[(y*1920+x)*4+3],0);
  }
});
test('full-frame cards and background remain opaque',async()=>{
  for(const file of ['title_card.html','outro_card.html','starfield_bg.html']){
    await open(file);
    const im=PNG.sync.read(await page.screenshot({omitBackground:true}));
    for(let i=3;i<im.data.length;i+=4)assert.equal(im.data[i],255);
  }
});
test('sponsors loop in a bottom strip separate from host identities',async()=>{
  for(const file of ['lower_stack.html','title_card.html','outro_card.html']){
    await open(file,1920,file==='lower_stack.html'?196:1080);
    for(const text of ['lordpatil.com','parthshastri.co.in','Lord Socks','House of Lords'])assert.ok((await page.locator('body').innerText()).includes(text));
    assert.equal(await page.locator('img[alt="Bev."]').count(),1);
    assert.ok(!(await page.locator('body').innerText()).includes('Bev.'));
    const strip=page.locator('.sponsor-strip');
    assert.equal(await strip.count(),1);
    assert.equal(await strip.locator('img[alt="Bev."]').count(),1);
    assert.equal(await strip.locator('img.sponsor-bev').count(),2);
    assert.ok(await strip.locator('img[alt="Bev."]').evaluate(e=>
      e.complete && e.naturalWidth/e.naturalHeight>5.9 &&
      getComputedStyle(e).objectFit==='contain' &&
      getComputedStyle(e).backgroundColor==='rgb(242, 235, 221)'));
    assert.match(await strip.innerText(),/Lord Socks/);
    assert.match(await strip.innerText(),/House of Lords/);
    assert.doesNotMatch(await strip.innerText(),/Chirag|Parth|lordpatil|parthshastri/);
    assert.equal(await page.locator('.host-identity .sponsor-strip, .host-identity .sponsor-bev').count(),0);
    assert.ok(await strip.evaluate(e=>e.getBoundingClientRect().bottom<=document.documentElement.clientHeight));
  }
});
test('sponsor ticker moves continuously, freezes for debug and rests for reduced motion',async()=>{
  await open('lower_stack.html',1920,196);
  const liveBefore=await page.locator('.sponsor-track').evaluate(e=>getComputedStyle(e).transform);
  await page.waitForTimeout(180);
  const liveAfter=await page.locator('.sponsor-track').evaluate(e=>getComputedStyle(e).transform);
  assert.notEqual(liveBefore,liveAfter);
  await open('lower_stack.html',1920,196,'?t=3');
  assert.ok(await page.locator('.sponsor-track').evaluate(e=>e.getAnimations().every(a=>a.playState==='paused')));
  await page.emulateMedia({reducedMotion:'reduce'});
  await open('lower_stack.html',1920,196);
  assert.equal(await page.locator('.sponsor-track').evaluate(e=>getComputedStyle(e).animationName),'none');
  await page.emulateMedia({reducedMotion:'no-preference'});
});
test('episode overrides and long text fit without injected markup',async()=>{
  const title='Exploring the future of artificial intelligence and the people building it';
  await open('lower_stack.html',1920,196,'?episode=42&title='+encodeURIComponent(title));
  assert.equal(await page.locator('.episode-title').innerText(),title);
  assert.ok(await page.locator('.episode-title').evaluate(e=>e.scrollWidth<=e.clientWidth+1&&e.scrollHeight<=e.clientHeight+1));
  await open('participant_label.html',488,64,'?name='+encodeURIComponent('<img src=x onerror=alert(1)>'));
  assert.equal(await page.locator('.name img').count(),0);
});
test('guest name and role fit the narrowest camera rail',async()=>{
  await open('participant_label.html',216,64,'?name=Dr.%20Alexandra%20Chandrasekhar&role=AI%20Researcher');
  assert.ok(await page.locator('.name').evaluate(e=>e.scrollWidth<=e.clientWidth+1));
});
const LOGO_PAGES=[['title_card.html',1920,1080],['lower_stack.html',1920,196],['outro_card.html',1920,1080]];
test('the orbital signal travels on every logo and debug time can freeze it',async()=>{
  for(const [file,w,h] of LOGO_PAGES){
    await open(file,w,h);
    assert.equal(await page.locator('img[src$="wtf-logo.svg"]').count(),0,file+' still embeds a static logo');
    assert.equal(await page.locator('svg .traveller').count(),1,file);
    const before=await page.locator('.traveller').boundingBox();
    await page.waitForTimeout(180);
    const after=await page.locator('.traveller').boundingBox();
    assert.notEqual(before.x,after.x,file+' signal does not move');
    await open(file,w,h,'?t=3');
    assert.ok(await page.locator('svg').evaluate(e=>e.animationsPaused()),file);
    assert.equal(await page.locator('svg').evaluate(e=>e.getCurrentTime()),3,file);
  }
});
test('the signal keeps a legible on-screen size at every logo scale',async()=>{
  const sizes={};
  for(const [file,w,h] of LOGO_PAGES){
    await open(file,w,h,'?t=3');
    sizes[file]=await page.locator('.traveller').boundingBox();
    const arc=await page.locator('svg path[stroke-width="3"]').evaluate(e=>getComputedStyle(e).vectorEffect);
    assert.equal(arc,'non-scaling-stroke',file+' arc thins with the logo');
  }
  for(const [file,box] of Object.entries(sizes)){
    assert.ok(box.width>=18&&box.width<=30,file+' signal is '+box.width+'px wide');
    assert.ok(Math.abs(box.width-sizes['title_card.html'].width)<2,file+' signal differs from the standby card');
  }
});
test('reduced motion rests the signal on every logo',async()=>{
  await page.emulateMedia({reducedMotion:'reduce'});
  for(const [file,w,h] of LOGO_PAGES){
    await open(file,w,h);
    assert.ok(await page.locator('svg').evaluate(e=>e.animationsPaused()),file);
    assert.equal(await page.locator('.traveller').evaluate(e=>getComputedStyle(e).display),'none',file);
    assert.equal(await page.locator('.resting-signal').evaluate(e=>getComputedStyle(e).display),'block',file);
  }
  await page.emulateMedia({reducedMotion:'no-preference'});
});
// Copies the planet canvas into a 2D canvas so the check works for any renderer.
const planetPixels=(points)=>page.locator('#planet').evaluate((c,points)=>{
  const copy=document.createElement('canvas');copy.width=c.width;copy.height=c.height;
  const ctx=copy.getContext('2d');ctx.drawImage(c,0,0);
  return points.map(([x,y])=>[...ctx.getImageData(x,y,1,1).data]);
},points);
const sphereRow=[];for(let x=120;x<=780;x+=4)sphereRow.push([x,450],[x,320]);
const differing=(a,b)=>a.filter((px,i)=>px.some((v,k)=>Math.abs(v-b[i][k])>2)).length;
test('planet hides rear rings and retains an opaque unlit hemisphere',async()=>{
  await open('title_card.html');
  const alpha=(await planetPixels([[450,450],[560,540],[0,0]])).map(px=>px[3]);
  assert.deepEqual(alpha,[255,255,0]);
});
test('planet surface turns over time and is deterministic when frozen',async()=>{
  await open('title_card.html',1920,1080,'?t=0');
  const start=await planetPixels(sphereRow);
  await open('title_card.html',1920,1080,'?t=75');
  const half=await planetPixels(sphereRow);
  assert.ok(differing(start,half)>sphereRow.length/4,'only '+differing(start,half)+' pixels changed after half a revolution');
  await open('outro_card.html',1920,1080,'?t=75');
  assert.equal(differing(half,await planetPixels(sphereRow)),0,'the same frozen time renders differently');
  await open('title_card.html');
  const live=await planetPixels(sphereRow);
  await page.waitForTimeout(400);
  assert.ok(differing(live,await planetPixels(sphereRow))>0,'the live planet does not move');
});
test('reduced motion keeps the planet still',async()=>{
  await page.emulateMedia({reducedMotion:'reduce'});
  await open('outro_card.html');
  const first=await planetPixels(sphereRow);
  await page.waitForTimeout(400);
  assert.equal(differing(first,await planetPixels(sphereRow)),0);
  await page.emulateMedia({reducedMotion:'no-preference'});
});
test('all twelve scenes preview with the actual components and no remote connections',async()=>{
  await page.setViewportSize({width:2100,height:1300});
  const preview=path.join(render,'studio-preview.html');
  assert.ok(!fs.readFileSync(preview,'utf8').includes('vdo.ninja'));
  await page.goto(pathToFileURL(preview).href);
  assert.equal(await page.locator('#scene').inputValue(),'04 Duo');
  const names=await page.locator('#scene option').allTextContents();assert.equal(names.length,12);
  for(const name of names){
    await page.locator('#scene').selectOption(name);
    await page.waitForFunction(()=>[...document.querySelectorAll('iframe')].every(f=>f.contentDocument?.readyState==='complete'));
    for(const frame of page.frames())await frame.evaluate(()=>document.fonts.ready);
    if(name==='04 Duo')assert.equal(await page.locator('.camera').count(),2);
    if(name==='07 Trio · With Guest')assert.equal(await page.locator('.camera').count(),3);
    if(['04 Duo','07 Trio · With Guest','05 Screen · Duo','08 Screen · Trio','01 Standby','10 Outro'].includes(name))
      await page.locator('.stage').screenshot({path:path.join(render,'scene-'+name.slice(0,2)+'.png')});
  }
});
test('local-host preview selector switches capture roles and preserves duo',async()=>{
  await page.goto(pathToFileURL(path.join(render,'studio-preview.html')).href);
  for(const host of ['parth','chirag']){
    await page.locator('#local-host').selectOption(host);
    assert.equal(await page.locator('#scene').inputValue(),'04 Duo');
    assert.equal(await page.locator('.camera.'+host+' small').innerText(),'LOCAL CAMERA PREVIEW');
    const remote=host==='chirag'?'parth':'chirag';
    assert.equal(await page.locator('.camera.'+remote+' small').innerText(),'REMOTE CAMERA PREVIEW');
  }
});
test('no browser runtime errors',()=>assert.deepEqual(errors,[]));
