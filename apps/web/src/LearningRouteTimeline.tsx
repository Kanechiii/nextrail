import {useEffect,useId,useMemo,useState} from 'react'
import {ArrowUpRight,CheckCircle2,CircleDashed,Clock3,Compass,GitBranch} from 'lucide-react'
import type {Pathway,Skill} from './api'

type RouteProgress={completed:number;total:number;milestones:{skill_id:string;status:string}[]}

type Props={
  pathway:Pathway
  skills:Skill[]
  progress?:RouteProgress|null
  onToggle?:(skillId:string,nextStatus:'completed'|'not_started')=>void
}

type MilestoneState='completed'|'in_progress'|'not_started'

export function nextRouteStep(pathway:Pathway,progress?:RouteProgress|null){
  if(!progress)return null
  const lookup=new Map(progress.milestones.map(m=>[m.skill_id,m.status]))
  return pathway.milestones.find(m=>lookup.get(m.skill_id)!=='completed')?.skill_id??null
}

export default function LearningRouteTimeline({pathway,skills,progress,onToggle}:Props){
  const id=useId()
  const next=nextRouteStep(pathway,progress)
  const [active,setActive]=useState<string|null>(null)
  useEffect(()=>setActive(null),[pathway])
  const selected=active&&pathway.milestones.some(m=>m.skill_id===active)?active:
    next??pathway.milestones[0]?.skill_id??null
  const knownSkills=useMemo(()=>new Map(skills.map(s=>[s.id,s])),[skills])
  const statuses=useMemo(()=>new Map(progress?.milestones.map(m=>[m.skill_id,m.status])??[]),[progress])
  const finished=progress?Math.max(0,Math.min(progress.completed,pathway.milestones.length)):0
  const percent=pathway.milestones.length?Math.round(finished/pathway.milestones.length*100):0

  return <section className="journey" aria-label="Learning route timeline">
    <div className="journey-heading">
      <div><small className="journey-eyebrow">YOUR LEARNING ROUTE</small><h3>{pathway.career_goal}</h3></div>
      <div className="journey-cadence"><Clock3 size={15}/>{pathway.weekly_hours} hours / week</div>
    </div>
    <div className="journey-summary">
      <span><GitBranch size={15}/>{pathway.milestones.length} prerequisite-ordered steps</span>
      <span><Compass size={15}/>{progress?'Self-reported progress':'Guest preview · progress not saved'}</span>
    </div>
    {progress&&<div className="journey-progress">
      <div><strong>{finished} of {pathway.milestones.length} completed</strong><span>{percent}%</span></div>
      <div className="journey-track" role="progressbar" aria-label="Route milestone completion" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}>
        <span style={{width:percent+'%'}}/>
      </div>
    </div>}
    {pathway.milestones.length===0?
      <p className="journey-empty">No steps in this route yet. Choose a target skill and generate a pathway.</p>:
      <ol className="journey-list">{pathway.milestones.map((milestone,index)=>{
        const state:MilestoneState=progress&&statuses.get(milestone.skill_id)==='completed'?'completed':
          progress&&statuses.get(milestone.skill_id)==='in_progress'?'in_progress':'not_started'
        const current=selected===milestone.skill_id
        const title=knownSkills.get(milestone.skill_id)?.name??milestone.skill_id
        const prerequisites=knownSkills.get(milestone.skill_id)?.prerequisites??[]
        const detailId=id+'-step-'+index
        return <li key={milestone.skill_id} className={'journey-step '+(current?'is-active ':'')+'is-'+state}>
          <button className="journey-step-toggle" type="button" onClick={()=>setActive(current?null:milestone.skill_id)}
            aria-expanded={current} aria-controls={detailId}>
            <span className="journey-step-icon" aria-hidden="true">{state==='completed'?<CheckCircle2 size={19}/>:state==='in_progress'?<CircleDashed size={19}/>:<span>{index+1}</span>}</span>
            <span className="journey-step-label"><small>STEP {String(index+1).padStart(2,'0')} <span>·</span> {progress?state.replaceAll('_',' '):'planned'}</small><strong>{title}</strong></span>
            <ArrowUpRight className="journey-step-arrow" size={17} aria-hidden="true"/>
          </button>
          {current&&<div id={detailId} className="journey-step-detail">
            <p>{milestone.rationale}</p>
            <div className="journey-step-metadata">
              <span>{prerequisites.length? 'Prerequisites: '+prerequisites.map(s=>knownSkills.get(s)?.name??s).join(', '):'No prerequisite skills'}</span>
              <span>{milestone.resource_ids.length} referenced {milestone.resource_ids.length===1?'resource':'resources'}</span>
            </div>
            {progress&&onToggle&&<button className="journey-complete-action" type="button"
              aria-label={(state==='completed'?'Mark incomplete: ':'Mark completed: ')+title}
              onClick={()=>onToggle(milestone.skill_id,state==='completed'?'not_started':'completed')}>
              {state==='completed'?'Mark as not started':'Mark completed'}
            </button>}
          </div>}
        </li>
      })}</ol>}
    <p className="journey-footnote">Milestone completion is self-reported. Resource links and certificates require separately reviewed provider evidence.</p>
  </section>
}
