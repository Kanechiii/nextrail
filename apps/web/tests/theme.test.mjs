import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
const theme=readFileSync(new URL('../src/ui/theme.ts',import.meta.url),'utf8')
const css=readFileSync(new URL('../src/ui/theme.css',import.meta.url),'utf8')
const switcher=readFileSync(new URL('../src/ui/ThemeSwitch.tsx',import.meta.url),'utf8')
test('theme choices include system, light and dark',()=>{for(const name of ['system','light','dark'])assert.ok(theme.includes("'"+name+"'"))})
test('design tokens support light and dark',()=>{assert.match(css,/--nx-page:/);assert.match(css,/\[data-theme="light"\]/)})
test('theme controls are keyboard accessible native buttons',()=>assert.match(switcher,/<button type="button"/))
test('reduced motion is supported',()=>assert.match(css,/prefers-reduced-motion: reduce/))
test('preferences are optional and do not contain bearer credentials',()=>{assert.doesNotMatch(theme,/Authorization|access_token|Bearer /)})
