import { expect, test, type Page, type TestInfo } from '@playwright/test'
import { installFakeApi, samplePdf } from './fakeApi.ts'
import { logIn } from './helpers.ts'

// The API is deliberately mocked; keep requests visible to Playwright routing.
test.use({ serviceWorkers: 'block' })

test('media groups accept multiple links and lock membership after starting a package (mock API)', async ({ page }, info) => {
  const api = await installFakeApi(page, { media: true })
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  let group: Record<string, any> | null = null
  let running = false
  let finished = false
  await page.route('**/api/video-downloader/packages**', async route => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (request.method() === 'DELETE' && path.endsWith('/p_group')) {
      if (running && !finished) return route.fulfill({ status: 409, json: { detail: 'Still downloading' } })
      group = null
      running = false
      return route.fulfill({ status: 204 })
    }
    if (path.endsWith('/packages') && request.method() === 'POST') {
      group = { package_id: 'p_group', name: request.postDataJSON().name, state: 'draft', items: [], job_id: null, status: null }
      return route.fulfill({ json: group })
    }
    if (path.endsWith('/items') && request.method() === 'POST') {
      if (running) return route.fulfill({ status: 409, json: { error: { code: 'package_locked', message: 'Locked' } } })
      group!.items.push({ item_id: `i_${group!.items.length}`, ...request.postDataJSON(), title: null, state: 'pending', error: null })
      return route.fulfill({ json: group })
    }
    if (path.endsWith('/start')) {
      running = true
      group!.job_id = 'j_group'
      group!.state = 'downloading'
      return route.fulfill({ json: { job_id: 'j_group' } })
    }
    if (running) group!.status = { job_id: 'j_group', state: finished ? 'done' : 'downloading', percent: finished ? 100 : 40, speed: null, eta: null, file: null, error: null }
    return route.fulfill({ json: group ? [group] : [] })
  })
  await logIn(page)
  await page.goto('/capabilities/video_downloader')
  await expect(page).toHaveURL(/\/capabilities\/media_downloader$/)
  await page.getByRole('button', { name: 'Download groups', exact: true }).click()
  await page.getByRole('textbox', { name: 'Group name' }).fill('My collection')
  await page.getByRole('button', { name: 'Create group', exact: true }).click()
  const panel = page.getByRole('article', { name: 'My collection' })
  await panel.getByRole('textbox', { name: 'Media links, one per line' }).fill('https://example.com/one\nhttps://example.com/two')
  await panel.getByRole('button', { name: 'Add links', exact: true }).click()
  await expect(panel.locator('.items li')).toHaveCount(2)
  await screenshots(page, info, 'package-draft')
  await panel.getByRole('button', { name: 'Download package', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Start package download?' })
  await expect(dialog).toContainText('permanently locked')
  await dialog.getByRole('button', { name: 'Start download', exact: true }).click()
  await expect(panel).toContainText('Locked')
  await expect(panel.getByRole('textbox')).toHaveCount(0)
  await expect(panel.getByRole('button', { name: 'Remove', exact: true })).toHaveCount(0)
  await expect(panel.getByRole('progressbar')).toBeVisible()
  await expect(panel.getByRole('button', { name: 'Remove package', exact: true })).toBeDisabled()
  await screenshots(page, info, 'package-locked')
  finished = true
  group!.state = 'done'
  await page.getByRole('button', { name: 'Refresh groups', exact: true }).click()
  await expect(panel.getByRole('button', { name: 'Remove package', exact: true })).toBeEnabled()
  await panel.getByRole('button', { name: 'Remove package', exact: true }).click()
  const remove = page.getByRole('dialog', { name: 'Remove this package?' })
  await expect(remove).toContainText('Downloaded files will remain')
  await remove.getByRole('button', { name: 'Cancel', exact: true }).click()
  await expect(panel).toBeVisible()
  await panel.getByRole('button', { name: 'Remove package', exact: true }).click()
  await remove.getByRole('button', { name: 'Remove package', exact: true }).click()
  await expect(panel).toHaveCount(0)
  expect(errors).toEqual([])
  expect(api.unexpected).toEqual([])
})

async function screenshots(page: Page, info: TestInfo, name: string): Promise<void> {
  for (const [theme, width] of [['light', 1280], ['dark', 1280], ['light', 768], ['dark', 375]] as const) {
    await page.setViewportSize({ width, height: 1200 })
    await page.evaluate(theme => { document.documentElement.style.colorScheme = theme; document.querySelector('.info-page')?.scrollTo(0, 0) }, theme)
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await expect.poll(() => page.locator('.info-page').evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true)
    await page.screenshot({ path: info.outputPath(`${name}-${theme}-${width}.png`), fullPage: true })
  }
}

test('media modes preserve drafts, checked formats, and file details across mobile and desktop', async ({ page }) => {
  const api = await installFakeApi(page, { media: true })
  const expiry = Date.now() / 1000 + 3600
  let deleted = false
  await page.route('**/api/video-downloader/files**', route => {
    if (route.request().method() === 'DELETE') { deleted = true; return route.fulfill({ status: 204 }) }
    return route.fulfill({ json: deleted ? [] : [{ file_id: 'saved', name: 'A saved video.mp4', kind: 'video', mime: 'video/mp4', size: 1024, duration: 60, expires_at: expiry, download_url: '/api/video-downloader/files/saved/download' }] })
  })
  await logIn(page)
  await page.setViewportSize({ width: 375, height: 812 })
  await page.goto('/capabilities/media_downloader')
  const tabs = page.locator('.mobile-tabs')
  await tabs.getByRole('button', { name: 'Groups', exact: true }).click()
  await page.getByRole('textbox', { name: 'Group name' }).fill('Weekend draft')
  await tabs.getByRole('button', { name: 'Download', exact: true }).click()
  await page.getByRole('textbox', { name: 'Media link' }).fill('https://example.com/media')
  await page.getByRole('button', { name: 'Check', exact: true }).click()
  await expect(page.getByRole('region', { name: 'Checked media' })).toBeVisible()
  await tabs.getByRole('button', { name: 'Groups', exact: true }).click()
  await expect(page.getByRole('textbox', { name: 'Group name' })).toHaveValue('Weekend draft')
  await tabs.getByRole('button', { name: /^My files/ }).click()
  await expect(page.getByRole('link', { name: 'Download A saved video.mp4', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'File options for A saved video.mp4' }).click()
  const details = page.getByRole('dialog', { name: 'File details' })
  for (const colorScheme of ['light', 'dark'] as const) {
    await page.emulateMedia({ colorScheme })
    for (const width of [1440, 768, 375]) {
      await page.setViewportSize({ width, height: 812 })
      await expect(details).toBeVisible()
      expect(await details.evaluate(e => e.scrollWidth <= e.clientWidth)).toBe(true)
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    }
  }
  await details.getByRole('button', { name: 'Delete file', exact: true }).click()
  const confirm = page.getByRole('dialog', { name: 'Delete file?', exact: true })
  await confirm.getByRole('button', { name: 'Cancel', exact: true }).click()
  await expect(details).toBeVisible()
  expect(deleted).toBe(false)
  await details.getByRole('button', { name: 'Delete file', exact: true }).click()
  await confirm.getByRole('button', { name: 'Delete file', exact: true }).click()
  await expect(details).toBeHidden()
  await expect(page.getByRole('link', { name: 'Download A saved video.mp4', exact: true })).toHaveCount(0)
  expect(deleted).toBe(true)
  expect(api.unexpected).toEqual([])
})

test('native PDF workspace uploads JSON, renders worker previews, reorders pages and downloads a merge (mock API)', async ({ page }, info) => {
  const api = await installFakeApi(page, { media: true })
  const errors: string[] = []
  const workers: string[] = []
  page.on('worker', worker => workers.push(worker.url()))
  page.on('pageerror', error => errors.push(error.message))
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()) })
  await logIn(page)
  errors.length = 0 // The login probe intentionally receives 401 before sign-in.
  await page.goto('/capabilities/pdf_merger')
  await expect(page.getByRole('heading', { name: 'PDF merger', exact: true })).toBeVisible()
  await page.locator('input[type=file]').setInputFiles([
    { name: 'Coast.pdf', mimeType: 'application/pdf', buffer: samplePdf('Coastal field notes') },
    { name: 'Woods.pdf', mimeType: 'application/pdf', buffer: samplePdf('Woodland field notes') },
  ])
  const pages = page.locator('ol.strip > li')
  await expect(pages).toHaveCount(2)
  // PDF.js must paint nonempty canvases using the built module worker under production CSP.
  await expect.poll(() => page.locator('ol.strip canvas').evaluateAll(canvases => canvases.filter(element => {
    const canvas = element as HTMLCanvasElement
    if (canvas.width !== 96 || canvas.height <= 0) return false
    const pixels = canvas.getContext('2d')!.getImageData(0, 0, canvas.width, canvas.height).data
    return pixels.some((value, index) => index % 4 === 0 && value < 180 && pixels[index + 3]! > 0)
  }).length)).toBe(2)
  expect(workers.some(url => url.includes('pdf.worker'))).toBe(true)
  expect(api.media.uploads.map(upload => upload.filename)).toEqual(['Coast.pdf', 'Woods.pdf'])
  expect(Buffer.from(api.media.uploads[0]!.data, 'base64').toString('ascii', 0, 5)).toBe('%PDF-')
  await pages.first().focus()
  await pages.first().press('Alt+ArrowRight')
  await expect(pages.first()).toContainText('Woods p1')
  await page.getByRole('button', { name: 'Merge', exact: true }).click()
  const downloadLink = page.getByRole('link', { name: /Download merged.pdf/ })
  await expect(downloadLink).toBeVisible()
  expect(api.media.merges[0]).toMatchObject({ segments: [{ file_id: 'pdf-2', pages: '1' }, { file_id: 'pdf-1', pages: '1' }] })
  const downloaded = page.waitForEvent('download')
  // Chrome's download-attribute requests bypass Playwright interception. The
  // same href is tested as a normal navigation; the fake attachment header
  // triggers the download, as the real gateway's Content-Disposition does.
  await expect(downloadLink).toHaveAttribute('download', '')
  await downloadLink.evaluate(element => element.removeAttribute('download'))
  await downloadLink.click()
  expect((await downloaded).suggestedFilename()).toBe('merged.pdf')
  await screenshots(page, info, 'pdf-workspace')
  expect(errors).toEqual([])
  expect(api.unexpected).toEqual([])
})

