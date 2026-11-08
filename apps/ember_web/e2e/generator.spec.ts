import { expect, test, type Page } from '@playwright/test'
import { installFakeApi } from './fakeApi.ts'
import { logIn } from './helpers.ts'

test.use({ serviceWorkers: 'block' })

async function setup(page: Page) {
  const api = await installFakeApi(page, { media: true })
  const calls: { name: string; arguments: Record<string, any> }[] = []
  await page.route('**/api/mcp/server', async route => {
    if (route.request().method() !== 'POST') return route.fallback()
    const message = route.request().postDataJSON()
    if (message.method !== 'tools/call') return route.fallback()
    calls.push(message.params)
    const args = message.params.arguments
    const samples: Record<string, Record<string, unknown>> = {
      tool_gen_generatePassword: { password: 'Ab3!'.repeat(32).slice(0, args.length ?? 20), entropy_bits: 160 },
      tool_gen_generatePassphrase: { passphrase: 'maple-orbit-river-lantern-copper-meadow', entropy_bits: 78 },
      tool_gen_generatePin: { pin: '604281', entropy_bits: 20 },
      tool_gen_generateTotpSecret: { secret: 'JBSWY3DPEHPK3PXP' },
      tool_gen_getTotpCode: { code: '023714', seconds_remaining: 30 },
    }
    return route.fulfill({ contentType: 'application/json', json: { jsonrpc: '2.0', id: message.id,
      result: { content: [], structuredContent: samples[message.params.name], isError: false } } })
  })
  await logIn(page)
  await page.goto('/generator')
  return { api, calls }
}

test('generator preserves values and options across responsive layouts and cancelled type changes', async ({ page }, info) => {
  const { api, calls } = await setup(page)
  await page.setViewportSize({ width: 375, height: 812 })
  expect(calls).toEqual([])
  const options = page.getByRole('button', { name: /^Options/ })
  await options.click()
  await page.getByRole('slider').press('End')
  await options.click()
  await page.getByRole('button', { name: 'Generate password', exact: true }).click()
  const value = page.getByTestId('generated-value')
  await expect(value).toHaveText('•'.repeat(32))
  await page.getByRole('button', { name: 'Reveal', exact: true }).click()
  await expect(value).toHaveText('Ab3!'.repeat(32))
  await page.getByRole('combobox', { name: 'Generator type' }).selectOption('pin')
  const discard = page.getByRole('dialog', { name: 'Discard the generated value?' })
  await expect(discard).toBeVisible()
  await expect(page.getByRole('combobox', { name: 'Generator type' })).toHaveValue('password')
  await discard.getByRole('button', { name: 'Cancel', exact: true }).click()
  await expect(value).toHaveText('Ab3!'.repeat(32))
  for (const theme of ['light', 'dark'] as const) {
    await page.evaluate(theme => { document.documentElement.style.colorScheme = theme }, theme)
    for (const width of [1440, 768, 375]) {
      await page.setViewportSize({ width, height: 812 })
      const generate = page.getByRole('button', { name: 'Regenerate password', exact: true })
      await expect(generate).toBeInViewport()
      const bounds = await generate.boundingBox()
      expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(812 - (width < 768 ? 52 : 0))
      await expect(value).toHaveText('Ab3!'.repeat(32))
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
      expect(await page.locator('.generator').evaluate(e => e.scrollWidth <= e.clientWidth)).toBe(true)
      await page.screenshot({ path: info.outputPath(`generator-${theme}-${width}.png`) })
    }
  }
  await page.evaluate(() => {
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: async (text: string) => { (window as any).copiedGeneratorValue = text } } })
  })
  await page.getByRole('button', { name: 'Copy value' }).click()
  expect(await page.evaluate(() => (window as any).copiedGeneratorValue)).toBe('Ab3!'.repeat(32))
  await expect(page.getByRole('button', { name: 'Copy value' })).toHaveText('Copied')
  await options.click()
  await expect(page.getByRole('slider')).toHaveValue('128')
  expect(calls).toHaveLength(1)
  await options.click()
  await page.getByRole('button', { name: 'Regenerate password', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Reveal', exact: true })).toBeVisible()
  await expect(value).toHaveText('•'.repeat(32))
  expect(calls).toHaveLength(2)
  expect(api.unexpected).toEqual([])
})

test('all generator types retain their tool arguments, masking, and discard behavior', async ({ page }) => {
  const { api, calls } = await setup(page)
  for (const [label, tool] of [
    ['Passphrase', 'tool_gen_generatePassphrase'], ['PIN', 'tool_gen_generatePin'],
    ['TOTP secret', 'tool_gen_generateTotpSecret'], ['TOTP code', 'tool_gen_getTotpCode'],
  ] as const) {
    await page.locator('.desktop-types').getByRole('button', { name: label, exact: true }).click()
    if (await page.getByRole('dialog', { name: 'Discard the generated value?' }).isVisible()) {
      await page.getByRole('dialog').getByRole('button', { name: 'Discard and leave', exact: true }).click()
    }
    await expect(page.getByTestId('generated-value')).toHaveCount(0)
    if (label === 'TOTP code') await page.getByLabel('Secret', { exact: true }).fill('JBSWY3DPEHPK3PXP')
    await page.getByRole('button', { name: /^Generate / }).click()
    await expect(page.getByTestId('generated-value')).toHaveText(/^•+$/)
    expect(calls.at(-1)?.name).toBe(tool)
    await page.getByRole('button', { name: 'Reveal', exact: true }).click()
    if (label === 'TOTP code') {
      await expect(page.getByTestId('generated-value')).toHaveText('023 714')
      expect(calls.at(-1)?.arguments).toEqual({ secret: 'JBSWY3DPEHPK3PXP', digits: 6, period: 30 })
    }
  }
  expect(calls).toHaveLength(4)
  expect(api.unexpected).toEqual([])
})
