import {afterEach,vi} from 'vitest'
import {cleanup} from '@testing-library/react'
vi.mock('animejs',()=>({animate:vi.fn(),stagger:vi.fn(()=>0),createScope:vi.fn(()=>{const scope={add:(callback:()=>void)=>{callback();return scope},revert:vi.fn()};return scope})}))
afterEach(()=>{cleanup();vi.restoreAllMocks();localStorage.clear();history.replaceState({},'','/')})
Object.defineProperty(window,'matchMedia',{writable:true,value:vi.fn((query:string)=>({matches:query.includes('reduced-motion')||query.includes('hover: hover'),media:query,addEventListener:vi.fn(),removeEventListener:vi.fn()}))})
HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','');this.querySelector<HTMLElement>('button,input')?.focus()}
HTMLDialogElement.prototype.close=function(){this.removeAttribute('open')}
