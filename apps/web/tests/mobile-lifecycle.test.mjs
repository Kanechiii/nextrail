import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {
  encodeCheckpoint,decodeCheckpoint,readCheckpoint,writeCheckpoint,discardCheckpoint,
  safeGuestPlan,GUEST_CHECKPOINT_KEY,CHECKPOINT_MAX_AGE_MS,
} from '../src/mobileDraft.ts'
import {ActionGate} from '../src/interactionGuard.ts'

const read=relative=>readFileSync(new URL(relative,import.meta.url),'utf8')
const app=read('../src/App.tsx')
const css=read('../src/mobile.css')
const lifecycle=read('../src/mobileLifecycle.ts')
const root=read('../src/main.tsx')
const draft={career_goal:'Frontend Developer',target_skill_ids:['css','javascript'],
  known_skill_ids:['html'],weekly_hours:8,zero_budget:true}
function fakeStorage(){
  const items=new Map()
  return {
    items,
    getItem:key=>items.get(key)??null,
    setItem:(key,value)=>{items.set(key,value)},
    removeItem:key=>{items.delete(key)},
  }
}
test('guest checkpoint is opt-in, six-hour bounded and never stores credentials',()=>{
  const storage=fakeStorage()
  assert.equal(readCheckpoint(storage,1000),null)
  assert.equal(storage.items.size,0,'No automatic background persistence')
  assert.equal(writeCheckpoint(storage,draft,1000),true)
  const raw=storage.items.get(GUEST_CHECKPOINT_KEY)
  assert.ok(raw)
  assert.deepEqual(readCheckpoint(storage,1001),draft)
  assert.deepEqual(decodeCheckpoint(raw,1000+CHECKPOINT_MAX_AGE_MS),draft)
  assert.equal(decodeCheckpoint(raw,1001+CHECKPOINT_MAX_AGE_MS),null)
  assert.doesNotMatch(raw,/password|access_token|email|bearer|session_id/i)
  assert.equal(discardCheckpoint(storage),true)
  assert.equal(storage.items.size,0)
})

test('invalid or tampered checkpoint fails closed and is pruned',()=>{
  const invalid=[
    {version:2,savedAt:1000,plan:draft},
    {version:1,savedAt:1000,plan:{...draft,email:'secret@example.org'}},
    {version:1,savedAt:1000,plan:{...draft,target_skill_ids:['css','css']}},
    {version:1,savedAt:1000,plan:{...draft,target_skill_ids:['../private']}},
    {version:1,savedAt:1000,plan:{...draft,weekly_hours:900}},
    {version:1,savedAt:1000,plan:draft,token:'access-token'},
  ]
  assert.equal(safeGuestPlan({...draft,token:'never-store'}),false)
  for(const item of invalid){
    assert.equal(decodeCheckpoint(JSON.stringify(item),1001),null)
  }
  const storage=fakeStorage()
  storage.setItem(GUEST_CHECKPOINT_KEY,'invalid-json')
  assert.equal(readCheckpoint(storage,2000),null)
  assert.equal(storage.items.size,0)
  assert.equal(decodeCheckpoint('x'.repeat(8193),2000),null)
  assert.equal(decodeCheckpoint(encodeCheckpoint(draft,3000),2999),null)
})

test('private browsing storage errors do not crash guest discovery',()=>{
  const storage={
    getItem(){throw new Error('storage denied')},
    setItem(){throw new Error('storage denied')},
    removeItem(){throw new Error('storage denied')},
  }
  assert.equal(readCheckpoint(storage),null)
  assert.equal(writeCheckpoint(storage,draft),false)
  assert.equal(discardCheckpoint(storage),false)
  assert.throws(()=>encodeCheckpoint({...draft,career_goal:' '}),/valid guest/)
})

