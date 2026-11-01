import {useEffect,useRef,useState,useCallback} from 'react'

export const SEARCH_DEBOUNCE_MS=280
export const SKELETON_DELAY_MS=150
export const ACTION_SUCCESS_MS=1600

/** Debounce only the public catalog query. Never delay real responses. */
export function useDebouncedValue<T>(value:T,delay=SEARCH_DEBOUNCE_MS){
  const [stable,setStable]=useState(value)
  useEffect(()=>{
    const timer=window.setTimeout(()=>setStable(value),delay)
    return()=>window.clearTimeout(timer)
  },[value,delay])
  return stable
}

/** Avoid flashing decorative placeholders on fast requests. */
export function useDelayedPending(pending:boolean,delay=SKELETON_DELAY_MS){
  const [visible,setVisible]=useState(false)
  useEffect(()=>{
    if(!pending){setVisible(false);return}
    const timer=window.setTimeout(()=>setVisible(true),delay)
    return()=>window.clearTimeout(timer)
  },[pending,delay])
  return pending&&visible
}

/** Confirmed action feedback, never a substitute for server persistence. */
export function useActionSuccess(){
  const [successKey,setSuccessKey]=useState<string|null>(null)
  const timer=useRef<number|null>(null)
  const reset=useCallback(()=>{
    if(timer.current!==null)window.clearTimeout(timer.current)
    timer.current=null
    setSuccessKey(null)
  },[])
  const celebrate=useCallback((key:string)=>{
    if(timer.current!==null)window.clearTimeout(timer.current)
    setSuccessKey(key)
    timer.current=window.setTimeout(()=>{
      setSuccessKey(null)
      timer.current=null
    },ACTION_SUCCESS_MS)
  },[])
  useEffect(()=>()=>{if(timer.current!==null)window.clearTimeout(timer.current)},[])
  return {successKey,celebrate,reset}
}
