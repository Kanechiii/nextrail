import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'

const source=(path)=>readFileSync(new URL(path,import.meta.url),'utf8')
const app=source('../src/App.tsx')
const details=source('../src/CourseDetails.tsx')
const journey=source('../src/LearningRouteTimeline.tsx')
const comparison=source('../src/CourseComparison.tsx')
const profile=source('../src/AccountPreferencesPanel.tsx')
const motion=source('../src/motion.ts')
const css=[source('../src/workspace-enhancements.css'),source('../src/motion.css'),source('../src/dashboard-insights.css'),source('../src/account-experience.css')].join('\n')

test('responsive navigation has descriptive labels and expanded state',()=>{
  assert.match(app,/<nav id="workspace-navigation" aria-label="Primary">/)
  assert.match(app,/aria-label="Open navigation menu" aria-controls="workspace-navigation" aria-expanded=\{mobile\}/)
  assert.match(app,/aria-label="Close menu"/)
  assert.match(app,/role="status" aria-label=\{online\?'API connected':'API offline'\}/)
})

test('course details preserve native modal focus and separate cost claims',()=>{
  assert.match(details,/<dialog ref=\{dialog\}/)
  assert.match(details,/element\.showModal\(\)/)
  assert.match(details,/aria-labelledby="course-dialog-title"/)
  assert.match(details,/aria-describedby="course-dialog-summary"/)
  assert.match(details,/aria-label="Close course details"/)
  assert.match(details,/costLabel\(course\.access_cost,'access'\)/)
  assert.match(details,/costLabel\(course\.certificate_cost,'certificate'\)/)
  assert.doesNotMatch(details,/localStorage|sessionStorage/)
})

test('the learning timeline is an ordered disclosure with accessible completion',()=>{
  assert.match(journey,/<ol className="journey-list">/)
  assert.match(journey,/aria-expanded=\{current\} aria-controls=\{detailId\}/)
  assert.match(journey,/role="progressbar"/)
  assert.match(journey,/aria-valuenow=\{percent\}/)
  assert.match(journey,/Milestone completion is self-reported/)
  assert.match(journey,/onToggle&&<button/)
})

test('comparison uses semantic table headings and keyboard scroll region',()=>{
  assert.match(comparison,/role="region" aria-label="Scrollable course comparison" tabIndex=\{0\}/)
  assert.match(comparison,/<table className="comparison-table">/)
  assert.match(comparison,/<th scope="col">/)
  assert.match(comparison,/<th scope="row">/)
  assert.match(comparison,/rel="noopener noreferrer"/)
  assert.match(comparison,/Illustrative preview only/)
})

test('account preferences remain optional, labeled and scope-limited',()=>{
  assert.match(profile,/aria-labelledby="preferences-heading"/)
  assert.match(profile,/aria-expanded=\{editOpen\} aria-controls="account-preferences-form"/)
  assert.match(profile,/role="alert"/)
  assert.match(app,/Nothing transfers automatically/)
  assert.match(app,/onClick=\{saveGuestPlan\}/)
  assert.match(app,/\/v1\/pathways\/preview/)
  assert.doesNotMatch(profile,/localStorage|sessionStorage/)
})

test('motion respects accessibility and responsive theme contracts',()=>{
  assert.match(motion,/prefers-reduced-motion: reduce/)
  assert.match(motion,/scope\?\.revert\(\)/)
  assert.match(css,/@media\(prefers-reduced-motion:reduce\)/)
  assert.match(css,/@media\(max-width:760px\)/)
  assert.match(css,/data-theme="light"/)
  assert.match(css,/:focus-visible/)
  assert.doesNotMatch(motion,/setInterval|loop:\s*true/)
})
