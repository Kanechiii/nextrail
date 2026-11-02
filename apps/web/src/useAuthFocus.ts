import {useEffect,useRef,type RefObject} from 'react'

type AuthFocusProps={
  open:boolean
  container:RefObject<HTMLDivElement|null>
  opener:RefObject<HTMLElement|null>
  onClose:()=>void
}
const SELECTOR='a[href],button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),[tabindex]:not([tabindex="-1"])'

/** Keyboard-only focus containment for the optional account overlay. */
export function useAuthFocus({open,container,opener,onClose}:AuthFocusProps){
  const latestClose=useRef(onClose)
  latestClose.current=onClose
  useEffect(()=>{
    if(!open)return
    const parent=container.current
    if(!parent)return
    const before=document.activeElement
    if(before instanceof HTMLElement&&!parent.contains(before))opener.current=before
    const focusable=()=>Array.from(parent.querySelectorAll<HTMLElement>(SELECTOR))
      .filter(el=>el.getClientRects().length>0&&!el.closest('[hidden],[inert]'))
    const frame=window.requestAnimationFrame(()=>{
      const input=parent.querySelector<HTMLElement>('input:not(:disabled)')
      ;(input??focusable()[0]??parent).focus()
    })
    const keydown=(event:KeyboardEvent)=>{
      if(event.key==='Escape'){
        event.preventDefault()
        event.stopPropagation()
        latestClose.current()
        return
      }
      if(event.key!=='Tab')return
      const controls=focusable()
      if(!controls.length){event.preventDefault();parent.focus();return}
      const first=controls[0],last=controls[controls.length-1]
      if(event.shiftKey){
        if(document.activeElement===first||!parent.contains(document.activeElement)){
          event.preventDefault();last.focus()
        }
      }else if(document.activeElement===last||!parent.contains(document.activeElement)){
        event.preventDefault();first.focus()
      }
    }
    document.addEventListener('keydown',keydown,true)
    return()=>{
      document.removeEventListener('keydown',keydown,true)
      window.cancelAnimationFrame(frame)
      window.requestAnimationFrame(()=>{
        const target=opener.current
        if(target?.isConnected)target.focus()
        else document.querySelector<HTMLElement>('.top .theme-switch')?.focus()
      })
    }
  },[open,container,opener])
}
