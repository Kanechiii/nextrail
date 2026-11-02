/** Same-origin, ephemeral progress invalidation without account or pathway data. */
export const PROGRESS_CHANNEL='nextrail:progress-invalidation:v1'
export const PROGRESS_EVENT='confirmed-progress-updated'
export type InvalidationMessage={kind:typeof PROGRESS_EVENT}

type ChannelLike={
  onmessage:((event:MessageEvent<unknown>)=>void)|null
  postMessage:(value:InvalidationMessage)=>void
  close:()=>void
}
export type ProgressBridge={available:boolean;publish:()=>void;close:()=>void}

export function isProgressInvalidation(value:unknown):value is InvalidationMessage{
  if(!value||typeof value!=='object'||Array.isArray(value))return false
  const item=value as Record<string,unknown>
  return Object.keys(item).length===1&&item.kind===PROGRESS_EVENT
}

/** BroadcastChannel is best-effort; no persistent storage or polling fallback. */
export function connectProgressBridge(
  onRemote:()=>void,
  create:()=>ChannelLike=()=>new BroadcastChannel(PROGRESS_CHANNEL),
):ProgressBridge{
  let channel:ChannelLike
  try{
    if(typeof BroadcastChannel==='undefined'&&arguments.length<2)
      return {available:false,publish:()=>{},close:()=>{}}
    channel=create()
    channel.onmessage=event=>{
      if(isProgressInvalidation(event.data))onRemote()
    }
  }catch{return {available:false,publish:()=>{},close:()=>{}}}
  let closed=false
  return {
    available:true,
    publish:()=>{
      if(closed)return
      try{
        // No account email, bearer, pathway id or completion details cross tabs.
        channel.postMessage({kind:PROGRESS_EVENT})
      }catch{/* Unsupported or disposed channel: backend If-Match still guards writes. */}
    },
    close:()=>{
      if(closed)return
      closed=true
      try{channel.onmessage=null;channel.close()}catch{}
    },
  }
}