test('native video workspace probes presets, follows a job and downloads its file (mock API)', async ({ page }, info) => {
  const api = await installFakeApi(page, { media: true })
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()) })
  await logIn(page)
  errors.length = 0
  await page.goto('/capabilities/media_downloader')
  await page.getByRole('textbox', { name: 'Media link' }).fill('https://www.youtube.com/watch?v=public-example')
  await page.getByRole('button', { name: 'Check', exact: true }).click()
  await expect(page.getByText('Coastal walk at sunset')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Best quality', exact: true })).toBeDisabled()
  await expect(page.getByText('Preview unavailable')).toBeVisible()
  await screenshots(page, info, 'video-presets')
  await page.getByRole('region', { name: 'Checked media' }).getByRole('button', { name: 'Download', exact: true }).click()
  await expect(page.getByRole('progressbar')).toBeVisible()
  await expect(page.getByRole('status').filter({ hasText: 'Done' })).toBeVisible()
  const links = page.getByRole('link', { name: /Download Coastal walk.mp4/ })
  await expect(links).toHaveCount(1)
  await page.locator('.mobile-tabs').getByRole('button', { name: /^My files/ }).click()
  await expect(links).toHaveCount(1)
  expect(api.media.downloads).toEqual([{ url: 'https://www.youtube.com/watch?v=public-example', preset: '720p' }])
  const downloaded = page.waitForEvent('download')
  await expect(links.last()).toHaveAttribute('download', '')
  await links.last().evaluate(element => element.removeAttribute('download'))
  await links.last().click()
  expect((await downloaded).suggestedFilename()).toBe('Coastal walk.mp4')
  await screenshots(page, info, 'video-complete')
  expect(errors).toEqual([])
  expect(api.unexpected).toEqual([])
})

