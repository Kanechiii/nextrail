/**
 * Real localhost Vite dev-server smoke, with an isolated disposable API.
 * No provider fetch, hosted service, paid tool or public listener.
 * Optional Chromium CDP checks exercise the actually rendered React UI.
 */
import assert from 'node:assert/strict'
import {spawn,spawnSync} from 'node:child_process'
import {mkdtemp,readFile,rm} from 'node:fs/promises'
import {existsSync} from 'node:fs'
import {tmpdir} from 'node:os'
import {join,resolve} from 'node:path'
import {fileURLToPath} from 'node:url'
import {setTimeout as sleep} from 'node:timers/promises'

const web=resolve(fileURLToPath(new URL('..',import.meta.url)))
const root=resolve(web,'../..')
const base='http://127.0.0.1:5173'
const started=[]
const logs=[]

function spawnService(cmd,args,cwd){
  const child=spawn(cmd,args,{cwd,env:{...process.env},detached:process.platform!=='win32',stdio:['ignore','pipe','pipe']})
  for(const stream of [child.stdout,child.stderr])stream?.on('data',buf=>{
    const line=String(buf)
    logs.push(line)
    if(logs.length>100)logs.shift()
  })
  started.push(child)
  return child
}
async function stopServices(){
  for(const child of [...started].reverse()){
    if(child.exitCode!==null||child.pid===undefined)continue
    try{
      if(process.platform==='win32')spawnSync('taskkill',['/PID',String(child.pid),'/T','/F'],{stdio:'ignore'})
      else process.kill(-child.pid,'SIGTERM')
    }catch{try{child.kill('SIGTERM')}catch{}}
  }
  await sleep(250)
}
async function probe(url,timeout=22000){
  const startedAt=Date.now()
  let error
  while(Date.now()-startedAt<timeout){
    try{
      const response=await fetch(url,{signal:AbortSignal.timeout(1200),cache:'no-store'})
      if(response.ok)return response
      error=Error('Unexpected HTTP '+response.status+' at '+url)
    }catch(reason){error=reason}
    await sleep(180)
  }
  throw Error('Dev server unavailable: '+url+'; '+String(error)+'; output: '+logs.join('').slice(-1800))
}
async function getText(path){
  const response=await probe(base+path)
  return response.text()
}

function chromeBinary(){
  if(process.env.CHROME_BIN&&spawnSync(process.env.CHROME_BIN,['--version'],{stdio:'ignore'}).status===0)return process.env.CHROME_BIN
  for(const name of ['google-chrome','google-chrome-stable','chromium','chromium-browser']){
    if(spawnSync(name,['--version'],{stdio:'ignore'}).status===0)return name
  }
  return null
}

