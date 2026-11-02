import {useCallback,useEffect,useRef} from 'react'
import {connectProgressBridge,type ProgressBridge} from './progressCoordination'

/** StrictMode-safe cross-tab signals; latest callback without reconnect churn. */
export function useCrossTabProgress(onRemote:()=>void){
  const latest=useRef(onRemote)
  latest.current=onRemote
  const bridge=useRef<ProgressBridge|null>(null)
  useEffect(()=>{
    const connected=connectProgressBridge(()=>latest.current())
    bridge.current=connected
    return()=>{
      connected.close()
      if(bridge.current===connected)bridge.current=null
    }
  },[])
  return useCallback(()=>bridge.current?.publish(),[])
}
