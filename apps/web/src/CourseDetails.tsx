import {useEffect,useRef} from 'react'
import {animate,createScope,stagger} from 'animejs'
import {ArrowUpRight,Bookmark,BookOpen,Check,ShieldCheck,X} from 'lucide-react'
import type {Course} from './api'

export type ProviderTone='microsoft'|'github'|'coursera'|'aws'|'claude'|'freecodecamp'|'linkedin'|'neutral'

/** Presentation-only accents. This classification never affects provider approval. */
export function providerTone(course:Pick<Course,'provider_id'|'provider_name'|'synthetic'>):ProviderTone{
  if(course.synthetic)return 'neutral'
  const provider=(course.provider_id+' '+course.provider_name).toLowerCase().replace(/[^a-z0-9]/g,'')
  if(provider.includes('microsoft'))return 'microsoft'
  if(provider.includes('github'))return 'github'
  if(provider.includes('coursera'))return 'coursera'
  if(provider.includes('aws')||provider.includes('amazon'))return 'aws'
  if(provider.includes('claude')||provider.includes('anthropic'))return 'claude'
  if(provider.includes('freecodecamp'))return 'freecodecamp'
  if(provider.includes('linkedin'))return 'linkedin'
  return 'neutral'
}

export function costLabel(cost:string,kind:'access'|'certificate'){
  const label=kind==='access'?'Access':'Certificate'
  if(cost==='free')return label+' · Free'
  if(cost==='paid')return label+' · Paid'
  if(cost==='conditional')return label+' · Conditions apply'
  return label+' · Not verified'
}

type Props={
  course:Course
  saved:boolean
  onClose:()=>void
  onSave:(id:string)=>void
}

export default function CourseDetails({course,saved,onClose,onSave}:Props){
  const dialog=useRef<HTMLDialogElement>(null)
  useEffect(()=>{
    const element=dialog.current
    if(!element)return
    if(!element.open)element.showModal()

    // Native dialog semantics and focus trapping remain functional without motion.
    const reduced=window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const scope=reduced?null:createScope({root:element}).add(()=>{
      const visual=element.querySelector<HTMLElement>('.course-dialog-visual')
      if(visual)animate(visual,{
        opacity:{from:.7,to:1},
        x:{from:-14,to:0},
        duration:410,
        ease:'out(3)',
      })
      const details=Array.from(element.querySelectorAll<HTMLElement>(
        '.course-dialog-content h2, .course-dialog-content>p, .course-facts>div'
      )).slice(0,7)
      if(details.length)animate(details,{
        opacity:{from:0,to:1},
        y:{from:9,to:0},
        delay:stagger(40),
        duration:350,
        ease:'out(3)',
      })
    })
    return ()=>{
      scope?.revert()
      if(element.open)element.close()
    }
  },[])
  const tone=providerTone(course)
  return <dialog ref={dialog} className={'course-dialog provider-'+tone} aria-labelledby="course-dialog-title" aria-describedby="course-dialog-summary" onClose={onClose}>
    <div className="course-dialog-grid">
      <div className="course-dialog-visual">
        <div className="course-dialog-kicker"><span>LEARNING RESOURCE</span><span>DETAIL / 01</span></div>
        <div className="course-dialog-symbol" aria-hidden="true"><span/><span/><BookOpen size={43} strokeWidth={1.4}/></div>
        <div className="course-dialog-provider"><span className="provider-mark"/><span>{course.provider_name}</span></div>
      </div>
      <div className="course-dialog-content">
        <button className="course-dialog-close" type="button" onClick={onClose} aria-label="Close course details"><X size={19}/></button>
        <small className="eyebrow">RESOURCE DETAILS</small>
        <h2 id="course-dialog-title">{course.title}</h2>
        <p id="course-dialog-summary">Review the available source and cost information before choosing this learning resource.</p>
        {course.synthetic&&<p className="course-demo-note">Illustrative example only. Not an actual course or provider listing.</p>}
        <div className="course-facts">
          <div><small>Provider</small><strong>{course.provider_name}</strong></div>
          <div><small>Learning topics</small><strong>{course.skills.length?course.skills.join(' · '):'Not specified'}</strong></div>
          <div><small>Access</small><strong>{costLabel(course.access_cost,'access')}</strong></div>
          <div><small>Certificate</small><strong>{costLabel(course.certificate_cost,'certificate')}</strong></div>
          <div><small>Source review</small><strong>{course.synthetic?'Not verified — demonstration':course.evidence_status.replaceAll('_',' ')}</strong></div>
        </div>
        <div className="course-dialog-foot">
          {course.synthetic?<span className="source-note"><ShieldCheck size={16}/> No fabricated enrollment link</span>:<>
            {course.url?<a className="course-visit" href={course.url} target="_blank" rel="noopener noreferrer">Visit course source <ArrowUpRight size={17}/></a>:<span className="source-note">No verified enrollment link available</span>}
            <button className="course-save" disabled={saved} onClick={()=>{onClose();onSave(course.id)}}>{saved?<Check size={16}/>:<Bookmark size={16}/>} {saved?'Saved':'Save course'}</button>
          </>}
        </div>
      </div>
    </div>
  </dialog>
}
