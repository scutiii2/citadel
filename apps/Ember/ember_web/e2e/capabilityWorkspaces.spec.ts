import { expect, test, type Page, type TestInfo } from '@playwright/test'
import { installFakeApi, samplePdf } from './fakeApi.ts'
import { logIn } from './helpers.ts'

// The API is deliberately mocked; keep requests visible to Playwright routing.
test.use({ serviceWorkers: 'block' })

async function screenshots(page: Page, info: TestInfo, name: string): Promise<void> {
  for (const [theme, width] of [['light', 1280], ['dark', 1280], ['light', 768], ['dark', 375]] as const) {
    await page.setViewportSize({ width, height: 1200 })
    await page.evaluate(theme => { document.documentElement.style.colorScheme = theme; document.querySelector('.info-page')?.scrollTo(0, 0) }, theme)
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await expect.poll(() => page.locator('.info-page').evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true)
    await page.screenshot({ path: info.outputPath(`${name}-${theme}-${width}.png`), fullPage: true })
  }
}

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
  await page.goto('/capabilities/video_downloader')
  await page.getByRole('textbox', { name: 'Video link' }).fill('https://www.youtube.com/watch?v=public-example')
  await page.getByRole('button', { name: 'Check', exact: true }).click()
  await expect(page.getByText('Coastal walk at sunset')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Best quality', exact: true })).toBeDisabled()
  await expect(page.getByText('Preview unavailable')).toBeVisible()
  await screenshots(page, info, 'video-presets')
  await page.getByRole('button', { name: 'Download', exact: true }).click()
  await expect(page.getByRole('progressbar')).toBeVisible()
  await expect(page.getByRole('status').filter({ hasText: 'Done' })).toBeVisible()
  const links = page.getByRole('link', { name: /Download Coastal walk.mp4/ })
  await expect(links).toHaveCount(2)
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
