import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
const app = readFileSync(new URL('../src/App.tsx',import.meta.url),'utf8')
const api = readFileSync(new URL('../src/api.ts',import.meta.url),'utf8')
test('guests may search and preview pathways without login',()=>{assert.match(app,/\/v1\/courses/);assert.match(app,/\/v1\/pathways\/preview/);assert.match(app,/Account optional/)} )
test('private paths bind to bearer access tokens',()=>{assert.match(api,/headers\.Authorization='Bearer '/);assert.match(app,/\/v1\/me\/pathways/);assert.match(app,/\/v1\/me\/courses/)} )
test('synthetic resources cannot link to invented courses',()=>{assert.match(app,/courseDetail\.url&&!courseDetail\.synthetic/);assert.match(app,/Synthetic example/)} )
test('web storage persists only theme preference, never session tokens',()=>{const storageCalls=app.match(/(?:localStorage|sessionStorage)\.[a-zA-Z]+\([^)]*\)/g)||[];assert.equal(storageCalls.length,2);storageCalls.forEach(call=>assert.match(call,/'nextrail-theme'/));assert.doesNotMatch(api,/localStorage|sessionStorage/)} )

