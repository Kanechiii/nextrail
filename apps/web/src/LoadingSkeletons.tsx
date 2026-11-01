/** Decorative placeholders mirror real workspace layout without inventing course data. */
function Bar({width,height='12px',className=''}:{width:string;height?:string;className?:string}){
  return <span className={'feedback-sheen skeleton-bar '+className} style={{width,height}}/>
}

export function CourseCardSkeletons({count=3}:{count?:number}){
  return <div className="cards skeleton-card-grid" aria-hidden="true">
    {Array.from({length:Math.min(6,Math.max(1,count))},(_,i)=><article className="card skeleton-course-card" key={i}>
      <div className="feedback-sheen skeleton-course-art"/>
      <div className="card-body skeleton-course-body">
        <Bar width="42%" height="10px"/>
        <Bar width="84%" height="20px"/>
        <Bar width="69%" height="20px"/>
        <div className="skeleton-buttons"><Bar width="44%" height="32px"/><Bar width="34%" height="32px"/></div>
        <div className="skeleton-tags"><Bar width="29%" height="25px"/><Bar width="35%" height="25px"/></div>
        <div className="skeleton-evidence"><Bar width="62%"/><Bar width="92%"/><Bar width="75%"/></div>
        <div className="skeleton-course-bottom"><Bar width="49%" height="12px"/><Bar width="24px" height="24px"/></div>
      </div>
    </article>)}
  </div>
}

export function RouteSkeleton(){
  return <div className="skeleton-route" aria-hidden="true">
    <div className="skeleton-route-head"><Bar width="60%"/><Bar width="30%" height="27px"/></div>
    <Bar width="80%" height="11px"/>
    {Array.from({length:3},(_,i)=><div className="skeleton-route-step" key={i}>
      <Bar width="42px" height="42px" className="skeleton-circle"/>
      <div><Bar width="26%" height="9px"/><Bar width={i===1?'75%':'55%'} height="15px"/></div>
    </div>)}
    <Bar width="52%" height="39px" className="skeleton-action"/>
  </div>
}

export function DashboardSkeleton(){
  return <div className="skeleton-dashboard" aria-hidden="true">
    <div className="stats">{Array.from({length:3},(_,i)=><div className="skeleton-stat" key={i}>
      <Bar width="68%" height="10px"/><Bar width="50%" height="36px"/>
    </div>)}</div>
    <div className="skeleton-dashboard-sections"><div className="skeleton-dashboard-panel">
      <Bar width="45%" height="21px"/><Bar width="100%" height="45px"/><Bar width="72%" height="19px"/>
    </div><div className="skeleton-dashboard-panel">
      <Bar width="55%" height="21px"/><Bar width="85%" height="16px"/><Bar width="50%" height="16px"/>
    </div></div>
  </div>
}

export function PreferencesSkeleton(){
  return <div className="skeleton-preferences" aria-hidden="true">
    <div className="skeleton-preferences-heading"><Bar width="42px" height="42px"/><div><Bar width="45%" height="10px"/><Bar width="64%" height="20px"/></div></div>
    <div className="skeleton-preferences-values">{Array.from({length:3},(_,i)=><div key={i}><Bar width="66%"/><Bar width="75%" height="22px"/></div>)}</div>
    <div className="skeleton-buttons"><Bar width="135px" height="37px"/><Bar width="160px" height="37px"/></div>
  </div>
}

export function ProgressSkeleton(){
  return <div className="skeleton-progress" aria-hidden="true">
    <Bar width="73%" height="15px"/>
    {Array.from({length:3},(_,i)=><div className="skeleton-progress-row" key={i}>
      <Bar width={i===1?'57%':'72%'} height="19px"/><Bar width="40px" height="35px"/>
    </div>)}
  </div>
}