test('synchronous action gate rejects rapid duplicate touch submits independently',()=>{
  const lock=new ActionGate()
  assert.equal(lock.acquire('primary'),true)
  assert.equal(lock.acquire('primary'),false)
  assert.equal(lock.acquire('progress'),true)
  assert.equal(lock.acquire('bookmark:course-a'),true)
  assert.equal(lock.acquire('bookmark:course-a'),false)
  assert.equal(lock.acquire('bookmark:course-b'),true)
  assert.equal(lock.has('primary'),true)
  lock.release('primary')
  assert.equal(lock.acquire('primary'),true)
  lock.clear()
  assert.equal(lock.has('progress'),false)
  assert.equal(lock.acquire('primary'),true)
})

test('mobile browser Back closes navigation drawer and restores view continuity',()=>{
  assert.match(app,/function openMobileMenu\(\)/)
  assert.match(app,/function closeMobileMenu\(\)/)
  assert.match(app,/__nextrailMobileMenu/)
  assert.match(app,/window\.history\.pushState/)
  assert.match(app,/window\.history\.back\(\)/)
  assert.match(app,/window\.addEventListener\('popstate',onBack\)/)
  assert.match(app,/onClick=\{openMobileMenu\}/)
  assert.match(app,/onClick=\{closeMobileMenu\}/)
  assert.match(app,/setView\(v\);closeMobileMenu\(\)/)
})

test('network changes run bounded read-only probes without repeating user writes',()=>{
  assert.match(app,/useMobileLifecycle\(\{/)
  assert.match(app,/onOnline:\(\)=>\{void verifyConnection\(false\)\}/)
  assert.match(app,/onOffline:\(\)=>\{/)
  assert.match(app,/const interrupted=connectionAttempt\.current/)
  assert.match(app,/if\(connectionAttempt\.current\)return/)
  assert.match(app,/call\('\/ready','GET'/)
  assert.match(app,/call<\{items:Skill\[\]\}>\('\/v1\/skills','GET'/)
  assert.match(app,/if\(token&&!progressUpdatingSkill&&selected\)setProgressRequest/)
  assert.match(lifecycle,/addEventListener\('visibilitychange',resume\)/)
  assert.match(lifecycle,/addEventListener\('pageshow',resume\)/)
  assert.match(lifecycle,/addEventListener\('online',online\)/)
  assert.match(lifecycle,/addEventListener\('offline',offline\)/)
  assert.match(lifecycle,/RESUME_INTERVAL_MS=15000/)
  assert.doesNotMatch(lifecycle,/setInterval|localStorage|sessionStorage/)
})

test('keyboard visible-area maintenance never captures focus or prevents pinch zoom',()=>{
  assert.match(lifecycle,/window\.visualViewport/)
  assert.match(lifecycle,/viewport\.addEventListener\('resize',schedule\)/)
  assert.match(lifecycle,/document\.addEventListener\('focusin',schedule\)/)
  assert.match(lifecycle,/focused\.scrollIntoView/)
  assert.match(lifecycle,/window\.cancelAnimationFrame\(frame\)/)
  assert.match(css,/@media\(pointer:coarse\)/)
  assert.match(css,/touch-action:manipulation/)
  assert.match(css,/min-width:44px;min-height:44px/)
  assert.match(css,/env\(safe-area-inset-bottom/)
  assert.match(css,/font-size:16px/)
  assert.match(css,/@media\(prefers-reduced-motion:reduce\),\(update:slow\)/)
  assert.doesNotMatch(css,/touch-action:none|user-scalable=no/)
  assert.match(root,/import '\.\/mobile\.css'/)
})

test('recovery copy is explicitly requested and never restores without permission',()=>{
  assert.match(app,/onClick=\{saveDeviceCheckpoint\}/)
  assert.match(app,/onClick=\{restoreDeviceCheckpoint\}/)
  assert.match(app,/onClick=\{removeDeviceCheckpoint\}/)
  assert.match(app,/!token&&deviceCheckpoint/)
  assert.match(app,/writeCheckpoint\(accessibleTabStorage\(\),plan\)/)
  assert.match(app,/readCheckpoint\(accessibleTabStorage\(\)\)/)
  assert.match(app,/discardCheckpoint\(accessibleTabStorage\(\)\)/)
  assert.match(app,/browser may still clear it/)
  assert.doesNotMatch(app,/window\.localStorage|window\.sessionStorage/)
})
