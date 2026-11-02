import type {Plan} from './api'

/** Explicit, tab-scoped guest planning checkpoint. Never persist auth state. */
export const GUEST_CHECKPOINT_KEY='nextrail:guest-draft-opt-in:v1'
export const CHECKPOINT_MAX_AGE_MS=6*60*60*1000

const SKILL_ID=/^[a-z0-9][a-z0-9._-]{0,63}$/
type Checkpoint={version:1;savedAt:number;plan:Plan}
type StorageLike=Pick<Storage,'getItem'|'setItem'|'removeItem'>

export function safeGuestPlan(value:unknown):value is Plan{
  if(value===null||typeof value!=='object'||Array.isArray(value))return false
  const obj=value as Record<string,unknown>
  const keys=Object.keys(obj)
  if(keys.length!==5||keys.some(key=>![
    'career_goal','target_skill_ids','known_skill_ids','weekly_hours','zero_budget',
  ].includes(key)))return false
  const skills=(ids:unknown)=>Array.isArray(ids)&&ids.length<=32&&
    ids.every(item=>typeof item==='string'&&SKILL_ID.test(item))&&
    new Set(ids).size===ids.length
  return typeof obj.career_goal==='string'&&obj.career_goal.length>0&&
    obj.career_goal.trim().length>0&&obj.career_goal.length<=120&&
    skills(obj.target_skill_ids)&&skills(obj.known_skill_ids)&&
    Number.isInteger(obj.weekly_hours)&&Number(obj.weekly_hours)>=1&&
    Number(obj.weekly_hours)<=30&&typeof obj.zero_budget==='boolean'
}
export function encodeCheckpoint(plan:Plan,now=Date.now()):string{
  if(!safeGuestPlan(plan)||!Number.isFinite(now)||now<=0)
    throw new Error('Only valid guest planning choices can be saved on this device.')
  const copy:Plan={
    career_goal:plan.career_goal,
    target_skill_ids:[...plan.target_skill_ids],
    known_skill_ids:[...plan.known_skill_ids],
    weekly_hours:plan.weekly_hours,
    zero_budget:plan.zero_budget,
  }
  return JSON.stringify({version:1,savedAt:now,plan:copy} satisfies Checkpoint)
}
export function decodeCheckpoint(raw:string|null,now=Date.now()):Plan|null{
  if(!raw||raw.length>8192)return null
  try{
    const data:unknown=JSON.parse(raw)
    if(data===null||typeof data!=='object'||Array.isArray(data))return null
    const item=data as Record<string,unknown>
    if(Object.keys(item).length!==3||item.version!==1||
      typeof item.savedAt!=='number'||!Number.isFinite(item.savedAt)||
      now<item.savedAt||now-item.savedAt>CHECKPOINT_MAX_AGE_MS||
      !safeGuestPlan(item.plan))return null
    const p=item.plan
    return {...p,target_skill_ids:[...p.target_skill_ids],known_skill_ids:[...p.known_skill_ids]}
  }catch{return null}
}
export function readCheckpoint(store:StorageLike|null,now=Date.now()):Plan|null{
  if(!store)return null
  try{
    const raw=store.getItem(GUEST_CHECKPOINT_KEY)
    const plan=decodeCheckpoint(raw,now)
    if(raw&&!plan)store.removeItem(GUEST_CHECKPOINT_KEY)
    return plan
  }catch{return null}
}
export function writeCheckpoint(store:StorageLike|null,plan:Plan,now=Date.now()):boolean{
  if(!store)return false
  try{store.setItem(GUEST_CHECKPOINT_KEY,encodeCheckpoint(plan,now));return true}
  catch{return false}
}
export function discardCheckpoint(store:StorageLike|null):boolean{
  if(!store)return false
  try{store.removeItem(GUEST_CHECKPOINT_KEY);return true}
  catch{return false}
}
export function accessibleTabStorage():StorageLike|null{
  try{return typeof window==='undefined'?null:window.sessionStorage}catch{return null}
}
