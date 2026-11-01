import {test, expect, type Page, type TestInfo} from '@playwright/test'

// Keep screenshots as review evidence but never block the functional route workflow.
async function captureReviewScreenshot(page: Page, info: TestInfo, filename: string) {
  if (!process.env.CI && process.env.NEXTRAIL_E2E_SCREENSHOTS !== '1') return
  await page.screenshot({
    path: info.outputPath(filename),
    animations: 'disabled',
    fullPage: false,
    timeout: 15000,
  })
}

async function navigate(page:Page, name:string) {
  const menu=page.getByRole('button',{name:'Open navigation',exact:true})
  if(await menu.isVisible()) await menu.click()
  await page.getByRole('navigation',{name:'Primary'}).getByRole('button',{name,exact:true}).click()
}

test('guest route, account save and confirmed completion', async ({page}, info)=>{
  await page.goto('/')
  await page.getByRole('group',{name:'Skills to learn'}).getByRole('checkbox').first().check()
  const previewResponse = page.waitForResponse(response =>
    response.url().includes('/api/v1/pathways/preview') &&
    response.request().method() === 'POST'
  )
  await page.getByRole('button',{name:'Generate learning route',exact:true}).click()
  const result = await previewResponse
  expect(result.ok(), `Pathway preview failed with HTTP ${result.status()}: ${await result.text()}`).toBe(true)
  await expect(page.getByRole('heading',{name:'Your learning route',exact:true})).toBeVisible()
  await page.getByRole('button',{name:'Save route',exact:true}).click()
  const dialog=page.getByRole('dialog')
  await dialog.getByRole('button',{name:'Create account',exact:true}).click()
  await dialog.getByLabel('Email', {exact:true}).fill(`review-${info.project.name}-${Date.now()}@example.com`)
  await dialog.getByLabel(/^Password/).fill('NextrailReview!2026')
  await dialog.getByRole('button',{name:'Create account',exact:true}).click()
  await expect(dialog).not.toBeVisible()
  await expect(page.getByRole('heading',{name:'Your learning route',exact:true})).toBeVisible()
  await page.getByRole('button',{name:'Save route',exact:true}).click()
  await expect(page.getByRole('button',{name:'Complete milestone',exact:true})).toBeEnabled()
  await page.getByRole('button',{name:'Complete milestone',exact:true}).click()
  await expect(page.getByRole('button',{name:'Mark as not started',exact:true})).toBeVisible()
  await page.getByRole('button',{name:'Sign out',exact:true}).click()
  await expect(page.getByRole('button',{name:'Complete milestone',exact:true})).toHaveCount(0)
  expect(await page.evaluate(()=>Object.keys(localStorage))).not.toContain('token')
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy()
  await page.evaluate(()=>window.scrollTo(0,0))
  await captureReviewScreenshot(page, info, 'learning-route.png')
})

test('themes, comparison, details and URL filter history', async ({page}, info)=>{
  await page.route('**/api/v1/courses?**', route=>route.fulfill({json:{items:[
    {id:'test-html',title:'HTML test resource',provider_id:'fixture',provider_name:'Test fixture provider',skills:['html'],access_cost:'free',certificate_cost:'paid',evidence_status:'verified',synthetic:false},
    {id:'test-css',title:'CSS test resource',provider_id:'fixture',provider_name:'Test fixture provider',skills:['css'],access_cost:'unknown',certificate_cost:'unknown',evidence_status:'verified',synthetic:false},
  ]}}))
  await page.goto('/')
  const menu=page.getByRole('button',{name:'Open navigation',exact:true})
  if(await menu.isVisible()) await menu.click()
  await page.getByLabel('Color theme').selectOption('dark')
  await expect(page.locator('html')).toHaveAttribute('data-theme','dark')
  await page.getByLabel('Color theme').selectOption('light')
  await expect(page.locator('html')).toHaveAttribute('data-theme','light')
  await page.getByRole('navigation',{name:'Primary'}).getByRole('button',{name:'Discover courses',exact:true}).click()
  await expect(page.getByRole('heading',{name:'HTML test resource',exact:true})).toBeVisible()
  await page.getByRole('checkbox',{name:'Compare',exact:true}).first().check()
  await page.getByRole('checkbox',{name:'Compare',exact:true}).nth(1).check()
  await page.getByRole('button',{name:/Compare courses/}).click()
  await expect(page.getByRole('dialog').getByRole('cell',{name:'Paid',exact:true})).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await page.getByRole('button',{name:'View course',exact:true}).first().click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.getByRole('button',{name:'Close dialog',exact:true}).click()
  await expect(page.getByRole('button',{name:'View course',exact:true}).first()).toBeFocused()
  await page.getByLabel('Filter access cost').selectOption('free')
  await expect(page).toHaveURL(/cost=free/)
  await page.getByLabel('Filter access cost').selectOption('paid')
  await page.goBack()
  await expect(page.getByLabel('Filter access cost')).toHaveValue('free')
  await expect(page.getByRole('heading',{name:'HTML test resource',exact:true})).toBeVisible()
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy()
  await page.emulateMedia({reducedMotion:'reduce'})
  await page.evaluate(()=>window.scrollTo(0,0))
  await captureReviewScreenshot(page, info, 'dashboard-light.png')
  if(await menu.isVisible()) await menu.click()
  await page.getByLabel('Color theme').selectOption('dark')
  await page.getByRole('navigation',{name:'Primary'}).getByRole('button',{name:'Discover courses',exact:true}).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme','dark')
  await page.evaluate(()=>window.scrollTo(0,0))
  await captureReviewScreenshot(page, info, 'dashboard-dark.png')
})

test('invalid stored theme preference falls back to system and tracks OS theme', async ({page})=>{
  await page.addInitScript(()=>localStorage.setItem('nextrail-theme','unsupported-theme'))
  await page.emulateMedia({colorScheme:'dark'})
  await page.goto('/')
  await expect(page.getByLabel('Color theme')).toHaveValue('system')
  await expect(page.locator('html')).toHaveAttribute('data-theme','dark')
  await page.emulateMedia({colorScheme:'light'})
  await expect(page.locator('html')).toHaveAttribute('data-theme','light')
})
