import {ArrowUpRight,BookCheck,Info,LockKeyhole,ShieldCheck} from 'lucide-react'
import type {Course} from './api'
import {accessNote,listingReviewState,reviewedCourseUrl,sourceReviewText} from './sourcePresentation'

type Props={course:Course;variant?:'card'|'detail'}

/** Source status is review metadata, never accreditation or guaranteed access. */
export default function ProviderEvidence({course,variant='card'}:Props){
  const status=listingReviewState(course)
  const notes=accessNote(course)
  const href=reviewedCourseUrl(course)
  return <section className={'provider-evidence provider-evidence-'+variant+' status-'+status}
    aria-label={'Provider evidence for '+course.title}>
    <div className="provider-evidence-top">
      <span className="provider-evidence-status">
        {status==='reviewed'?<ShieldCheck size={15}/>:status==='illustrative'?<Info size={15}/>:<LockKeyhole size={15}/>}
        {sourceReviewText(course)}
      </span>
      <span className="provider-evidence-provider">{course.provider_name}</span>
    </div>
    <div className="provider-evidence-facts">
      <span><BookCheck size={14}/>{course.synthetic?'Access is illustrative':notes.access}</span>
      <span>{course.synthetic?'Certificate details are illustrative':notes.certificate}</span>
    </div>
    {course.access_cost==='conditional'&&!course.synthetic&&<p className="provider-evidence-caution">
      Eligibility is provider-dependent; student benefits, trial access, registration and subscription requirements have not been checked for your account.
    </p>}
    {variant==='detail'&&<p className="provider-evidence-caution">
      A reviewed listing does not confirm current enrollment, certificate eligibility or independent provider authorization. Verify the official page before enrolling.
    </p>}
    {variant==='detail'&&(href?<a className="provider-evidence-link" href={href}
      target="_blank" rel="noopener noreferrer">Open reviewed source <ArrowUpRight size={15}/></a>:
      <span className="provider-evidence-link-missing">No reviewed official course link available</span>)}
  </section>
}