async function browserSmoke(binary){
  const profile=await mkdtemp(join(tmpdir(),'nextrail-headless-'))
  try{
    const chrome=spawnService(binary,[
      '--headless=new','--no-sandbox','--disable-gpu','--disable-dev-shm-usage',
      '--no-first-run','--no-default-browser-check','--remote-debugging-port=0',
      '--user-data-dir='+profile,'about:blank',
    ],root)
    let port
    for(let i=0;i<90;i++){
      try{
        const path=join(profile,'DevToolsActivePort')
        if(existsSync(path)){
          port=Number((await readFile(path,'utf8')).split('\n')[0])
          if(Number.isInteger(port))break
        }
      }catch{}
      if(chrome.exitCode!==null)throw Error('Chrome exited early; '+logs.join('').slice(-2000))
      await sleep(150)
    }
    assert.ok(port,'Headless Chrome did not open DevTools port')
    const targets=await (await fetch('http://127.0.0.1:'+port+'/json/list')).json()
    const page=targets.find(t=>t.type==='page')
    assert.ok(page,'Chrome page target missing')
    const socket=new WebSocket(page.webSocketDebuggerUrl)
    await new Promise((ok,fail)=>{
      socket.addEventListener('open',ok,{once:true})
      socket.addEventListener('error',fail,{once:true})
    })
    const requests=new Map()
    const network=[]
    let id=0
    socket.addEventListener('message',event=>{
      const data=JSON.parse(String(event.data))
      if(data.id&&requests.has(data.id)){
        const handle=requests.get(data.id)
        requests.delete(data.id)
        data.error?handle.reject(Error(data.error.message)):handle.resolve(data.result)
      }else if(data.method==='Network.requestWillBeSent'&&data.params?.request?.url?.includes('/api/v1/courses')){
        network.push(data.params.request.url)
      }
    })
    function send(method,params={}){
      return new Promise((resolve,reject)=>{
        const next=++id
        const timer=setTimeout(()=>{requests.delete(next);reject(Error('CDP timeout: '+method))},12000)
        requests.set(next,{resolve:value=>{clearTimeout(timer);resolve(value)},reject:err=>{clearTimeout(timer);reject(err)}})
        socket.send(JSON.stringify({id:next,method,params}))
      })
    }
    async function expression(src){
      const result=await send('Runtime.evaluate',{expression:src,returnByValue:true,awaitPromise:true})
      if(result.exceptionDetails)throw Error('Browser JS: '+result.exceptionDetails.text)
      return result.result?.value
    }
    async function waitFor(js,timeout=8000){
      const start=Date.now()
      while(Date.now()-start<timeout){
        if(await expression(js))return
        await sleep(110)
      }
      throw Error('Browser condition timed out: '+js)
    }
    await send('Page.enable')
    await send('Runtime.enable')
    await send('Network.enable')
    await send('Page.navigate',{url:base})
    await waitFor("document.querySelector('h1')?.textContent?.includes('Find your next')")
    await waitFor("Boolean(document.querySelector('.catalog-results[aria-busy=\\\"false\\\"]'))")
    assert.equal(await expression("Boolean(document.querySelector('.reconnection-banner'))"),false)
    console.log('PASS: Chrome rendered guest discovery through npm run dev')

    // Simulated slow link and CPU are proxies for responsiveness, NOT a real
    // low-powered device measurement or an actual screen-reader session.
    await send('Emulation.setCPUThrottlingRate',{rate:4})
    await send('Network.emulateNetworkConditions',{offline:false,latency:1100,downloadThroughput:100000,uploadThroughput:100000})
    await expression("document.querySelector('input[aria-label=\\\"Search courses\\\"]').focus()")
    const before=network.length
    await send('Input.insertText',{text:'j'})
    await send('Input.insertText',{text:'a'})
    await send('Input.insertText',{text:'v'})
    await waitFor("Boolean(document.querySelector('.catalog-loading-status'))")
    await sleep(650)
    assert.equal(await expression("Boolean(document.querySelector('.skeleton-card-grid'))"),true,
      'Slow catalog request should show a delayed skeleton')
    const typed=network.slice(before).filter(url=>url.includes('query='))
    assert.equal(typed.length,1,'Rapid search keystrokes should trigger one debounced request')
    assert.ok(typed[0].includes('query=jav'))
    console.log('PASS: CPU-throttled search debounces, delayed skeleton visible')

    await send('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]})
    assert.equal(await expression("getComputedStyle(document.querySelector('.feedback-sheen'),'::after').display"),'none')
    console.log('PASS: Reduced-motion removes shimmer animation')

    await send('Emulation.setCPUThrottlingRate',{rate:1})
    await send('Network.emulateNetworkConditions',{offline:false,latency:0,downloadThroughput:-1,uploadThroughput:-1})
    await waitFor("document.querySelector('.catalog-results')?.getAttribute('aria-busy')==='false'",10000)
    await expression("document.querySelector('nav button:nth-child(2)')?.click()")
    await waitFor("Boolean(document.querySelector('button[type=submit]'))")
    await expression("document.querySelector('button[type=submit]')?.click()")
    await waitFor("Boolean([...document.querySelectorAll('.feedback-toast[role=status]')].find(e=>e.textContent.includes('route is ready')))",12000)
    assert.equal(await expression("document.activeElement?.classList.contains('feedback-toast-close')"),false,
      'Toast arrival must not move focus')
    assert.equal(await expression("document.querySelector('.feedback-toast[role=status]')?.getAttribute('aria-live')"),'polite')
    await expression("document.querySelector('.feedback-toast-close')?.focus()")
    await expression("document.querySelector('.feedback-toast-close')?.click()")
    assert.equal(await expression("document.activeElement?.classList.contains('theme-switch')"),true,
      'Focused toast close should return focus to stable control')
    console.log('PASS: Confirmed guest action toast semantics and keyboard focus')

    await expression("document.querySelector('nav button:first-child')?.click()")
    await send('Network.emulateNetworkConditions',{offline:true,latency:0,downloadThroughput:0,uploadThroughput:0})
    await expression("document.querySelector('input[aria-label=\\\"Search courses\\\"]').focus()")
    await send('Input.insertText',{text:'x'})
    await waitFor("Boolean(document.querySelector('.reconnection-banner'))",10000)
    assert.equal(await expression("Boolean(document.querySelector('.reconnection-banner button'))"),true)
    await send('Network.emulateNetworkConditions',{offline:false,latency:0,downloadThroughput:-1,uploadThroughput:-1})
    await expression("document.querySelector('.reconnection-banner button')?.click()")
    await waitFor("!document.querySelector('.reconnection-banner')",12000)
    console.log('PASS: Offline banner offers manual reconnect and clears on recovery')
    socket.close()
  }finally{await rm(profile,{recursive:true,force:true}).catch(()=>{})}
}

try{
  spawnService(process.platform==='win32'?'python':'python',['-m','uvicorn','nextrail_api.main:app','--app-dir','services/api','--host','127.0.0.1','--port','8000'],root)
  await probe('http://127.0.0.1:8000/health')
  spawnService(process.platform==='win32'?'npm.cmd':'npm',['run','dev','--','--strictPort'],web)
  const html=await getText('/')
  assert.match(html,/id="root"/)
  for(const path of ['/src/main.tsx','/src/App.tsx','/src/api.ts','/src/useFeedbackTiming.ts','/src/FeedbackToasts.tsx','/src/feedback.css']){
    const transformed=await getText(path)
    assert.ok(transformed.length>100,'Vite transform missing '+path)
  }
  const skills=await (await probe(base+'/api/v1/skills')).json()
  assert.ok(skills.items.some(item=>item.id==='html'))
  const courses=await (await probe(base+'/api/v1/courses')).json()
  assert.deepEqual(courses.items,[],'Real provider sample must remain empty')
  console.log('PASS: npm run dev served React, Vite transforms and FastAPI proxy on loopback')
  const binary=chromeBinary()
  if(binary)await browserSmoke(binary)
  else console.log('SKIP: No headless Chrome installed; rendered-browser QA remains pending')
  console.log('PASS: Development-server smoke finished without deployment or paid services')
}catch(reason){
  console.error('FAIL: npm run dev smoke:',reason)
  console.error(logs.join('').slice(-4000))
  process.exitCode=1
}finally{await stopServices()}
