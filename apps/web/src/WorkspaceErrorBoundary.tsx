import {Component,type ErrorInfo,type ReactNode} from 'react'
import {AlertTriangle,RefreshCw} from 'lucide-react'

type Props={children:ReactNode;scope?:'section'|'application';onReturn?:()=>void}
type State={failed:boolean}

/** Catch render/lifecycle crashes without logging private course or account data. */
export default class WorkspaceErrorBoundary extends Component<Props,State>{
  state:State={failed:false}
  static getDerivedStateFromError():State{return {failed:true}}
  componentDidCatch(_error:Error,_info:ErrorInfo){
    // Intentionally do not log error objects or component stacks: render
    // failures can contain private account data or sensitive request context.
  }
  render(){
    if(!this.state.failed)return this.props.children
    return <section className="workspace-recovery" role="alert" aria-labelledby="workspace-recovery-title">
      <AlertTriangle size={28} aria-hidden="true"/>
      <h2 id="workspace-recovery-title">This part of Nextrail couldn't be displayed.</h2>
      <p>Your existing account data was not deleted. Unsaved changes on the failed
        screen might need to be entered again. No save or progress update was retried.</p>
      <div className="workspace-recovery-actions">
        <button type="button" onClick={()=>this.setState({failed:false})}>
          <RefreshCw size={16} aria-hidden="true"/> Try displaying again
        </button>
        {this.props.onReturn&&<button type="button" onClick={()=>{
          this.setState({failed:false})
          this.props.onReturn?.()
        }}>Return to Discover</button>}
        {this.props.scope==='application'&&<button type="button" onClick={()=>window.location.reload()}>
          Reload application
        </button>}
      </div>
    </section>
  }
}
