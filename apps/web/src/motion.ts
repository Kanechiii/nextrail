import {useEffect,type RefObject} from 'react'
import {animate,createScope,stagger,svg} from 'animejs'

const MAX_CARDS=8
const MAX_STEPS=12

/** Animation is decorative. Content is always fully visible without JavaScript motion. */
export function useWorkspaceMotion(
  root:RefObject<HTMLDivElement|null>,
  view:'discover'|'pathway'|'learning',
  previewExamples:boolean,
  milestoneCount:number,
  completed:number,
){
  useEffect(()=>{
    const element=root.current
    if(!element||typeof window==='undefined')return
    const preference=window.matchMedia('(prefers-reduced-motion: reduce)')
    let scope:ReturnType<typeof createScope>|null=null

    function renderMotion(){
      scope?.revert()
      scope=null
      if(preference.matches||!element)return

      scope=createScope({root:element}).add(()=>{
        const headings=Array.from(element.querySelectorAll<HTMLElement>(
          'main .hero h1, main .hero p, main .intro h1, main .intro p'
        )).slice(0,4)
        if(headings.length)animate(headings,{
          opacity:{from:0,to:1},
          y:{from:14,to:0},
          delay:stagger(65),
          duration:460,
          ease:'out(3)',
        })

        const cards=Array.from(element.querySelectorAll<HTMLElement>('.cards .card-body')).slice(0,MAX_CARDS)
        if(cards.length)animate(cards,{
          opacity:{from:0,to:1},
          y:{from:10,to:0},
          delay:stagger(40),
          duration:340,
          ease:'out(3)',
        })

        const route=element.querySelector<SVGPathElement>('[data-motion-route]')
        if(route&&view==='discover'){
          animate(svg.createDrawable(route),{
            draw:['0 0','0 1'],
            duration:880,
            ease:'inOut(3)',
          })
        }

        const steps=Array.from(element.querySelectorAll<HTMLElement>('.output .step')).slice(0,MAX_STEPS)
        if(steps.length)animate(steps,{
          opacity:{from:0,to:1},
          y:{from:12,to:0},
          delay:stagger(50),
          duration:390,
          ease:'out(3)',
        })

        const progressFill=element.querySelector<HTMLElement>('.completion-meter-fill')
        if(progressFill&&view==='learning')animate(progressFill,{
          scaleX:{from:0,to:1},
          duration:560,
          ease:'out(3)',
        })

        const completeIcons=Array.from(element.querySelectorAll<SVGElement>(
          '.progress-row.is-complete button svg'
        )).slice(0,MAX_STEPS)
        if(completeIcons.length&&view==='learning')animate(completeIcons,{
          scale:{from:.8,to:1},
          delay:stagger(36),
          duration:260,
          ease:'out(3)',
        })

        const activeIcon=element.querySelector<SVGElement>('.rail nav button.active svg')
        if(activeIcon)animate(activeIcon,{
          rotate:{from:-8,to:0},
          scale:{from:.86,to:1},
          duration:290,
          ease:'out(3)',
        })
      })
    }

    renderMotion()
    preference.addEventListener('change',renderMotion)
    return ()=>{
      preference.removeEventListener('change',renderMotion)
      scope?.revert()
    }
  },[root,view,previewExamples,milestoneCount,completed])
}
