import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {accessNote,listingReviewState,reviewedCourseUrl,sourceReviewText} from '../src/sourcePresentation.ts'

const read=(path)=>readFileSync(new URL(path,import.meta.url),'utf8')
const app=read('../src/App.tsx')
const details=read('../src/CourseDetails.tsx')
const compare=read('../src/CourseComparison.tsx')
const provider=read('../src/ProviderEvidence.tsx')
const css=read('../src/provider-evidence.css')
const entry=read('../src/main.tsx')

function course(overrides={}){
  return {id:'safe-a',title:'Reviewed example',provider_id:'example-approved',provider_name:'Illustrative provider',
    skills:['html'],access_cost:'free',certificate_cost:'unknown',evidence_status:'verified',
    synthetic:false,url:'https://courses.example.org/learning',...overrides}
}

test('display state never confuses synthetic, reviewed and unverified listings',()=>{
  assert.equal(listingReviewState(course()),'reviewed')
  assert.equal(listingReviewState(course({synthetic:true})),'illustrative')
  assert.equal(listingReviewState(course({evidence_status:'unverified'})),'unverified')
  assert.equal(sourceReviewText(course()),'Listing reviewed')
  assert.equal(sourceReviewText(course({synthetic:true})),'Illustrative only')
  assert.equal(sourceReviewText(course({evidence_status:'pending'})),'Source not verified')
})

test('official source link is only available for reviewed nonsynthetic HTTPS URLs',()=>{
  assert.equal(reviewedCourseUrl(course()),'https://courses.example.org/learning')
  assert.equal(reviewedCourseUrl(course({url:'http://courses.example.org'})),null)
  assert.equal(reviewedCourseUrl(course({url:'javascript:alert(1)'})),null)
  assert.equal(reviewedCourseUrl(course({url:'https://user:pass@courses.example.org'})),null)
  assert.equal(reviewedCourseUrl(course({url:'https://courses.example.org:7443'})),null)
  assert.equal(reviewedCourseUrl(course({url:'invalid'})),null)
  assert.equal(reviewedCourseUrl(course({url:undefined})),null)
  assert.equal(reviewedCourseUrl(course({synthetic:true})),null)
  assert.equal(reviewedCourseUrl(course({evidence_status:'unverified'})),null)
})

test('access costs and certificate fees are not conflated or guessed',()=>{
  assert.deepEqual(accessNote(course()),{access:'Access listed free',certificate:'Certificate terms not verified'})
  assert.deepEqual(accessNote(course({access_cost:'conditional',certificate_cost:'paid'})),{
    access:'Access conditions apply',certificate:'Certificate may cost extra',
  })
  assert.deepEqual(accessNote(course({access_cost:'unknown',certificate_cost:'free'})),{
    access:'Access price not verified',certificate:'Certificate listed free',
  })
  assert.equal(accessNote(course({access_cost:'trial'})).access,'Access price not verified')
})

test('the UI uses the backend certificate_cost filter without guest authentication',()=>{
  assert.match(app,/params\.set\('certificate_cost',certificateCost\)/)
  assert.match(app,/\[debouncedQuery,provider,skill,cost,certificateCost,catalogRequest,previewExamples\]/)
  assert.match(app,/aria-label="Filter certificate cost"/)
  assert.match(app,/value="conditional">Conditional certificate/)
  assert.match(app,/Reviewed catalog/)
  assert.match(app,/\[previewExamples,query,provider,skill,cost,certificateCost\]/)
  assert.match(app,/!certificateCost\|\|c\.certificate_cost===certificateCost/)
  assert.doesNotMatch(app,/enableProviderAdapter\(|fetch\(provider/)
})

test('card, comparison and detail links all honor the same review gate',()=>{
  assert.match(app,/reviewedCourseUrl\(c\)/)
  assert.match(details,/listingReviewState\(course\)==='reviewed'/)
  assert.match(details,/<ProviderEvidence course=\{course\} variant="detail"\/>/)
  assert.match(compare,/reviewedCourseUrl\(course\)/)
  assert.match(provider,/reviewedCourseUrl\(course\)/)
  assert.match(provider,/No reviewed official course link available/)
  assert.match(provider,/Eligibility is provider-dependent/)
  assert.match(provider,/does not confirm current enrollment/)
  assert.match(provider,/rel="noopener noreferrer"/)
})

test('provider panels do not manufacture certifications or eligibility checks',()=>{
  assert.match(provider,/student benefits, trial access, registration and subscription requirements have not been checked/)
  assert.match(provider,/listingReviewState\(course\)/)
  assert.match(provider,/course\.synthetic\?'Access is illustrative'/)
  assert.match(css,/\.provider-evidence.status-illustrative/)
  assert.match(css,/\.provider-evidence.status-unverified/)
  assert.match(css,/@media\(max-width:760px\)/)
  assert.match(css,/@media\(prefers-reduced-motion:reduce\)/)
  assert.match(entry,/import '\.\/provider-evidence\.css'/)
})
