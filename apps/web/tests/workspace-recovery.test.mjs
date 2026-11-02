import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {call,ApiError} from '../src/api.ts'
import {validatePathwayDraft,validatePreferencesDraft} from '../src/fieldValidation.ts'
import {suppressRepeatedError} from '../src/feedbackModel.ts'

const read=path=>readFileSync(new URL(path,import.meta.url),'utf8')
const app=read('../src/App.tsx')
const mobileLifecycle=read('../src/mobileLifecycle.ts')
const boundary=read('../src/WorkspaceErrorBoundary.tsx')
const preferences=read('../src/AccountPreferencesPanel.tsx')
const css=read('../src/recovery.css')
const root=read('../src/main.tsx')
const toasts=read('../src/FeedbackToasts.tsx')
const plan={career_goal:'Frontend developer',target_skill_ids:['css'],known_skill_ids:[],weekly_hours:6,zero_budget:true}

test('invalid pathway and preferences drafts report field-specific corrections',()=>{
  assert.deepEqual(validatePathwayDraft(plan),{})
  assert.match(validatePathwayDraft({...plan,career_goal:' '}).career_goal,/career direction/)
  assert.match(validatePathwayDraft({...plan,target_skill_ids:[]}).target_skill_ids,/at least one/)
  assert.match(validatePathwayDraft({...plan,weekly_hours:0}).weekly_hours,/1 and 30/)
  assert.deepEqual(validatePreferencesDraft({
    display_name:'Test',career_goal:'Frontend',weekly_hours:6,target_skill_ids:['css'],known_skill_ids:[],
  }),{})
  assert.match(validatePreferencesDraft({
    display_name:'Test',career_goal:'Frontend',weekly_hours:101,target_skill_ids:[],known_skill_ids:[],
  }).weekly_hours,/1 and 80/)
})

test('conditional progress API sends opaque revision and classifies 409 as stale state',async t=>{
  const original=globalThis.fetch
  t.after(()=>{globalThis.fetch=original})
  globalThis.fetch=async(_url,options)=>{
    assert.equal(options.headers['If-Match'],'"15"')
    assert.equal(options.headers.Authorization,'Bearer account-token')
    return new Response('{}',{status:409})
  }
  await assert.rejects(()=>call('/v1/me/pathways/id/progress/html','PUT',{status:'completed'},'account-token',{progressRevision:'15'}),
    error=>{
      assert.ok(error instanceof ApiError)
      assert.equal(error.code,'PROGRESS_STALE')
      assert.equal(error.status,409)
      assert.match(error.message,/Reload/)
      return true
    })
  globalThis.fetch=async()=>new Response('{}',{status:409})
  await assert.rejects(()=>call('/v1/me/pathways','POST',plan,'account-token'),err=>{
    assert.equal(err.code,'IDEMPOTENCY_CONFLICT')
    return true
  })
})

test('React error boundaries contain render failures and offer local recovery',()=>{
  assert.match(boundary,/getDerivedStateFromError/)
  assert.match(boundary,/componentDidCatch/)
  assert.match(boundary,/role="alert"/)
  assert.match(boundary,/Try displaying again/)
  assert.match(boundary,/Return to Discover/)
  assert.match(root,/<WorkspaceErrorBoundary scope="application"><App\/><\/WorkspaceErrorBoundary>/)
  assert.match(app,/<WorkspaceErrorBoundary key=\{view\}/)
  assert.match(app,/<\/WorkspaceErrorBoundary><\/main>/)
  assert.doesNotMatch(boundary,/console\.(log|error)|localStorage|sessionStorage/)
})

