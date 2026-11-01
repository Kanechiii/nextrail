export type Course={id:string;title:string;url?:string;provider_id:string;provider_name:string;skills:string[];access_cost:string;certificate_cost:string;evidence_status:string;synthetic:boolean}
export type Skill={id:string;name:string;prerequisites:string[]}
export type Plan={career_goal:string;target_skill_ids:string[];known_skill_ids:string[];weekly_hours:number;zero_budget:boolean}
export type Pathway={schema_version:string;career_goal:string;weekly_hours:number;generation_mode:string;milestones:{order:number;skill_id:string;resource_ids:string[];rationale:string}[]}
export type LearningPreferences={display_name:string;career_goal:string;weekly_hours:number;target_skill_ids:string[];known_skill_ids:string[];onboarding_completed:boolean;updated_at:string|null}
export type LearningPreferencesUpdate=Pick<LearningPreferences,'display_name'|'career_goal'|'weekly_hours'|'target_skill_ids'|'known_skill_ids'>
const base=(import.meta.env?.VITE_API_BASE_URL||'/api').replace(/\/$/,'')
export class ApiError extends Error{
  readonly status:number
  readonly code:string
  readonly retryAfterSeconds:number|null
  constructor(message:string,status:number,code:string,retryAfterSeconds:number|null=null){
    super(message)
    this.name='ApiError'
    this.status=status
    this.code=code
    this.retryAfterSeconds=retryAfterSeconds
  }
}
export const isAuthFailure=(reason:unknown)=>reason instanceof ApiError&&reason.status===401
const retrySeconds=(value:string|null)=>{
  if(!value||!/^\d{1,5}$/.test(value))return null
  const seconds=Number(value)
  return seconds>0&&seconds<=86400?seconds:null
}
type CallOptions={idempotencyKey?:string;timeoutMs?:number}
export async function call<T>(path:string,method='GET',body?:unknown,token?:string,options:CallOptions={}):Promise<T>{
  const headers:Record<string,string>={'Accept':'application/json'}
  if(body!==undefined)headers['Content-Type']='application/json'
  if(token)headers.Authorization='Bearer '+token
  if(options.idempotencyKey)headers['Idempotency-Key']=options.idempotencyKey
  const timeoutMs=options.timeoutMs??12000
  if(!Number.isFinite(timeoutMs)||timeoutMs<1000||timeoutMs>60000)throw new ApiError('Invalid timeout settings.',0,'CLIENT_INVALID_TIMEOUT')
  const controller=new AbortController()
  const timer=setTimeout(()=>controller.abort(),timeoutMs)
  let res:Response
  try{
    res=await fetch(base+path,{method,headers,body:body===undefined?undefined:JSON.stringify(body),cache:'no-store',signal:controller.signal})
  }catch(reason){
    if(controller.signal.aborted)throw new ApiError('The request timed out. Check your connection and retry.',0,'REQUEST_TIMEOUT')
    throw new ApiError('API unavailable. Start the backend or check your connection.',0,'NETWORK_UNAVAILABLE')
  }finally{
    clearTimeout(timer)
  }
  if(!res.ok){
    if(res.status===401)throw new ApiError('Session expired or invalid.',401,'SESSION_INVALID')
    if(res.status===429){
      const retry=retrySeconds(res.headers.get('Retry-After'))
      throw new ApiError(retry!==null?'Too many requests. Try again in '+retry+' seconds.':'Too many requests. Try again shortly.',429,'RATE_LIMITED',retry)
    }
    if(res.status===503)throw new ApiError('Service temporarily unavailable. Your changes may not have been saved.',503,'SERVICE_UNAVAILABLE',retrySeconds(res.headers.get('Retry-After')))
    if(res.status===422)throw new ApiError('Please check your inputs.',422,'INVALID_INPUT')
    if(res.status===409)throw new ApiError('This save key was already used with different inputs.',409,'IDEMPOTENCY_CONFLICT')
    if(res.status>=500)throw new ApiError('Server temporarily unavailable. Please retry.',res.status,'SERVER_ERROR')
    throw new ApiError('Request failed ('+res.status+').',res.status,'REQUEST_REJECTED')
  }
  try{return await res.json() as T}catch{
    throw new ApiError('The service returned an invalid response. Please reload this view.',0,'INVALID_RESPONSE')
  }
}