test('media workspace downloads a TikTok photo carousel as a ZIP (mock API)', async ({ page }, info) => {
  const api = await installFakeApi(page, { media: true })
  const url = 'https://www.tiktok.com/@alice/photo/1234567890'
  const file = { file_id: 'photos', name: 'Holiday.zip', kind: 'photo', mime: 'application/zip', size: 1024, duration: null,
    expires_at: Date.now() / 1000 + 21600, download_url: '/api/video-downloader/files/photos/download' }
  let done = false
  const downloads: unknown[] = []
  await page.route('**/api/video-downloader/**', async route => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path.endsWith('/probe')) return route.fulfill({ json: { url, title: 'Holiday', duration: null, uploader: 'alice', thumbnail: null, photo_count: 3,
      options: [{ id: 'photos', label: 'Original photos', kind: 'photo', blocked: false, estimated_bytes: null, code: null, reason: null }] } })
    if (path.endsWith('/downloads')) {
      downloads.push(request.postDataJSON())
      return route.fulfill({ status: 202, json: { job_id: 'photos-job' } })
    }
    if (path.endsWith('/jobs/photos-job')) {
      done = true
      return route.fulfill({ json: { job_id: 'photos-job', state: 'done', percent: 100, speed: null, eta: null, file, error: null } })
    }
    if (path.endsWith('/files')) return route.fulfill({ json: done ? [file] : [] })
    if (path.endsWith('/files/photos/download')) return route.fulfill({ contentType: 'application/zip',
      headers: { 'Content-Disposition': 'attachment; filename="Holiday.zip"' }, body: Buffer.from('UEsFBgAAAAAAAAAAAAAAAAAAAAAAAA==', 'base64') })
    return route.fallback()
  })
  await logIn(page)
  await page.goto('/capabilities/media_downloader')
  await expect(page.getByRole('heading', { name: 'Media downloader', exact: true })).toBeVisible()
  await page.getByRole('textbox', { name: 'Media link' }).fill(url)
  await page.getByRole('button', { name: 'Check', exact: true }).click()
  await expect(page.getByText('3 photos · Downloaded together as a ZIP')).toBeVisible()
  await page.getByRole('region', { name: 'Checked media' }).getByRole('button', { name: 'Download', exact: true }).click()
  await expect(page.getByRole('link', { name: /Download Holiday.zip/ })).toHaveCount(2)
  expect(downloads).toEqual([{ url, preset: 'photos' }])
  await screenshots(page, info, 'media-photos')
  expect(api.unexpected).toEqual([])
})
