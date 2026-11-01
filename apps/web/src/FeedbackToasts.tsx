import {useCallback,useEffect,useRef,useState} from 'react'
import {AlertCircle,CheckCircle2,Info,X} from 'lucide-react'
import {appendFeedback,removeFeedback,type FeedbackKind,type FeedbackMessage} from './feedbackModel'

type ToastKind=FeedbackKind
type ToastMessage=FeedbackMessage

export function useFeedbackToasts(){
  const [toasts,setToasts]=useState<ToastMessage[]>([])
  const serial=useRef(0)
  const push=useCallback((kind:ToastKind,message:string)=>{
    const id=++serial.current
    setToasts(previous=>appendFeedback(previous,kind,message,id))
  },[])
  const dismiss=useCallback((id:number)=>setToasts(previous=>removeFeedback(previous,id)),[])
  const clear=useCallback(()=>setToasts([]),[])
  return {toasts,push,dismiss,clear}
}

function ToastItem({toast,onDismiss}:{toast:ToastMessage;onDismiss:(id:number)=>void}){
  const [paused,setPaused]=useState(false)
  useEffect(()=>{
    // Keep errors visible until the user dismisses them.
    if(paused||toast.kind==='error')return
    const timer=window.setTimeout(()=>onDismiss(toast.id),toast.kind==='success'?4500:6000)
    return()=>window.clearTimeout(timer)
  },[toast.id,toast.kind,paused,onDismiss])
  const Icon=toast.kind==='success'?CheckCircle2:toast.kind==='error'?AlertCircle:Info
  return <div className={'feedback-toast feedback-toast-'+toast.kind}
    role={toast.kind==='error'?'alert':'status'} aria-atomic="true"
    onMouseEnter={()=>setPaused(true)} onMouseLeave={()=>setPaused(false)}
    onFocusCapture={()=>setPaused(true)} onBlurCapture={event=>{
      if(!event.currentTarget.contains(event.relatedTarget))setPaused(false)
    }}>
    <Icon size={19} aria-hidden="true" className="feedback-toast-icon"/>
    <span className="feedback-toast-message">{toast.message}</span>
    <button type="button" className="feedback-toast-close"
      aria-label={'Dismiss '+toast.kind+' notification'} onClick={()=>onDismiss(toast.id)}>
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
