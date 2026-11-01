import test from 'node:test'
import assert from 'node:assert/strict'
import {spawnSync} from 'node:child_process'
import {mkdtempSync,readFileSync,rmSync,writeFileSync} from 'node:fs'
import {tmpdir} from 'node:os'
import {join} from 'node:path'
import {devServerInvocation} from './dev-server-launch.mjs'

test('Windows dev smoke launches npm JavaScript CLI through node.exe, not npm.cmd',()=>{
  const result=devServerInvocation({
    platform:'win32',
    nodePath:'C:\\Program Files\\nodejs\\node.exe',
    npmCli:'C:\\Program Files\\nodejs\\node_modules\\npm\\bin\\npm-cli.js',
  })
  assert.equal(result.command,'C:\\Program Files\\nodejs\\node.exe')
  assert.deepEqual(result.args,[
    'C:\\Program Files\\nodejs\\node_modules\\npm\\bin\\npm-cli.js',
    'run','dev','--','--strictPort',
  ])
  assert.ok(!result.command.endsWith('.cmd'))
})

test('safe Windows launch works for script paths with spaces, without a shell',()=>{
  const folder=mkdtempSync(join(tmpdir(),'nextrail npm cli '))
  try{
    const file=join(folder,'npm-cli.js')
    writeFileSync(file,'process.stdout.write(JSON.stringify(process.argv.slice(2)))')
    const run=devServerInvocation({
      platform:'win32',
      nodePath:process.execPath,
      npmCli:file,
    })
    const result=spawnSync(run.command,run.args,{encoding:'utf8',shell:false})
    assert.equal(result.status,0,result.stderr)
    assert.deepEqual(JSON.parse(result.stdout),['run','dev','--','--strictPort'])
  }finally{rmSync(folder,{recursive:true,force:true})}
})

test('missing or invalid npm JS CLI fails with a clear setup error',()=>{
  for(const cli of [undefined,'npm.cmd','',42]){
    assert.throws(
      ()=>devServerInvocation({platform:'win32',nodePath:process.execPath,npmCli:cli}),
      /npm run test:dev/,
    )
  }
})

test('non-Windows launch retains the existing npm run dev behavior',()=>{
  const run=devServerInvocation({platform:'linux'})
  assert.equal(run.command,'npm')
  assert.deepEqual(run.args,['run','dev','--','--strictPort'])
})

test('smoke runner uses cross-platform invocation rather than direct Windows shim',()=>{
  const text=readFileSync(new URL('./dev-server-smoke.mjs',import.meta.url),'utf8')
  assert.match(text,/const dev=devServerInvocation\(\)/)
  assert.match(text,/spawnService\(dev\.command,dev\.args,web\)/)
  assert.doesNotMatch(text,/spawnService\([^\n]*['"]npm\.cmd['"]/)
  assert.match(text,/npm_execpath must point to an existing npm CLI/)
})
