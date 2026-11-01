import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
const app = readFileSync(new URL('../src/App.tsx',import.meta.url),'utf8')
const api = readFileSync(new URL('../src/api.ts',import.meta.url),'utf8')
test('guests may search and preview pathways without login',()=>{assert.match(app,/\/v1\/courses/);assert.match(app,/\/v1\/pathways\/preview/);assert.match(app,/Account optional/)} )
test('private paths bind to bearer access tokens',()=>{assert.match(api,/headers\.Authorization='Bearer '/);assert.match(app,/\/v1\/me\/pathways/);assert.match(app,/\/v1\/me\/courses/)} )
test('synthetic examples cannot link to invented courses',()=>{assert.match(app,/illustrative-/);assert.match(app,/!c\.synthetic&&/);assert.match(app,/Illustrative examples only/)} )
test('session token is not persisted in web storage',()=>{assert.doesNotMatch(app,/localStorage|sessionStorage/);assert.doesNotMatch(api,/localStorage|sessionStorage/)} )
