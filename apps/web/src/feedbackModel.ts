/** Pure toast queue. Keep the latest three distinct messages, no browser storage. */
export type FeedbackKind='success'|'error'|'info'
export type FeedbackMessage={id:number;kind:FeedbackKind;message:string}

export function appendFeedback(
  previous:FeedbackMessage[],kind:FeedbackKind,message:string,id:number
):FeedbackMessage[]{
  const trimmed=message.trim().slice(0,300)
  if(!trimmed)return previous
  return [...previous.filter(item=>item.message!==trimmed).slice(-2),{id,kind,message:trimmed}]
}

export function removeFeedback(previous:FeedbackMessage[],id:number){
  return previous.filter(item=>item.id!==id)
}
