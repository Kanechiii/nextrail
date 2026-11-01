import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {call,isRequestCancelled,isConnectionFailure,ApiError} from '../src/api.ts'

const read=path=>readFileSync(new URL(path,import.meta.url),'utf8')
const app=read('../src/App.tsx')
const timing=read('../src/useFeedbackTiming.ts')
const toast=read('../src/FeedbackToasts.tsx')
const css=read('../src/feedback.css')
const profile=read('../src/AccountPreferencesPanel.tsx')
const route=read('../src/LearningRouteTimeline.tsx')

test('public catalog typing is debounced and old HTTP requests are aborted',()=>{
  assert.match(timing,/SEARCH_DEBOUNCE_MS=280/)
  assert.match(timing,/SKELETON_DELAY_MS=150/)
  assert.match(timing,/ACTION_SUCCESS_MS=1600/)
  assert.match(timing,/window\.setTimeout\(\(\)=>setStable\(value\),delay\)/)
  assert.match(timing,/window\.clearTimeout\(timer\)/)
  assert.match(app,/const debouncedQuery=useDebouncedValue\(query\)/)
  assert.match(app,/const searchSettling=query!==debouncedQuery/)
  assert.match(app,/catalogAbort\.current\?\.abort\(\);setQuery\(e\.target\.value\)/)
  assert.match(app,/signal:controller\.signal/)
  assert.match(app,/controller\.abort\(\)/)
  assert.match(app,/isRequestCancelled\(reason\)/)
  assert.match(app,/\[debouncedQuery,provider,skill,cost,certificateCost,catalogRequest,previewExamples\]/)
})

test('already aborted searches make no outgoing request',async t=>{
  const old=globalThis.fetch
  t.after(()=>{globalThis.fetch=old})
  let networkCount=0
  globalThis.fetch=async()=>{networkCount++;throw new Error('unexpected request')}
  const controller=new AbortController()
  controller.abort()
  await assert.rejects(()=>call('/v1/courses','GET',undefined,undefined,{signal:controller.signal}),
    error=>isRequestCancelled(error))
  assert.equal(networkCount,0)
})

test('abort of in-flight catalog search is separate from timeout and network failure',async t=>{
  const old=globalThis.fetch
  t.after(()=>{globalThis.fetch=old})
  let seenSignal
  let requests=0
  globalThis.fetch=async(_url,opts)=>{
    requests++
    seenSignal=opts.signal
    return await new Promise((_resolve,reject)=>{
      opts.signal.addEventListener('abort',()=>reject(new Error('aborted')),{once:true})
    })
  }
  const controller=new AbortController()
  const promise=call('/v1/courses','GET',undefined,undefined,{signal:controller.signal,timeoutMs:6000})
  assert.equal(requests,1)
  controller.abort()
  await assert.rejects(promise,error=>{
    assert.equal(error.code,'REQUEST_CANCELLED')
    assert.equal(isRequestCancelled(error),true)
    assert.equal(isConnectionFailure(error),false)
    return true
  })
  assert.equal(seenSignal.aborted,true)
})

test('connection failures exclude expected search aborts and rate limits',()=>{
  for(const code of ['NETWORK_UNAVAILABLE','REQUEST_TIMEOUT','SERVICE_UNAVAILABLE','SERVER_ERROR']){
    assert.equal(isConnectionFailure(new ApiError('test',503,code)),true)
  }
  assert.equal(isConnectionFailure(new ApiError('cancelled',0,'REQUEST_CANCELLED')),false)
  assert.equal(isConnectionFailure(new ApiError('wait',429,'RATE_LIMITED')),false)
  assert.equal(isConnectionFailure(new ApiError('invalid',422,'INVALID_INPUT')),false)
})

test('skeleton reveal is delayed without delaying the underlying fetch',()=>{
  assert.match(timing,/window\.setTimeout\(\(\)=>setVisible\(true\),delay\)/)
  assert.match(timing,/if\(!pending\)\{setVisible\(false\);return\}/)
  assert.match(timing,/return pending&&visible/)
  assert.match(app,/const courseSkeletonVisible=useDelayedPending\(catalogPending\)/)
  assert.match(app,/courseSkeletonVisible&&<CourseCardSkeletons\/>/)
  assert.match(app,/routeSkeletonVisible\?<RouteSkeleton\/>/)
  assert.match(app,/dashboardSkeletonVisible\?<DashboardSkeleton\/>/)
  assert.match(app,/preferencesSkeletonVisible\?<PreferencesSkeleton\/>/)
  assert.match(app,/progressSkeletonVisible\?<ProgressSkeleton\/>/)
  assert.match(app,/skillsSkeletonVisible\?<SkillChoicesSkeleton\/>/)
  assert.match(app,/aria-busy=\{catalogPending\}/)
})

test('persistent outage banner offers manual ready-and-skills recovery',()=>{
  assert.match(app,/const \[connectionProblem,setConnectionProblem\]=useState/)
  assert.match(app,/connectionProblem&&<div className="reconnection-banner" role="status" aria-live="polite"/)
  assert.match(app,/onClick=\{retryConnection\}/)
  assert.match(app,/disabled=\{connectionChecking\} aria-busy=\{connectionChecking\}/)
  assert.match(app,/async function retryConnection\(\)/)
  assert.match(app,/call\('\/ready','GET'/)
  assert.match(app,/call<\{items:Skill\[\]\}>\('\/v1\/skills','GET'/)
  assert.match(app,/setConnectionProblem\(null\)/)
  assert.match(app,/setCatalogRequest\(n=>n\+1\)/)
  assert.match(app,/markConnectionFailure\(reason\)/)
  assert.doesNotMatch(app,/setInterval\([^)]*retryConnection/)
})

test('confirmed network writes receive ephemeral checkmark transformations',()=>{
  assert.match(timing,/setSuccessKey\(key\)/)
  assert.match(timing,/ACTION_SUCCESS_MS/)
  assert.match(timing,/useEffect\(\(\)=>\(\)=>/)
  assert.match(app,/celebrate\('course:'\+id\)/)
  assert.match(app,/celebrate\('preferences'\)/)
  assert.match(app,/celebrate\('progress:'\+skillId\)/)
  assert.match(app,/celebrate\('pathway'\)/)
  assert.match(app,/successKey==='course:'\+c\.id/)
  assert.match(app,/saved=\{successKey==='preferences'\}/)
  assert.match(app,/savedSkill=\{successKey\?\.startsWith\('progress:'\)/)
  assert.match(profile,/saved&&!changed\?'Saved':'Save preferences'/)
  assert.match(route,/savedSkill===milestone\.skill_id/)
  assert.match(app,/setProgressError\(''\);celebrate\('progress:'\+skillId\);notify/)
})

test('toast announcements preserve focus and avoid motion-heavy shimmer',()=>{
  assert.match(toast,/aria-live=\{toast\.kind==='error'\?'assertive':'polite'\}/)
  assert.match(toast,/role=\{toast\.kind==='error'\?'alert':'status'\}/)
  assert.match(toast,/document\.activeElement===closeRef\.current/)
  assert.match(toast,/\.top \.theme-switch/)
  assert.match(toast,/next\?\.focus\(\)/)
  assert.match(css,/\.feedback-sheen\{contain:paint\}/)
  assert.match(css,/@media\(update:slow\),\(prefers-reduced-data:reduce\)/)
  assert.match(css,/@media\(prefers-reduced-motion:reduce\)/)
  assert.doesNotMatch(css,/infinite;will-change:transform/)
})
