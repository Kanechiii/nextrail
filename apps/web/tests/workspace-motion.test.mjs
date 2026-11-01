import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'

const source=(path)=>readFileSync(new URL(path,import.meta.url),'utf8')
const motion=source('../src/motion.ts')
const app=source('../src/App.tsx')
const dialog=source('../src/CourseDetails.tsx')
const style=source('../src/motion.css')
const entry=source('../src/main.tsx')
const pkg=JSON.parse(source('../package.json'))
const lock=JSON.parse(source('../package-lock.json'))

test('Anime.js stable v4 is explicitly pinned with matching lock integrity',()=>{
  assert.equal(pkg.dependencies.animejs,'4.5.0')
  assert.equal(lock.packages[''].dependencies.animejs,'4.5.0')
  assert.equal(lock.packages['node_modules/animejs'].version,'4.5.0')
  assert.match(lock.packages['node_modules/animejs'].integrity,/^sha512-[A-Za-z0-9+/]+=*$/)
  assert.match(motion,/from 'animejs'/)
  assert.match(dialog,/from 'animejs'/)
  assert.match(entry,/import '\.\/motion\.css'/)
})

test('motion is scoped to one workspace and automatically reverted',()=>{
  assert.match(motion,/createScope\(\{root:element\}\)/)
  assert.match(motion,/scope\?\.revert\(\)/)
  assert.match(motion,/preference\.removeEventListener\('change',renderMotion\)/)
  assert.match(app,/ref=\{workspaceRoot\}/)
  assert.match(app,/useWorkspaceMotion\(workspaceRoot,view,previewExamples/)
  assert.doesNotMatch(motion,/setInterval|requestAnimationFrame|loop:\s*true/)
})

test('reduced-motion preference disables JS motion and permits real-time changes',()=>{
  assert.match(motion,/prefers-reduced-motion: reduce/)
  assert.match(motion,/if\(preference\.matches\|\|!element\)return/)
  assert.match(motion,/preference\.addEventListener\('change',renderMotion\)/)
  assert.match(dialog,/const reduced=window\.matchMedia/)
  assert.match(dialog,/const scope=reduced\?null:createScope/)
  assert.match(style,/@media\(prefers-reduced-motion:reduce\)/)
})

test('staggered motion is bounded, transform-only and nonblocking',()=>{
  assert.match(motion,/const MAX_CARDS=8/)
  assert.match(motion,/const MAX_STEPS=12/)
  assert.match(motion,/stagger\(40\)/)
  assert.match(motion,/svg\.createDrawable\(route\)/)
  assert.match(motion,/duration:880/)
  assert.match(app,/data-motion-route/)
  assert.doesNotMatch(motion,/fetch\(|localStorage|sessionStorage|\.play\(\)/)
})

test('route completion remains server-derived, numeric, and screen-reader exposed',()=>{
  assert.match(app,/role="progressbar"/)
  assert.match(app,/aria-valuenow=\{Math\.round\(progress\.completed\/progress\.total\*100\)\}/)
  assert.match(app,/aria-valuemin=\{0\} aria-valuemax=\{100\}/)
  assert.match(app,/className="completion-meter-fill"/)
  assert.match(app,/aria-pressed=\{m\.status==='completed'\}/)
  assert.match(style,/\.completion-meter-fill\{/)
  assert.doesNotMatch(motion,/\/v1\/me|Authorization|access_token/)
})

test('dialog animation retains native dialog and reverts after use',()=>{
  assert.match(dialog,/element\.showModal\(\)/)
  assert.match(dialog,/return \(\)=>\{/)
  assert.match(dialog,/scope\?\.revert\(\)/)
  assert.match(dialog,/if\(element\.open\)element\.close\(\)/)
  assert.match(dialog,/aria-labelledby="course-dialog-title"/)
  assert.match(dialog,/No fabricated enrollment link/)
})
