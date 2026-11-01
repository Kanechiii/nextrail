import type {Course} from './api'

/** UI interpretation only. Never grants permission or verifies provider rights. */
export function listingReviewState(course:Pick<Course,'synthetic'|'evidence_status'>):
  'illustrative'|'reviewed'|'unverified'{
  if(course.synthetic)return 'illustrative'
  return course.evidence_status==='verified'?'reviewed':'unverified'
}

export function accessNote(course:Pick<Course,'access_cost'|'certificate_cost'>){
  const access=course.access_cost==='free'?'Access listed free':
    course.access_cost==='paid'?'Paid access listed':
    course.access_cost==='conditional'?'Access conditions apply':'Access price not verified'
  const certificate=course.certificate_cost==='free'?'Certificate listed free':
    course.certificate_cost==='paid'?'Certificate may cost extra':
    course.certificate_cost==='conditional'?'Certificate conditions apply':'Certificate terms not verified'
  return {access,certificate}
}

/**
 * Only return official links from reviewed non-synthetic records.
 * The backend validates source/provider host permissions separately.
 * This check is a frontend defense, not a substitute for the backend gate.
 */
export function reviewedCourseUrl(course:Pick<Course,'synthetic'|'evidence_status'|'url'>){
  if(listingReviewState(course)!=='reviewed'||!course.url)return null
  try{
    const url=new URL(course.url)
    if(url.protocol!=='https:'||!url.hostname||url.username||url.password||url.port&&url.port!=='443')return null
    return course.url
  }catch{return null}
}

export function sourceReviewText(course:Pick<Course,'synthetic'|'evidence_status'>){
  const state=listingReviewState(course)
  return state==='illustrative'?'Illustrative only':state==='reviewed'?'Listing reviewed':'Source not verified'
}
