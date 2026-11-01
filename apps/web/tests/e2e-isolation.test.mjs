import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const playwright = readFileSync(new URL('../playwright.config.ts', import.meta.url), 'utf8')
const vite = readFileSync(new URL('../vite.config.ts', import.meta.url), 'utf8')

test('browser tests use dedicated ports instead of the running development servers', () => {
  assert.match(playwright, /const apiPort = 18000/)
  assert.match(playwright, /const webPort = 15173/)
  assert.equal((playwright.match(/reuseExistingServer: false/g) || []).length, 2)
})

test('test API never reads the developer persistent database path', () => {
  assert.match(playwright, /NEXTRAIL_DB_PATH: ':memory:'/)
  assert.match(playwright, /VITE_API_BASE_URL: '\/api'/)
})

test('Vite proxy accepts a test-only backend target without affecting normal local usage', () => {
  assert.match(vite, /NEXTRAIL_DEV_API_TARGET/)
  assert.match(vite, /http:\/\/127\.0\.0\.1:8000/)
})

test('local browser tests allow slower Windows operation without relaxing CI checks', () => {
  assert.match(playwright, /timeout: process\.env\.CI \? 45000 : 90000/)
  assert.match(playwright, /workers: process\.env\.CI \? 2 : 1/)
})

test('functional assertions precede screenshots and local screenshot capture is opt-in', () => {
  const scenarios = readFileSync(new URL('../e2e/dashboard.spec.ts', import.meta.url), 'utf8')
  assert.match(scenarios, /NEXTRAIL_E2E_SCREENSHOTS !== '1'/)
  assert.match(scenarios, /animations: 'disabled'/)
  assert.match(scenarios, /previewResponse = page\.waitForResponse/)
  const firstScreenshot = scenarios.indexOf("captureReviewScreenshot(page, info, 'learning-route.png')")
  const completion = scenarios.indexOf("name:'Mark as not started'")
  assert.ok(firstScreenshot > completion && completion >= 0)
})