test('mobile and page lifecycle interruptions preserve draft and session state',()=>{
  assert.match(mobileLifecycle,/addEventListener\('visibilitychange',resume\)/)
  assert.match(mobileLifecycle,/addEventListener\('pageshow',resume\)/)
  assert.match(mobileLifecycle,/addEventListener\('online',online\)/)
  assert.match(mobileLifecycle,/addEventListener\('offline',offline\)/)
  assert.match(app,/if\(token&&!progressUpdatingSkill&&selected\)setProgressRequest/)
  assert.match(mobileLifecycle,/RESUME_INTERVAL_MS=15000/)
  assert.match(app,/window\.addEventListener\('beforeunload',warn\)/)
  assert.match(app,/planDirty\|\|preferenceDraftDirty\|\|pendingSave!==null/)
  assert.match(app,/setGuestDraft\(snapshot\)/)
  assert.match(app,/await call<Pathway>\('\/v1\/pathways\/preview'/)
  assert.doesNotMatch(app,/localStorage|sessionStorage/)
})

test('browser Back closes modal and restores the opening control',()=>{
  assert.match(app,/window\.history\.pushState/)
  assert.match(app,/__nextrailCourseDialog/)
  assert.match(app,/window\.addEventListener\('popstate',onBack\)/)
  assert.match(app,/setDetailCourse\(null\)/)
  assert.match(app,/dialogAnchor\.current\?\.focus\(\)/)
  assert.match(app,/onDetails=\{openCourseDetails\}/)
  assert.match(app,/onClose=\{closeCourseDetails\}/)
  assert.match(app,/onClick=\{\(\)=>openCourseDetails\(c\)\}/)
})

test('save-response uncertainty remains user-controlled and idempotent',()=>{
  assert.match(app,/setPendingSave\('pathway'\)/)
  assert.match(app,/setPendingSave\('guest'\)/)
  assert.match(app,/idempotencyKey:saveKey\(plan,token,'pathway'\)/)
  assert.match(app,/idempotencyKey:saveKey\(guestDraft,token,'guest'\)/)
  assert.match(app,/onClick=\{savePath\}>Check save status/)
  assert.match(app,/onClick=\{saveGuestPlan\}>Check guest-plan save/)
  assert.match(app,/setPendingSave\(null\)/)
  assert.match(app,/may already have saved this route/)
  assert.doesNotMatch(app,/setInterval\(.*savePath/)
})

test('forms focus their first invalid field and retain editor changes',()=>{
  assert.match(app,/validatePathwayDraft\(plan\)/)
  assert.match(app,/querySelector<HTMLInputElement>/)
  assert.match(app,/role="alert" className="field-error"/)
  assert.match(app,/aria-invalid=\{Boolean\(planErrors\.career_goal\)\}/)
  assert.match(app,/aria-invalid=\{Boolean\(authFieldErrors\.email\)\}/)
  assert.match(preferences,/validatePreferencesDraft\(draft\)/)
  assert.match(preferences,/onDirtyChange\?\.\(editOpen&&changed\)/)
  assert.match(preferences,/Discard unsaved preference changes/)
  assert.match(preferences,/aria-invalid=\{Boolean\(fieldErrors\.weekly_hours\)\}/)
  assert.match(preferences,/role="alert"/)
})

test('same repeated API error is suppressed in the accessibility live region',()=>{
  assert.equal(suppressRepeatedError(null,'offline',100),false)
  assert.equal(suppressRepeatedError({message:'offline',at:100},'offline',200),true)
  assert.equal(suppressRepeatedError({message:'offline',at:100},'offline',6200),false)
  assert.equal(suppressRepeatedError({message:'offline',at:100},'another error',200),false)
  assert.match(toasts,/suppressRepeatedError\(lastError\.current,message,now\)/)
  assert.match(toasts,/lastError\.current=null;setToasts\(\[\]\)/)
})

test('mobile keyboard, large text and reduced-motion recovery controls are operable',()=>{
  assert.match(css,/scroll-margin-block-end:max\(48px,30vh\)/)
  assert.match(css,/font-size:max\(1rem,16px\)/)
  assert.match(css,/env\(safe-area-inset-bottom/)
  assert.match(css,/@media \(max-width:760px\)/)
  assert.match(css,/@media \(prefers-reduced-motion:reduce\)/)
  assert.match(css,/\.workspace-recovery-actions button:focus-visible/)
  assert.match(root,/import '\.\/recovery\.css'/)
})
