/** A synchronous single-flight lock prevents duplicate touch actions before React renders. */
export class ActionGate{
  private readonly pending=new Set<string>()
  acquire(key:string):boolean{
    if(this.pending.has(key))return false
    this.pending.add(key)
    return true
  }
  release(key:string):void{this.pending.delete(key)}
  has(key:string):boolean{return this.pending.has(key)}
  clear():void{this.pending.clear()}
}
