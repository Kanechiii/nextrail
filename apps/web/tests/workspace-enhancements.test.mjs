import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'

const app=readFileSync(new URL('../src/App.tsx',import.meta.url),'utf8')
const details=readFileSync(new URL('../src/CourseDetails.tsx',import.meta.url),'utf8')
const css=readFileSync(new URL('../src/workspace-enhancements.css',import.meta.url),'utf8')
const entry=readFileSync(new URL('../src/main.tsx',import.meta.url),'utf8')

test('light and dark themes use explicit user-controlled state and responsive tokens',()=>{
  assert.match(app,/data-theme=\{theme\}/)
  assert.match(app,/setTheme\(t=>t==='dark'\?'light':'dark'\)/)
  assert.match(css,/\.layout\[data-theme="light"\]/)
  assert.match(entry,/workspace-enhancements\.css/)
})

test('course details are accessible, closable and keep source claims separate',()=>{
  assert.match(details,/<dialog ref=\{dialog\}/)
  assert.match(details,/aria-labelledby="course-dialog-title"/)
  assert.match(details,/aria-label="Close course details"/)
  assert.match(details,/costLabel\(course\.access_cost,'access'\)/)
  assert.match(details,/costLabel\(course\.certificate_cost,'certificate'\)/)
  assert.match(details,/course\.evidence_status/)
  assert.match(app,/className="card-detail-trigger"/)
})

test('synthetic items cannot receive source or bookmark calls via details',()=>{
  assert.match(details,/course\.synthetic\?<span className="source-note"/)
  assert.match(details,/No fabricated enrollment link/)
  assert.match(details,/course\.url\?<a/)
  assert.match(details,/onClick=\{\(\)=>\{onClose\(\);onSave\(course\.id\)\}\}/)
  assert.match(app,/\!c\.synthetic&&/)
})

test('provider accents are restrained and never based on untrusted CSS values',()=>{
  assert.match(details,/if\(course\.synthetic\)return 'neutral'/)
  for(const tone of ['microsoft','github','coursera','aws','claude','freecodecamp','linkedin','neutral']){
    assert.match(css,new RegExp('\\.provider-'+tone+'\\{'))
  }
  assert.doesNotMatch(details,/style=\{\{/)
})

test('motion and small-screen details respect accessibility constraints',()=>{
  assert.match(css,/@media\(prefers-reduced-motion:reduce\)/)
  assert.match(css,/@media\(max-width:760px\)/)
  assert.match(css,/\.course-dialog-grid\{grid-template-columns:1fr\}/)
})
