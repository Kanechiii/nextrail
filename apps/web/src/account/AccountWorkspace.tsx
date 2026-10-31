import { useState } from 'react'
import { ArrowRight, Bookmark, BookOpen, CheckCircle2, Compass, GitBranch, Layers3, LogOut, RotateCcw } from 'lucide-react'
import type { Pathway, Skill } from '../api'

export type SavedPathway = { id: string; pathway: Pathway; created_at: string }
export type ProgressSnapshot = { completed: number; total: number; milestones: { skill_id: string; status: string }[] }
type Section = 'overview' | 'pathways' | 'resources'
type Props = {
  account: string
  saved: SavedPathway[]
  bookmarks: string[]
  skills: Skill[]
  selected: string
  progress: ProgressSnapshot | null
  onSelect: (value: string) => void
  onProgress: (skillId: string, status: string) => void | Promise<void>
  onExplore: () => void
  onBuild: () => void
  onLogout: () => void | Promise<void>
}
export default function AccountWorkspace({
  account, saved, bookmarks, skills, selected, progress, onSelect, onProgress,
  onExplore, onBuild, onLogout,
}: Props) {
  const [section, setSection] = useState<Section>('overview')
  const current = saved.find(path => path.id === selected) ?? saved[0]
  const completed = progress?.completed ?? 0
  const total = progress?.total ?? 0
  const percent = total ? Math.round(completed / total * 100) : 0
  const next = progress?.milestones.find(m => m.status !== 'completed')
  const skillName = (id: string) => skills.find(skill => skill.id === id)?.name ?? id
  const tabs: { id: Section; text: string }[] = [
    { id: 'overview', text: 'Overview' },
    { id: 'pathways', text: 'My pathways' },
    { id: 'resources', text: 'Saved courses' },
  ]
  return <section className="account-workspace" aria-label="Registered learning workspace">
    <header className="account-heading">
      <div><small className="eyebrow">PERSONAL LEARNING WORKSPACE</small><h1>Make progress <em>your way.</em></h1><p>Continue your saved routes, review completed skills, and keep learning resources in one place.</p></div>
      <button className="ghost" onClick={onLogout} type="button"><LogOut size={16}/> Sign out</button>
    </header>
    <div className="account-identity"><div className="account-avatar" aria-hidden="true">{account.slice(0,1).toUpperCase()}</div><div><small>Signed in as</small><strong>{account}</strong></div></div>
    <nav className="account-tabs" aria-label="My learning sections">
      {tabs.map(tab => <button key={tab.id} type="button" aria-current={section === tab.id ? 'page' : undefined} className={section === tab.id ? 'selected' : ''} onClick={() => setSection(tab.id)}>{tab.text}</button>)}
    </nav>
    {section === 'overview' && <>
      <div className="account-stats">
        <article><Layers3 size={20}/><span>Saved pathways</span><strong>{saved.length}</strong><small>Stored in your account</small></article>
        <article><Bookmark size={20}/><span>Bookmarked courses</span><strong>{bookmarks.length}</strong><small>Saved learning references</small></article>
        <article><CheckCircle2 size={20}/><span>Current route progress</span><strong>{total ? percent + '%' : '—'}</strong><small>{total ? completed + ' of ' + total + ' milestones' : 'No active pathway'}</small></article>
      </div>
      <div className="account-panels">
        <article className="account-panel"><small className="eyebrow">PICK UP WHERE YOU LEFT OFF</small><h2>{current?.pathway.career_goal ?? 'Your learning starts here'}</h2>
          {current ? <><p>Your saved route is available anytime you sign in. Select a milestone to continue.</p><div className="account-meter" role="progressbar" aria-label="Milestones completed" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100}><span style={{width:percent+'%'}}/></div><div className="account-meter-caption">{completed} / {total} milestones completed</div><button className="primary" type="button" onClick={() => setSection('pathways')}>Open pathway <ArrowRight size={16}/></button></>
          : <><p>Generate a prerequisite-aware pathway as a guest, then save it to your account.</p><button className="primary" type="button" onClick={onBuild}>Build a pathway <ArrowRight size={16}/></button></>}
        </article>
        <article className="account-panel account-next"><small className="eyebrow">YOUR NEXT STEP</small><div className="account-next-icon"><GitBranch size={25}/></div><h2>{next ? skillName(next.skill_id) : current ? 'All milestones completed' : 'Choose your first skill'}</h2><p>{next ? 'Continue this prerequisite-ordered milestone when you are ready.' : 'Progress is calculated from your saved learning milestones, not estimated.'}</p>{next ? <button className="ghost" type="button" onClick={() => setSection('pathways')}>View next milestone <ArrowRight size={16}/></button> : <button className="ghost" onClick={onExplore} type="button">Explore courses <Compass size={16}/></button>}</article>
      </div>
    </>}
    {section === 'pathways' && <div className="account-panel"><div className="account-section-head"><div><small className="eyebrow">SAVED ROUTES</small><h2>My pathways</h2></div><button className="ghost" type="button" onClick={onBuild}>New route <ArrowRight size={16}/></button></div>
      {saved.length ? <><label className="account-path-select">Select a saved pathway<select value={current?.id ?? ''} onChange={e => onSelect(e.target.value)}>{saved.map(item => <option key={item.id} value={item.id}>{item.pathway.career_goal}</option>)}</select></label>
        {progress ? <div className="account-milestones">{progress.milestones.map((step, index) => <div className="account-milestone" key={step.skill_id}><div className="account-milestone-number">{String(index+1).padStart(2,'0')}</div><div><h3>{skillName(step.skill_id)}</h3><small>{step.status.replaceAll('_',' ')}</small></div><button type="button" aria-label={(step.status === 'completed' ? 'Mark incomplete: ' : 'Mark complete: ') + skillName(step.skill_id)} onClick={() => onProgress(step.skill_id,step.status === 'completed' ? 'not_started' : 'completed')}><CheckCircle2 size={18}/>{step.status === 'completed' ? 'Completed' : 'Mark complete'}</button></div>)}</div>
        : <p className="account-subtle">Loading this pathway's progress…</p>}</>
      : <div className="account-blank"><GitBranch size={30}/><h3>No saved pathways</h3><p>Create a learning plan and save it here when you are ready.</p><button className="primary" onClick={onBuild} type="button">Build a pathway</button></div>}</div>}
    {section === 'resources' && <div className="account-panel"><div className="account-section-head"><div><small className="eyebrow">PERSONAL LIBRARY</small><h2>Saved courses</h2></div><button className="ghost" onClick={onExplore} type="button">Browse courses <ArrowRight size={16}/></button></div>
      {bookmarks.length ? <div className="account-bookmarks">{bookmarks.map(id => <div key={id}><BookOpen size={19}/><span>{id}</span><small>Saved reference</small></div>)}</div>
      : <div className="account-blank"><Bookmark size={29}/><h3>No bookmarks yet</h3><p>Save real catalog courses when approved learning providers become available.</p><button className="primary" onClick={onExplore} type="button">Explore courses</button></div>}</div>}
    <div className="account-privacy"><RotateCcw size={15}/> Your progress comes from account-scoped records. Unverified course listings are not presented as completed learning.</div>
  </section>
}
