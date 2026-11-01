import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'

const src=(filename)=>readFileSync(new URL(filename,import.meta.url),'utf8')
const app=src('../src/App.tsx')
const panel=src('../src/AccountPreferencesPanel.tsx')
const api=src('../src/api.ts')
const css=src('../src/account-experience.css')
const entry=src('../src/main.tsx')

test('account preference types use existing backend contract with no new service',()=>{
  assert.match(api,/export type LearningPreferences=\{display_name:string;career_goal:string;weekly_hours:number;target_skill_ids:string\[\];known_skill_ids:string\[\];onboarding_completed:boolean;updated_at:string\|null\}/)
  assert.match(api,/export type LearningPreferencesUpdate=Pick<LearningPreferences/)
  assert.match(app,/call<LearningPreferences>\('\/v1\/me\/preferences','GET',undefined,token\)/)
  assert.match(app,/call<LearningPreferences>\('\/v1\/me\/preferences','PATCH',changes,token\)/)
  assert.match(api,/headers\.Authorization='Bearer '/)
})

test('preference editor reflects server defaults, separates save from applying a plan',()=>{
  assert.match(panel,/editablePreferences\(value\)/)
  assert.match(panel,/value\.onboarding_completed/)
  assert.match(panel,/value\.weekly_hours/)
  assert.match(panel,/disabled=\{!canApply\}/)
  assert.match(panel,/onClick=\{onApply\}/)
  assert.match(panel,/onSubmit=\{submit\}/)
  assert.match(panel,/onSave\(\{/)
  assert.match(app,/setPlan\(previous=>\(\{\.\.\.previous,career_goal:preferences\.career_goal/)
  assert.match(app,/setPathway\(null\);changeView\('pathway'\)/)
})

test('guest pathway snapshot is captured after actual preview, never silently transferred',()=>{
  assert.match(app,/const \[guestDraft,setGuestDraft\]=useState<Plan\|null>\(null\)/)
  assert.match(app,/const snapshot:Plan=\{\.\.\.plan,target_skill_ids:\[\.\.\.plan\.target_skill_ids\],known_skill_ids:\[\.\.\.plan\.known_skill_ids\]\}/)
  assert.match(app,/if\(!token\)setGuestDraft\(snapshot\)/)
  assert.match(app,/async function saveGuestPlan\(\)/)
  assert.match(app,/call<\{id:string;pathway:Pathway\}>\('\/v1\/me\/pathways','POST',guestDraft,token\)/)
  assert.match(app,/onClick=\{saveGuestPlan\}/)
  assert.match(app,/Nothing transfers automatically/)
  assert.match(app,/onClick=\{\(\)=>setGuestDraft\(null\)\}/)
  assert.doesNotMatch(app,/useEffect\([^\n]*saveGuestPlan\(/)
})

test('sign-out clears private profile state, guest draft and selected route',()=>{
  assert.match(app,/setSaved\(\[\]\);setBookmarks\(\[\]\);setSelected\(''\);setProgress\(null\);setPreferences\(null\);setGuestDraft\(null\)/)
  assert.match(app,/if\(!token\)\{setPreferences\(null\)/)
  assert.match(app,/return\(\)=>\{active=false\}/)
  assert.doesNotMatch(app,/localStorage|sessionStorage/)
  assert.doesNotMatch(panel,/localStorage|sessionStorage/)
})

test('preferences form honors existing field limits and optional skill choices',()=>{
  assert.match(panel,/maxLength=\{80\}/)
  assert.match(panel,/maxLength=\{120\}/)
  assert.match(panel,/min=\{1\} max=\{80\}/)
  assert.match(panel,/draft\.target_skill_ids\.length>=32/)
  assert.match(panel,/draft\.known_skill_ids\.length>=128/)
  assert.match(panel,/value\.career_goal\.trim\(\)&&value\.target_skill_ids\.length>0/)
  assert.match(panel,/Discard changes/)
  assert.match(panel,/role="alert"/)
})

test('learning profile stays account-only and never blocks guest discovery',()=>{
  assert.match(app,/\{token\?<><div className="account-bar"/)
  assert.match(app,/<AccountPreferencesPanel value=\{preferences\}/)
  assert.match(app,/\/v1\/courses/)
  assert.match(app,/\/v1\/pathways\/preview/)
  assert.match(app,/Account optional/)
  assert.match(app,/Illustrative examples only/)
  assert.match(app,/!c\.synthetic&&/)
})

test('profile and transfer UI support light dark mobile focus and reduced motion',()=>{
  assert.match(panel,/aria-labelledby="preferences-heading"/)
  assert.match(panel,/aria-expanded=\{editOpen\} aria-controls="account-preferences-form"/)
  assert.match(css,/\.layout\[data-theme="light"\] \.account-preferences/)
  assert.match(css,/\.layout\[data-theme="light"\] \.guest-plan-transfer/)
  assert.match(css,/@media\(max-width:650px\)/)
  assert.match(css,/@media\(prefers-reduced-motion:reduce\)/)
  assert.match(css,/:focus-visible/)
  assert.match(entry,/import '\.\/account-experience\.css'/)
})
