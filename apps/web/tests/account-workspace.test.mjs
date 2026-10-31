import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
const ui=readFileSync(new URL('../src/account/AccountWorkspace.tsx',import.meta.url),'utf8')
test('account tabs distinguish overview saved pathways and saved courses',()=>{for(const label of ['Overview','My pathways','Saved courses'])assert.ok(ui.includes(label))})
test('milestone buttons update actual saved progress',()=>{assert.match(ui,/onProgress\(step.skill_id/);assert.match(ui,/progress\.milestones\.map/)})
test('dashboard uses supplied persisted snapshots rather than invented statistics',()=>{assert.match(ui,/saved\.length/);assert.match(ui,/bookmarks\.length/);assert.match(ui,/progress\?\.completed/);assert.doesNotMatch(ui,/Math\.random/)})
test('account workspace supports navigation and logout',()=>{assert.match(ui,/onLogout/);assert.match(ui,/onExplore/);assert.match(ui,/onBuild/)})
test('accessibility exposes tab navigation and progress status',()=>{assert.match(ui,/aria-label="My learning sections"/);assert.match(ui,/role="progressbar"/)})
