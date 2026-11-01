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
