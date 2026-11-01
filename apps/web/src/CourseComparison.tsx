import {ArrowUpRight,Layers3,Scale,X} from 'lucide-react'
import type {Course} from './api'
import {costLabel,providerTone} from './CourseDetails'
import {reviewedCourseUrl,sourceReviewText} from './sourcePresentation'

type Props={
  items:Course[]
  onRemove:(id:string)=>void
  onClear:()=>void
  onDetails:(course:Course)=>void
}

/** Compare only actual returned fields. No ratings, durations, or invented offers. */
export default function CourseComparison({items,onRemove,onClear,onDetails}:Props){
  if(items.length===0)return null
  const demo=items.some(course=>course.synthetic)
  return <section className="comparison-panel" aria-label="Course comparison" aria-live="polite">
    <div className="comparison-heading">
      <div className="comparison-heading-title"><Scale size={19}/><div><small className="comparison-kicker">RESOURCE WORKBENCH</small><h3>Compare courses <span>{items.length} / 3</span></h3></div></div>
      <button type="button" className="comparison-clear" onClick={onClear}>Clear selection</button>
    </div>
    {demo?<p className="comparison-disclaimer">Illustrative preview only — these are not real courses, prices, certificates or enrollment opportunities.</p>:
      <p className="comparison-disclaimer">Compare source-returned information only. Verify current prices and certificate terms with each provider.</p>}
    {items.length===1?<div className="comparison-start">
      <Layers3 size={18}/><span>One resource selected. Choose another course to compare details side by side.</span>
      <button type="button" onClick={()=>onRemove(items[0].id)} aria-label={'Remove '+items[0].title}>Remove <X size={14}/></button>
    </div>:
    <div className="comparison-overflow" role="region" aria-label="Scrollable course comparison" tabIndex={0}>
      <table className="comparison-table">
        <caption>Side-by-side comparison of {items.length} selected {demo?'illustrative':'source-returned'} courses</caption>
        <thead><tr><th scope="col">Compare</th>{items.map(course=><th scope="col" className={'provider-'+providerTone(course)} key={course.id}>
          <div className="comparison-course-head">
            <small>{course.provider_name}</small>
            <button type="button" onClick={()=>onRemove(course.id)} aria-label={'Remove '+course.title+' from comparison'}><X size={17}/></button>
          </div>
          <strong>{course.title}</strong>
          <button type="button" className="comparison-detail" onClick={()=>onDetails(course)}>View details <ArrowUpRight size={14}/></button>
        </th>)}</tr></thead>
        <tbody>
          <tr><th scope="row">Access cost</th>{items.map(course=><td key={course.id}>{costLabel(course.access_cost,'access')}</td>)}</tr>
          <tr><th scope="row">Certificate</th>{items.map(course=><td key={course.id}>{costLabel(course.certificate_cost,'certificate')}</td>)}</tr>
          <tr><th scope="row">Skill coverage</th>{items.map(course=><td key={course.id}>{course.skills.length?<ul className="comparison-skills">{course.skills.map(s=><li key={s}>{s}</li>)}</ul>:'Not specified'}</td>)}</tr>
          <tr><th scope="row">Evidence</th>{items.map(course=><td key={course.id}>{sourceReviewText(course)}</td>)}</tr>
          <tr><th scope="row">Source</th>{items.map(course=><td key={course.id}>
            {reviewedCourseUrl(course)?<a className="comparison-official" href={reviewedCourseUrl(course)??undefined} rel="noopener noreferrer" target="_blank">Provider source <ArrowUpRight size={15}/></a>:<span>Not available</span>}
          </td>)}</tr>
        </tbody>
      </table>
    </div>}
  </section>
}
