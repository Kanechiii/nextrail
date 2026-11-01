import {useCallback,useEffect,useRef,useState} from 'react'
import {AlertCircle,CheckCircle2,Info,X} from 'lucide-react'
import {appendFeedback,removeFeedback,suppressRepeatedError,type FeedbackKind,type FeedbackMessage} from './feedbackModel'

type ToastKind=FeedbackKind
type ToastMessage=FeedbackMessage

export function useFeedbackToasts(){
  const [toasts,setToasts]=useState<ToastMessage[]>([])
  const serial=useRef(0)
  const lastError=useRef<{message:string;at:number}|null>(null)
  const push=useCallback((kind:ToastKind,message:string)=>{
    const now=Date.now()
    if(kind==='error'){
      if(suppressRepeatedError(lastError.current,message,now))return
      lastError.current={message,at:now}
    }
    const id=++serial.current
    setToasts(previous=>appendFeedback(previous,kind,message,id))
  },[])
  const dismiss=useCallback((id:number)=>setToasts(previous=>removeFeedback(previous,id)),[])
  const clear=useCallback(()=>{lastError.current=null;setToasts([])},[])
  return {toasts,push,dismiss,clear}
}

function ToastItem({toast,onDismiss}:{toast:ToastMessage;onDismiss:(id:number)=>void}){
  const [paused,setPaused]=useState(false)
  const closeRef=useRef<HTMLButtonElement>(null)
  const dismiss=()=>{
    // Arrival never steals focus. When a focused dismiss button disappears,
    // return focus to the next toast or a stable workspace control.
    if(document.activeElement===closeRef.current){
      const buttons=Array.from(closeRef.current?.closest('.feedback-toast-region')?.querySelectorAll<HTMLButtonElement>('.feedback-toast-close')??[])
      const index=buttons.indexOf(closeRef.current!)
      const next=buttons[index+1]??buttons[index-1]??document.querySelector<HTMLButtonElement>('.top .theme-switch')
      next?.focus()
    }
    onDismiss(toast.id)
  }
  useEffect(()=>{
    // Keep errors visible until the user dismisses them.
    if(paused||toast.kind==='error')return
    const timer=window.setTimeout(()=>onDismiss(toast.id),toast.kind==='success'?4500:6000)
    return()=>window.clearTimeout(timer)
  },[toast.id,toast.kind,paused,onDismiss])
  const Icon=toast.kind==='success'?CheckCircle2:toast.kind==='error'?AlertCircle:Info
  return <div className={'feedback-toast feedback-toast-'+toast.kind}
    role={toast.kind==='error'?'alert':'status'} aria-live={toast.kind==='error'?'assertive':'polite'} aria-atomic="true"
    onMouseEnter={()=>setPaused(true)} onMouseLeave={()=>setPaused(false)}
    onFocusCapture={()=>setPaused(true)} onBlurCapture={event=>{
      if(!event.currentTarget.contains(event.relatedTarget))setPaused(false)
    }}>
    <Icon size={19} aria-hidden="true" className="feedback-toast-icon"/>
    <span className="feedback-toast-message">{toast.message}</span>
    <button type="button" ref={closeRef} className="feedback-toast-close"
      aria-label={'Dismiss '+toast.kind+' notification'} onClick={dismiss}>
      <X size={16} aria-hidden="true"/>
    </button>
  </div>
}

export function FeedbackToasts({toasts,onDismiss}:{
  toasts:ToastMessage[];onDismiss:(id:number)=>void
}){
  return <div className="feedback-toast-region" aria-label="Notifications">
    {toasts.map(toast=><ToastItem key={toast.id} toast={toast} onDismiss={onDismiss}/>)}
  </div>
}
