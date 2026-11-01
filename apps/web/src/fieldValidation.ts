import type {Plan,LearningPreferencesUpdate} from './api'

export type FieldErrors=Partial<Record<'career_goal'|'target_skill_ids'|'weekly_hours'|'display_name',string>>

export function validatePathwayDraft(plan:Plan):FieldErrors{
  const errors:FieldErrors={}
  const direction=plan.career_goal.trim()
  if(!direction||direction.length>120)errors.career_goal='Enter a career direction (up to 120 characters).'
  if(!plan.target_skill_ids.length)errors.target_skill_ids='Select at least one target skill to build a pathway.'
  if(!Number.isInteger(plan.weekly_hours)||plan.weekly_hours<1||plan.weekly_hours>30)
    errors.weekly_hours='Choose between 1 and 30 study hours each week.'
  return errors
}

export function validatePreferencesDraft(value:LearningPreferencesUpdate):FieldErrors{
  const errors:FieldErrors={}
  if(value.display_name.trim().length>80)errors.display_name='Use no more than 80 characters.'
  if(value.career_goal.trim().length>120)errors.career_goal='Use no more than 120 characters.'
  if(!Number.isInteger(value.weekly_hours)||value.weekly_hours<1||value.weekly_hours>80)
    errors.weekly_hours='Enter between 1 and 80 study hours each week.'
  if(value.target_skill_ids.length>32)errors.target_skill_ids='Select no more than 32 target skills.'
  return errors
}
