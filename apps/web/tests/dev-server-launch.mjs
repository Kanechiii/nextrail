/** Resolve the real npm JS CLI instead of spawning Windows' npm.cmd shim.
 *
 * Node child_process.spawn() cannot directly execute .cmd/.bat files on
 * Windows; shell:true adds quoting/security concerns. npm run test:dev
 * exposes npm_execpath, so node.exe can execute npm's CLI as a normal JS file.
 */
export function devServerInvocation({
  platform=process.platform,
  nodePath=process.execPath,
  npmCli=process.env.npm_execpath,
}={}){
  if(platform==='win32'){
    if(typeof npmCli!=='string'||!/\.(?:c|m)?js$/i.test(npmCli)){
      throw new Error('Windows smoke test must run through npm run test:dev (npm_execpath unavailable).')
    }
    return {command:nodePath,args:[npmCli,'run','dev','--','--strictPort']}
  }
  return {command:'npm',args:['run','dev','--','--strictPort']}
}
