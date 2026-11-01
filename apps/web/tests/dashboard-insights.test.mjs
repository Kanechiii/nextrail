import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'

const read=(filename)=>readFileSync(new URL(filename,import.meta.url),'utf8')
const app=read('../src/App.tsx')
const journey=read('../src/LearningRouteTimeline.tsx')
const compare=read('../src/CourseComparison.tsx')
const styles=read('../src/dashboard-insights.css')
const motion=read('../src/motion.ts')
const entry=read('../src/main.tsx')

test('timeline uses backend prerequisite order and optional saved progress',()=>{
  assert.match(journey,/pathway\.milestones\.map\(\(milestone,index\)=>/)
  assert.match(journey,/progress\?\.milestones\.map/)
  assert.match(journey,/nextRouteStep\(pathway,progress\)/)
  assert.match(journey,/milestone\.rationale/)
  assert.match(journey,/knownSkills\.get\(milestone\.skill_id\)/)
  assert.match(journey,/Guest preview · progress not saved/)
  assert.doesNotMatch(journey,/Date\.now\(|localStorage|fetch\(/)
})

test('timeline does not invent learning achievements or provider links',()=>{
  assert.match(journey,/Milestone completion is self-reported/)
  assert.match(journey,/referenced \{milestone\.resource_ids\.length===1/)
  assert.match(journey,/aria-label="Learning route timeline"/)
  assert.match(journey,/aria-expanded=\{current\}/)
  assert.match(journey,/aria-controls=\{detailId\}/)
  assert.match(journey,/setActive\(current\?false:milestone\.skill_id\)/)
  assert.match(journey,/onToggle&&<button/)
  assert.match(journey,/onToggle\(milestone\.skill_id/)
  assert.doesNotMatch(journey,/<a href=/)
})

test('saved dashboard drives status updates through its existing authenticated API',()=>{
  assert.match(app,/onToggle=\{mark\}/)
  assert.match(app,/\/v1\/me\/pathways\/\x27\+encodeURIComponent\(selected\)/)
  assert.match(app,/setProgress\(await call<Progress>/)
  assert.match(app,/role="progressbar"/)
  assert.match(app,/saved\.find\(item=>item\.id===selected\)\?\.pathway/)
  assert.match(app,/Saved course reference/)
  assert.match(app,/setProgress\(null\);let alive=true/)
  assert.match(app,/setSelected\(''\)/)
})

test('comparison is bounded to three and clears on filter and catalog-mode changes',()=>{
  assert.match(app,/useState<Course\[\]>\(\[\]\)/)
  assert.match(app,/useEffect\(\(\)=>setCompared\(\[\]\),\[previewExamples,query,provider,skill,cost\]\)/)
  assert.match(app,/items\.length<3\?\[\.\.\.items,course\]:items/)
  assert.match(app,/aria-pressed=\{compared\.some\(item=>item\.id===c\.id\)\}/)
  assert.match(app,/disabled=\{!compared\.some\(item=>item\.id===c\.id\)&&compared\.length>=3\}/)
  assert.match(app,/onClear=\{\(\)=>setCompared\(\[\]\)\}/)
})

test('comparison presents separate source-returned cost, certificate, skills and evidence fields',()=>{
  assert.match(compare,/costLabel\(course\.access_cost,'access'\)/)
  assert.match(compare,/costLabel\(course\.certificate_cost,'certificate'\)/)
  assert.match(compare,/course\.skills\.map/)
  assert.match(compare,/course\.evidence_status\.replaceAll/)
  assert.match(compare,/course\.provider_name/)
  assert.match(compare,/<table className="comparison-table">/)
  assert.match(compare,/<th scope="row">/)
  assert.doesNotMatch(compare,/course\.(?:rating|estimated_duration|verified_certificate)\b/)
})

test('illustrative comparison cannot show fabricated provider enrollment actions',()=>{
  assert.match(compare,/items\.some\(course=>course\.synthetic\)/)
  assert.match(compare,/Illustrative preview only/)
  assert.match(compare,/!course\.synthetic&&course\.url\?\.startsWith\('https:\/\/'\)/)
  assert.match(compare,/rel="noopener noreferrer"/)
  assert.match(compare,/onRemove\(course\.id\)/)
})

test('dashboard controls and responsive styles support keyboard and reduced motion',()=>{
  assert.match(compare,/aria-label="Scrollable course comparison" tabIndex=\{0\}/)
  assert.match(compare,/aria-label=\{'Remove '\+course\.title\+' from comparison'\}/)
  assert.match(journey,/type="button"/)
  assert.match(styles,/@media\(max-width:760px\)/)
  assert.match(styles,/@media\(prefers-reduced-motion:reduce\)/)
  assert.match(motion,/\.output \.step, \.journey-step/)
  assert.match(styles,/\.layout\[data-theme="light"\] \.journey-step-toggle/)
  assert.match(styles,/\.layout\[data-theme="light"\] \.comparison-panel/)
  assert.match(entry,/import '\.\/dashboard-insights\.css'/)
})
