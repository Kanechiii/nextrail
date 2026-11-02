import {useEffect,useRef} from 'react'

type LifecycleActions={onResume:()=>void;onOffline:()=>void;onOnline:()=>void}
const RESUME_INTERVAL_MS=15000

/** Read-only revalidation on return; never submits a write or clears login state. */
export function useMobileLifecycle(actions:LifecycleActions){
  const latest=useRef(actions)
  latest.current=actions
  useEffect(()=>{
    let lastResume=0
    const resume=()=>{
      if(document.visibilityState==='hidden')return
      const now=Date.now()
      if(now-lastResume<RESUME_INTERVAL_MS)return
      lastResume=now
      latest.current.onResume()
    }
    const offline=()=>latest.current.onOffline()
    const online=()=>latest.current.onOnline()
    document.addEventListener('visibilitychange',resume)
    window.addEventListener('pageshow',resume)
    window.addEventListener('online',online)
    window.addEventListener('offline',offline)
    return()=>{
      document.removeEventListener('visibilitychange',resume)
      window.removeEventListener('pageshow',resume)
      window.removeEventListener('online',online)
      window.removeEventListener('offline',offline)
    }
  },[])
}

/** Scroll an obscured focused form control into view when the mobile keyboard
 * reduces visualViewport. No focus changes, no zoom or scroll restrictions.
 */
export function useVisibleMobileInput(){
  useEffect(()=>{
    const viewport=window.visualViewport
    if(!viewport)return
    let frame=0
    const placeFocus=()=>{
      frame=0
      if(document.visibilityState==='hidden')return
      const focused=document.activeElement
      if(!(focused instanceof HTMLElement)||!
        focused.matches('input,textarea,select,[contenteditable="true"]'))return
      // Don't interfere with ordinary desktop resize or zoom-only events.
      if(viewport.height>window.innerHeight-120)return
      const bounds=focused.getBoundingClientRect()
      const high=viewport.offsetTop+12
      const low=viewport.offsetTop+viewport.height-16
      if(bounds.top<high||bounds.bottom>low)
        focused.scrollIntoView({block:'nearest',inline:'nearest',behavior:'auto'})
    }
    const schedule=()=>{
      if(frame)window.cancelAnimationFrame(frame)
      frame=window.requestAnimationFrame(placeFocus)
    }
    viewport.addEventListener('resize',schedule)
    viewport.addEventListener('scroll',schedule)
    document.addEventListener('focusin',schedule)
    return()=>{
      viewport.removeEventListener('resize',schedule)
      viewport.removeEventListener('scroll',schedule)
      document.removeEventListener('focusin',schedule)
      if(frame)window.cancelAnimationFrame(frame)
    }
  },[])
}
