import {useEffect,useState,type FormEvent} from 'react'
import {ArrowRight,CheckCircle2,Clock3,Compass,LoaderCircle,Save,SlidersHorizontal} from 'lucide-react'
import type {LearningPreferences,LearningPreferencesUpdate,Skill} from './api'

type Props={
  value:LearningPreferences
  skills:Skill[]
  saving:boolean
  onSave:(changes:LearningPreferencesUpdate)=>Promise<void>
  onApply:()=>void
}

export function editablePreferences(value:LearningPreferences):LearningPreferencesUpdate{
  return {
    display_name:value.display_name,
    career_goal:value.career_goal,
    weekly_hours:value.weekly_hours,
    target_skill_ids:[...value.target_skill_ids],
    known_skill_ids:[...value.known_skill_ids],
  }
}

export default function AccountPreferencesPanel({value,skills,saving,onSave,onApply}:Props){
  const [draft,setDraft]=useState<LearningPreferencesUpdate>(()=>editablePreferences(value))
  const [editOpen,setEditOpen]=useState(!value.onboarding_completed)
  const [problem,setProblem]=useState('')
  useEffect(()=>{
    setDraft(editablePreferences(value))
    setProblem('')
  },[value])

  const changed=JSON.stringify(draft)!==JSON.stringify(editablePreferences(value))
  const canApply=Boolean(value.career_goal.trim()&&value.target_skill_ids.length>0)
  const toggle=(key:'target_skill_ids'|'known_skill_ids',id:string)=>
    setDraft(state=>({
      ...state,
      [key]:state[key].includes(id)?state[key].filter(skill=>skill!==id):[...state[key],id],
    }))

  async function submit(event:FormEvent<HTMLFormElement>){
    event.preventDefault()
    if(saving)return
    setProblem('')
    try{
      await onSave({
        ...draft,
        display_name:draft.display_name.trim(),
        career_goal:draft.career_goal.trim(),
      })
    }catch{
      setProblem('Your changes could not be saved. Check your connection and skill selections.')
    }
  }

  return <section className="account-preferences" aria-labelledby="preferences-heading">
    <div className="account-preferences-header">
      <div className="account-preferences-icon"><SlidersHorizontal size={20}/></div>
      <div className="account-preferences-lead">
        <small className="eyebrow">PERSONALIZE YOUR LEARNING</small>
        <h2 id="preferences-heading">Your learning profile</h2>
        <p>Set your goals once, then choose when to apply them to a pathway.</p>
      </div>
      <span className={'account-preferences-status '+(value.onboarding_completed?'is-ready':'is-pending')}>
        {value.onboarding_completed?<CheckCircle2 size={15}/>:<Compass size={15}/>}
        {value.onboarding_completed?'Profile ready':'Setup optional'}
      </span>
    </div>
    <div className="account-preferences-summary">
      <div><small>Career direction</small><strong>{value.career_goal||'Not set'}</strong></div>
      <div><small>Weekly study time</small><strong><Clock3 size={15}/>{value.weekly_hours} hours</strong></div>
      <div><small>Target skills</small><strong>{value.target_skill_ids.length}</strong></div>
    </div>
    <div className="account-preferences-actions">
      <button type="button" className="account-preferences-edit" onClick={()=>setEditOpen(open=>!open)} aria-expanded={editOpen} aria-controls="account-preferences-form">{editOpen?'Hide editor':'Edit preferences'} <SlidersHorizontal size={15}/></button>
      <button type="button" className="account-preferences-apply" disabled={!canApply} onClick={onApply}>Use in pathway builder <ArrowRight size={16}/></button>
    </div>
    {editOpen&&<form id="account-preferences-form" className="account-preferences-form" onSubmit={submit}>
      <div className="account-preferences-fields">
        <label>Display name <input type="text" maxLength={80} autoComplete="nickname"
          value={draft.display_name} onChange={event=>setDraft(state=>({...state,display_name:event.target.value}))}
          placeholder="How you'd like to be addressed"/></label>
        <label>Career goal <input type="text" maxLength={120}
          value={draft.career_goal} onChange={event=>setDraft(state=>({...state,career_goal:event.target.value}))}
          placeholder="e.g. Frontend Developer"/></label>
        <label>Hours per week <input type="number" inputMode="numeric" min={1} max={80} required
          value={draft.weekly_hours} onChange={event=>setDraft(state=>({...state,weekly_hours:Number(event.target.value)}))}/></label>
      </div>
      <div className="account-preferences-skillsets">
        <fieldset>
          <legend>Skills you want to learn <small>Target skills</small></legend>
          {skills.length?skills.map(skill=><label className="account-skill-choice" key={skill.id}>
            <input type="checkbox" checked={draft.target_skill_ids.includes(skill.id)}
              disabled={saving||(!draft.target_skill_ids.includes(skill.id)&&draft.target_skill_ids.length>=32)}
              onChange={()=>toggle('target_skill_ids',skill.id)}/><span>{skill.name}</span>
          </label>):<p>Skill catalog unavailable. Keep existing selections until it is connected.</p>}
        </fieldset>
        <fieldset>
          <legend>Skills you already know <small>Optional</small></legend>
          {skills.length?skills.map(skill=><label className="account-skill-choice" key={skill.id}>
            <input type="checkbox" checked={draft.known_skill_ids.includes(skill.id)}
              disabled={saving||(!draft.known_skill_ids.includes(skill.id)&&draft.known_skill_ids.length>=128)}
              onChange={()=>toggle('known_skill_ids',skill.id)}/><span>{skill.name}</span>
          </label>):<p>Skill catalog unavailable.</p>}
        </fieldset>
      </div>
      <div className="account-preferences-foot">
        <p>Preferences are private to this signed-in account. They do not change a saved pathway until you explicitly create or update one.</p>
        <div>
          <button type="button" className="account-preferences-reset" disabled={!changed||saving}
            onClick={()=>{setDraft(editablePreferences(value));setProblem('')}}>Discard changes</button>
          <button type="submit" className="account-preferences-save" disabled={!changed||saving||!Number.isInteger(draft.weekly_hours)||draft.weekly_hours<1||draft.weekly_hours>80}>
            {saving?<LoaderCircle size={16} className="feedback-busy-icon" aria-hidden="true"/>:<Save size={16}/>}{saving?'Saving…':'Save preferences'}</button>
        </div>
      </div>
      {problem&&<p className="account-preferences-error" role="alert">{problem}</p>}
    </form>}
  </section>
}
