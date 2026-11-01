import test from 'node:test'
import assert from 'node:assert/strict'
import {ApiError,call,isAuthFailure} from '../src/api.ts'

const stub=(t,fn)=>{
  const before=globalThis.fetch
  globalThis.fetch=fn
  t.after(()=>{globalThis.fetch=before})
}

test('a real 401 invalidates auth, but a 503 keeps the session eligible for retry',async t=>{
  stub(t,async()=>new Response(JSON.stringify({detail:'invalid'}),{status:401}))
  await assert.rejects(()=>call('/v1/me','GET',undefined,'token'),error=>{
    assert.ok(error instanceof ApiError)
    assert.equal(error.status,401)
    assert.equal(isAuthFailure(error),true)
    return true
  })
  globalThis.fetch=async()=>new Response(JSON.stringify({error:{code:'DATABASE_UNAVAILABLE'}}),{status:503,headers:{'Retry-After':'3'}})
  await assert.rejects(()=>call('/v1/me','GET',undefined,'token'),error=>{
    assert.equal(error.status,503)
    assert.equal(error.retryAfterSeconds,3)
    assert.equal(isAuthFailure(error),false)
    assert.doesNotMatch(error.message,/token|sqlite|private/i)
    return true
  })
})

test('429 reads safe Retry-After seconds with useful feedback',async t=>{
  stub(t,async()=>new Response('{}',{status:429,headers:{'Retry-After':'8'}}))
  await assert.rejects(()=>call('/v1/courses'),error=>{
    assert.equal(error.status,429)
    assert.equal(error.code,'RATE_LIMITED')
    assert.equal(error.retryAfterSeconds,8)
    assert.match(error.message,/8 seconds/)
    return true
  })
  globalThis.fetch=async()=>new Response('{}',{status:429,headers:{'Retry-After':'infinite'}})
  await assert.rejects(()=>call('/v1/courses'),error=>{
    assert.equal(error.retryAfterSeconds,null)
    assert.match(error.message,/shortly/)
    return true
  })
})

test('network failures are non-auth errors and never leak internal exception text',async t=>{
  stub(t,async()=>{throw new Error('private credentials leaked in network stack')})
  await assert.rejects(()=>call('/v1/courses'),error=>{
    assert.equal(error.code,'NETWORK_UNAVAILABLE')
    assert.equal(isAuthFailure(error),false)
    assert.doesNotMatch(error.message,/credentials|leaked/i)
    return true
  })
})

test('timed-out fetch aborts and produces an explicit recoverable error',async t=>{
  stub(t,async(_url,opts)=>new Promise((_resolve,reject)=>{
    opts.signal.addEventListener('abort',()=>reject(new Error('aborted')),{once:true})
  }))
  await assert.rejects(()=>call('/v1/courses','GET',undefined,undefined,{timeoutMs:1000}),error=>{
    assert.equal(error.code,'REQUEST_TIMEOUT')
    assert.match(error.message,/timed out/)
    return true
  })
})

test('corrupt JSON returns controlled invalid-response error',async t=>{
  stub(t,async()=>new Response('invalid-json',{status:200,headers:{'content-type':'application/json'}}))
  await assert.rejects(()=>call('/v1/me'),error=>{
    assert.equal(error.code,'INVALID_RESPONSE')
    assert.equal(isAuthFailure(error),false)
    return true
  })
})

test('idempotent create passes exact UUID key but never retries automatically',async t=>{
  let count=0
  const key='a3d53e6f-e581-4d17-8791-5ac155ab3900'
  stub(t,async(_url,opts)=>{
    count++
    assert.equal(opts.headers['Idempotency-Key'],key)
    assert.equal(opts.headers.Authorization,'Bearer token')
    assert.equal(opts.method,'POST')
    return new Response(JSON.stringify({id:'saved'}),{status:201})
  })
  assert.deepEqual(await call('/v1/me/pathways','POST',{career_goal:'Frontend'},'token',{idempotencyKey:key}),{id:'saved'})
  assert.equal(count,1)
})

test('HTTP 409 conflicts and validation remain non-retryable',async t=>{
  stub(t,async()=>new Response('{}',{status:409}))
  await assert.rejects(()=>call('/v1/me/pathways','POST'),error=>{
    assert.equal(error.code,'IDEMPOTENCY_CONFLICT')
    assert.equal(isAuthFailure(error),false)
    return true
  })
  globalThis.fetch=async()=>new Response('{}',{status:422})
  await assert.rejects(()=>call('/v1/pathways/preview','POST'),error=>{
    assert.equal(error.code,'INVALID_INPUT')
    return true
  })
})
