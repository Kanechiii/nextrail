import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {
  connectProgressBridge,isProgressInvalidation,PROGRESS_CHANNEL,PROGRESS_EVENT,
} from '../src/progressCoordination.ts'

const read=path=>readFileSync(new URL(path,import.meta.url),'utf8')
const app=read('../src/App.tsx')
const hook=read('../src/useCrossTabProgress.ts')
const auth=read('../src/useAuthFocus.ts')
const route=read('../src/LearningRouteTimeline.tsx')
const css=read('../src/desktop.css')
const main=read('../src/main.tsx')

function mockBridge(){
  const sent=[]
  let closed=false
  const channel={onmessage:null,postMessage(value){sent.push(value)},close(){closed=true}}
  return {channel,sent,isClosed:()=>closed}
}

test('anonymous progress signals never transmit account identifiers or tokens',()=>{
  const incoming=[]
  const fake=mockBridge()
  const bridge=connectProgressBridge(()=>incoming.push('invalidate'),()=>fake.channel)
  assert.equal(bridge.available,true)
  assert.equal(PROGRESS_CHANNEL,'nextrail:progress-invalidation:v1')
  bridge.publish()
  assert.deepEqual(fake.sent,[{kind:PROGRESS_EVENT}])
  const content=JSON.stringify(fake.sent)
  assert.doesNotMatch(content,/token|password|email|account|pathway|progress|milestone|revision|user_id/i)
  fake.channel.onmessage({data:{kind:PROGRESS_EVENT}})
  assert.deepEqual(incoming,['invalidate'])
  fake.channel.onmessage({data:{kind:PROGRESS_EVENT,token:'stolen'}})
  fake.channel.onmessage({data:{kind:'unknown'}})
  fake.channel.onmessage({data:null})
  assert.deepEqual(incoming,['invalidate'])
  bridge.close()
  assert.equal(fake.isClosed(),true)
  assert.equal(fake.channel.onmessage,null)
  bridge.publish()
  assert.equal(fake.sent.length,1)
  bridge.close()
})

test('unsupported or blocked BroadcastChannel fails closed without remote writes',()=>{
  const unavailable=connectProgressBridge(()=>{throw new Error('called')},()=>{throw new Error('blocked')})
  assert.equal(unavailable.available,false)
  unavailable.publish()
  unavailable.close()
  const throwing=mockBridge()
  throwing.channel.postMessage=()=>{throw new Error('send denied')}
  const other=connectProgressBridge(()=>{},()=>throwing.channel)
  other.publish()
  other.close()
  assert.equal(throwing.isClosed(),true)
  assert.equal(isProgressInvalidation({kind:PROGRESS_EVENT}),true)
  assert.equal(isProgressInvalidation({kind:PROGRESS_EVENT,owner:'a'}),false)
})

test('React listener uses latest account state and cleans up on unmount',()=>{
  assert.match(hook,/useCrossTabProgress\(onRemote/)
  assert.match(hook,/const connected=connectProgressBridge/)
  assert.match(hook,/connected\.close\(\)/)
  assert.match(hook,/useCallback\(\(\)=>bridge\.current\?\.publish\(\),\[\]\)/)
  assert.match(app,/const announceProgress=useCrossTabProgress\(\(\)=>\{/)
  assert.match(app,/if\(!token\|\|!selected\)return/)
  assert.match(app,/externalRevisionEpoch\.current\+\+/)
  assert.match(app,/setExternalProgressPending\(true\)/)
  assert.doesNotMatch(hook,/localStorage|sessionStorage|setInterval/)
})

test('stale cross-tab progress is blocked until a confirmed GET completes',()=>{
  assert.match(app,/const requestEpoch=externalRevisionEpoch\.current/)
  assert.match(app,/if\(requestEpoch!==externalRevisionEpoch\.current\)/)
  assert.match(app,/setProgressError\('Progress changed while loading/)
  assert.match(app,/if\(externalRevisionPending\.current\)/)
  assert.match(app,/setExternalProgressPending\(false\)/)
  assert.match(app,/announceProgress\(\)/)
  assert.match(app,/if\(reason instanceof ApiError&&reason\.code==='PROGRESS_STALE'\)/)
  assert.match(app,/className="cross-tab-notice" role="status" aria-live="polite"/)
  assert.match(app,/Load latest progress/)
  assert.match(app,/syncBlocked=\{externalProgressPending\}/)
  assert.match(route,/disabled=\{syncBlocked\|\|Boolean\(pendingSkill\)\}/)
  assert.match(route,/Refresh progress first/)
  assert.doesNotMatch(app,/setInterval\([^)]*announceProgress/)
})

test('optional account dialog contains Tab focus and restores opener on Escape',()=>{
  assert.match(auth,/if\(event\.key==='Escape'\)/)
  assert.match(auth,/if\(event\.key!=='Tab'\)return/)
  assert.match(auth,/event\.shiftKey/)
  assert.match(auth,/document\.addEventListener\('keydown',keydown,true\)/)
  assert.match(auth,/document\.removeEventListener\('keydown',keydown,true\)/)
  assert.match(auth,/if\(target\?\.isConnected\)target\.focus\(\)/)
  assert.match(app,/useAuthFocus\(\{open:authOpen,container:authOverlay/)
  assert.match(app,/ref=\{authOverlay\} tabIndex=\{-1\} className="overlay auth-focus-overlay"/)
  assert.match(app,/role="dialog" aria-modal="true" aria-labelledby="auth-title"/)
})

test('desktop zoom and high contrast preserve recovery actions',()=>{
  assert.match(css,/\.cross-tab-notice/)
  assert.match(css,/flex-wrap:wrap/)
  assert.match(css,/overflow-wrap:anywhere/)
  assert.match(css,/@media\(max-width:380px\)/)
  assert.match(css,/@media\(prefers-reduced-motion:reduce\)/)
  assert.match(css,/@media\(forced-colors:active\)/)
  assert.match(css,/\.auth-focus-overlay \.dialog/)
  assert.match(css,/focus-visible/)
  assert.match(main,/import '\.\/desktop\.css'/)
})
